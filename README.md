# TTC Delay Analytics Framework

What Drives Transit Delays? A Multi-Factor Operations Analytics Framework for the TTC.
BSMM-8730, Data Acquisition and Management — Summer 2026.

Diagnostic (not predictive) comparison of how weather, temporal patterns, and major
sports events relate to TTC subway, streetcar, and bus delays.

## Repo structure

```
etl/                  Extraction, cleaning, and load scripts for each data source
  extract_ttc_delays.py     Toronto Open Data CKAN API
  extract_weather.py        ECCC historical climate API
  extract_sports_events.py  Home game schedules
  extract_reddit.py         Optional: PRAW / r/toronto, r/TTC
  transform.py               Cleaning, joins, derived temporal features
  load_mysql.py               Writes structured tables to MySQL
  load_mongo.py               Writes raw/unstructured text to MongoDB
analysis/
  diagnostic_analysis.py    Weather / temporal / event comparisons
dashboard/
  app.py                     Streamlit dashboard
sql/
  schema.sql                 MySQL table definitions
docs/
  ai_prompt_log.md            Required AI-use disclosure log
data/
  raw/                        Untouched pulls (gitignored)
  processed/                  Cleaned/joined outputs (gitignored)
```

## Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # fill in your own DB credentials and API keys
```

## Branch naming

Use `feature/short-description` (e.g. `feature/weather-extraction`,
`feature/streamlit-dashboard`). No personal names in branch names — this was
feedback on our last project.

## Data sources

| Source | Storage | Notes |
|---|---|---|
| TTC delay logs (CKAN API) | MySQL + MongoDB | Structured fields → MySQL, raw incident text → MongoDB |
| ECCC historical weather | MySQL | Daily climate data |
| Sports schedules | MySQL | Home game dates for Leafs/Raptors/Blue Jays/Toronto FC |
| Derived temporal features | MySQL | Rush hour, weekend, holiday flags |
| Reddit (optional) | MongoDB | Supplementary unstructured color only |

## AI use disclosure

All prompts used with AI tools during this project must be logged in
`docs/ai_prompt_log.md` per course requirements.
