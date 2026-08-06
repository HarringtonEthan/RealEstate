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

# --- Active sources ------------------------------------------------------------
# One place to see/toggle what actually runs. Reddit is off by default —
# focus is on MLS-licensed data and public property records.
ENABLE_REDDIT_SOURCE = os.environ.get("LEADDESK_ENABLE_REDDIT", "0") == "1"
ENABLE_RECORDS_SOURCE = os.environ.get("LEADDESK_ENABLE_RECORDS", "1") == "1"
ENABLE_MLS_SOURCE = os.environ.get("LEADDESK_ENABLE_MLS", "1") == "1"

# --- Sources ------------------------------------------------------------------
# Reddit locked down its public www.reddit.com/*.json endpoints (2023+) — they
# now 403 almost all automated requests regardless of User-Agent. The
# sanctioned, free fix is a read-only OAuth "script" app: register one at
# https://www.reddit.com/prefs/apps (free, no login required by the tool
# itself) and set these two env vars. Without them, the adapter falls back to
# the public endpoint, which is likely to keep getting blocked.
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

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

# --- Public records: renovation / flip watch (Wake County + City of Raleigh) --
# Zero AI cost by design — permit and tax records are structured data, so
# matching and scoring are pure arithmetic (see scoring_records.py).
#
# Field names below are CONFIRMED against the live schema via
# scripts/probe_records.py (run 2026-08-06) — not guesses. The Raleigh permits
# feed conveniently already includes the owner-of-record's mailing address on
# every permit row (parcelownername / parcelowneraddress1-2), so the
# absentee-owner signal needs no separate join. The Wake County parcels layer
# is queried afterward, by exact PIN, purely to enrich with year built /
# heated sqft / assessed value / deed date — if that lookup fails for a given
# PIN the candidate still stands, just without those extras.
WAKE_PARCELS_URL = os.environ.get(
    "LEADDESK_WAKE_PARCELS_URL",
    "https://maps.wakegov.com/arcgis/rest/services/Property/Parcels/FeatureServer/0",
)
RALEIGH_PERMITS_URL = os.environ.get(
    "LEADDESK_RALEIGH_PERMITS_URL",
    "https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/"
    "Building_Permits_Issued_Past_180_Days/FeatureServer/0",
)

WAKE_PARCEL_FIELDS = {
    "pin": "PIN_NUM",
    "deed_date": "DEED_DATE",
    "assessed_value": "TOTAL_VALUE_ASSD",
    "year_built": "YEAR_BUILT",
    "heated_area": "HEATEDAREA",
}
RALEIGH_PERMIT_FIELDS = {
    "pin": "pin",
    "permit_number": "permitnum",
    "permit_type": "permittype",
    "description": "description",
    "status": "statuscurrentmapped",
    "issue_date": "issueddate",
    "valuation": "estprojectcost",
    "situs_address": "originaladdress1",
    "situs_city": "originalcity",
    "owner": "parcelownername",
    "mail_address": "parcelowneraddress1",
    "mail_address2": "parcelowneraddress2",
}

RENOVATION_KEYWORDS = [
    "kitchen", "bath", "remodel", "renovation", "renovate", "addition",
    "roof", "structural", "rehab", "gut", "interior alteration", "repair",
    "deck", "porch", "basement", "flooring",
]
# Filters out permit categories the absentee-owner+valuation score would
# otherwise mistake for a "homeowner about to sell" signal: apartment
# complexes, commercial/institutional renovations, and other multifamily
# work aren't a single-family buy/sell lead no matter how it scores.
RENOVATION_EXCLUDE_KEYWORDS = [
    "apartment", "complex", "affordable housing", "clubhouse", "leasing office",
    "parking deck", "hotel", "dormitory", "church", "school",
]
RENOVATION_LOOKBACK_DAYS = 180      # matches the Raleigh feed's own window
RENOVATION_MIN_VALUE = 10000        # ignore trivial permits (fences, water heaters)
RENOVATION_QUALIFY_THRESHOLD = 55  # below this, not worth Diane's time

# --- MLS-licensed data: expired / withdrawn listings ---------------------------
# Diane exports these herself from her MLS (Matrix) — the tool never logs in
# and never touches her MLS credentials. Drop exported CSV files in
# MLS_IMPORT_DIR; see mls_export_template.csv at the repo root for the
# expected shape (column names are matched flexibly — see mls_import.py).
# Zero AI cost: scoring is arithmetic (scoring_mls.py), same as records.
MLS_IMPORT_DIR = REPO_ROOT / "mls_exports"
MLS_EXPIRED_MAX_AGE_DAYS = 180     # ignore listings that came off market longer ago than this
MLS_QUALIFY_THRESHOLD = 55
MLS_HIGH_PRIORITY_THRESHOLD = 80

# MLS-derived leads are held back from the public website by default until
# Diane confirms with Triangle MLS / her broker-in-charge that showing
# summarized derived info (not raw MLS data) on her own unauthenticated site
# is fine under her data license. Until then they appear in the local
# Markdown brief and `leaddesk status` only. Flip to True once confirmed.
PUBLISH_MLS_LEADS_TO_SITE = os.environ.get("LEADDESK_PUBLISH_MLS", "0") == "1"
