# wiki contributor guide

This repository is a Layer design-preview customer. It posts native request shapes to the gateway and renders the gateway echo. Do not add client-side embedding, retrieval fusion, tokenization, or reranking.

Read request and response shapes from `../layer-pro/site/src/content/docs/` and `../layer-pro/apps/layer-gateway/openapi.yaml`. Gateway/API friction becomes a GitHub issue on `hev/layer-pro`; engine friction becomes an issue on `hev/search`.

## Local verification

```sh
uv sync
uv run pytest
npm install
npm test
uv run uvicorn search.app:app --host 127.0.0.1 --port 8000
```

Secrets belong only in gitignored `.env` and `.dev.vars`. The live namespace is `wiki-simple`; disposable tests must use `wiki-scratch-*` and delete them afterward.
