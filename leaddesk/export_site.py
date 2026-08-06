"""Export lead data for the Diane-facing website (docs/).

Writes docs/data/leads.js (window.LEAD_DATA = {...}) so the page works when
opened directly from disk AND on GitHub Pages, plus leads.json for anything
programmatic.
"""

import json
from datetime import datetime, timezone

from . import config
from .brief import STAGE_LABELS, TYPE_LABELS


def export(conn) -> str:
    # MLS-licensed leads are held back from the public website by default —
    # see config.PUBLISH_MLS_LEADS_TO_SITE. They're still fully visible in the
    # local Markdown brief (brief.py) and `leaddesk status`.
    mls_filter = "" if config.PUBLISH_MLS_LEADS_TO_SITE else "AND mls_licensed=0"
    leads = conn.execute(
        f"SELECT * FROM leads WHERE stage NOT IN ('REJECTED','INVALID') {mls_filter} "
        "ORDER BY lead_score DESC, date_discovered DESC"
    ).fetchall()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reviewed_today = conn.execute(
        "SELECT COUNT(*) c FROM leads WHERE date_discovered LIKE ?", (today + "%",)
    ).fetchone()["c"]
    rejected_total = conn.execute(
        "SELECT COUNT(*) c FROM leads WHERE stage='REJECTED'"
    ).fetchone()["c"]

    pipeline = {}
    for row in conn.execute("SELECT stage, COUNT(*) c FROM leads GROUP BY stage"):
        pipeline[STAGE_LABELS.get(row["stage"], row["stage"])] = row["c"]

    data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "is_sample": False,
        "stats": {
            "qualified": sum(1 for l in leads if l["stage"] in ("QUALIFIED", "HIGH_PRIORITY")),
            "high_priority": sum(1 for l in leads if l["stage"] == "HIGH_PRIORITY"),
            "reviewed_today": reviewed_today,
            "rejected_total": rejected_total,
        },
        "pipeline": pipeline,
        "market_notes": [],
        "leads": [_lead_dict(l) for l in leads],
    }
    return write_site_data(data)


def write_site_data(data: dict) -> str:
    config.SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    js_path = config.SITE_DATA_DIR / "leads.js"
    js_path.write_text("window.LEAD_DATA = " + json.dumps(data, indent=2) + ";\n", encoding="utf-8")
    (config.SITE_DATA_DIR / "leads.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(js_path)


def _lead_dict(lead) -> dict:
    breakdown = json.loads(lead["score_breakdown"] or "{}")
    notes = json.loads(lead["research_notes"] or "{}")
    info = json.loads(lead["property_info"] or "{}")

    location = lead["city"] or "Area to be determined"
    if lead["subject_kind"] == "property" and lead["property_address"]:
        location = f"{lead['property_address']}, {lead['city'] or ''}".rstrip(", ")

    return {
        "id": lead["lead_id"],
        "sample": False,
        "author": lead["display_name"],
        "type": lead["lead_type"],
        "type_label": TYPE_LABELS.get(lead["lead_type"], lead["lead_type"]),
        "stage": lead["stage"],
        "stage_label": STAGE_LABELS.get(lead["stage"], lead["stage"]),
        "location": location,
        "score": lead["lead_score"],
        "confidence": lead["confidence"],
        "verification": lead["verification"],
        "discovered": (lead["date_discovered"] or "")[:10],
        "signal_date": (lead["signal_date"] or "")[:10],
        "signal": lead["signal"],
        "why": lead["why_it_matters"],
        "next_action": lead["next_action"],
        "source": lead["source"],
        "source_url": lead["source_url"],
        "timeframe": notes.get("timeframe") or "",
        "budget": notes.get("budget_hint") or "",
        "property_info": info,
        "score_breakdown": {
            k: {"points": v["points"], "max": v["max"], "rationale": v["rationale"]}
            for k, v in breakdown.items()
        },
    }
