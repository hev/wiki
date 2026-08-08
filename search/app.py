from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from wiki_common.config import Settings
from wiki_common.gateway import DIMS, MODEL, SERVING, search_gateway

WEB = Path(__file__).resolve().parent.parent / "web" / "static"
settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=settings.timeout_seconds)
    yield
    await app.state.http.aclose()


app = FastAPI(title="Wikipedia search · Lattice on Layer", lifespan=lifespan)


class SearchRequest(BaseModel):
    query: str = Field(max_length=500)
    top_k: int = Field(default=12, ge=1, le=30)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/styles.css")
async def styles() -> FileResponse:
    return FileResponse(WEB / "styles.css")


@app.get("/app.js")
async def script() -> FileResponse:
    return FileResponse(WEB / "app.js")


@app.get("/api/config")
async def config() -> dict:
    return {
        "namespace": settings.namespace,
        "gateway": settings.gateway_url,
        "serving": {"prefer": SERVING, "model": MODEL, "dims": DIMS},
    }


@app.post("/api/search")
async def search(req: SearchRequest) -> dict:
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must not be empty")
    try:
        return await search_gateway(
            app.state.http,
            gateway_url=settings.gateway_url,
            api_key=settings.gateway_api_key,
            namespace=settings.namespace,
            query=query,
            top_k=req.top_k,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise HTTPException(status_code=status if status < 500 else 502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"gateway unreachable: {exc}") from exc
