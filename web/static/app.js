const form = document.querySelector("#search-form");
const input = document.querySelector("#query");
const submit = form.querySelector("button[type=submit]");
const resultsSection = document.querySelector("#results-section");
const results = document.querySelector("#results");
const empty = document.querySelector("#empty");
const status = document.querySelector("#status");
const summary = document.querySelector("#result-summary");
const embedLatency = document.querySelector("#embed-latency");
const totalLatency = document.querySelector("#total-latency");
const routeTaken = document.querySelector("#route-taken");
const namespaceLabel = document.querySelector("#namespace-label");

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[char]);

function excerpt(row) {
  const text = String(row.text || "");
  const title = String(row.title || "");
  const body = text.startsWith(`${title}\n\n`) ? text.slice(title.length + 2) : text;
  return body.length > 340 ? `${body.slice(0, 337).trim()}…` : body;
}

function renderRows(rows) {
  results.innerHTML = rows.map((row, index) => `
    <li class="result">
      <span class="rank">${index + 1}</span>
      <article>
        <h3><a href="${escapeHtml(row.url)}" target="_blank" rel="noreferrer">${escapeHtml(row.title || "Untitled")}</a></h3>
        <p>${escapeHtml(excerpt(row))}</p>
      </article>
      <span class="distance">${Number.isFinite(row.$dist) ? `distance ${row.$dist.toFixed(4)}` : Number.isFinite(row.$score) ? `RRF ${row.$score.toFixed(4)}` : "routed match"}</span>
    </li>`).join("");
}

const ROUTE_LABELS = {
  hybrid_text: "full-text",
  semantic: "semantic",
  fused: "fused (RRF)",
};

function routingLabel(routing) {
  if (!routing?.route) return "unavailable";
  const label = ROUTE_LABELS[routing.route] || routing.route;
  return routing.executed === false ? `${label} · deferred` : label;
}

async function runSearch(query) {
  submit.disabled = true;
  submit.textContent = "Searching…";
  status.textContent = "Layer is choosing the retrieval route…";
  routeTaken.textContent = "routing…";
  resultsSection.hidden = true;
  empty.hidden = true;
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, top_k: 12 }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Search failed (${response.status})`);
    const rows = data.rows || [];
    const route = data.routing?.route;
    routeTaken.textContent = routingLabel(data.routing);
    embedLatency.textContent = route === "hybrid_text"
      ? "not needed"
      : data.performance?.embedding_ms == null
        ? "cache hit"
        : `${Number(data.performance.embedding_ms).toFixed(2)} ms`;
    totalLatency.textContent = `${Number(data.took_ms).toFixed(1)} ms`;
    namespaceLabel.textContent = data.serving ? `${data.serving.prefer} · ${data.serving.dims}d` : "wiki-simple";
    summary.textContent = `${rows.length} ${routingLabel(data.routing)} matches for “${query}”`;
    if (rows.length) {
      renderRows(rows);
      resultsSection.hidden = false;
    } else {
      empty.hidden = false;
    }
    const embedWork = route === "hybrid_text"
      ? "no embedding needed"
      : `${data.performance?.embedding_tokens ?? "cached"} embedding tokens`;
    status.textContent = `Gateway echo: ${routingLabel(data.routing)} · ${embedWork}.`;
    history.replaceState(null, "", `?q=${encodeURIComponent(query)}`);
  } catch (error) {
    routeTaken.textContent = "unavailable";
    empty.hidden = false;
    empty.querySelector("h3").textContent = "Search is temporarily unavailable.";
    empty.querySelector("p").textContent = error.message;
    status.textContent = error.message;
  } finally {
    submit.disabled = false;
    submit.textContent = "Search";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = input.value.trim();
  if (query) runSearch(query);
});

document.querySelectorAll(".examples button").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.textContent;
    runSearch(input.value);
  });
});

fetch("/api/config").then((response) => response.json()).then((config) => {
  namespaceLabel.textContent = config.namespace;
}).catch(() => {});

// Exact figures from the completed 2026-08-08 full-dump run. Metadata row
// counts are approximate, so the proof tile uses the completed-run totals.
const INDEXED_ARTICLES = 283997;
const INDEXED_ROWS = 1737141;
const corpusArticles = document.querySelector("#corpus-articles");
const corpusSize = document.querySelector("#corpus-size");

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

fetch("/api/stats").then((response) => response.json()).then((stats) => {
  corpusArticles.textContent = `${INDEXED_ARTICLES.toLocaleString()} · ${INDEXED_ROWS.toLocaleString()} rows`;
  corpusSize.textContent = Number.isFinite(stats.approx_logical_bytes) ? formatBytes(stats.approx_logical_bytes) : "unavailable";
}).catch(() => {
  corpusArticles.textContent = `${INDEXED_ARTICLES.toLocaleString()} · ${INDEXED_ROWS.toLocaleString()} rows`;
  corpusSize.textContent = "unavailable";
});

const initial = new URL(location.href).searchParams.get("q");
if (initial) {
  input.value = initial;
  runSearch(initial);
}
