"""Intent Scout, stage 1 — cheap triage.

A fast model reads a batch of public posts and keeps only those containing
EXPLICIT first-person real-estate intent relevant to the Raleigh/Triangle
market. Everything else is discarded. It is instructed to reject aggressively:
a false negative costs us one maybe-lead; a false positive costs an expensive
qualifier call.
"""

from .. import config
from . import llm

SYSTEM = """You are the first-pass filter for a real-estate lead research tool used by a
licensed REALTOR in Raleigh, North Carolina. You read public forum posts and decide
which ones contain EXPLICIT, FIRST-PERSON real-estate intent relevant to the
Raleigh / Triangle NC market.

Keep a post ONLY if the author themselves clearly signals one of:
- buying a home (incl. first-time buyer questions, preapproval/mortgage questions tied to buying)
- selling their home, or seriously considering selling
- relocating to the Raleigh/Triangle area (or into NC) and will need housing
- looking for a real-estate agent
- investing in residential property in the area
- selling land or property they own

REJECT everything else, including: general market chatter, news links, rent-price
complaints without a purchase/sale intent, landlord/tenant disputes, people asking
about apartments to RENT with no ownership intent, jokes, surveys, posts about other
regions, and anything ambiguous. When in doubt, reject.

NEVER consider, infer, or record race, color, religion, sex, disability, familial
status, national origin, age, or any other protected characteristic. Judge only the
stated intent, location, and timing.

Return a decision for EVERY item you are given, in the same order, keyed by its id."""

SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "is_candidate": {"type": "boolean"},
                    "intent_type": {
                        "type": "string",
                        "enum": ["buyer", "seller", "relocation", "first_time_buyer",
                                 "investor", "agent_search", "land", "none"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["id", "is_candidate", "intent_type", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["decisions"],
    "additionalProperties": False,
}

BATCH_SIZE = 25


def triage(conn, items: list[dict]) -> list[dict]:
    """Return the subset of items judged to be candidates, annotated with intent_type."""
    candidates = []
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        lines = []
        for item in batch:
            lines.append(
                f"<post id=\"{item['item_key']}\" source=\"{item['source']}\">\n"
                f"TITLE: {item['title']}\nBODY: {item['body'][:1500]}\n</post>"
            )
        result = llm.structured_call(
            conn,
            agent="triage",
            model=config.TRIAGE_MODEL,
            system=SYSTEM,
            user_content="\n\n".join(lines),
            schema=SCHEMA,
            max_tokens=4000,
        )
        if not result:
            continue
        by_id = {d["id"]: d for d in result.get("decisions", [])}
        for item in batch:
            decision = by_id.get(item["item_key"])
            if decision and decision["is_candidate"]:
                item["intent_type"] = decision["intent_type"]
                item["triage_reason"] = decision["reason"]
                candidates.append(item)
    return candidates
