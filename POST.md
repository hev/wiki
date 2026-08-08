# An 8 MB Model Is Searching Wikipedia Inside Our Gateway

*We put Erik Kaum’s Lattice retriever inside hev layer, streamed a real Wikipedia slice through it, and shipped the result at [wiki.hevlayer.com](https://wiki.hevlayer.com). A fresh query took 0.16 ms to embed. The interesting part is not only that number—it is what disappears from the architecture when embedding becomes cheap enough to run in the retrieval gateway itself.*

Search for “the largest planet in the solar system” and the first result is the paragraph that says Jupiter is the biggest planet. Search for “a country famous for the Eiffel Tower” and Eiffel Tower passages rise to the top. The browser did not download a model, call a separate inference service, or compute a vector. It sent text to Layer and rendered the answer—including Layer’s embedding-time echo.

The demo is live now: **[wiki.hevlayer.com](https://wiki.hevlayer.com)**.

## Lattice, briefly

Most modern embedding models are transformers. They pass tokens through layers of attention and matrix multiplication to produce one vector. That machinery buys retrieval quality, but it also brings model servers, memory pressure, batching decisions, cold starts, and usually a GPU conversation.

[Lattice](https://github.com/ErikKaum/lattice) is deliberately different. Its learned model is a static token-embedding table. Inference looks up the rows for the input tokens, mean-pools them, and L2-normalizes the result. There is no transformer and no attention pass.

We use a 512-dimensional artifact quantized to int4 per row. It is roughly 8 MB. That quantization describes the model weights—the lookup table—not the vectors stored in the search index. Layer emits normalized vectors and this demo stores them on Turbopuffer as `f32[512]`.

That distinction matters. “An int4 model” does not mean “an int4 search index,” and quietly conflating the two would make the demo hard to reproduce.

Lattice is not our claim that small static embeddings replace transformer embeddings everywhere. They do not. It is a deliberately fast, lower-fidelity serving option for workloads where CPU throughput, deployment size, and operational simplicity matter more than the last points of retrieval quality.

Wikipedia is a useful way to find out whether that trade is real.

## Why put embedding in the gateway?

The obvious way to build this demo is to add an embedding service beside the app. The indexer calls it for documents; the Worker calls it for queries; both carry vectors into the database. That works, but it makes every client responsible for the same model contract.

We wanted a narrower application boundary:

```text
Wikipedia dump → Layer gateway → Lattice → f32[512] → Turbopuffer

browser → Cloudflare Worker → Layer gateway → Lattice → ANN search
```

The indexer writes ordinary text with an embedding profile:

```json
{
  "model": "erikkaum/lattice-retrieval",
  "dims": 512,
  "serving": { "prefer": "lattice" }
}
```

The app queries with the same Turbopuffer-compatible `Embed` expression used by the other Layer serving modes:

```json
{
  "rank_by": [
    "text",
    "ANN",
    ["Embed", "largest planet in the solar system"]
  ],
  "top_k": 12
}
```

Layer resolves both document and query text through the in-process Lattice provider. Only concrete vectors reach Turbopuffer. The application owns neither embedding code nor model instructions, and there is no separate network hop to an inference server.

The serving choice is explicit. `prefer: lattice` never silently falls back to a native or autoscaled model. If the artifact is missing or the profile is wrong, the request fails. That is less magical and much easier to operate.

It also makes the mechanism visible. Layer merges provider measurements into the normal response `performance` object. The demo UI shows the serving leg, dimensions, gateway embedding time, and complete request time rather than asking visitors to trust a benchmark written somewhere else.

## What we measured

The live corpus was loaded on August 8, 2026 from the Simple English Wikipedia pages-and-articles XML dump.

- **2,000 articles**
- **30,268 paragraph chunks**
- **396.3 seconds** for the bounded ingest
- Usually **4–10 ms of gateway-reported Lattice time per write batch**
- **0.16 ms** of gateway-reported Lattice time for a fresh eight-token query
- **427 ms** for that full public Worker-to-gateway search request

The query measurement and the request measurement are intentionally separate. The 0.16 ms number is the Lattice embedding echo. The 427 ms number includes the public Worker, network, gateway handling, Turbopuffer ANN query, and response. On repeated queries, Layer’s short query-vector cache can hit; the UI says “cache hit” instead of inventing a zero-token measurement.

The ingest profile told the same story at a larger scale. Lattice embedded whole write batches in a few milliseconds. The end-to-end run was dominated by committing the resulting rows to Turbopuffer, not by computing their vectors. Once embedding becomes this cheap, optimizing the model call is no longer the first systems problem in the pipeline.

That is the architectural result we cared about more than a standalone tokens-per-second score.

## Does it find anything useful?

On the bounded slice, yes. A few searches we verified against the live deployment:

- **“largest planet in the solar system”** returned the passage saying Jupiter is the biggest planet first.
- **“country famous for the Eiffel Tower”** returned Eiffel Tower passages first.
- **“computer operating system created by Microsoft”** returned Microsoft and Microsoft Windows first.
- **“how plants turn sunlight into energy”** surfaced the Plant and Photosynthesis passages near the top.

The results are recognizably semantic: the useful passage does not need to repeat the query verbatim. They are also not transformer-quality magic. Some vague queries return a broadly related article before the exact one, and paragraph-level indexing means several chunks from one article can appear together. The demo does not hide that with a client-side reranker or dedup pass. What you see is the vector retrieval result from the stack.

## A bounded slice, honestly

The live site does **not** yet contain all of Wikipedia. It contains the first 2,000 main-namespace, non-redirect articles from Simple English Wikipedia. We chose that bounded slice to get the real system public first and learn from it.

Each article is stripped of wiki markup and split at paragraph granularity. Every row contains the title plus one paragraph; unusually long paragraphs split at a sentence or word boundary under 1,800 characters. Stable content-derived IDs make reruns idempotent. The loader checkpoints only at article boundaries, so an interrupted run cannot skip the tail of a large article.

The downloaded dump and checkpoint are deliberately not committed. To extend the corpus, rerun the indexer: it resumes at article 2,000. Set `--limit-articles 0` to continue through the dump, or point it at another Wikimedia pages-and-articles dump to change editions.

Calling a 2,000-article slice “all of Wikipedia” would make for a sharper headline and a worse artifact. The live, measured slice is enough to show the serving path and expose its tradeoffs. Expanding it is now batch time, not new architecture.

## Two backends, one request

The repository includes a FastAPI backend for local development and a Cloudflare Worker for production. Both inject the gateway key server-side, send the same `Embed` request, and return Layer’s `performance`, `billing`, `routing`, and `hybrid` echo fields unchanged when present. The UI is a small vanilla page shared by both.

There is no client-side embedding, tokenizer, fusion function, or reranker in the app. Those are stack responsibilities. The demo’s job is to supply Wikipedia text, issue a query, and make the stack’s decision legible.

The same split is what makes the demo useful beyond its landing page. The indexer is a resumable batch client. FastAPI is an inspectable reference client. The Worker is the public edge. The declarative bundle describes the corresponding VectorStore, Warehouse, Pipeline, and Index resources for an in-cluster deployment.

## Small enough to move a boundary

Embedding usually arrives as infrastructure: a hosted API, a GPU deployment, an autoscaler, or a client library that quietly becomes part of every write and query path. Lattice is small and fast enough that another placement becomes practical.

Putting it inside Layer did not only remove a service. It gave document writes and queries one model profile, kept vectors off the client boundary, made serving selection explicit, and returned the work as observable response data. The Wikipedia demo is the proof that this is not just a provider interface—it is a usable end-to-end path over real content.

Try it at **[wiki.hevlayer.com](https://wiki.hevlayer.com)**, then read the [Layer Embed documentation](https://hevlayer.com/docs/api/embed/) for the wire and serving modes behind it.
