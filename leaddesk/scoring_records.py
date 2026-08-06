"""Deterministic scoring for public-records signals (renovation / flip watch).

No AI calls anywhere in this file. Permit and tax records are structured data
— a permit either is or isn't a kitchen remodel, a mailing address either does
or doesn't match the property address — so pattern-matching and scoring are
pure arithmetic. This is what makes the records source effectively free to run.
"""

from datetime import datetime, timezone

from . import config


def _days_since(value) -> float | None:
    """Accepts an ISO date string or an ArcGIS epoch-millis timestamp."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            dt = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError, OSError):
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def _to_number(value) -> float | None:
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def score_renovation_candidate(candidate: dict) -> dict:
    """Score one merged permit+parcel record. Returns total, breakdown, and facts."""
    mail = (candidate.get("mail_address") or "").strip().lower()
    situs = (candidate.get("situs_address") or "").strip().lower()
    absentee = bool(mail) and bool(situs) and mail != situs

    tenure_days = _days_since(candidate.get("deed_date"))
    permit_days_ago = _days_since(candidate.get("final_date") or candidate.get("issue_date"))
    valuation = _to_number(candidate.get("valuation"))

    pts_absentee = 35 if absentee else 0

    pts_tenure, tenure_note = 0, "ownership length unknown"
    if tenure_days is not None:
        if tenure_days <= 548:  # ~18 months — classic flip hold time
            pts_tenure = 25 if absentee else 15
            tenure_note = f"owned about {tenure_days / 30:.0f} months — a short hold"
        else:
            pts_tenure = 12 if absentee else 5
            tenure_note = f"owned about {tenure_days / 365:.1f} years"

    pts_recency, recency_note = 0, "permit date unknown"
    if permit_days_ago is not None:
        if permit_days_ago <= 30:
            pts_recency = 20
        elif permit_days_ago <= 60:
            pts_recency = 15
        elif permit_days_ago <= 90:
            pts_recency = 10
        else:
            pts_recency = 5
        recency_note = f"renovation permit closed about {permit_days_ago:.0f} days ago"

    pts_value, value_note = 0, "permit value unknown"
    if valuation:
        if valuation >= 75_000:
            pts_value = 20
        elif valuation >= 40_000:
            pts_value = 15
        elif valuation >= config.RENOVATION_MIN_VALUE:
            pts_value = 10
        else:
            pts_value = 5
        value_note = f"permit valued at ${valuation:,.0f}"

    total = min(100, pts_absentee + pts_tenure + pts_recency + pts_value)

    breakdown = {
        "absentee_owner": {
            "points": pts_absentee, "max": 35,
            "rationale": ("owner's mailing address differs from the property — "
                          "likely an investor or rental owner") if absentee else
                         "owner's mailing address matches the property — likely owner-occupied",
        },
        "ownership_tenure": {"points": pts_tenure, "max": 25, "rationale": tenure_note},
        "permit_recency": {"points": pts_recency, "max": 20, "rationale": recency_note},
        "permit_value": {"points": pts_value, "max": 20, "rationale": value_note},
    }
    return {
        "total": total, "breakdown": breakdown, "absentee": absentee,
        "tenure_days": tenure_days, "permit_days_ago": permit_days_ago, "valuation": valuation,
    }


def gate(total: int) -> tuple[str, str | None]:
    """Records patterns are inference, not stated intent — this source never
    reaches HIGH_PRIORITY; the strongest matches land at QUALIFIED, everything
    else below the threshold is a research candidate or rejected outright."""
    if total < config.RENOVATION_QUALIFY_THRESHOLD:
        return "REJECTED", f"pattern score {total} below threshold {config.RENOVATION_QUALIFY_THRESHOLD}"
    if total >= 80:
        return "QUALIFIED", None
    return "RESEARCHING", None
