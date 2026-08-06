# Diane's Lead Desk 🏡

An AI-assisted prospecting system for **Diane Harrington, REALTOR®** — it finds, researches,
verifies, and scores legitimate real-estate opportunities in the **Raleigh / Triangle, NC**
market from public sources, and presents them on a simple webpage Diane can open like any
other website. **Nothing is ever contacted automatically.**

- 📐 Full design: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- 🌐 Diane's page: the [`docs/`](docs/) folder (GitHub Pages-ready)
- 🐍 The pipeline: the [`leaddesk/`](leaddesk/) Python package

---

## 1. Give Diane her webpage (GitHub Pages)

1. Merge this branch to `main`.
2. On GitHub: **Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder: `/docs` → Save.**
3. In a minute or two the site is live at `https://<your-username>.github.io/RealEstate/`.
4. Send that link to Diane — she can bookmark it on her phone/iPad. It currently shows
   clearly-labeled **example data** so she can see how it works; it switches to real data
   automatically after the first pipeline run is pushed.

(The page also works by just double-clicking `docs/index.html` — no server needed.)

## 2. Run the pipeline (Ethan's side)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...                  # console.anthropic.com

python -m leaddesk init-db
python -m leaddesk run-once      # fetch → triage → qualify → brief → website data
python -m leaddesk status        # pipeline counts + today's spend
```

`run-once` does the full loop:

1. Pulls new public posts from Triangle subreddits (low volume, polite).
2. A fast model (Haiku) discards everything without **explicit** real-estate intent.
3. A strong model (Opus) verifies, judges, and explains each survivor; **code** enforces the
   scoring arithmetic, recency/location math, and quality gates (below 60 = rejected).
4. Writes a Markdown brief to `briefs/` and refreshes `docs/data/leads.js` for the website.

Then publish the update for Diane:

```bash
git add docs/data && git commit -m "Lead update" && git push
```

Typical cost: **well under $1 per run** (budget-capped at $5/day by default — see
`leaddesk/config.py` for every knob: models, subreddits, thresholds, budget).

## 3. Optional: run it automatically every morning

A GitHub Actions workflow (`.github/workflows/refresh.yml`) can run the pipeline daily and
push the updated data — making the whole thing hosted, no laptop required:

1. Repo **Settings → Secrets and variables → Actions → New repository secret** →
   name `ANTHROPIC_API_KEY`, value your key.
2. Merge to `main`. It runs every morning at 7:00 AM Eastern (and on demand via
   **Actions → Refresh leads → Run workflow**).

*Caveat: Reddit sometimes blocks requests from cloud IPs. If the action logs show fetch
errors, run locally instead, or register Reddit API credentials (see `leaddesk/sources/reddit.py`).*

## 4. What this system will and won't do

**Does:** monitor permitted public sources (Reddit today; Wake County records, market data,
and Diane's own MLS exports are next per the roadmap in `ARCHITECTURE.md`), aggressively
reject weak leads, score with a written rationale, and track its own cost per lead.

**Won't, by design:** contact anyone, scrape sites whose terms forbid it (Zillow, Craigslist,
Facebook, Nextdoor, LinkedIn), touch MLS credentials, hunt for private contact info, or
consider any protected characteristic anywhere in the pipeline (Fair Housing by construction).

**Honest expectations:** high-quality public-intent leads arrive in the single digits per
*week*, not per day. The system's value is that it never misses one, researches it properly,
and never wastes Diane's time on junk — a quiet day is an honest day.

## Roadmap

v0.1 (this) → county records signals → MLS-export ingestion & enrichment → compliance gate &
feedback → market intelligence → richer dashboard → learning loop → draft outreach
(drafts only, Diane approves each). Full roadmap with definitions of done: `ARCHITECTURE.md` §12.
