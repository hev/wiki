import assert from "node:assert/strict";
import test from "node:test";

import { proxySearch, searchBody } from "../src/worker.js";

test("worker sends one Auto query with an inline Embed expression", () => {
  assert.deepEqual(searchBody("moon landing", 50), {
    rank_by: ["title", "Auto", "moon landing", { vector: ["Embed", "moon landing"] }],
    top_k: 30,
    include_attributes: ["title", "text", "url", "article_id", "paragraph", "is_lead"],
  });
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
    { vector: ["Embed", "first people on the moon"] },
  ]);
  assert.equal(body.performance.embedding_ms, 0.13);
  assert.deepEqual(body.routing, { route: "semantic", policy: "v1", tokens: 8, executed: true });
  assert.equal(body.serving.prefer, "lattice");
});
