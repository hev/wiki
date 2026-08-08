from __future__ import annotations

import time
from typing import Any

import httpx

MODEL = "erikkaum/lattice-retrieval"
DIMS = 512
SERVING = "lattice"
INCLUDE_ATTRIBUTES = [
    "title",
    "text",
    "url",
    "article_id",
    "paragraph",
    "is_lead",
]


def embedding_schema() -> dict[str, Any]:
    """The documented Layer schema; the gateway embeds text and stores f32[512]."""
    return {
        "text": {
            "type": "string",
            "embed": {
                "model": MODEL,
                "dims": DIMS,
                "serving": {"prefer": SERVING},
            },
        },
        "title": {"type": "string"},
        "url": {"type": "string"},
        "article_id": {"type": "string"},
        "paragraph": {"type": "int"},
        "is_lead": {"type": "bool"},
    }


def search_body(query: str, top_k: int) -> dict[str, Any]:
    return {
        "rank_by": ["text", "ANN", ["Embed", query]],
        "top_k": max(1, min(top_k, 30)),
        "include_attributes": INCLUDE_ATTRIBUTES,
    }


async def search_gateway(
    client: httpx.AsyncClient,
    *,
    gateway_url: str,
    api_key: str,
    namespace: str,
    query: str,
    top_k: int,
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("LAYER_GATEWAY_API_KEY is not configured")
    started = time.perf_counter()
    response = await client.post(
        f"{gateway_url.rstrip('/')}/v2/namespaces/{namespace}/query",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "x-hevlayer-search-query": query,
            "x-hevlayer-tags": "app:wiki,serving:lattice",
        },
        json=search_body(query, top_k),
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    if response.is_error:
        detail = response.text[:1000]
        raise httpx.HTTPStatusError(detail, request=response.request, response=response)
    upstream = response.json()
    return {
        "query": query,
        "rows": upstream.get("rows", []),
        "performance": upstream.get("performance", {}),
        "billing": upstream.get("billing"),
        "routing": upstream.get("routing"),
        "hybrid": upstream.get("hybrid"),
        "serving": {"prefer": SERVING, "model": MODEL, "dims": DIMS},
        "took_ms": elapsed_ms,
    }
