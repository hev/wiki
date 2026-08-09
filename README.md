# Wikipedia × Layer auto-routing

A public hybrid-search demo over Simple English Wikipedia. One Layer `Auto` query routes each search to full-text, semantic retrieval with Erik Kaum's compact CPU-only Lattice model, or RRF fusion of both. The gateway owns routing, embedding, tokenization, and fusion.

Live: **https://wiki.hevlayer.com**

## What is visible

Every search response includes the gateway's `routing` echo, including the selected route and whether it executed. The UI translates only those documented route values into `full-text`, `semantic`, or `fused (RRF)` and places the result beside the fixed serving contract. When the chosen route uses Lattice, the same response includes `performance.embedding_ms` and `performance.embedding_tokens`.

```json
{
  "model": "erikkaum/lattice-retrieval",
  "dims": 512,
  "serving": { "prefer": "lattice" }
}
```

Lattice's int4-per-row quantization applies to its approximately 8 MB lookup-table artifact. Layer emits normalized vectors and this demo stores them as `f32[512]`; Turbopuffer's int8 vector storage is a separate option and is not used here. See the Layer 0.5 docs for [query routing](https://v0.5.x.hevlayer.com/docs/api/query#query-routing), [hybrid text fusion](https://v0.5.x.hevlayer.com/docs/api/query#hybrid-text-fusion), and the [Embed API](https://v0.5.x.hevlayer.com/docs/api/embed).

## Corpus and chunking

The live corpus is the complete Simple English Wikipedia `pages-articles` XML dump. Redirects and non-article namespaces are skipped. Wiki markup is stripped, then each article becomes stable chunks containing `title + paragraph`; paragraphs over 1,800 characters split at a sentence or word boundary. The lead is marked separately. Both `title` and `text` are full-text and fuzzy indexed; `text` also carries the Lattice embedding profile.

As verified by a clean full-corpus rewrite on 2026-08-08, `wiki-simple` contains **283,997 articles / 1,737,141 paragraph rows** from `simplewiki-latest-pages-articles.xml.bz2`, stored in aws-us-east-1 turbopuffer. The schema rewrite completed in about 20 minutes at 237 articles/sec with `--batch-size 10000`. “George H. W. Bush” exercises the full-text route, “Super Mario Bros. 3” exercises fused retrieval, and “why do plants turn sunlight into useful chemical energy” exercises the semantic route.

The loader checkpoints an article cursor under `.state/` and uses stable content-derived row ids. Re-running is idempotent; rerun the same command to resume, increase `--limit-articles`, or point `--dump` at another Wikimedia pages-articles dump to expand the corpus.

## Run

```sh
cp .env.example .env
# Fill LAYER_GATEWAY_API_KEY from 1Password; never commit it.
uv sync

# Write the full corpus, including the full-text indexes, into wiki-simple.
# Stable content-derived row ids make this an idempotent rewrite.
uv run python -m indexer --limit-articles 0 --start-article 0 --batch-size 10000

# Reference backend + the same UI production serves.
uv run uvicorn search.app:app --host 127.0.0.1 --port 8000
```

The indexer accepts a local `.xml`/`.xml.bz2` file or a dump URL. `--limit-articles 0` continues to the end of the dump. Use `--start-article N` to override the checkpoint explicitly. Disposable live checks must use a `wiki-scratch-*` namespace and delete it afterward.

## Production

`src/worker.js` is the production backend. It injects `LAYER_API_KEY` server-side and serves `web/static/` through Cloudflare assets.

```sh
cp .dev.vars.example .dev.vars
npm install
npx wrangler dev
npx wrangler secret put LAYER_API_KEY
npx wrangler deploy
```

Both backends send the same single query directly to Layer:

```json
{
  "rank_by": ["title", "Auto", "George H. W. Bush", {
    "vector": ["Embed", "George H. W. Bush", {"field": "text"}]
  }],
  "top_k": 12
}
```

There is no mode toggle and no client-side embedding, fusion, tokenizer, routing heuristic, or reranker. The route tile is rendered from the gateway's `routing` echo rather than inferred from query text or result scores.
