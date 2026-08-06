"""Central configuration. Everything tunable lives here or in environment variables."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.environ.get("LEADDESK_DB", REPO_ROOT / "leaddesk.db"))
BRIEFS_DIR = REPO_ROOT / "briefs"
DOCS_DIR = REPO_ROOT / "docs"
SITE_DATA_DIR = DOCS_DIR / "data"

# --- Models -----------------------------------------------------------------
# Two-tier design: a cheap model throws away the noise, a strong model does the
# judgment that determines lead quality. Both are config knobs.
TRIAGE_MODEL = os.environ.get("LEADDESK_TRIAGE_MODEL", "claude-haiku-4-5")
REASONING_MODEL = os.environ.get("LEADDESK_REASONING_MODEL", "claude-opus-5")

# $ per 1M tokens (input, output) — used for the cost ledger.
MODEL_PRICES = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# --- Budget governor ----------------------------------------------------------
DAILY_BUDGET_USD = float(os.environ.get("LEADDESK_DAILY_BUDGET", "5.00"))

# --- Pipeline thresholds ------------------------------------------------------
QUALIFY_THRESHOLD = 60          # below this a lead is rejected (with reason)
HIGH_PRIORITY_THRESHOLD = 80
MAX_SIGNAL_AGE_DAYS = 30        # intent leads older than this are auto-rejected as stale
MAX_QUALIFY_PER_RUN = 10        # cap expensive qualifier calls per run

# --- Sources ------------------------------------------------------------------
# Reddit: public JSON endpoints, low volume, descriptive User-Agent.
# For sustained use, register a script app at reddit.com/prefs/apps and set
# REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET to use the official OAuth API instead.
REDDIT_SUBREDDITS = [
    "raleigh",
    "triangle",
    "Cary",
    "bullcity",       # Durham
    "chapelhill",
    "NorthCarolina",
]
REDDIT_LIMIT_PER_SUB = 40
REDDIT_USER_AGENT = os.environ.get(
    "LEADDESK_USER_AGENT",
    "leaddesk/0.1 (personal real-estate lead research tool; low volume)",
)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
