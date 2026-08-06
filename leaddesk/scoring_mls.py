"""Deterministic scoring for MLS-licensed expired/withdrawn listings.

No AI calls — an expired listing is direct, confirmed proof someone recently
tried to sell and didn't. That's stronger evidence than any inferred pattern,
so unlike the public-records source, a strong match here can reach
HIGH_PRIORITY. Still zero-cost: pure arithmetic over structured fields.
"""

from datetime import datetime, timezone

from . import config


def _days_since(value) -> float | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(str(value).strip(), fmt).replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        except ValueError:
            continue
    return None


def _to_number(value) -> float | None:
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def score_expired_listing(row: dict) -> dict:
    off_days = _days_since(row.get("off_market_date"))
    orig = _to_number(row.get("original_list_price"))
    final = _to_number(row.get("list_price"))
    dom = _to_number(row.get("dom"))

    pts_recency, recency_note = 0, "off-market date unknown"
    if off_days is not None:
        if off_days <= 7:
            pts_recency = 40
        elif off_days <= 30:
            pts_recency = 30
        elif off_days <= 90:
            pts_recency = 15
        else:
            pts_recency = 5
        recency_note = f"came off market about {off_days:.0f} days ago"

    pts_drop, drop_note = 0, "no price-change history available"
    if orig and final and orig > final:
        pct = (orig - final) / orig * 100
        pts_drop = min(30, round(pct * 2))
        drop_note = f"price was reduced {pct:.0f}% (${orig:,.0f} → ${final:,.0f}) before coming off market"
    elif orig and final:
        drop_note = "no price reduction on record"

    pts_dom, dom_note = 0, "days on market unknown"
    if dom is not None:
        pts_dom = min(20, int(dom // 10))
        dom_note = f"was on the market {dom:.0f} days"

    pts_value, value_note = 0, "list price unknown"
    price = final or orig
    if price:
        if price >= 600_000:
            pts_value = 10
        elif price >= 400_000:
            pts_value = 8
        elif price >= 250_000:
            pts_value = 6
        else:
            pts_value = 4
        value_note = f"listed around ${price:,.0f}"

    total = min(100, pts_recency + pts_drop + pts_dom + pts_value)

    breakdown = {
        "recency": {"points": pts_recency, "max": 40, "rationale": recency_note},
        "price_history": {"points": pts_drop, "max": 30, "rationale": drop_note},
        "days_on_market": {"points": pts_dom, "max": 20, "rationale": dom_note},
        "value": {"points": pts_value, "max": 10, "rationale": value_note},
    }
    return {"total": total, "breakdown": breakdown, "off_days": off_days}


def gate(total: int) -> tuple[str, str | None]:
    if total < config.MLS_QUALIFY_THRESHOLD:
        return "REJECTED", f"score {total} below threshold {config.MLS_QUALIFY_THRESHOLD}"
    if total >= config.MLS_HIGH_PRIORITY_THRESHOLD:
        return "HIGH_PRIORITY", None
    return "QUALIFIED", None
