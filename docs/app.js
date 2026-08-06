/* Diane's Lead Desk — renders window.LEAD_DATA (written by the pipeline). */

(function () {
  const data = window.LEAD_DATA;
  if (!data) {
    document.getElementById("leads").innerHTML =
      '<div class="empty">No data file found yet. Run the pipeline, then refresh.</div>';
    return;
  }

  document.getElementById("updated").textContent = "Updated " + data.generated_at;
  if (data.is_sample) document.getElementById("sample-banner").hidden = false;

  // ---- Summary sentence ----------------------------------------------------
  const s = data.stats || {};
  const bits = [];
  bits.push(plural(s.qualified || 0, "qualified opportunity", "qualified opportunities"));
  if (s.high_priority) bits.push(s.high_priority + " marked high priority");
  if (s.reviewed_today) bits.push(s.reviewed_today + " candidates reviewed today");
  if (s.rejected_total) bits.push(s.rejected_total + " rejected as not good enough");
  document.getElementById("summary").textContent =
    bits.length ? "Right now: " + bits.join(" · ") + "." : "";

  // ---- Filters ---------------------------------------------------------------
  const GROUPS = [
    ["all", "All"],
    ["buy", "🔑 Buyers"],
    ["sell", "🏡 Sellers"],
    ["relocation", "🚚 Relocation"],
    ["investor", "📈 Investors"],
  ];
  const groupOf = (lead) => {
    if (lead.type === "relocation") return "relocation";
    if (lead.type === "investor") return "investor";
    if (["seller", "fsbo", "expired", "downsizer", "land"].includes(lead.type)) return "sell";
    return "buy";
  };

  const filtersEl = document.getElementById("filters");
  let active = "all";
  GROUPS.forEach(([key, label]) => {
    const count = key === "all" ? data.leads.length
      : data.leads.filter((l) => groupOf(l) === key).length;
    if (key !== "all" && count === 0) return;
    const btn = document.createElement("button");
    btn.textContent = label + " (" + count + ")";
    btn.dataset.key = key;
    if (key === "all") btn.classList.add("active");
    btn.addEventListener("click", () => {
      active = key;
      filtersEl.querySelectorAll("button").forEach((b) =>
        b.classList.toggle("active", b.dataset.key === key));
      render();
    });
    filtersEl.appendChild(btn);
  });

  // ---- Lead cards ------------------------------------------------------------
  function render() {
    const el = document.getElementById("leads");
    const leads = data.leads.filter((l) => active === "all" || groupOf(l) === active);
    if (!leads.length) {
      el.innerHTML = '<div class="empty">No opportunities in this group right now.<br>' +
        "A quiet day is an honest day — the system only shows leads worth your time.</div>";
      return;
    }
    el.innerHTML = leads.map(card).join("");
  }

  function card(lead) {
    const tier = lead.score >= 80 ? "hot" : lead.score >= 70 ? "warm" : "cool";
    const rows = Object.entries(lead.score_breakdown || {}).map(
      ([name, v]) =>
        '<div class="bd-row"><span class="bd-name">' + esc(name) +
        '</span><span class="bd-pts">' + v.points + "/" + v.max +
        '</span><span class="bd-why">' + esc(v.rationale || "") + "</span></div>"
    ).join("");

    return (
      '<article class="lead">' +
      '<div class="lead-top">' +
      '<span class="score ' + tier + '">' + lead.score + "/100</span>" +
      '<span class="lead-title">' + esc(lead.type_label) + " · " + esc(lead.location) + "</span>" +
      '<span class="badge">' + esc(lead.stage_label) + "</span>" +
      (lead.sample ? '<span class="badge sample">Sample</span>' : "") +
      "</div>" +
      "<dl>" +
      dt("What they said", lead.signal) +
      dt("Why this matters", lead.why) +
      dt("Suggested next step", lead.next_action) +
      (lead.timeframe ? dt("Timeframe", lead.timeframe) : "") +
      (lead.budget ? dt("Budget mentioned", lead.budget) : "") +
      '<dt>Source</dt><dd class="quiet">' + sourceLink(lead) +
      (lead.signal_date ? " · posted " + esc(lead.signal_date) : "") + "</dd>" +
      "</dl>" +
      '<div class="meta-row">' +
      '<span>Found ' + esc(lead.discovered) + "</span>" +
      '<span>Confidence: ' + esc(lead.confidence) + "</span>" +
      '<span class="' + (lead.verification === "verified" ? "ok" : "") + '">' +
      (lead.verification === "verified" ? "✓ Source verified" : "Source " + esc(lead.verification)) +
      "</span></div>" +
      (rows
        ? '<details class="breakdown"><summary>How this score was calculated</summary>' +
          rows + "</details>"
        : "") +
      "</article>"
    );
  }

  function dt(label, value) {
    return value ? "<dt>" + esc(label) + "</dt><dd>" + esc(value) + "</dd>" : "";
  }

  function sourceLink(lead) {
    const name = esc(lead.source || "source");
    if (lead.source_url && lead.source_url !== "#") {
      return '<a href="' + esc(lead.source_url) + '" target="_blank" rel="noopener">' +
        name + " ↗</a>";
    }
    return name;
  }

  // ---- Market notes & pipeline -------------------------------------------------
  if ((data.market_notes || []).length) {
    document.getElementById("market-panel").hidden = false;
    document.getElementById("market-notes").innerHTML =
      data.market_notes.map((n) => "<li>" + esc(n) + "</li>").join("");
  }

  const pipelineEl = document.getElementById("pipeline");
  const pipe = data.pipeline || {};
  pipelineEl.innerHTML = Object.keys(pipe).length
    ? Object.entries(pipe).map(([stage, n]) =>
        "<li><span>" + esc(stage) + '</span><span class="count">' + n + "</span></li>").join("")
    : "<li><span>Nothing in the pipeline yet</span><span class='count'>0</span></li>";

  function esc(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }

  render();
})();
