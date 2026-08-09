import assert from "node:assert/strict";
import test from "node:test";

import { dedupeByArticle, proxySearch, searchBody } from "../src/worker.js";

test("worker sends one Auto query with an inline Embed expression", () => {
  assert.deepEqual(searchBody("moon landing", 50), {
    rank_by: ["title", "Auto", "moon landing", {
      vector: ["Embed", "moon landing", { field: "text" }],
    }],
    top_k: 120,
    include_attributes: ["title", "text", "url", "article_id", "paragraph", "is_lead"],
  });
});

test("dedupeByArticle keeps only the best-ranked chunk per article", () => {
  const rows = [
    { id: "42-0", article_id: "42", title: "A" },
    { id: "42-3", article_id: "42", title: "A" },
    { id: "7-1", article_id: "7", title: "B" },
    { id: "42-1", article_id: "42", title: "A" },
    { id: "9-0", article_id: "9", title: "C" },
  ];
  assert.deepEqual(dedupeByArticle(rows, 2).map((r) => r.id), ["42-0", "7-1"]);
  assert.deepEqual(dedupeByArticle(rows, 10).map((r) => r.id), ["42-0", "7-1", "9-0"]);
});

test("worker preserves gateway performance and routing echoes", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = previousFetch; });
  let sent;
  let fetchCalls = 0;
  globalThis.fetch = async (_url, options) => {
    fetchCalls += 1;
    sent = JSON.parse(options.body);
    return new Response(JSON.stringify({
      rows: [{ id: "1", title: "Apollo 11" }],
      performance: { embedding_ms: 0.13, embedding_tokens: 4 },
      routing: { route: "semantic", policy: "v1", tokens: 8, executed: true },
      hybrid: null,
    }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const request = new Request("https://wiki.test/api/search", {
    method: "POST",
    body: JSON.stringify({ query: "first people on the moon", top_k: 3 }),
  });
  const response = await proxySearch(request, {
    LAYER_API_KEY: "secret",
    LAYER_GATEWAY_URL: "https://gateway.test",
    LAYER_NAMESPACE: "wiki",
  });
  const body = await response.json();
  assert.equal(fetchCalls, 1);
  assert.deepEqual(sent.rank_by, [
    "title",
    "Auto",
    "first people on the moon",
    { vector: ["Embed", "first people on the moon", { field: "text" }] },
  ]);
  assert.equal(body.performance.embedding_ms, 0.13);
  assert.deepEqual(body.routing, { route: "semantic", policy: "v1", tokens: 8, executed: true });
  assert.equal(body.serving.prefer, "lattice");
});
