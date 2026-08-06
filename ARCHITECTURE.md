# Diane's Lead Desk — System Architecture Proposal

**An AI-powered prospecting department for Diane Harrington, REALTOR®, Raleigh/Triangle NC**

> Status: PROPOSAL (v1) — for review before any code is written.
> Author: Claude (principal AI systems architect role), commissioned by Ethan Harrington.

---

## 1. What we're building

A locally-run application that continuously discovers, researches, verifies, scores, and organizes **a small number of high-quality, legitimate real-estate leads** for the Raleigh/Triangle market, and presents them to Diane in a daily brief and a simple dashboard. Nothing contacts anyone automatically — ever. Diane reviews, approves, and acts.

The honest framing: this is **not** "many LLM agents talking to each other." It is a **deterministic Python pipeline** (scheduling, deduplication, storage, state machine, cost accounting) that invokes **a small number of specialized Claude-powered agents** exactly where judgment over unstructured text is required: reading public posts for genuine intent, synthesizing research, scoring with a rationale, checking compliance edge cases, and writing the brief. That split is the single most important design decision — it is what keeps the system cheap, debuggable, and honest.

### Design principles

1. **Quality over quantity.** Agents are instructed and measured on *rejection rate*. A day with zero leads is a valid, reportable outcome. The system must never fabricate a lead, a source, a date, or a confidence level.
2. **Code for determinism, Claude for judgment.** Dedup, filtering, scheduling, math, parsing, CRM state → Python. Interpreting a Reddit post, weighing evidence, explaining a score → Claude.
3. **Legitimate sources only.** Public government records, official open-data APIs, platform APIs used within their terms, licensed data Diane already has (Triangle MLS), and first-party data. No scraping behind logins, no ToS violations, no private-group harvesting.
4. **Human in the loop.** DISCOVER → RESEARCH → VERIFY → SCORE → PRESENT → DIANE DECIDES. Outreach drafts (later versions) stay drafts until she approves each one.
5. **Fair Housing by construction.** No field in the data model, no prompt, and no score component may reference or infer protected characteristics. Geography is used only as market geography (city/ZIP/price band), never as a demographic proxy for targeting people.
6. **Built to be watched.** Every agent action is an event in an append-only event log, which powers both the future live dashboard and today's debugging.

---

## 2. The sub-agent roster (consolidated: 15 proposed → 6 LLM agents + a deterministic core)

Your 15-agent list is a good functional decomposition, but roughly half of those "agents" should not be LLM agents at all — they're database operations, scheduled jobs, or libraries. Making them LLM agents would add cost, latency, and nondeterminism with no benefit. Here's the consolidation and the reasoning:

