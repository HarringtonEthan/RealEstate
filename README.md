# Diane's Lead Desk 🏡

An AI-assisted prospecting system for **Diane Harrington, REALTOR®** — it finds, researches,
verifies, and scores legitimate real-estate opportunities in the **Raleigh / Triangle, NC**
market from her MLS exports and public property records, and presents them on a simple webpage
Diane can open like any other website. **Nothing is ever contacted automatically.**

Current focus: **MLS expired/withdrawn listings** (highest-converting seller source there is)
and **public renovation/ownership records** (finds recently-renovated homes an investor doesn't
live in — a classic pre-sale pattern). Both run at **zero AI cost** — pure record-matching, no
Claude API calls. Reddit exists in the codebase but is off by default.

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

## 2. Export Diane's MLS listings (the highest-value source)

1. In Matrix (or your MLS's export tool), run a saved search for **expired** and **withdrawn**
   listings in your service area.
2. Export the results as **CSV**. Column names don't need to match exactly — see
   [`mls_export_template.csv`](mls_export_template.csv) for the shape the importer expects
   (address, status, prices, dates, DOM, etc. — matched flexibly by header name).
3. Save the file into the `mls_exports/` folder in this project (created automatically by
   `init-db`, or just make the folder yourself). Any number of CSV files can sit there.
4. **The tool never logs into your MLS.** It only reads the file you already exported.

If the importer can't find a required column, it'll print the exact headers it found in your
file in the terminal — send those to Claude/Ethan and the mapping gets fixed in a couple of
minutes.

**Privacy:** MLS-derived leads are held back from the public website by default (they're fully
visible in the local `briefs/*.md` file and `leaddesk status`) until Diane confirms with
Triangle MLS / her broker-in-charge that showing summarized derived info on her own
unauthenticated page is fine under her data license. Flip `PUBLISH_MLS_LEADS_TO_SITE=1` in the
environment once confirmed.

## 3. Run the pipeline

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m leaddesk init-db
python -m leaddesk run-once      # public records + MLS import -> score -> brief -> website data
python -m leaddesk status        # pipeline counts + today's spend + MLS-lead count
```

No API key is required for today's sources — both the records scan and the MLS import are
free, deterministic record-matching. (An `ANTHROPIC_API_KEY` is only needed if you turn the
Reddit source back on — see below.)

Then publish the update for Diane:

```bash
git add docs/data && git commit -m "Lead update" && git push
```

## 4. Sources — what's on, what's off

Set with environment variables (or edit `leaddesk/config.py` directly):

| Source | Default | Cost | Toggle |
|---|---|---|---|
| Wake County / Raleigh public records (renovation watch) | **on** | free | `LEADDESK_ENABLE_RECORDS=0` to turn off |
| MLS export (expired/withdrawn) | **on** | free | `LEADDESK_ENABLE_MLS=0` to turn off |
| Reddit public-intent monitoring | **off** | needs `ANTHROPIC_API_KEY` | `LEADDESK_ENABLE_REDDIT=1` to turn on |

The public-records source hits Wake County's and Raleigh's open-data servers; the exact field
names are configured (and easy to fix) in `leaddesk/config.py` — see the comments there if a
run logs a records-scan warning.

## 5. Optional: run it automatically every morning

A GitHub Actions workflow (`.github/workflows/refresh.yml`) can run the pipeline daily and
push the updated data:

1. If Reddit is on, add repo secret `ANTHROPIC_API_KEY` (**Settings → Secrets and variables →
   Actions**). Not needed for the default MLS + records sources.
2. Merge to `main`. It runs every morning at 7:00 AM Eastern (and on demand via
   **Actions → Refresh leads → Run workflow**).
3. **You still need to get your MLS export file onto whatever machine runs this.** GitHub
   Actions can't reach your MLS for you — for now, run `run-once` locally whenever you have a
   fresh export, or keep the whole pipeline local rather than on GitHub's schedule.

## 6. What this system will and won't do

**Does:** read Diane's own MLS exports and public Wake County/Raleigh records, aggressively
reject weak leads, score every lead with a written rationale, and track cost per lead.

**Won't, by design:** contact anyone, scrape sites whose terms forbid it (Zillow, Craigslist,
Facebook, Nextdoor, LinkedIn), touch MLS credentials, hunt for private contact info, or
consider any protected characteristic anywhere in the pipeline (Fair Housing by construction).

## Roadmap

v0.1 records + MLS (this) → compliance gate & feedback → market intelligence → richer
dashboard → learning loop → draft outreach (drafts only, Diane approves each). Full roadmap:
`ARCHITECTURE.md` §12.
