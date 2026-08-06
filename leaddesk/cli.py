"""Command-line interface.

  python -m leaddesk init-db        create the local database
  python -m leaddesk run-once       full pipeline: sources -> score -> brief -> site
  python -m leaddesk brief          regenerate today's brief from the database
  python -m leaddesk export-site    regenerate the website data from the database
  python -m leaddesk status         pipeline counts and spend

Active sources are controlled by config.ENABLE_REDDIT_SOURCE /
ENABLE_RECORDS_SOURCE / ENABLE_MLS_SOURCE.
"""

import argparse
import sys
from datetime import datetime, timezone

from . import brief as brief_mod
from . import config, db, export_site
from .agents import flip_scanner, listing_scout, qualifier, triage
from .sources import reddit

_LOG_LINES = []


def log(msg: str = ""):
    """Print AND remember, so run-once can leave a durable, git-committable
    record of exactly what happened — readable without downloading Action
    logs (see docs/data/last_run.txt after any run)."""
    print(msg)
    _LOG_LINES.append(msg)


def cmd_init_db(_args):
    conn = db.connect()
    conn.close()
    config.MLS_IMPORT_DIR.mkdir(exist_ok=True)
    print(f"Database ready at {config.DB_PATH}")
    print(f"MLS import folder ready at {config.MLS_IMPORT_DIR} — drop your MLS export CSVs there")


def cmd_run_once(_args):
    conn = db.connect()
    db.log_event(conn, "run_started", agent="orchestrator")
    qualified = 0
    step_n, total_steps = 1, sum([config.ENABLE_REDDIT_SOURCE, config.ENABLE_RECORDS_SOURCE,
                                  config.ENABLE_MLS_SOURCE]) + 2

    log(f"Run started {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    if config.ENABLE_REDDIT_SOURCE:
        if not config.ANTHROPIC_API_KEY:
            log("ERROR: ANTHROPIC_API_KEY is not set (required for the Reddit intent source).")
            _write_run_log()
            sys.exit(1)
        log(f"[{step_n}/{total_steps}] Fetching public posts (Reddit)…")
        items = reddit.fetch_new_posts()
        errors = [i["_error"] for i in items if "_error" in i]
        items = [i for i in items if "_error" not in i]
        for e in errors:
            log(f"      warning: {e}")
        fresh = [i for i in items if db.mark_seen(conn, i["item_key"])] if items else []
        log(f"      {len(items)} posts pulled, {len(fresh)} not seen before")

        candidates = triage.triage(conn, fresh)
        log(f"      triage kept {len(candidates)}/{len(fresh)}")

        candidates = candidates[: config.MAX_QUALIFY_PER_RUN]
        for item in candidates:
            lead = qualifier.qualify(conn, item)
            if lead and lead["stage"] in ("QUALIFIED", "HIGH_PRIORITY"):
                qualified += 1
                log(f"      ✓ {lead['lead_type']} · {lead.get('city') or '?'} · score {lead['lead_score']}")
            elif lead:
                log(f"      ✗ rejected: {lead['rejection_reason']}")
        step_n += 1
    else:
        log("[skipped] Reddit source is off (config.ENABLE_REDDIT_SOURCE = False)")

    if config.ENABLE_RECORDS_SOURCE:
        log(f"[{step_n}/{total_steps}] Scanning Wake County / Raleigh public records "
            f"(free — no AI calls)…")
        try:
            flip_leads, flip_warnings = flip_scanner.scan(conn)
            for w in flip_warnings:
                log(f"      warning: {w}")
            found = sum(1 for l in flip_leads if l["stage"] in ("QUALIFIED", "RESEARCHING"))
            qualified += sum(1 for l in flip_leads if l["stage"] == "QUALIFIED")
            log(f"      {found} property signal(s) found")
        except Exception as exc:
            log(f"      warning: records scan failed ({exc}); continuing without it")
            db.log_event(conn, "agent_error", agent="flip_scanner", detail={"error": str(exc)})
        step_n += 1

    if config.ENABLE_MLS_SOURCE:
        log(f"[{step_n}/{total_steps}] Reading your MLS export (free — no AI calls)…")
        try:
            mls_leads, mls_warnings = listing_scout.scan(conn)
            for w in mls_warnings:
                log(f"      warning: {w}")
            found = sum(1 for l in mls_leads if l["stage"] in ("QUALIFIED", "HIGH_PRIORITY"))
            qualified += found
            log(f"      {found} expired/withdrawn listing lead(s) found")
        except Exception as exc:
            log(f"      warning: MLS import failed ({exc}); continuing without it")
            db.log_event(conn, "agent_error", agent="listing_scout", detail={"error": str(exc)})
        step_n += 1

    log(f"[{step_n}/{total_steps}] Writing daily brief…")
    path = brief_mod.generate(conn)
    log(f"      {path}")
    step_n += 1

    log(f"[{step_n}/{total_steps}] Exporting website data…")
    site = export_site.export(conn)
    log(f"      {site}")

    spend = db.spend_today(conn)
    log(f"\nDone. {qualified} qualified/high-priority lead(s) today · spend ${spend:.2f}"
        + (f" · ${spend / qualified:.2f}/qualified lead" if qualified else ""))
    db.log_event(conn, "run_finished", agent="orchestrator",
                 detail={"qualified": qualified, "spend_usd": round(spend, 4)})
    _write_run_log()


def _write_run_log():
    config.SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.SITE_DATA_DIR / "last_run.txt").write_text(
        "\n".join(_LOG_LINES) + "\n", encoding="utf-8"
    )


def cmd_brief(_args):
    conn = db.connect()
    print(brief_mod.generate(conn))


def cmd_export_site(_args):
    conn = db.connect()
    print(export_site.export(conn))


def cmd_status(_args):
    conn = db.connect()
    print("Pipeline:")
    for row in conn.execute("SELECT stage, COUNT(*) c FROM leads GROUP BY stage ORDER BY c DESC"):
        print(f"  {row['stage']:<15} {row['c']}")
    mls_count = conn.execute("SELECT COUNT(*) c FROM leads WHERE mls_licensed=1").fetchone()["c"]
    if mls_count and not config.PUBLISH_MLS_LEADS_TO_SITE:
        print(f"\n{mls_count} MLS-licensed lead(s) — visible here and in briefs/, "
              f"held back from the public website (config.PUBLISH_MLS_LEADS_TO_SITE=False)")
    print(f"\nSpend today: ${db.spend_today(conn):.2f} (budget ${config.DAILY_BUDGET_USD:.2f})")


def main():
    parser = argparse.ArgumentParser(prog="leaddesk", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in [("init-db", cmd_init_db), ("run-once", cmd_run_once),
                     ("brief", cmd_brief), ("export-site", cmd_export_site),
                     ("status", cmd_status)]:
        sub.add_parser(name).set_defaults(func=fn)
    args = parser.parse_args()
    args.func(args)