| Your proposed agent | Disposition | Why |
|---|---|---|
| 1. Lead Orchestrator | **Python service, not an LLM** | Task assignment, dedup, status tracking, "don't re-research this" are bookkeeping. An LLM orchestrator would be slower, costlier, and less reliable than a scheduler + queue. (A tiny optional LLM "planning" call can prioritize the day's work later — v0.8.) |
| 2. Seller Signal | **Split** → Records Analyst (records-derived signals) + Intent Scout (public posts about selling) + Listing Scout (listing-derived signals) | "Seller signals" come from three totally different source types with different access methods. |
| 3. Buyer Intent | **Merged into Intent Scout** | Buyer intent, relocation intent, and community intent are the same job: monitor permitted public communities for explicit statements of intent. One agent, one source set, one classifier — with `intent_type` as an output field. |
| 4. Relocation | **Merged into Intent Scout** (individual signals) + **Market Analyst** (employer/macro relocation trends) | An individual saying "moving to Cary" is an intent lead; "Apple expanding RTP campus" is market intelligence that directs prospecting, not a lead. |
| 5. FSBO / Expired | **Listing Scout** (kept, scoped honestly — see §7 on what's actually accessible) | |
| 6. Property & Public Records | **Records Analyst** (kept — this is the highest-value free source in the system) | |
| 7. Market Intelligence | **Market Analyst** (kept, absorbs #8 and the analysis half of #9) | |
| 8. New Construction | **Merged into Market Analyst** | New construction tracking is market intelligence (permits, builder inventory) — same sources, same cadence. Individual buyer-rep opportunities it surfaces flow through the normal lead pipeline. |
| 9. Investor Opportunity | **Merged into Market Analyst** (screening) — investor *leads* are just leads with `lead_type=investor` | Cash-flow math and $/sqft comps are arithmetic (Python), not LLM work. |
| 10. Community Intent | **Merged into Intent Scout** | Same job as #3/#4. |
| 11. Lead Research | **Enrichment Agent** (kept) | |
| 12. Lead Scoring | **Merged with #13 into the Qualifier** | Verification and scoring are one pass over the same evidence. Scoring an unverified lead is wasted work; verifying without scoring leaves the judgment undone. The rubric arithmetic is enforced in code; Claude supplies the per-category judgment and the mandatory rationale. |
| 13. Duplicate / Verification | Dedup → **Python** (fuzzy address/URL/name matching is deterministic). Verification → **Qualifier** (URL liveness/recency checks in code, evidence assessment by Claude). | |
| 14. CRM / Pipeline | **Database + state machine, not an agent** | A lead's stage transition is a row update with an audit event. No LLM needed. |
| 15. Daily Briefing | **Briefing Agent** (kept) | |
| (Phase 9) Compliance | **Compliance Gate** (kept — deterministic rules first, Claude for edge cases) | |
| (Phase 12) Search Query Generator | **Library + data, not a standing agent** | Query templates live in config; effectiveness tracking is a table; the Intent Scout composes/adapts queries per run. A weekly "query review" job (v0.8) uses Claude to propose new queries from feedback — as reviewable config diffs, never self-modifying code. |
| (Phase 13) Geographic Intelligence | **Static knowledge layer (YAML/SQLite), not an agent** | Cities, ZIPs, counties, neighborhoods, adjacency, active developments — curated reference data that agents read. Updated by humans or by reviewed suggestions. |

### Final roster

**Deterministic core (Python, no LLM):**
- **Orchestrator** — APScheduler jobs, task queue, dedup engine, CRM state machine, budget governor (per-day token/cost caps, kills runaway jobs), event log writer.
- **Geo layer** — Triangle reference data (see §13 of your brief; file `data/geo.yaml`).
- **Query library** — parameterized search templates + per-query effectiveness stats.

**Claude-powered agents (each = a system prompt + tool set + structured output schema):**

1. **Intent Scout** — monitors permitted public communities (Reddit API first) for *explicit* buy/sell/relocate/invest intent in the Triangle. Input: batch of posts/comments from the source adapters. Output: candidate leads with quoted evidence, source URL, post date, intent classification — or (mostly) rejections with reasons. Explicitly instructed: no inference about protected characteristics; no collecting info about people who haven't publicly signaled intent; reject anything ambiguous.
2. **Listing Scout** — FSBO / expired / withdrawn / re-listed / long-DOM opportunities from legally accessible sources: Diane's own Triangle MLS exports (she has licensed access — the system *ingests files she pulls*, it never touches MLS credentials), plus public listing signals where terms permit. Flags what requires MLS data vs. what's public.
3. **Records Analyst** — turns Wake County (and neighbor county) public-records pulls into seller-side signals: long ownership tenure + recent permit activity, absentee owners (mailing ≠ situs address), recent estate/deed transfers, investor-owned portfolios, rental properties listed for sale. The *data pull* is code (ArcGIS REST / CSV downloads); Claude interprets combinations of signals and drafts the "why this matters" narrative. Hard rule: records signals alone produce *research candidates*, never "distressed homeowner" labels.
4. **Enrichment Agent** — deepens a promising candidate using web search + the records cache: property facts, listing history, prior sale, assessed value, and for person-leads only what they themselves posted publicly. Never hunts for private phone numbers, emails, or any sensitive attribute.
5. **Qualifier** — the gatekeeper. Code first re-checks: source URL still resolves, dates parse, not a dupe, not stale. Then Claude applies the scoring rubric (§9) with a mandatory per-category rationale and an explicit confidence, and answers the 10 quality questions from your Phase 7. Leads below threshold (default 60) are archived with the rejection reason — Diane never sees them unless she asks.
6. **Briefing Agent** — composes Diane's daily brief (your Phase 8 lead card format + pipeline summary + market notes) from already-verified data only. It formats and prioritizes; it adds no new facts.

**Compliance Gate** — a hybrid: a deterministic rule pass on every lead and every draft (blocked-field checks, source-allowlist check, staleness, DNC/TCPA flags on any future outreach) plus a Claude review on flagged edge cases (e.g., "does this brief's language raise Fair Housing steering concerns?"). Anything uncertain is flagged `NEEDS_HUMAN_REVIEW`, never silently passed or silently dropped.

---

## 3. Architecture & agent communication

```
                        ┌──────────────────────────────────────────────┐
                        │           ORCHESTRATOR (Python)              │
                        │  scheduler · task queue · dedup · CRM state  │
                        │  budget governor · event log (SSE feed)      │
                        └──────┬───────────────┬───────────────┬───────┘
        schedules/tasks        │               │               │
             ┌─────────────────┼───────────────┼───────────────┘
             ▼                 ▼               ▼
   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐      ┌─────────────────┐
   │ Intent Scout │   │Listing Scout │   │Records Analyst│ ◄──── │ Market Analyst  │
   │ (Reddit API, │   │ (MLS exports,│   │ (Wake Co APIs)│ focus │ (Redfin/Zillow  │
   │  forums)     │   │  FSBO public)│   │               │ hints │ data, permits,  │
   └──────┬───────┘   └──────┬───────┘   └──────┬────────┘       │ employer news)  │
          │  candidate leads (JSON)      │                       └────────┬────────┘
          └───────────────┬──────────────┘                                │
                          ▼                                               │
                ┌───────────────────┐     dedup (code) happens BEFORE     │
                │  Enrichment Agent │◄─── enrichment, not after — don't   │
                └─────────┬─────────┘     pay to research a duplicate     │
                          ▼                                               │
                ┌───────────────────┐                                     │
                │     Qualifier     │  verify (code+LLM) + score (rubric) │
                └─────────┬─────────┘                                     │
                          ▼                                               │
                ┌───────────────────┐                                     │
                │  Compliance Gate  │  rules + LLM edge cases             │
                └─────────┬─────────┘                                     │
                          ▼                                               ▼
                ┌─────────────────────────────────────────────────────────┐
                │        SQLite: leads · events · sources · costs         │
                └─────────┬───────────────────────────────┬───────────────┘
                          ▼                               ▼
                ┌───────────────────┐            ┌─────────────────┐
                │  Briefing Agent   │            │ FastAPI + SSE   │
                │  (daily 7:00 AM)  │            │ (dashboard API) │
                └─────────┬─────────┘            └────────┬────────┘
                          ▼                               ▼
                   DIANE'S BRIEF                   LIVE DASHBOARD
                          └──────────► DIANE ◄────────────┘
                                        │ 👍 ✓ ~ 👎 🚫  feedback
                                        ▼
                          feedback table → weekly learning job (v0.8)
                          (source weights, query stats, threshold tuning —
                           as reviewable config diffs)
```

**How agents "communicate":** they don't talk to each other directly, and that's deliberate. Every agent is a stateless function: `(task JSON in) → (result JSON out)`, invoked by the orchestrator. All coordination happens through two tables:

- `tasks` — the work queue (`id, agent, payload, status, attempts, cost, created_at, finished_at`).
- `events` — append-only log of everything (`ts, agent, task_id, lead_id, event_type, detail JSON`). This is the dashboard's data source: agent started/finished, source queried, lead discovered/rejected/scored, cost incurred, error raised.

Structured JSON everywhere: each agent call uses the Claude API with a **strict output schema** (`output_config.format` / `client.messages.parse()`), so results are validated objects, never free text to parse. Improvements over your Phase 4 diagram: dedup happens *before* enrichment (cheaper), the Market Analyst feeds *focus hints* into scouts rather than sitting outside the loop, and compliance sits *in* the pipeline rather than being an afterthought.

---

## 4. Technology stack (and why)

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.12** | Ecosystem for data pulls, official Anthropic SDK, your future-hire pool. |
| AI | **Anthropic API directly** (`anthropic` SDK) with structured outputs + tool use (server-side web search where needed) | Full control over cost, prompts, and schemas. The Claude Agent SDK is overkill here — we don't need a filesystem-coding harness; we need six well-prompted structured calls. Fewer moving parts. |
| Models | **`claude-opus-5`** for judgment-heavy stages (Qualifier, Enrichment synthesis, Compliance edge cases, Briefing) · **`claude-haiku-4-5`** for high-volume triage (first-pass post classification: "does this post contain explicit RE intent, yes/no + type"). | Two-tier design: Haiku throws away the 95% of posts that are noise for ~1/25th the cost; Opus does the reasoning that determines lead quality. `claude-sonnet-5` is a valid mid-tier swap for enrichment if costs need trimming — a one-line config change; see cost table in §10. |
| Storage | **SQLite (WAL mode)** | Local-first, zero setup, plenty for tens of thousands of leads/events. Schema written with plain SQL + a thin repository layer so a later Postgres move is mechanical. |
| API/backend | **FastAPI + SSE** (`/events/stream`) | One process serves the pipeline API and the live event feed the dashboard will subscribe to. SSE over WebSockets: one-directional updates, simpler, reconnects free. |
| Scheduling | **APScheduler** in-process | No Redis/Celery for a single-user local app. Batch-friendly overnight jobs can use the **Batch API (50% off)** for non-urgent classification sweeps. |
| HTTP/parsing | **httpx** + **BeautifulSoup** (only on pages whose terms permit automated access) + official API clients (PRAW for Reddit) | |
| Frontend (v0.6+) | **React + Vite**, served by FastAPI as static files | No Next.js/SSR needed for a local single-user tool. Until then: the daily brief is a Markdown/HTML file + a minimal server-rendered status page. |
| Config | YAML for geo layer, query templates, source registry, scoring weights — all human-reviewable, all in git | This is the "learning system" surface: changes land as diffs, never as self-modified code. |

Runs locally: `python -m leaddesk run` starts scheduler + API; `.env` holds `ANTHROPIC_API_KEY` and Reddit API credentials.

---

## 5. Data sources (Phase 2 research plan)

Verified-stable sources first; each gets a full source-registry entry (name, URL, access, cost, fields, cadence, ToS notes, consuming agent, value score) in `data/sources.yaml` during v0.5, with terms re-checked at integration time. Value = expected contribution to *qualified* leads.

### Free — government / open data (the backbone)

| Source | Access | What it gives us | Agent | Value |
|---|---|---|---|---|
| **Wake County Real Estate / Tax Administration** (services.wakegov.com/realestate + bulk files) | Public; bulk CSV downloads of the full parcel/ownership file | Owner name & **mailing address** (absentee detection), situs address, last sale date/price (ownership tenure), assessed value, beds/baths/sqft/year built | Records Analyst, Enrichment | **9/10** — the single best free source |
| **Wake County Open Data / GIS** (data.wake.gov, ArcGIS REST) | Public API, JSON | Parcels, zoning, addresses, geocoding | Records Analyst | 7/10 |
| **Wake County Register of Deeds** | Public online index | Deed transfers, estate/executor deeds, quitclaims — early transition signals | Records Analyst | 7/10 (index search is clunky; automate carefully) |
| **City of Raleigh Open Data** (data-ral.opendata.arcgis.com) | Public API | Building permits, development plan applications | Records Analyst, Market Analyst | 7/10 — permits are a classic pre-sale signal |
| **Town permit portals** (Cary, Apex, Wake Forest, Holly Springs…) | Varies (some open data, some search-only) | Same, per town | Market Analyst | 5/10, uneven |
| **Durham / Orange / Johnston county equivalents** | Public | Extends coverage to Durham, Chapel Hill, Clayton | Records Analyst | 6/10 (v0.5+) |
| **NC OneMap** | Public API | Statewide parcels — fills county gaps | Records Analyst | 5/10 |
| **Redfin Data Center** | Free downloadable TSVs (attribution required) | Metro/ZIP inventory, median price, DOM, price drops — weekly | Market Analyst | 8/10 |
| **Zillow Research data** (ZHVI/ZORI CSVs) | Free download — *research data only; scraping Zillow listings is prohibited* | ZIP-level value & rent indices | Market Analyst | 6/10 |
| **FRED API** | Free API key | Mortgage rates, macro context | Market Analyst | 5/10 |
| **Census/ACS** | Free API | County migration flows — aggregate market context only, never person-targeting | Market Analyst | 4/10 |

### Free — community / intent

| Source | Access | Notes | Agent | Value |
|---|---|---|---|---|
| **Reddit API** (r/raleigh, r/triangle, r/Cary, r/bullcity, r/chapelhill, r/NorthCarolina, r/RealEstate…) | Official API, OAuth, free tier is ample at our volume | The primary intent source for v0.1. ToS-compliant at low volume; we store links + quoted public text, don't republish datasets. Respect subreddit norms — leads here are "opportunities to be helpful," not cold-call targets. | Intent Scout | **8/10** for quality; low volume (a few genuine leads/week, not per day — see §11) |
| **Public web search** (Anthropic server-side web-search tool or Brave/SerpAPI) | Metered (~$10/1k searches on Anthropic's tool; verify current pricing at build time) | Runs the Phase-12 query library against the open web: news, forums, employer relocation announcements, estate-sale listings | Intent Scout, Market Analyst, Enrichment | 7/10 |
| **WRAL TechWire / local business news** | Public pages/RSS | Employer expansions & relocations (Apple RTP, biotech, etc.) → relocation-wave intelligence | Market Analyst | 6/10 |
| **Builder public inventory pages** (public spec/inventory listings) | Public, per-site terms check | New-construction inventory & incentives | Market Analyst | 5/10 |
| **EstateSales.net and similar** | Public listings; terms check before automating | Estate-sale signals → possible upcoming property sale | Records Analyst cross-ref | 4/10 |

### Licensed / first-party (Diane's own access)

| Source | Access | Notes | Value |
|---|---|---|---|
| **Triangle MLS** | Diane's license. **The system never logs in.** Diane exports expired/withdrawn/hotsheet CSVs from Matrix (or an MLS-approved tool like RPR) and drops them in a watched folder; the Listing Scout ingests them. | Expired/withdrawn/DOM/price-change history — the classic seller-lead source — is *only* legitimately available this way. Her MLS agreement governs use; the Compliance Gate tags every MLS-derived record `mls_licensed=true` and keeps it out of anything that could be republished. | **9/10** |
| Diane's sphere/past-client list (CSV) | First-party | Optional NURTURE pipeline seeding | 6/10 |

### Paid (later, only if free tier proves the concept)

| Source | ~Cost | What it adds | When |
|---|---|---|---|
| **REDX / Vulcan7 / Landvoice** | $50–150/mo | Packaged expired + FSBO leads with contact data, DNC-scrubbed | v0.9 — buy vs. build for FSBO |
| **ATTOM / Cotality (CoreLogic)** | $$$, contract | Multi-county normalized property data, pre-foreclosure | Only at real scale |
| **PropStream / BatchLeads** | ~$100/mo | Investor-grade filters, absentee/equity lists | If investor pipeline takes off |
| **Smarty / USPS CASS** | ~$50/mo | Address normalization at scale | v0.5 if fuzzy dedup struggles |

### Explicitly excluded (and why)

- **Zillow/Trulia FSBO scraping** — prohibited by ToS; no public listing API. FSBO discovery = public web search hits + Diane's manual flags + (later) a paid feed.
- **Craigslist** — ToS prohibits scraping.
- **Facebook groups, Nextdoor, LinkedIn** — platform rules prohibit automated collection; private/closed spaces besides. If Diane is in a group and sees something, she can add a lead manually through the dashboard — the human doing it is the legitimate path.
- **MLS credential automation** — never. Export-file ingestion only.
- **Skip-tracing / contact-info hunting** — the system records only contact info a person published themselves in the signal context.

---

## 6. Data model (Phase 3)

SQLite, plain SQL. Core tables:

```sql
-- The lead record: current state lives here; history lives in lead_events.
CREATE TABLE leads (
  lead_id            TEXT PRIMARY KEY,          -- ULID
  lead_type          TEXT NOT NULL,             -- seller|buyer|first_time_buyer|move_up|downsizer|investor|relocation|fsbo|expired|land|new_construction|rental_to_own
  subject_kind       TEXT NOT NULL,             -- property|person|entity
  display_name       TEXT,                      -- public handle or owner-of-record only
  property_address   TEXT, city TEXT, state TEXT DEFAULT 'NC', zip TEXT, county TEXT,
  geo_area           TEXT,                      -- geo-layer key (e.g. 'north_raleigh')
  source             TEXT NOT NULL,             -- source registry key
  source_url         TEXT,
  mls_licensed       INTEGER DEFAULT 0,         -- MLS-derived: restricted handling
  signal             TEXT NOT NULL,             -- verbatim/summarized public signal
  signal_date        TEXT,                      -- when the signal occurred
  date_discovered    TEXT NOT NULL,
  est_transaction    TEXT,                      -- buy|sell|both|invest|unknown
  property_info      TEXT,                      -- JSON: beds/baths/sqft/year/last_sale/assessed...
  research_notes     TEXT,
  lead_score         INTEGER,                   -- 0-100, null until qualified
  score_breakdown    TEXT,                      -- JSON: per-category points + rationale (required with score)
  confidence         TEXT,                      -- low|medium|high
  verification       TEXT DEFAULT 'unverified', -- unverified|verified|failed|stale
  stage              TEXT DEFAULT 'NEW',        -- NEW|RESEARCHING|QUALIFIED|HIGH_PRIORITY|CONTACT_READY|CONTACTED|RESPONDED|APPOINTMENT|CLIENT|NURTURE|NOT_INTERESTED|INVALID|REJECTED|CLOSED
  rejection_reason   TEXT,
  compliance_flags   TEXT,                      -- JSON array
  dedup_key          TEXT,                      -- normalized addr or source_url+handle hash
  next_followup      TEXT, last_contacted TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_leads_dedup ON leads(dedup_key);

CREATE TABLE lead_events (   -- full history; leads are never overwritten silently
  id INTEGER PRIMARY KEY, lead_id TEXT NOT NULL, ts TEXT NOT NULL,
  actor TEXT NOT NULL,       -- agent name | 'orchestrator' | 'diane'
  event_type TEXT NOT NULL,  -- discovered|enriched|verified|scored|stage_change|feedback|note
  detail TEXT                -- JSON
);

CREATE TABLE tasks (         -- work queue
  task_id TEXT PRIMARY KEY, agent TEXT NOT NULL, payload TEXT NOT NULL,
  status TEXT DEFAULT 'queued',   -- queued|running|done|failed|skipped
  attempts INTEGER DEFAULT 0,
  input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, runtime_ms INTEGER,
  created_at TEXT, started_at TEXT, finished_at TEXT, error TEXT
);

CREATE TABLE events (        -- system-wide activity feed (dashboard/SSE source)
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, agent TEXT, task_id TEXT, lead_id TEXT,
  event_type TEXT NOT NULL, detail TEXT
);

CREATE TABLE sources (       -- registry + performance
  source_key TEXT PRIMARY KEY, name TEXT, url TEXT, access TEXT, cost TEXT,
  tos_notes TEXT, enabled INTEGER DEFAULT 1,
  leads_discovered INTEGER DEFAULT 0, leads_qualified INTEGER DEFAULT 0,
  last_run TEXT, avg_lead_score REAL
);

CREATE TABLE queries (       -- Phase 12: query library + effectiveness
  query_id TEXT PRIMARY KEY, template TEXT, params TEXT, source_key TEXT,
  runs INTEGER DEFAULT 0, candidates INTEGER DEFAULT 0, qualified INTEGER DEFAULT 0,
  last_run TEXT, enabled INTEGER DEFAULT 1
);

CREATE TABLE feedback (      -- Phase 10: Diane's ratings
  id INTEGER PRIMARY KEY, lead_id TEXT NOT NULL, ts TEXT NOT NULL,
  rating TEXT NOT NULL,      -- excellent|useful|maybe|bad|not_a_lead
  reason TEXT
);

CREATE TABLE properties_cache ( -- Wake County pull cache, keyed by parcel PIN
  pin TEXT PRIMARY KEY, county TEXT, data TEXT, fetched_at TEXT
);
```

Deliberately **absent** fields: anything demographic. No names beyond public handles/owner-of-record, no inferred age/family status/origin, nothing that could smuggle a protected characteristic into scoring or filtering.

---

## 7. What's realistically automatable vs. not

**Fully automatable:** county-records pulls & signal extraction; Redfin/Zillow-research market stats; permit monitoring; Reddit intent monitoring; web-search sweeps; MLS-export-file ingestion; dedup; scoring; verification checks; brief generation; cost accounting.

**Semi-automated (Diane's workflow feeds it):** expired/withdrawn (she exports from MLS — 2 minutes/day); FSBO (search hits surface candidates, she confirms); manual lead entry from her sphere and from communities the system rightly won't touch.

**Not automatable, by design:** any contact with a human; joining/reading private groups; MLS logins; obtaining non-public contact info; and — hard truth — most "life event" signals your Phase-2 list imagines. What *is* legitimately visible: public estate/deed records, public estate-sale listings, publicly posted statements. What is *not*: divorce, job loss, health events. We do not go looking, full stop.

**Expectation-setting on volume (the most important pushback in this document):** public-intent monitoring in a metro like Raleigh yields **a handful of genuine, high-quality opportunities per week** — not per day. The records side yields larger candidate pools (hundreds of absentee owners, long-tenure + permit combos) but those are *research lists*, colder than intent leads and score-capped accordingly. "10 highly researched opportunities" per your Phase 7 is a realistic *weekly* target for v1.0, not daily. Anyone promising 10/day from free public sources is describing a spam machine.

---

## 8. Compliance design (Phase 9)

Layered, and honest about what software can and can't determine:

1. **Structural (can't-do-it-by-construction):** no protected-characteristic fields; no demographic inputs to scoring; geography = market geography only; source allowlist enforced in code — an agent literally cannot task itself against an unregistered source.
2. **Deterministic rule pass (every lead, every brief, every future draft):** source in registry & enabled; MLS-derived data flagged and handling-restricted; signal age limits; no contact info present that wasn't in the public signal; future outreach drafts checked against DNC-flag status, CAN-SPAM structural requirements (identity, address, opt-out) and TCPA rules (no autodialed/texted contact — v1 outreach is drafts-for-Diane only, which sidesteps most TCPA/DNC exposure since *she* decides and dials).
3. **Claude review on flagged cases:** Fair-Housing language review of briefs/drafts (steering-adjacent phrasing like "great for families" gets flagged), ToS-uncertainty questions, NCREC advertising-rule concerns (e.g., any future draft must carry her name + brokerage per NC rules).
4. **Human review queue:** anything uncertain → `NEEDS_HUMAN_REVIEW` with the specific question stated. The system flags; it does not render legal conclusions. Standing recommendation: Diane confirms MLS export-use terms with Triangle MLS, and any outreach templates get a one-time review by her broker-in-charge.

---

## 9. Lead scoring (Phase 8/12)

Your 0–100 rubric is kept with one change: category scores come from Claude *with mandatory rationale text per category*, but the **arithmetic, caps, and gates are enforced in code** — a model can't hand-wave a total.

| Category | Points | Hard rules enforced in code |
|---|---|---|
| Intent strength | 0–30 | Explicit first-person intent required for >20. Records-only signals cap at 12. |
| Recency | 0–15 | Computed from `signal_date`, not judged: ≤48h=15 · ≤7d=12 · ≤30d=8 · ≤90d=3 · older=0. |
| Location relevance | 0–15 | From geo layer: core Triangle=15 · adjacent=10 · NC-inbound relocation=8–12 · else 0. |
| Transaction likelihood | 0–15 | Stated timeframe ≤6mo required for >10. |
| Evidence quality | 0–10 | Direct quote + live URL required for >6. |
| Potential value | 0–10 | Price-band arithmetic (from property data or stated budget) — computed, not judged. |
| Data confidence | 0–5 | Verification status caps this: unverified ≤2. |

**Gates (code):** no verified source URL → score capped at 40 and stage stays RESEARCHING; intent-lead signal >30 days old → auto-REJECTED (stale); total <60 → REJECTED with reason logged; ≥80 → HIGH_PRIORITY. Every scored lead stores the full breakdown JSON — Diane always sees *why*. Confidence is never asserted above what the evidence supports; "unverified" is a valid, displayed state.

---

## 10. Cost model (Phase 11)

Tracked per task in the `tasks` table (tokens, $, runtime), rolled up per source/per lead. Budget governor: configurable daily cap (default **$5/day**) — pipeline pauses non-critical jobs when hit.

Current API pricing (per 1M tokens): Opus 5 $5 in / $25 out · Sonnet 5 $3/$15 (intro $2/$10 through 8/31/26) · Haiku 4.5 $1/$5. Web search ~$10 per 1,000 searches plus tokens (verify at build). Batch API: 50% off for overnight sweeps.

Estimated typical day at prototype scale:

| Job | Volume | Model | ~Cost/day |
|---|---|---|---|
| Reddit triage | ~150 posts/comments classified | Haiku (batched) | $0.05–0.15 |
| Intent deep-read | ~10 survivors | Opus | $0.30–0.60 |
| Web-search sweep | ~30 searches | tool + Opus | $0.40–0.80 |
| Records signal extraction | 1 batch (data pull itself is free) | Opus | $0.20–0.50 |
| Enrichment | 3–8 candidates | Opus | $0.50–1.50 |
| Qualify + score | 3–8 | Opus | $0.20–0.60 |
| Daily brief + compliance pass | 1 | Opus | $0.15–0.40 |
| **Total** | | | **≈ $1.80–4.50/day → ~$55–135/mo** |

Swapping enrichment/triage tiers to Sonnet/Haiku can roughly halve this; that's a config knob, and per-stage cost reporting will show exactly what each stage is worth. Metrics computed from day one: cost per discovered lead, cost per qualified lead, and (once Diane logs outcomes) cost per appointment.

---

## 11. UI / dashboard (Phase 14)

- **Now → v0.5:** daily brief as Markdown/HTML file + minimal FastAPI status page (pipeline counts, last runs, spend). Feedback via CLI/simple form.
- **v0.6–0.7 (React):** pages in priority order — **Lead Inbox** (approve/reject/rate), **Lead Detail** (full evidence + score breakdown + history), **Daily Brief**, **Pipeline** (kanban on `stage`), **Command Center** (live agent activity via SSE from `events`), **Sources & Analytics** (per-source qualified-lead rates, cost/lead), **Map** (Leaflet + OpenStreetMap — free, no Google Maps key), **System Activity** (raw log).
- Design rule: Diane-facing pages never mention tokens, models, or agents. She sees "New leads: 3 · Why: …". The nerd stuff lives in Command Center/System pages for Ethan.

The backend is dashboard-ready from v0.1 because every action already writes to `events` — the UI is just a subscriber.

---

## 12. Roadmap (Phase 15, revised)

| Version | Ships | Definition of done |
|---|---|---|
| **v0.1** | **Vertical slice:** SQLite schema + orchestrator skeleton + Reddit adapter + Haiku triage + Opus qualify/score + dedup + Markdown daily brief + cost tracking | `leaddesk run-once` produces a real brief from live r/raleigh (or triangle) data, with real scores, real rejection logs, and a cost report |
| **v0.2** | Wake County records: bulk parcel ingestion, absentee/tenure/transfer signals, Records Analyst | Records-derived research candidates appear in the brief, clearly labeled colder-tier |
| **v0.3** | Enrichment Agent + web-search sweeps + query library with effectiveness tracking + MLS-export-folder ingestion (Listing Scout) | Expired/withdrawn from Diane's export show up enriched & scored |
| **v0.4** | Compliance Gate (rules + LLM edge review) + full CRM state machine + Diane feedback capture | Every lead passes the gate; feedback stored with reasons |
| **v0.5** | Market Analyst (Redfin/Zillow-research/permits/FRED) + focus hints + full source registry docs | Brief includes market section; scouts prioritize hot areas |
| **v0.6** | FastAPI + React dashboard: Inbox, Detail, Pipeline, Brief | Diane can run her morning entirely in the dashboard |
| **v0.7** | Command Center live view (SSE), Sources/Analytics, Map | You can watch agents work |
| **v0.8** | Learning loop: weekly job proposes source-weight/query/threshold changes from feedback **as reviewable diffs** | First accepted tuning improves qualified-rate on a held-out week |
| **v0.9** | Draft outreach (drafts only, compliance-checked, Diane-approved), optional CRM export (CSV/Follow Up Boss API) | No message ever sends without an explicit click |
| **v1.0** | Hardening: retries, backup, docs, install script; optional hosted deployment path | Runs unattended for 2 weeks with zero babysitting |

Each version is 1–2 focused build sessions. v0.1 is deliberately narrow: one source, end-to-end, so we validate lead *quality* and cost before widening.

---

## 13. Where I'm pushing back on the original spec (summary)

1. **Most of your 15 "agents" shouldn't be LLM agents.** Orchestration, CRM, dedup, query generation, geo knowledge → code and config. Final count: 6 Claude agents + a compliance gate + a deterministic core. Cheaper, faster, debuggable.
2. **Volume expectations.** High-quality public-intent leads arrive in single digits per *week*. The system's honesty about this is a feature. The best agents in Raleigh get most business from sphere + referrals; this system is a *supplement* that catches public signals humans miss — it will not replace prospecting fundamentals.
3. **The FSBO/expired dream runs through Diane's MLS access, not scraping.** Zillow/Craigslist/Facebook automation is off the table legally. The export-folder workflow (2 min/day for her) is the legitimate 90% solution; paid feeds (REDX) are the buy-option later.
4. **"Seller signal" imagination vs. reality.** Public records give tenure, absentee status, permits, estate transfers — genuinely useful. Life-event inference beyond public records is both creepy and off-limits; it's excluded by construction, not just by policy.
5. **Learning system scoped down.** No self-modifying agents. Feedback → weekly proposal job → human-reviewed config diffs. That's the version that's safe and actually debuggable.
6. **Next.js/WebSockets/Postgres deferred.** Local single-user tool: Vite+React later, SSE, SQLite. Every one of these has a clean upgrade path if it ever becomes a hosted product.
7. **One addition you didn't list:** the **budget governor** and per-task cost ledger as a first-class orchestrator component from v0.1 — cost control designed in, not bolted on.

---

## 14. What v0.1 actually does (first prototype)

One command. One source. Full pipeline. Real output.

```
$ leaddesk run-once
[07:00:01] intent_scout   → reddit:r/raleigh+r/triangle+r/Cary   142 items pulled
[07:00:18] triage(haiku)  → 142 items → 9 candidates (133 rejected: no explicit intent)
[07:01:02] dedup          → 9 → 7 (2 already known)
[07:03:41] qualifier(opus)→ 7 → 3 qualified (4 rejected: stale ×2, vague ×1, outside area ×1)
[07:04:20] brief          → briefs/2026-08-06.md   (3 leads, top score 84)
[07:04:20] costs          → $0.87 today · $0.29/qualified lead
```

And the brief contains exactly your Phase-8 lead card format — every field real, sourced, and dated, with the rejection log available for audit.

---

*Next step: on your go-ahead, I build v0.1 on this branch.*
