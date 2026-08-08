from __future__ import annotations

import argparse
import bz2
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import mwparserfromhell
import mwxml

from wiki_common.config import Settings
from wiki_common.gateway import embedding_schema

DEFAULT_DUMP = "https://dumps.wikimedia.org/simplewiki/latest/simplewiki-latest-pages-articles.xml.bz2"
DEFAULT_CACHE = Path(".cache/simplewiki-latest-pages-articles.xml.bz2")
DEFAULT_STATE = Path(".state/indexer.json")
PARAGRAPH_BREAK = re.compile(r"\n\s*\n+")
SPACE = re.compile(r"[ \t\r\f\v]+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream a Wikimedia pages-articles dump and let Layer embed every chunk with Lattice."
    )
    parser.add_argument("--dump", default=DEFAULT_DUMP, help="local .xml/.bz2 path or Wikimedia dump URL")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--namespace", default=None)
    parser.add_argument("--limit-articles", type=int, default=2_000, help="0 means no limit")
    parser.add_argument("--start-article", type=int, default=None, help="override saved resume cursor")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-chars", type=int, default=1_800)
    parser.add_argument("--reset-state", action="store_true")
    return parser.parse_args()


def download_dump(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {
        "User-Agent": "hev-wiki-demo/0.1 (+https://github.com/hev/wiki; contact: hello@hevmind.com)",
        **({"Range": f"bytes={offset}-"} if offset else {}),
    }
    mode = "ab" if offset else "wb"
    print(f"Downloading {url} -> {target} (resume at {offset:,} bytes)", file=sys.stderr)
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=None) as response:
        response.raise_for_status()
        if offset and response.status_code != 206:
            offset, mode = 0, "wb"
        total = offset
        with partial.open(mode) as output:
            for block in response.iter_bytes(1024 * 1024):
                output.write(block)
                total += len(block)
                if total // (50 * 1024 * 1024) != (total - len(block)) // (50 * 1024 * 1024):
                    print(f"  {total / 1024 / 1024:.0f} MiB", file=sys.stderr)
    partial.replace(target)
    return target


def resolve_dump(source: str, cache: Path) -> Path:
    if urllib.parse.urlparse(source).scheme in {"http", "https"}:
        return cache if cache.exists() else download_dump(source, cache)
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def clean_wikitext(raw: str) -> str:
    # Parsing wiki markup is source extraction, not retrieval tokenization.
    text = mwparserfromhell.parse(raw).strip_code(normalize=True, collapse=True)
    text = html.unescape(text).replace("\u00a0", " ")
    return "\n\n".join(
        SPACE.sub(" ", part.replace("\n", " ")).strip()
        for part in PARAGRAPH_BREAK.split(text)
        if SPACE.sub(" ", part.replace("\n", " ")).strip()
    )


def split_long_paragraph(paragraph: str, max_chars: int) -> Iterator[str]:
    remaining = paragraph
    while len(remaining) > max_chars:
        boundary = remaining.rfind(". ", 0, max_chars)
        if boundary < max_chars // 2:
            boundary = remaining.rfind(" ", 0, max_chars)
        if boundary <= 0:
            boundary = max_chars
        else:
            boundary += 1
        yield remaining[:boundary].strip()
        remaining = remaining[boundary:].strip()
    if remaining:
        yield remaining


def article_chunks(article_id: str, title: str, raw: str, max_chars: int) -> Iterator[dict[str, Any]]:
    clean = clean_wikitext(raw)
    if not clean:
        return
    url = "https://simple.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="()_/-")
    paragraph_index = 0
    for paragraph in PARAGRAPH_BREAK.split(clean):
        for piece in split_long_paragraph(paragraph, max_chars - len(title) - 2):
            text = f"{title}\n\n{piece}"
            digest = hashlib.sha1(f"{article_id}:{paragraph_index}:{text}".encode()).hexdigest()[:16]
            yield {
                "id": f"{article_id}-{paragraph_index}-{digest}",
                "article_id": str(article_id),
                "title": title,
                "text": text,
                "url": url,
                "paragraph": paragraph_index,
                "is_lead": paragraph_index == 0,
            }
            paragraph_index += 1


