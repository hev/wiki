# Wikipedia × Lattice

A public semantic-search demo over Simple English Wikipedia. Layer embeds every document and query inside the gateway with Erik Kaum's compact CPU-only Lattice model, then stores and searches the resulting vectors on Turbopuffer.

Live: **https://wiki.hevlayer.com**

## What is visible

Every search response includes the gateway's `performance.embedding_ms` and `performance.embedding_tokens` echo. The UI places that evidence beside the fixed serving contract:

```json
{
  "model": "erikkaum/lattice-retrieval",
  "dims": 512,
  "serving": { "prefer": "lattice" }
}
```

Lattice's int4-per-row quantization applies to its approximately 8 MB lookup-table artifact. Layer emits normalized vectors and this demo stores them as `f32[512]`; Turbopuffer's int8 vector storage is a separate option and is not used here.

## Corpus and chunking

The initial live corpus is a bounded slice of Simple English Wikipedia from Wikimedia's `pages-articles` XML dump. Redirects and non-article namespaces are skipped. Wiki markup is stripped, then each article becomes stable chunks containing `title + paragraph`; paragraphs over 1,800 characters split at a sentence or word boundary. The lead is marked separately.

As deployed on 2026-08-08, `wiki-simple` contains the first **2,000 articles / 30,268 paragraph chunks** from `simplewiki-latest-pages-articles.xml.bz2`. The bounded ingest took 396 seconds. Example live queries include “largest planet in the solar system,” “how plants turn sunlight into energy,” and “computer operating system created by Microsoft.”

The loader checkpoints an article cursor under `.state/` and uses stable content-derived row ids. Re-running is idempotent; rerun the same command to resume, increase `--limit-articles`, or point `--dump` at another Wikimedia pages-articles dump to expand the corpus.

## Run

```sh
cp .env.example .env
# Fill LAYER_GATEWAY_API_KEY from 1Password; never commit it.
uv sync

# Load/resume a 2,000-article bounded slice into wiki-simple.
uv run python -m indexer --limit-articles 2000

# Reference backend + the same UI production serves.
uv run uvicorn search.app:app --host 127.0.0.1 --port 8000
```

The indexer accepts a local `.xml`/`.xml.bz2` file or a dump URL. `--limit-articles 0` continues to the end of the dump. Use `--start-article N` to override the checkpoint explicitly.

## Production

`src/worker.js` is the production backend. It injects `LAYER_API_KEY` server-side and serves `web/static/` through Cloudflare assets.

```sh
cp .dev.vars.example .dev.vars
npm install
npx wrangler dev
npx wrangler secret put LAYER_API_KEY
npx wrangler deploy
```

Both backends send the same query directly to Layer:

```json
{
  "rank_by": ["text", "ANN", ["Embed", "largest planet in the solar system"]],
  "top_k": 12
}
```

There is no client-side embedding, fusion, tokenizer, or reranker.
