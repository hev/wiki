import json

import httpx
import pytest
import respx

from indexer.__main__ import article_chunks, clean_wikitext
from wiki_common.gateway import DIMS, MODEL, embedding_schema, search_body, search_gateway


def test_embedding_schema_pins_lattice_f32_output_profile():
    embed = embedding_schema()["text"]["embed"]
    assert embed == {
        "model": MODEL,
        "dims": DIMS,
        "serving": {"prefer": "lattice"},
    }


def test_search_uses_gateway_embed_expression():
    body = search_body("people on the moon", 999)
    assert body["rank_by"] == ["text", "ANN", ["Embed", "people on the moon"]]
    assert body["top_k"] == 30
    assert "vector" not in json.dumps(body).lower()


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
    assert route.called
    request = json.loads(route.calls[0].request.content)
    assert request["rank_by"] == ["text", "ANN", ["Embed", "moon landing"]]
    assert result["performance"]["embedding_ms"] == 0.17
    assert result["serving"]["prefer"] == "lattice"


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
