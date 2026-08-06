"""Renovation / Flip Watch — public-records pattern scanner.

Cross-references City of Raleigh building permits with Wake County tax
records to find properties that just had a real, substantial renovation
where the owner's mailing address doesn't match the property — a classic
signal for an investor flip or rental turnover that may be about to list.

Fully deterministic (see scoring_records.py) — no AI calls, so this source
costs nothing to run. Every result is explicitly a research candidate: it
tells Diane where to look, never that a sale is confirmed.
"""

import json

from .. import db, geo, scoring_records
from ..sources import wake_records


def scan(conn) -> list[dict]:
    candidates = wake_records.find_renovation_candidates()
    errors = [c["_error"] for c in candidates if "_error" in c]
    candidates = [c for c in candidates if "_error" not in c]
    for e in errors:
        db.log_event(conn, "source_error", agent="flip_scanner", detail={"error": e})

    leads = []
    for cand in candidates:
        dedup_key = f"wake_permit:{cand.get('pin')}:{cand.get('permit_number')}"
        result = scoring_records.score_renovation_candidate(cand)
        stage, reason = scoring_records.gate(result["total"])

        area = geo.match_area(cand.get("situs_city") or cand.get("situs_address") or "")
        geo_tier = area[2] if area else None

        desc = (cand.get("description") or cand.get("permit_type") or "renovation").strip()
        val = result["valuation"]
        val_txt = f"${val:,.0f}" if val else "an unlisted value"
        owner_note = (
            "the owner's mailing address is different from the property, suggesting an "
            "investor or rental owner" if result["absentee"] else
            "county records show the owner's mailing address matches the property"
        )
        signal = (
            f"Wake County permit records show a {desc} permit ({val_txt}) closed at this "
            f"property; {owner_note}."
        )
        why = (
            "A real, recent renovation on a home the owner doesn't appear to live in is a "
            "classic pattern that precedes a sale or a rental turnover — worth a look before "
            "it's listed." if result["absentee"] else
            "A homeowner who just completed a substantial renovation sometimes lists soon "
            "after, even though this owner appears to live in the home."
        )
        next_action = (
            "Check whether this address is already listed or recently sold. If not, this is "
            "a candidate to bring to a buyer client (a freshly renovated home that may hit the "
            "market soon) or an owner worth reaching out to about future listing "
            "representation. This is a pattern from public records, not a confirmed intent to "
            "sell — verify independently before acting on it."
        )

        lead = {
            "lead_type": "renovation_watch",
            "subject_kind": "property",
            "display_name": None,
            "property_address": cand.get("situs_address"),
            "city": (area[0] if area else cand.get("situs_city")),
            "county": "Wake",
            "geo_area": geo_tier,
            "source": "Wake County / Raleigh public permit & tax records",
            "source_url": None,
            "signal": signal,
            "signal_date": cand.get("final_date") or cand.get("issue_date"),
            "date_discovered": db.now_iso(),
            "est_transaction": "both",
            "property_info": json.dumps({
                "permit_number": cand.get("permit_number"),
                "permit_type": cand.get("permit_type"),
                "permit_valuation": val,
                "year_built": cand.get("year_built"),
                "heated_area_sqft": cand.get("heated_area"),
                "assessed_value": cand.get("assessed_value"),
            }),
            "research_notes": json.dumps({
                "owner_of_record": cand.get("owner"),
                "mailing_address": cand.get("mail_address"),
                "absentee_owner": result["absentee"],
                "ownership_tenure_days": result["tenure_days"],
                "permit_days_ago": result["permit_days_ago"],
            }),
            "why_it_matters": why,
            "next_action": next_action,
            "lead_score": result["total"],
            "score_breakdown": json.dumps(result["breakdown"]),
            "confidence": "medium" if result["absentee"] else "low",
            "verification": "verified",  # the permit + tax records themselves are authoritative
            "stage": stage,
            "rejection_reason": reason,
            "dedup_key": dedup_key,
        }
        if db.insert_lead(conn, lead):
            db.log_event(conn, "lead_scored", agent="flip_scanner", lead_id=lead["lead_id"],
                         detail={"score": result["total"], "stage": stage})
            leads.append(lead)
    return leads
