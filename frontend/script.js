const $ = (id) => document.getElementById(id);
let lastSources = [];

document.querySelectorAll(".chips button").forEach(btn => {
  btn.addEventListener("click", () => $("question").value = btn.dataset.q);
});

function renderActivity(items) {
  $("activity").innerHTML = (items || []).map(item => {
    const message = typeof item === "string" ? item : (item?.message || "");
    const status = typeof item === "string" ? "done" : (item?.status || "done");
    const cls = status === "warning" || status === "blocked" ? "warning" : "";
    return `<div class="activity-row ${cls}">
      <span class="mark">${status === "blocked" ? "!" : "✓"}</span>
      <span>${escapeHtml(message)}</span>
    </div>`;
  }).join("");
}

function renderSources(items) {
  lastSources = items || [];
  $("sources").innerHTML = lastSources.length
    ? lastSources.map(s => `
      <div class="source">
        <a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.title || s.type)}</a>
        <div class="source-meta">${escapeHtml((s.source_id || "") + " • " + (s.type || "") + " • " + (s.retrieved_at || "retrieved now"))}</div>
      </div>`).join("")
    : "<div class='answer empty'>No source was used.</div>";
}

function renderSuggestions(id, values) {
  $(id).innerHTML = (values || []).map(v =>
    `<button data-q="${escapeAttr(v)}">${escapeHtml(v)}</button>`
  ).join("");
  $(id).querySelectorAll("button").forEach(btn => {
    btn.addEventListener("click", () => {
      $("question").value = btn.dataset.q;
      window.scrollTo({top: 0, behavior: "smooth"});
      $("question").focus();
    });
  });
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;"
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

async function search() {
  const question = $("question").value.trim();
  if (!question) return;

  $("ask").disabled = true;
  $("ask").textContent = "Researching…";
  $("answer").classList.remove("empty");
  $("answer").textContent = "Finding live evidence and checking it…";

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        question,
        output_template: $("template").value
      })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || data.message || `Search failed (${res.status})`);
    }

    $("answer").textContent = data.answer || "No answer returned.";
    $("intent").textContent = data.intent || "—";
    $("route").textContent = (data.route || []).join(" + ") || "—";
    $("confidence").textContent = data.confidence || "—";
    $("freshness").textContent = data.freshness || "—";

    $("grounded").textContent = data.grounded ? "Grounded" : "Not grounded";
    $("grounded").className = "badge" + (data.grounded ? "" : " bad");

    renderActivity(data.activity);
    renderSources(data.sources);
    renderSuggestions("followups", data.follow_ups);
    renderSuggestions("related", data.related);

    document.querySelector(".report").scrollIntoView({behavior:"smooth", block:"start"});
  } catch (err) {
    $("answer").textContent = err?.message || "The search service could not be reached. Make sure the FastAPI server is running.";
    $("grounded").textContent = "Error";
    $("grounded").className = "badge bad";
  } finally {
    $("ask").disabled = false;
    $("ask").textContent = "Search →";
  }
}

$("ask").addEventListener("click", search);
$("question").addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") search();
});

document.querySelectorAll("[data-helpful]").forEach(btn => {
  btn.addEventListener("click", async () => {
    await fetch("/api/feedback", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({
        helpful: btn.dataset.helpful === "true",
        sources: lastSources.map(x => x.type)
      })
    });
    btn.textContent = "Thanks";
  });
});
