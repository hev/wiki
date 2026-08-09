import json

import httpx
import pytest
import respx

from indexer.__main__ import article_chunks, clean_wikitext
from wiki_common.gateway import DIMS, MODEL, embedding_schema, search_body, search_gateway, stats_gateway


def test_embedding_schema_pins_lattice_f32_output_profile():
    embed = embedding_schema()["text"]["embed"]
    assert embed == {
        "model": MODEL,
        "dims": DIMS,
        "serving": {"prefer": "lattice"},
    }


def test_embedding_schema_indexes_title_and_text_for_hybrid_search():
    schema = embedding_schema()
    assert schema["text"]["full_text_search"] is True
    assert schema["text"]["fuzzy"] is True
    assert schema["title"] == {
        "type": "string",
        "full_text_search": True,
        "fuzzy": True,
    }


def test_search_uses_one_auto_query_with_inline_gateway_embed():
    body = search_body("people on the moon", 999)
    assert body["rank_by"] == [
        "title",
        "Auto",
        "people on the moon",
        {"vector": ["Embed", "people on the moon", {"field": "text"}]},
    ]
    assert body["top_k"] == 30
    assert "ANN" not in json.dumps(body)


@pytest.mark.asyncio
@respx.mock
async def test_gateway_echo_is_preserved():
    route = respx.post("https://gateway.test/v2/namespaces/wiki/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "rows": [{"id": "1", "title": "Moon"}],
                "performance": {"embedding_ms": 0.17, "embedding_tokens": 3},
                "billing": {"billable_logical_bytes_queried": 42},
                "routing": {"route": "fused", "policy": "v1", "tokens": 3, "executed": True},
                "hybrid": {"tokens": ["moon", "landing"], "legs": 4},
            },
        )
    )
    async with httpx.AsyncClient() as client:
        result = await search_gateway(
            client,
            gateway_url="https://gateway.test",
            api_key="secret",
            namespace="wiki",
            query="moon landing",
            top_k=5,
        )
    assert route.call_count == 1
    request = json.loads(route.calls[0].request.content)
    assert request["rank_by"] == [
        "title",
        "Auto",
        "moon landing",
        {"vector": ["Embed", "moon landing", {"field": "text"}]},
    ]
    assert result["performance"]["embedding_ms"] == 0.17
    assert result["routing"] == {"route": "fused", "policy": "v1", "tokens": 3, "executed": True}
    assert result["hybrid"]["legs"] == 4
    assert result["serving"]["prefer"] == "lattice"


@pytest.mark.asyncio
@respx.mock
async def test_stats_gateway_matches_worker_metadata_projection():
    respx.get("https://gateway.test/v1/namespaces/wiki/metadata").mock(
        return_value=httpx.Response(
            200,
            json={
                "approx_row_count": 1_737_141,
                "approx_logical_bytes": 4_211_806_087,
                "updated_at": "2026-08-08T00:00:00Z",
                "schema": {"text": {"type": "string"}},
            },
        )
    )
    async with httpx.AsyncClient() as client:
        result = await stats_gateway(
            client,
            gateway_url="https://gateway.test",
            api_key="secret",
            namespace="wiki",
        )
    assert result == {
        "approx_row_count": 1_737_141,
        "approx_logical_bytes": 4_211_806_087,
        "updated_at": "2026-08-08T00:00:00Z",
    }


def test_article_chunks_are_stable_paragraph_units():
    raw = "'''Moon''' is Earth's satellite.\n\nIt affects ocean tides.\n\n== References ==\n<ref>Example</ref>"
    rows = list(article_chunks("123", "Moon", raw, 120))
    assert rows[0]["is_lead"] is True
    assert rows[0]["text"].startswith("Moon\n\n")
    assert all(row["article_id"] == "123" for row in rows)
    assert [row["id"] for row in rows] == [row["id"] for row in article_chunks("123", "Moon", raw, 120)]


def test_clean_wikitext_removes_markup():
    assert "'''" not in clean_wikitext("'''Apollo 11''' was a [[spaceflight]].")
    assert "Apollo 11" in clean_wikitext("'''Apollo 11''' was a [[spaceflight]].")
