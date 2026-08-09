const MODEL = "erikkaum/lattice-retrieval";
const DIMS = 512;
const SERVING = "lattice";
const INCLUDE = ["title", "text", "url", "article_id", "paragraph", "is_lead"];

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });

// Rows are paragraph chunks; several chunks of one article can dominate a
// result page (fused legs especially — every paragraph of a title match ranks).
// Over-fetch, then keep only the best-ranked chunk per article.
const OVERFETCH = 4;

export function searchBody(query, topK = 12) {
  const k = Math.max(1, Math.min(Number(topK) || 12, 30));
  return {
    rank_by: ["title", "Auto", query, { vector: ["Embed", query, { field: "text" }] }],
    top_k: Math.min(k * OVERFETCH, 120),
    include_attributes: INCLUDE,
  };
}

export function dedupeByArticle(rows, topK = 12) {
  const k = Math.max(1, Math.min(Number(topK) || 12, 30));
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    const article = row.article_id ?? row.id;
    if (seen.has(article)) continue;
    seen.add(article);
    out.push(row);
    if (out.length >= k) break;
  }
  return out;
}

export async function proxySearch(request, env) {
  const key = env.LAYER_API_KEY || env.LAYER_GATEWAY_API_KEY;
  if (!key) return json({ detail: "Layer gateway key is not configured" }, 503);

  let input;
  try {
    input = await request.json();
  } catch {
    return json({ detail: "request body must be JSON" }, 400);
  }
  const query = String(input.query || "").trim();
  if (!query) return json({ detail: "query must not be empty" }, 422);
  if (query.length > 500) return json({ detail: "query must be 500 characters or fewer" }, 422);

  const gateway = String(env.LAYER_GATEWAY_URL || "https://aws-us-east-1.hevlayer.com").replace(/\/+$/, "");
  const namespace = env.LAYER_NAMESPACE || "wiki-simple";
  const started = performance.now();
  let response;
  try {
    response = await fetch(`${gateway}/v2/namespaces/${namespace}/query`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${key}`,
        "content-type": "application/json",
        "x-hevlayer-search-query": query,
        "x-hevlayer-tags": "app:wiki,serving:lattice,search:auto-routing",
      },
      body: JSON.stringify(searchBody(query, input.top_k)),
    });
  } catch (error) {
    return json({ detail: `gateway unreachable: ${String(error)}` }, 502);
  }
  const tookMs = Math.round((performance.now() - started) * 10) / 10;
  const text = await response.text();
  let upstream;
  try {
    upstream = JSON.parse(text);
  } catch {
    return json({ detail: `gateway returned invalid JSON (${response.status})` }, 502);
  }
  if (!response.ok) {
    return json({ detail: upstream.detail || upstream.error || text.slice(0, 1000) }, response.status >= 500 ? 502 : response.status);
  }
  return json({
    query,
    rows: dedupeByArticle(upstream.rows || [], input.top_k),
    performance: upstream.performance || {},
    billing: upstream.billing || null,
    routing: upstream.routing || null,
    hybrid: upstream.hybrid || null,
    serving: { prefer: SERVING, model: MODEL, dims: DIMS },
    took_ms: tookMs,
  });
}

export async function proxyStats(env) {
  const key = env.LAYER_API_KEY || env.LAYER_GATEWAY_API_KEY;
  if (!key) return json({ detail: "Layer gateway key is not configured" }, 503);
  const gateway = String(env.LAYER_GATEWAY_URL || "https://aws-us-east-1.hevlayer.com").replace(/\/+$/, "");
  const namespace = env.LAYER_NAMESPACE || "wiki-simple";
  let response;
  try {
    response = await fetch(`${gateway}/v1/namespaces/${namespace}/metadata`, {
      headers: { authorization: `Bearer ${key}` },
    });
  } catch (error) {
    return json({ detail: `gateway unreachable: ${String(error)}` }, 502);
  }
  const text = await response.text();
  let upstream;
  try {
    upstream = JSON.parse(text);
  } catch {
    return json({ detail: `gateway returned invalid JSON (${response.status})` }, 502);
  }
  if (!response.ok) {
    return json({ detail: upstream.detail || upstream.error || text.slice(0, 1000) }, response.status >= 500 ? 502 : response.status);
  }
  return json({
    approx_row_count: upstream.approx_row_count ?? null,
    approx_logical_bytes: upstream.approx_logical_bytes ?? null,
    updated_at: upstream.updated_at ?? null,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/config") {
      return json({
        namespace: env.LAYER_NAMESPACE || "wiki-simple",
        gateway: env.LAYER_GATEWAY_URL || "https://aws-us-east-1.hevlayer.com",
        serving: { prefer: SERVING, model: MODEL, dims: DIMS },
      });
    }
    if (url.pathname === "/api/stats") {
      return proxyStats(env);
    }
    if (url.pathname === "/api/search") {
      if (request.method !== "POST") return json({ detail: "method not allowed" }, 405);
      return proxySearch(request, env);
    }
    return env.ASSETS.fetch(request);
  },
};
