"""SQLite storage: leads, history, task/cost ledger, event feed."""

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  lead_id            TEXT PRIMARY KEY,
  lead_type          TEXT NOT NULL,
  subject_kind       TEXT NOT NULL DEFAULT 'person',
  display_name       TEXT,
  property_address   TEXT,
  city               TEXT,
  state              TEXT DEFAULT 'NC',
  zip                TEXT,
  county             TEXT,
  geo_area           TEXT,
  source             TEXT NOT NULL,
  source_url         TEXT,
  mls_licensed       INTEGER DEFAULT 0,
  signal             TEXT NOT NULL,
  signal_date        TEXT,
  date_discovered    TEXT NOT NULL,
  est_transaction    TEXT,
  property_info      TEXT,
  research_notes     TEXT,
  why_it_matters     TEXT,
  next_action        TEXT,
  lead_score         INTEGER,
  score_breakdown    TEXT,
  confidence         TEXT,
  verification       TEXT DEFAULT 'unverified',
  stage              TEXT DEFAULT 'NEW',
  rejection_reason   TEXT,
  compliance_flags   TEXT,
  dedup_key          TEXT UNIQUE,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  event_type TEXT NOT NULL,
  detail TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  agent TEXT NOT NULL,
  status TEXT DEFAULT 'done',
  model TEXT,
  input_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0,
  cost_usd REAL DEFAULT 0,
  runtime_ms INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  error TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  agent TEXT,
  lead_id TEXT,
  event_type TEXT NOT NULL,
  detail TEXT
);

CREATE TABLE IF NOT EXISTS seen_items (
  item_key TEXT PRIMARY KEY,      -- e.g. reddit post fullname; prevents re-triaging
  first_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  rating TEXT NOT NULL,
  reason TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str = "lead") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def log_event(conn, event_type: str, agent: str = None, lead_id: str = None, detail: dict = None):
    conn.execute(
        "INSERT INTO events (ts, agent, lead_id, event_type, detail) VALUES (?,?,?,?,?)",
        (now_iso(), agent, lead_id, event_type, json.dumps(detail or {})),
    )
    conn.commit()


def log_lead_event(conn, lead_id: str, actor: str, event_type: str, detail: dict = None):
    conn.execute(
        "INSERT INTO lead_events (lead_id, ts, actor, event_type, detail) VALUES (?,?,?,?,?)",
        (lead_id, now_iso(), actor, event_type, json.dumps(detail or {})),
    )
    conn.commit()


def record_task(conn, agent: str, model: str, input_tokens: int, output_tokens: int,
                runtime_ms: int, error: str = None) -> float:
    """Record an LLM task and return its cost in USD."""
    prices = config.MODEL_PRICES.get(model, (0.0, 0.0))
    cost = input_tokens / 1e6 * prices[0] + output_tokens / 1e6 * prices[1]
    conn.execute(
        "INSERT INTO tasks (task_id, agent, status, model, input_tokens, output_tokens,"
        " cost_usd, runtime_ms, created_at, error) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (new_id("task"), agent, "failed" if error else "done", model,
         input_tokens, output_tokens, cost, runtime_ms, now_iso(), error),
    )
    conn.commit()
    return cost


def spend_today(conn) -> float:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM tasks WHERE created_at LIKE ?",
        (today + "%",),
    ).fetchone()
    return row["c"]


def mark_seen(conn, item_key: str) -> bool:
    """Returns True if the item is new (and marks it seen)."""
    try:
        conn.execute("INSERT INTO seen_items (item_key, first_seen) VALUES (?,?)",
                     (item_key, now_iso()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def insert_lead(conn, lead: dict) -> bool:
    """Insert a lead. Returns False if the dedup key already exists."""
    lead.setdefault("lead_id", new_id())
    lead.setdefault("created_at", now_iso())
    lead["updated_at"] = now_iso()
    cols = [k for k in lead.keys()]
    try:
        conn.execute(
            f"INSERT INTO leads ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [lead[c] for c in cols],
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def update_lead(conn, lead_id: str, **fields):
    fields["updated_at"] = now_iso()
    sets = ",".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE leads SET {sets} WHERE lead_id=?", [*fields.values(), lead_id])
    conn.commit()
