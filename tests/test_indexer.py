from __future__ import annotations

import json
from argparse import Namespace
from types import SimpleNamespace

import indexer.__main__ as indexer


def test_resume_keeps_cumulative_checkpoint_rows(monkeypatch, tmp_path, capsys) -> None:
    dump = tmp_path / "wiki.xml"
    dump.write_text("unused")
    state = tmp_path / "indexer.json"
    state.write_text(
        json.dumps({"dump": str(dump.resolve()), "next_article": 1, "rows": 2})
    )
    args = Namespace(
        dump=str(dump),
        cache=tmp_path / "cache",
        state=state,
        namespace="wiki-scratch-resume",
        limit_articles=0,
        start_article=None,
        batch_size=2,
        max_chars=1_800,
        reset_state=False,
    )
    articles = [
        ("1", "Skipped", "old"),
        ("2", "Second", "two chunks"),
        ("3", "Third", "one chunk"),
    ]

    monkeypatch.setattr(indexer, "parse_args", lambda: args)
    monkeypatch.setattr(
        indexer,
        "Settings",
        lambda: SimpleNamespace(
            gateway_api_key="test-key",
            namespace="unused",
            gateway_url="https://gateway.test",
            timeout_seconds=1,
        ),
    )
    monkeypatch.setattr(indexer, "iter_articles", lambda _path: iter(articles))
    monkeypatch.setattr(
        indexer,
        "article_chunks",
        lambda article_id, _title, _raw, _max_chars: iter(
            {"id": f"{article_id}-{offset}"}
            for offset in range(2 if article_id == "2" else 1)
        ),
    )
    monkeypatch.setattr(indexer, "write_batch", lambda *_args: {"performance": {"embedding_ms": 1}})

    indexer.main()

    saved = json.loads(state.read_text())
    summary = json.loads(capsys.readouterr().out)
    assert saved == {"dump": str(dump.resolve()), "next_article": 3, "rows": 5}
    assert summary["articles_processed"] == 2
    assert summary["rows_written"] == 3
    assert summary["checkpoint_rows"] == 5
