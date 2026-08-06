"""Command-line interface.

  python -m leaddesk init-db        create the local database
  python -m leaddesk run-once       full pipeline: fetch -> triage -> qualify -> brief -> site
  python -m leaddesk brief          regenerate today's brief from the database
  python -m leaddesk export-site    regenerate the website data from the database
  python -m leaddesk status         pipeline counts and spend
"""

import argparse
import sys

from . import brief as brief_mod
from . import config, db, export_site
from .agents import qualifier, triage
from .sources import reddit


def cmd_init_db(_args):
    conn = db.connect()
    conn.close()
    print(f"Database ready at {config.DB_PATH}")


def cmd_run_once(_args):
    if not config.ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY is not set. Add it to your environment or .env.")
        sys.exit(1)
    conn = db.connect()
    db.log_event(conn, "run_started", agent="orchestrator")

    print("[1/5] Fetching public posts (Reddit)…")
    items = reddit.fetch_new_posts()
    errors = [i["_error"] for i in items if "_error" in i]
    items = [i for i in items if "_error" not in i]
    for e in errors:
        print(f"      warning: {e}")
    if not items and errors:
        print("ERROR: no posts could be fetched from any source (network blocked or Reddit "
              "unavailable). Leaving the website data untouched.")
        sys.exit(2)
    fresh = [i for i in items if db.mark_seen(conn, i["item_key"])]
    print(f"      {len(items)} posts pulled, {len(fresh)} not seen before")

    print("[2/5] Triage (fast model)…")
    candidates = triage.triage(conn, fresh)
    print(f"      {len(candidates)} candidate(s) kept, {len(fresh) - len(candidates)} rejected")

    candidates = candidates[: config.MAX_QUALIFY_PER_RUN]
    print(f"[3/5] Qualifying {len(candidates)} candidate(s) (reasoning model)…")
    qualified = 0
    for item in candidates:
        lead = qualifier.qualify(conn, item)
        if lead and lead["stage"] in ("QUALIFIED", "HIGH_PRIORITY"):
            qualified += 1
            print(f"      ✓ {lead['lead_type']} · {lead.get('city') or '?'} · score {lead['lead_score']}")
        elif lead:
            print(f"      ✗ rejected: {lead['rejection_reason']}")

    print("[4/5] Writing daily brief…")
    path = brief_mod.generate(conn)
    print(f"      {path}")

    print("[5/5] Exporting website data…")
    site = export_site.export(conn)
    print(f"      {site}")

    spend = db.spend_today(conn)
    print(f"\nDone. {qualified} qualified lead(s) today · spend ${spend:.2f}"
          + (f" · ${spend / qualified:.2f}/qualified lead" if qualified else ""))
    db.log_event(conn, "run_finished", agent="orchestrator",
                 detail={"qualified": qualified, "spend_usd": round(spend, 4)})


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
    print(f"Spend today: ${db.spend_today(conn):.2f} (budget ${config.DAILY_BUDGET_USD:.2f})")


def main():
    parser = argparse.ArgumentParser(prog="leaddesk", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in [("init-db", cmd_init_db), ("run-once", cmd_run_once),
                     ("brief", cmd_brief), ("export-site", cmd_export_site),
                     ("status", cmd_status)]:
        sub.add_parser(name).set_defaults(func=fn)
    args = parser.parse_args()
    args.func(args)
