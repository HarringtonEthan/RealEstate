"""Listing Scout — turns Diane's MLS export into scored leads.

Reads whatever CSV files she's dropped in the import folder (never touches
her MLS login), finds expired/withdrawn listings, and scores them
deterministically. mls_licensed=1 on every lead this produces, which keeps
it out of the public website export unless config.PUBLISH_MLS_LEADS_TO_SITE
is explicitly turned on.
"""

import json

from .. import config, db, geo, scoring_mls
from ..sources import mls_import


def scan(conn) -> tuple[list[dict], list[str]]:
    rows, warnings = mls_import.find_expired_withdrawn()
    for w in warnings:
        db.log_event(conn, "source_warning", agent="listing_scout", detail={"warning": w})

    leads = []
    for row in rows:
        address = (row.get("address") or "").strip()
        if not address:
            continue
        dedup_key = f"mls:{row.get('mls_number') or address}"

        result = scoring_mls.score_expired_listing(row)
        stage, reason = scoring_mls.gate(result["total"])
        if result["off_days"] is not None and result["off_days"] > config.MLS_EXPIRED_MAX_AGE_DAYS:
            stage, reason = "REJECTED", f"came off market {result['off_days']:.0f} days ago — too stale"

        area = geo.match_area(f"{row.get('city') or ''} {address}")
        geo_tier = area[2] if area else None

        status = (row.get("status") or "").strip().title()
        price = row.get("list_price") or row.get("original_list_price")
        price_txt = f"${price}" if price else "an unlisted price"
        signal = (
            f"{status} MLS listing at {address}, last listed at {price_txt}. "
            f"{result['breakdown']['price_history']['rationale']}."
        )
        why = (
            "This owner tried to sell recently and didn't succeed with their previous agent — "
            "they may still want to sell and don't currently have representation. Expired and "
            "withdrawn listings are one of the highest-converting seller opportunities when "
            "approached respectfully."
        )
        next_action = (
            "Pull the full listing history and prepare a fresh pricing/marketing analysis "
            "before any contact. Follow MLS and NCREC rules for reaching out to "
            "expired/withdrawn listing owners (and your MLS's specific waiting-period rules, "
            "if any)."
        )

        lead = {
            "lead_type": "expired" if "expired" in status.lower() else "withdrawn",
            "subject_kind": "property",
            "display_name": row.get("list_agent"),
            "property_address": address,
            "city": (area[0] if area else row.get("city")),
            "county": "Wake",
            "geo_area": geo_tier,
            "source": "Diane's MLS export (licensed data)",
            "source_url": None,
            "mls_licensed": 1,
            "signal": signal,
            "signal_date": row.get("off_market_date"),
            "date_discovered": db.now_iso(),
            "est_transaction": "sell",
            "property_info": json.dumps({
                "beds": row.get("beds"), "baths": row.get("baths"), "sqft": row.get("sqft"),
                "year_built": row.get("year_built"),
                "list_price": row.get("list_price"),
                "original_list_price": row.get("original_list_price"),
                "dom": row.get("dom"),
            }),
            "research_notes": json.dumps({
                "mls_number": row.get("mls_number"),
                "list_agent": row.get("list_agent"),
                "list_office": row.get("list_office"),
                "list_date": row.get("list_date"),
                "source_file": row.get("_source_file"),
            }),
            "why_it_matters": why,
            "next_action": next_action,
            "lead_score": result["total"],
            "score_breakdown": json.dumps(result["breakdown"]),
            "confidence": "high",
            "verification": "verified",
            "stage": stage,
            "rejection_reason": reason,
            "dedup_key": dedup_key,
        }
        if db.insert_lead(conn, lead):
            db.log_event(conn, "lead_scored", agent="listing_scout", lead_id=lead["lead_id"],
                         detail={"score": result["total"], "stage": stage})
            leads.append(lead)
    return leads, warnings
