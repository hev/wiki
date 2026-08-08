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
      <span class="distance">${Number.isFinite(row.$dist) ? `distance ${row.$dist.toFixed(4)}` : "semantic match"}</span>
    </li>`).join("");
}

async function runSearch(query) {
  submit.disabled = true;
  submit.textContent = "Searching…";
  status.textContent = "Layer is embedding the query with Lattice…";
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
    embedLatency.textContent = data.performance?.embedding_ms == null ? "cache hit" : `${Number(data.performance.embedding_ms).toFixed(2)} ms`;
    totalLatency.textContent = `${Number(data.took_ms).toFixed(1)} ms`;
    namespaceLabel.textContent = data.serving ? `${data.serving.prefer} · ${data.serving.dims}d` : "wiki-simple";
    summary.textContent = `${rows.length} semantic matches for “${query}”`;
    if (rows.length) {
      renderRows(rows);
      resultsSection.hidden = false;
    } else {
      empty.hidden = false;
    }
    status.textContent = `Gateway echo: ${data.performance?.embedding_tokens ?? "cached"} embedding tokens.`;
    history.replaceState(null, "", `?q=${encodeURIComponent(query)}`);
  } catch (error) {
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

const initial = new URL(location.href).searchParams.get("q");
if (initial) {
  input.value = initial;
  runSearch(initial);
}
