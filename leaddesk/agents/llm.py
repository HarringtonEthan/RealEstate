"""Shared Claude client helpers: structured-output calls with cost recording."""

import json
import time

import anthropic

from .. import config, db

_client = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def structured_call(conn, *, agent: str, model: str, system: str, user_content: str,
                    schema: dict, max_tokens: int = 8000) -> dict | None:
    """One structured-output call. Records tokens/cost in the task ledger.

    Returns the parsed JSON object, or None on refusal/error (logged, never raised
    to the pipeline — a failed call must not kill the run).
    """
    if db.spend_today(conn) >= config.DAILY_BUDGET_USD:
        db.log_event(conn, "budget_exceeded", agent=agent,
                     detail={"budget": config.DAILY_BUDGET_USD})
        return None

    start = time.monotonic()
    try:
        response = client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APIError as exc:
        db.record_task(conn, agent, model, 0, 0,
                       int((time.monotonic() - start) * 1000), error=str(exc))
        db.log_event(conn, "agent_error", agent=agent, detail={"error": str(exc)})
        return None

    runtime_ms = int((time.monotonic() - start) * 1000)
    cost = db.record_task(conn, agent, model,
                          response.usage.input_tokens, response.usage.output_tokens,
                          runtime_ms)
    db.log_event(conn, "agent_call", agent=agent,
                 detail={"model": model, "cost_usd": round(cost, 4), "runtime_ms": runtime_ms})

    if response.stop_reason == "refusal":
        db.log_event(conn, "agent_refusal", agent=agent)
        return None

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        db.log_event(conn, "agent_parse_error", agent=agent)
        return None