def iter_articles(path: Path) -> Iterator[tuple[str, str, str]]:
    opener = bz2.open if path.suffix == ".bz2" else open
    with opener(path, "rb") as stream:
        dump = mwxml.Dump.from_file(stream)
        for page in dump:
            if page.namespace != 0 or page.redirect is not None:
                continue
            revision = None
            for revision in page:
                pass
            text = revision.text if revision and revision.text else ""
            if text:
                yield str(page.id), page.title, text


def load_cursor(path: Path, *, dump: str) -> int:
    if not path.exists():
        return 0
    saved = json.loads(path.read_text())
    if saved.get("dump") != dump:
        raise RuntimeError(f"resume state belongs to another dump: {saved.get('dump')}")
    return int(saved.get("next_article", 0))


def save_cursor(path: Path, *, dump: str, next_article: int, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"dump": dump, "next_article": next_article, "rows": rows}, indent=2) + "\n")


def write_batch(client: httpx.Client, settings: Settings, namespace: str, rows: list[dict]) -> dict:
    response = client.post(
        f"{settings.gateway_url.rstrip('/')}/v2/namespaces/{namespace}",
        headers={"Authorization": f"Bearer {settings.gateway_api_key}"},
        json={
            "distance_metric": "cosine_distance",
            "schema": embedding_schema(),
            "upsert_rows": rows,
        },
    )
    if response.is_error:
        raise RuntimeError(f"gateway write failed ({response.status_code}): {response.text[:1000]}")
    return response.json()


def main() -> None:
    args = parse_args()
    settings = Settings()
    if not settings.gateway_api_key:
        raise SystemExit("LAYER_GATEWAY_API_KEY is required")
    namespace = args.namespace or settings.namespace
    dump_path = resolve_dump(args.dump, args.cache)
    dump_identity = str(dump_path.resolve())
    if args.reset_state and args.state.exists():
        args.state.unlink()
    start = args.start_article if args.start_article is not None else load_cursor(args.state, dump=dump_identity)
    articles_done = start
    rows_done = 0
    batch: list[dict] = []
    batch_last_article = start
    started = time.perf_counter()

    with httpx.Client(timeout=settings.timeout_seconds) as client:
        for article_index, (article_id, title, raw) in enumerate(iter_articles(dump_path)):
            if article_index < start:
                continue
            if args.limit_articles and article_index >= start + args.limit_articles:
                break
            chunks = list(article_chunks(article_id, title, raw, args.max_chars))
            articles_done = article_index + 1
            batch_last_article = articles_done
            batch.extend(chunks)
            # Flush only at article boundaries. A saved cursor can therefore
            # never skip the tail of a many-paragraph article after a crash.
            if len(batch) >= args.batch_size:
                result = write_batch(client, settings, namespace, batch)
                rows_done += len(batch)
                embed_ms = (result.get("performance") or {}).get("embedding_ms")
                save_cursor(args.state, dump=dump_identity, next_article=batch_last_article, rows=rows_done)
                print(f"articles={articles_done:,} rows={rows_done:,} batch_embed_ms={embed_ms}", file=sys.stderr)
                batch.clear()
        if batch:
            result = write_batch(client, settings, namespace, batch)
            rows_done += len(batch)
            embed_ms = (result.get("performance") or {}).get("embedding_ms")
            save_cursor(args.state, dump=dump_identity, next_article=batch_last_article, rows=rows_done)
            print(f"articles={articles_done:,} rows={rows_done:,} batch_embed_ms={embed_ms}", file=sys.stderr)

    elapsed = time.perf_counter() - started
    print(json.dumps({
        "namespace": namespace,
        "articles_processed": articles_done - start,
        "rows_written": rows_done,
        "next_article": articles_done,
        "elapsed_seconds": round(elapsed, 1),
        "articles_per_second": round((articles_done - start) / elapsed, 2) if elapsed else None,
    }, indent=2))


if __name__ == "__main__":
    main()
