# TTC Delay Analytics Framework

What Drives Transit Delays? A Multi-Factor Operations Analytics Framework for the TTC.
BSMM-8730, Data Acquisition and Management — Summer 2026.

Diagnostic (not predictive) comparison of how weather, temporal patterns, and major
sports events relate to TTC subway, streetcar, and bus delays, across 349,358 incidents
from January 2023 through mid-2026.

## Repo structure

```
etl/
  extract_ttc_delays.py       Toronto Open Data (CKAN API) — subway/streetcar/bus, combined
  extract_weather.py          ECCC historical climate API (Toronto Pearson Intl A)
  extract_sports_events.py    NHL/NBA/MLB home game schedules (ESPN API)
  extract_reddit.py           Not implemented — scoped out under time constraints
  transform.py                Cleaning, column harmonization, delay-category mapping,
                              derived temporal features
  load_mysql.py               Loads structured tables into MySQL; writes
                              delay_id_mapping.csv for load_mongo.py
  load_mongo.py               Loads raw incident text into MongoDB, linked to MySQL
                              by delay_id (requires load_mysql.py to run first)
  init_mongo.py               One-time setup: creates MongoDB collections + validation
  test_connections.py         Sanity-checks MySQL and MongoDB connectivity
analysis/
  diagnostic_analysis.py      Weather / temporal / event comparisons, cross-factor ranking
  advanced_visualizations.py  Correlation, time series, category composition, bubble chart
  outputs/                    Generated charts (PNG) and data (CSV)
dashboard/
  app.py                      Interactive Streamlit dashboard
sql/
  schema.sql                  MySQL table definitions (source of truth for the schema)
docs/
  ai_prompt_log.md            AI-use disclosure log
data/
  raw/                        Untouched pulls (gitignored)
  processed/                  Cleaned/joined outputs, incl. delay_id_mapping.csv (gitignored)
```

## Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # fill in your own DB credentials
```

`.env` needs: `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`,
`MYSQL_DATABASE`, `MONGO_URI`. Run `python etl/test_connections.py` after filling
these in to confirm both databases are reachable before running anything else.

## Running the pipeline

Order matters — each step depends on the one before it:

```bash
# 1. One-time setup (run once per fresh database)
mysql < sql/schema.sql              # or run sql/schema.sql in MySQL Workbench
python etl/init_mongo.py

# 2. Extract (pulls live from each source's public API)
python etl/extract_ttc_delays.py
python etl/extract_weather.py
python etl/extract_sports_events.py

# 3. Transform (cleans + combines the raw pulls)
python etl/transform.py

# 4. Load — load_mysql.py MUST run before load_mongo.py:
#    MySQL's delay_id is auto-generated at insert time, and load_mysql.py writes
#    it out to delay_id_mapping.csv, which load_mongo.py needs to link its
#    documents back to the right MySQL row.
python etl/load_mysql.py
python etl/load_mongo.py

# 5. Analyze and view
python analysis/diagnostic_analysis.py
python analysis/advanced_visualizations.py
streamlit run dashboard/app.py
```

The whole pipeline is safely re-runnable end to end — load scripts truncate/upsert
rather than duplicate, so re-running as new data lands doesn't require manual cleanup.

## Data sources

| Source | Storage | Coverage |
|---|---|---|
| TTC delay logs (CKAN API) — subway, streetcar, bus | MySQL (`delays`) | 349,358 incidents, Jan 2023 – mid-2026 |
| ECCC historical weather (Toronto Pearson Intl A) | MySQL (`weather`) | 1,461 daily observations, 2023–2026 |
| Major sports events (Leafs, Raptors, Blue Jays home games) | MySQL (`sports_events`) | 452 games, 2023–2025 |
| Raw incident-reason text (streetcar, bus only) | MongoDB (`raw_delay_incidents`) | 144,034 documents, linked to MySQL by `delay_id` |
| Derived temporal features (rush hour, weekend, holiday, season) | MySQL (`date_dim`, `delays`) | Computed, not sourced externally |

## Known limitations

- **Toronto FC / MLS is not included** in the sports events comparison — ESPN's API
  returned 0 events for it across all seasons pulled; the comparison covers NHL, NBA,
  and MLB only.
- **Sports events coverage ends at 2025**, one year short of weather/delays (2026) —
  ESPN's season list didn't extend to 2026 at time of extraction.
- **21.7% of delay incidents are uncategorized** for `delay_category`. Subway uses
  TTC's official code dictionary; streetcar/bus fall back to keyword matching for
  codes not covered by the available official descriptions.
- **MongoDB's raw incident text does not carry additional information** beyond
  MySQL's `incident_code` field for streetcar/bus — both are populated from the same
  source column (`Incident`) during extraction, so this is expected by construction,
  not a surprising empirical result.
- **Subway has no raw incident text at all** — its delay reason is a short structured
  code, not free text, so only streetcar/bus incidents appear in MongoDB.

## Branch naming

Use `feature/short-description` (e.g. `feature/weather-extraction`,
`feature/dashboard`). No personal names in branch names — this was feedback on our
last project.

## AI use disclosure

Prompts used with AI tools during this project are logged in
`docs/ai_prompt_log.md`, with a curated summary in the report's LLM Acknowledgement
section.
