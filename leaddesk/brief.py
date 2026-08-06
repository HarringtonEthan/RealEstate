"""Daily brief — Markdown file for Diane, built only from already-verified data."""

import json
from datetime import datetime, timezone

from . import config

STAGE_LABELS = {
    "NEW": "New", "RESEARCHING": "Researching", "QUALIFIED": "Qualified",
    "HIGH_PRIORITY": "High priority", "CONTACT_READY": "Contact ready",
    "CONTACTED": "Contacted", "RESPONDED": "Responded", "APPOINTMENT": "Appointment",
    "CLIENT": "Client", "NURTURE": "Nurture",
}

TYPE_LABELS = {
    "buyer": "Buyer", "first_time_buyer": "First-time buyer", "move_up_buyer": "Move-up buyer",
    "downsizer": "Downsizer", "seller": "Seller", "relocation": "Relocation",
    "investor": "Investor", "land": "Land", "fsbo": "FSBO", "expired": "Expired listing",
    "other": "Other",
}


def generate(conn) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    leads = conn.execute(
        "SELECT * FROM leads WHERE stage IN ('QUALIFIED','HIGH_PRIORITY') "
        "ORDER BY lead_score DESC"
    ).fetchall()
    new_today = conn.execute(
        "SELECT COUNT(*) c FROM leads WHERE date_discovered LIKE ?", (today + "%",)
    ).fetchone()["c"]
    rejected_today = conn.execute(
        "SELECT COUNT(*) c FROM leads WHERE stage='REJECTED' AND date_discovered LIKE ?",
        (today + "%",),
    ).fetchone()["c"]
    spend = conn.execute(
        "SELECT COALESCE(SUM(cost_usd),0) c FROM tasks WHERE created_at LIKE ?", (today + "%",)
    ).fetchone()["c"]

    lines = [f"# Diane's Raleigh Lead Brief — {today}", ""]
    if not leads:
        lines.append("_No qualified leads in the pipeline right now. "
                     f"({new_today} candidates reviewed today, {rejected_today} rejected — "
                     "a quiet day is an honest day.)_")
    else:
        lines.append(f"**{len(leads)} qualified lead(s)** · {new_today} candidates reviewed today · "
                     f"{rejected_today} rejected as not good enough")
        lines.append("")
        for lead in leads:
            lines.extend(_lead_card(lead))

    pipeline = conn.execute(
        "SELECT stage, COUNT(*) c FROM leads WHERE stage NOT IN ('REJECTED','INVALID','CLOSED') "
        "GROUP BY stage"
    ).fetchall()
    lines.append("\n## 📊 Pipeline")
    for row in pipeline:
        lines.append(f"- {STAGE_LABELS.get(row['stage'], row['stage'])}: {row['c']}")
    lines.append(f"\n_System cost today: ${spend:.2f}_")

    config.BRIEFS_DIR.mkdir(exist_ok=True)
    path = config.BRIEFS_DIR / f"{today}.md"
    path.write_text("\n".join(lines))
    return str(path)


def _lead_card(lead) -> list[str]:
    breakdown = json.loads(lead["score_breakdown"] or "{}")
    flag = "🔥 " if lead["stage"] == "HIGH_PRIORITY" else ""
    out = [
        f"---\n### {flag}{TYPE_LABELS.get(lead['lead_type'], lead['lead_type'])} — "
        f"{lead['city'] or 'Area TBD'} · Score {lead['lead_score']}/100",
        f"**Signal:** {lead['signal']}",
        f"**Why this matters:** {lead['why_it_matters']}",
        f"**Source:** {lead['source']} — {lead['source_url']} (posted {lead['signal_date'] or 'unknown'})",
        f"**Verification:** {lead['verification']} · **Confidence:** {lead['confidence']}",
        f"**Recommended next action:** {lead['next_action']}",
    ]
    parts = [f"{k} {v['points']}/{v['max']}" for k, v in breakdown.items()]
    if parts:
        out.append(f"**Score breakdown:** {' · '.join(parts)}")
    out.append("")
    return out
