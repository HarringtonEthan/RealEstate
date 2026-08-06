"""Scoring rubric — arithmetic, caps, and gates enforced in code.

Claude judges intent strength, transaction likelihood, and evidence quality
(with mandatory rationales). Code computes recency, location, and value points,
applies caps and gates, and produces the final 0-100 score. A model can never
hand-wave a total.
"""

from datetime import datetime, timezone

from . import config, geo


def recency_points(signal_date_iso: str | None) -> int:
    """0-15, computed — not judged."""
    age = signal_age_days(signal_date_iso)
    if age is None:
        return 0
    if age <= 2:
        return 15
    if age <= 7:
        return 12
    if age <= 30:
        return 8
    if age <= 90:
        return 3
    return 0


def signal_age_days(signal_date_iso: str | None) -> float | None:
    if not signal_date_iso:
        return None
    try:
        dt = datetime.fromisoformat(signal_date_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def value_points(budget_hint: str | None) -> int:
    """0-10 from a stated price band; conservative default when unknown."""
    if not budget_hint:
        return 4
    digits = "".join(c for c in budget_hint if c.isdigit())
    if not digits:
        return 4
    amount = int(digits)
    if amount < 10000:            # e.g. "450" or "450k" written without zeros
        amount *= 1000
    if amount >= 900_000:
        return 10
    if amount >= 600_000:
        return 8
    if amount >= 400_000:
        return 6
    if amount >= 250_000:
        return 5
    return 3


def confidence_points(confidence: str, verification: str) -> int:
    """0-5; unverified leads are hard-capped at 2 regardless of model confidence."""
    base = {"high": 5, "medium": 3, "low": 1}.get(confidence, 1)
    if verification != "verified":
        base = min(base, 2)
    return base


def compose_score(judged: dict, signal_date: str | None, geo_tier: str | None,
                  budget_hint: str | None, verification: str) -> dict:
    """Combine judged + computed categories, apply caps/gates, return breakdown."""
    intent = _clamp(judged.get("intent_strength", 0), 0, 30)
    transaction = _clamp(judged.get("transaction_likelihood", 0), 0, 15)
    evidence = _clamp(judged.get("evidence_quality", 0), 0, 10)
    confidence = judged.get("confidence", "low")

    # Hard cap: evidence >6 requires a live, verified source URL.
    if verification != "verified":
        evidence = min(evidence, 6)

    recency = recency_points(signal_date)
    location = geo.location_points(geo_tier)
    value = value_points(budget_hint)
    conf_pts = confidence_points(confidence, verification)

    total = intent + recency + location + transaction + evidence + value + conf_pts

    # Gate: no verified source → total capped at 40.
    capped = False
    if verification != "verified" and total > 40:
        total, capped = 40, True

    breakdown = {
        "intent": {"points": intent, "max": 30, "rationale": judged.get("intent_rationale", "")},
        "recency": {"points": recency, "max": 15, "rationale": _recency_note(signal_date)},
        "location": {"points": location, "max": 15, "rationale": f"area tier: {geo_tier or 'outside service area'}"},
        "transaction": {"points": transaction, "max": 15, "rationale": judged.get("transaction_rationale", "")},
        "evidence": {"points": evidence, "max": 10, "rationale": judged.get("evidence_rationale", "")},
        "value": {"points": value, "max": 10, "rationale": f"budget hint: {budget_hint or 'unknown'}"},
        "confidence": {"points": conf_pts, "max": 5, "rationale": f"model confidence {confidence}; verification {verification}"},
    }
    return {
        "total": total,
        "capped_unverified": capped,
        "breakdown": breakdown,
        "confidence": confidence,
    }


def gate(score: dict, signal_date: str | None) -> tuple[str, str | None]:
    """Return (stage, rejection_reason)."""
    age = signal_age_days(signal_date)
    if age is not None and age > config.MAX_SIGNAL_AGE_DAYS:
        return "REJECTED", f"stale signal ({age:.0f} days old, limit {config.MAX_SIGNAL_AGE_DAYS})"
    total = score["total"]
    if total < config.QUALIFY_THRESHOLD:
        return "REJECTED", f"score {total} below threshold {config.QUALIFY_THRESHOLD}"
    if total >= config.HIGH_PRIORITY_THRESHOLD:
        return "HIGH_PRIORITY", None
    return "QUALIFIED", None


def _clamp(v, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


def _recency_note(signal_date: str | None) -> str:
    age = signal_age_days(signal_date)
    return f"signal is {age:.1f} days old" if age is not None else "signal date unknown"
