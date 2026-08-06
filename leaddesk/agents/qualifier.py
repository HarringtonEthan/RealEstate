"""Qualifier — the gatekeeper.

Verification checks run in code (does the source URL still resolve?), then the
reasoning model judges intent strength, transaction likelihood, and evidence
quality with mandatory rationales. Code composes the final score (scoring.py),
applies gates, and writes the lead. The model can reject; it cannot inflate.
"""

import json

import httpx

from .. import config, db, geo, scoring
from . import llm

SYSTEM = """You are the lead qualifier for a real-estate lead research tool used by Diane
Harrington, a licensed REALTOR serving Raleigh / the Triangle, North Carolina. You
receive ONE public post that a first-pass filter flagged as possible real-estate
intent. Your job is to judge it honestly and conservatively.

Rules — non-negotiable:
- Judge ONLY what the author explicitly wrote. Never invent facts, dates, budgets,
  timeframes, or motivations that are not in the text.
- Never consider or infer any protected characteristic (race, color, religion, sex,
  disability, familial status, national origin, age, etc.).
- If the post is ambiguous, low-intent, secondhand, hypothetical, or not actually
  about the Raleigh/Triangle area, set qualified=false with a clear reject_reason.
- A rejected post is a GOOD outcome. This tool exists to deliver a few excellent
  leads, not many weak ones.

Scoring categories you judge (rationale required for each):
- intent_strength (0-30): 25-30 only for explicit, first-person, active intent with
  specifics ("we're moving to Cary in October and starting our home search").
  15-24 for clear but less specific intent. <=12 for exploratory questions.
- transaction_likelihood (0-15): >10 requires a stated timeframe of ~6 months or
  less, or equivalent concrete commitment (sold previous home, job start date, etc.).
- evidence_quality (0-10): how directly the quoted text supports the classification.

Also extract: a one-sentence factual summary of the signal (signal_summary), the
location mentioned (verbatim-ish), any stated timeframe and budget, why this matters
to Diane in one or two sentences, and a recommended next action. The next action for
forum leads should respect community norms — e.g. "review the thread; if Diane can
add genuine value, reply helpfully in-thread or wait for the author to ask for agent
recommendations" — never anything spammy.
Set confidence to how sure you are of your overall read: low / medium / high."""

SCHEMA = {
    "type": "object",
    "properties": {
        "qualified": {"type": "boolean"},
        "reject_reason": {"type": "string"},
        "lead_type": {
            "type": "string",
            "enum": ["buyer", "first_time_buyer", "move_up_buyer", "downsizer", "seller",
                     "relocation", "investor", "land", "fsbo", "other"],
        },
        "est_transaction": {"type": "string", "enum": ["buy", "sell", "both", "invest", "unknown"]},
        "signal_summary": {"type": "string"},
        "location_mentioned": {"type": "string"},
        "timeframe": {"type": "string"},
        "budget_hint": {"type": "string"},
        "intent_strength": {"type": "integer"},
        "intent_rationale": {"type": "string"},
        "transaction_likelihood": {"type": "integer"},
        "transaction_rationale": {"type": "string"},
        "evidence_quality": {"type": "integer"},
        "evidence_rationale": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "why_it_matters": {"type": "string"},
        "next_action": {"type": "string"},
    },
    "required": ["qualified", "reject_reason", "lead_type", "est_transaction",
                 "signal_summary", "location_mentioned", "timeframe", "budget_hint",
                 "intent_strength", "intent_rationale", "transaction_likelihood",
                 "transaction_rationale", "evidence_quality", "evidence_rationale",
                 "confidence", "why_it_matters", "next_action"],
    "additionalProperties": False,
}


def verify_url(url: str) -> str:
    """'verified' if the public source URL still resolves, else 'failed'."""
    if not url:
        return "failed"
    try:
        headers = {"User-Agent": config.REDDIT_USER_AGENT}
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        return "verified" if resp.status_code == 200 else "failed"
    except Exception:
        return "failed"


def qualify(conn, item: dict) -> dict | None:
    """Qualify one candidate. Writes the lead (qualified or rejected) and returns it."""
    verification = verify_url(item.get("url", ""))

    judged = llm.structured_call(
        conn,
        agent="qualifier",
        model=config.REASONING_MODEL,
        system=SYSTEM,
        user_content=(
            f"SOURCE: {item['source']}\nURL: {item.get('url','')}\n"
            f"POSTED: {item.get('signal_date','unknown')}\n"
            f"AUTHOR (public handle): {item.get('author','unknown')}\n"
            f"URL VERIFICATION: {verification}\n\n"
            f"TITLE: {item['title']}\n\nBODY:\n{item['body'][:3000]}"
        ),
        schema=SCHEMA,
        max_tokens=16000,
    )
    if judged is None:
        return None

    area = geo.match_area(f"{item['title']} {item['body']} {judged.get('location_mentioned','')}")
    geo_tier = area[2] if area else None

    score = scoring.compose_score(
        judged,
        signal_date=item.get("signal_date"),
        geo_tier=geo_tier,
        budget_hint=judged.get("budget_hint") or None,
        verification=verification,
    )

    if not judged["qualified"]:
        stage, reason = "REJECTED", judged.get("reject_reason") or "model rejected"
    else:
        stage, reason = scoring.gate(score, item.get("signal_date"))

    lead = {
        "lead_type": judged["lead_type"],
        "subject_kind": "person",
        "display_name": item.get("author"),
        "city": area[0] if area else (judged.get("location_mentioned") or None),
        "county": area[1] if area else None,
        "geo_area": geo_tier,
        "source": item["source"],
        "source_url": item.get("url"),
        "signal": judged["signal_summary"],
        "signal_date": item.get("signal_date"),
        "date_discovered": db.now_iso(),
        "est_transaction": judged["est_transaction"],
        "research_notes": json.dumps({
            "timeframe": judged.get("timeframe"),
            "budget_hint": judged.get("budget_hint"),
            "triage_reason": item.get("triage_reason"),
            "quoted_title": item.get("title"),
        }),
        "why_it_matters": judged["why_it_matters"],
        "next_action": judged["next_action"],
        "lead_score": score["total"],
        "score_breakdown": json.dumps(score["breakdown"]),
        "confidence": score["confidence"],
        "verification": verification,
        "stage": stage,
        "rejection_reason": reason,
        "dedup_key": item.get("url") or item.get("item_key"),
    }
    if db.insert_lead(conn, lead):
        db.log_event(conn, "lead_scored", agent="qualifier", lead_id=lead["lead_id"],
                     detail={"score": score["total"], "stage": stage})
        db.log_lead_event(conn, lead["lead_id"], "qualifier", "scored",
                          {"score": score["total"], "stage": stage, "reason": reason})
    return lead
