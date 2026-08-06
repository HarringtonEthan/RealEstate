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
  const el = document.getElementById("summary");
  const bits = [];
  if (s.high_priority) bits.push(s.high_priority + " marked high priority");
  if (s.reviewed_today) bits.push(s.reviewed_today + " candidates reviewed today");
  if (s.rejected_total) bits.push(s.rejected_total + " rejected as not good enough");
  el.innerHTML = "<strong>" +
    plural(s.qualified || 0, "qualified opportunity", "qualified opportunities") +
    "</strong>" + (bits.length ? " · " + bits.map(esc).join(" · ") : "") + ".";

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
    const box = document.getElementById("leads");
    const leads = data.leads.filter((l) => active === "all" || groupOf(l) === active);
    if (!leads.length) {
      box.innerHTML = '<div class="empty">No opportunities in this group right now.<br>' +
        "A quiet day is an honest day — the system only shows leads worth your time.</div>";
      return;
    }
    box.innerHTML = leads.map(card).join("");
  }

  function tierVars(score) {
    const t = score >= 80 ? "hot" : score >= 70 ? "warm" : "cool";
    return "--pct:" + score + "%;--tier:var(--" + t + ");--tier-soft:var(--" + t + "-soft)";
  }

  function card(lead) {
    const rows = Object.entries(lead.score_breakdown || {}).map(([name, v]) => {
      const pct = v.max ? Math.round((v.points / v.max) * 100) : 0;
      return (
        '<div class="bd-row"><span class="bd-name">' + esc(name) +
        '</span><span class="bd-pts">' + v.points + "/" + v.max + "</span>" +
        '<span class="bd-bar"><span class="bd-fill" style="width:' + pct + '%"></span></span>' +
        (v.rationale ? '<span class="bd-why">' + esc(v.rationale) + "</span>" : "") +
        "</div>"
      );
    }).join("");

    const priority = lead.stage === "HIGH_PRIORITY";
    const postedBy = lead.author ? "Posted by " + esc(lead.author) + " · " : "";

    return (
      '<article class="lead">' +
      '<div class="lead-top">' +
      '<div class="ring" style="' + tierVars(lead.score) + '" role="img" aria-label="Score ' +
        lead.score + ' out of 100"><span>' + lead.score + "</span></div>" +
      '<div class="lead-heading">' +
      '<div class="lead-title">' + esc(lead.type_label) + " · " + esc(lead.location) + "</div>" +
      '<div class="lead-sub">' +
      '<span class="badge' + (priority ? " priority" : "") + '">' + esc(lead.stage_label) + "</span>" +
      (lead.sample ? '<span class="badge sample">Sample</span>' : "") +
      "</div></div></div>" +
      "<dl>" +
      dt("What they said", lead.signal) +
      dt("Why this matters", lead.why) +
      dt("Suggested next step", lead.next_action) +
      (lead.timeframe ? dt("Timeframe", lead.timeframe) : "") +
      (lead.budget ? dt("Budget mentioned", lead.budget) : "") +
      '<dt>Source</dt><dd class="quiet">' + postedBy + esc(lead.source) +
      (lead.signal_date ? " · posted " + esc(lead.signal_date) : "") +
      sourceLink(lead) + "</dd>" +
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
    if (lead.source_url && lead.source_url !== "#") {
      return '<br><a class="post-link" href="' + esc(lead.source_url) +
        '" target="_blank" rel="noopener">Open the post ↗</a>';
    }
    return "";
  }

  // ---- Market notes & pipeline -------------------------------------------------
  if ((data.market_notes || []).length) {
    document.getElementById("market-panel").hidden = false;
    document.getElementById("market-notes").innerHTML =
      data.market_notes.map((n) => "<li>" + esc(n) + "</li>").join("");
  }

  const pipe = data.pipeline || {};
  document.getElementById("pipeline").innerHTML = Object.keys(pipe).length
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
