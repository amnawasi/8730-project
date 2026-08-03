"""
Load processed CSVs into MySQL, matching sql/schema.sql.

Populates, in dependency order (date_dim first, since everything else
has a foreign key to it):
    1. date_dim      — generated for the full date range found across
                        all processed files, using the `holidays`
                        package for real Ontario statutory holidays
                        (not a hardcoded guess)
    2. weather        — from data/processed/toronto_weather_cleaned.csv
    3. sports_events  — from data/processed/toronto_sports_events_cleaned.csv
    4. delays         — from data/processed/ttc_delays_transformed.csv

Re-runnable: uses INSERT ... ON DUPLICATE KEY UPDATE / INSERT IGNORE
so running this twice doesn't create duplicate rows or crash.

Note: sql/schema.sql is the single source of truth for the delays table
shape (including delay_category and the widened incident_code/
route_or_line/direction/vehicle_number columns). This script used to
alter the schema at runtime to add/widen those on the fly; now that
schema.sql has been updated to match, that logic has been removed —
run sql/schema.sql once via MySQL Workbench (or `mysql < sql/schema.sql`)
before running this script.

Requires: pip install holidays  (in addition to requirements.txt)

Usage:
    python etl/load_mysql.py
"""

import os
import sys
import pandas as pd
import mysql.connector
from dotenv import load_dotenv

try:
    import holidays as holidays_lib
except ImportError:
    holidays_lib = None

load_dotenv()

PROCESSED_DIR = os.path.join("data", "processed")
WEATHER_CSV = os.path.join(PROCESSED_DIR, "toronto_weather_cleaned.csv")
SPORTS_CSV = os.path.join(PROCESSED_DIR, "toronto_sports_events_cleaned.csv")
DELAYS_CSV = os.path.join(PROCESSED_DIR, "ttc_delays_transformed.csv")

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE", "ttc_delays"),
}


def get_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        print(f"ERROR: could not connect to MySQL — check your .env credentials.\n{e}")
        sys.exit(1)


def season_for_month(month):
    return {12: "Winter", 1: "Winter", 2: "Winter",
            3: "Spring", 4: "Spring", 5: "Spring",
            6: "Summer", 7: "Summer", 8: "Summer",
            9: "Fall", 10: "Fall", 11: "Fall"}[month]


def robust_read_csv_column(path, col):
    """Read a single column as dates, working around a pandas C-parser bug
    that throws IndexError on some files with mixed-type columns even when
    usecols narrows to one column. Falls back to the python engine, then to
    a full dtype=str read, before giving up."""
    attempts = [
        lambda: pd.read_csv(path, usecols=[col], low_memory=False),
        lambda: pd.read_csv(path, usecols=[col], engine="python"),
        lambda: pd.read_csv(path, dtype=str)[[col]],
    ]
    last_error = None
    for attempt in attempts:
        try:
            return attempt()
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Could not read column '{col}' from {path}: {last_error}")


def collect_date_range():
    """Find the min/max date across whichever processed files exist,
    so date_dim covers everything without needing it hardcoded."""
    all_dates = []
    for path, col in [(WEATHER_CSV, "Date/Time"), (DELAYS_CSV, "date")]:
        if os.path.exists(path):
            df = robust_read_csv_column(path, col)
            all_dates.append(pd.to_datetime(df[col], errors="coerce", format="mixed"))
    if os.path.exists(SPORTS_CSV):
        df = robust_read_csv_column(SPORTS_CSV, "event_date")
        all_dates.append(pd.to_datetime(df["event_date"], errors="coerce", format="mixed"))

    if not all_dates:
        print("ERROR: no processed files found to determine date range. "
              "Run etl/transform.py first.")
        sys.exit(1)

    combined = pd.concat(all_dates).dropna()
    return combined.min().date(), combined.max().date()


def build_date_dim(start, end):
    dates = pd.date_range(start, end, freq="D")
    if holidays_lib:
        on_holidays = holidays_lib.Canada(prov="ON", years=range(start.year, end.year + 1))
    else:
        print("WARNING: `holidays` package not installed — is_holiday will be False "
              "for all rows. Run: pip install holidays")
        on_holidays = {}

    rows = []
    for d in dates:
        d_date = d.date()
        rows.append((
            d_date,
            d.day_name(),
            d.weekday() >= 5,
            d_date in on_holidays,
            season_for_month(d.month),
        ))
    return rows


def load_date_dim(conn, rows):
    cur = conn.cursor()
    sql = """
        INSERT INTO date_dim (date, day_of_week, is_weekend, is_holiday, season)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            day_of_week=VALUES(day_of_week), is_weekend=VALUES(is_weekend),
            is_holiday=VALUES(is_holiday), season=VALUES(season)
    """
    cur.executemany(sql, rows)
    conn.commit()
    print(f"date_dim: upserted {len(rows):,} rows")
    cur.close()


def load_weather(conn):
    if not os.path.exists(WEATHER_CSV):
        print(f"Skipped weather — file not found: {WEATHER_CSV}")
        return
    df = pd.read_csv(WEATHER_CSV)
    df["Date/Time"] = pd.to_datetime(df["Date/Time"], errors="coerce", format="mixed")

    rows = []
    for _, r in df.iterrows():
        if pd.isna(r["Date/Time"]):
            continue
        rows.append((
            r["Date/Time"].date(),
            r.get("Mean Temp (\u00b0C)"), r.get("Min Temp (\u00b0C)"), r.get("Max Temp (\u00b0C)"),
            r.get("Total Precip (mm)"), r.get("Total Rain (mm)"), r.get("Total Snow (cm)"),
            r.get("Snow on Grnd (cm)"),
        ))

    cur = conn.cursor()
    sql = """
        INSERT INTO weather (date, mean_temp_c, min_temp_c, max_temp_c,
                              total_precip_mm, total_rain_mm, total_snow_cm, snow_on_grnd_cm)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            mean_temp_c=VALUES(mean_temp_c), min_temp_c=VALUES(min_temp_c),
            max_temp_c=VALUES(max_temp_c), total_precip_mm=VALUES(total_precip_mm),
            total_rain_mm=VALUES(total_rain_mm), total_snow_cm=VALUES(total_snow_cm),
            snow_on_grnd_cm=VALUES(snow_on_grnd_cm)
    """
    cur.executemany(sql, rows)
    conn.commit()
    print(f"weather: upserted {len(rows):,} rows")
    cur.close()


def load_sports_events(conn):
    if not os.path.exists(SPORTS_CSV):
        print(f"Skipped sports_events — file not found: {SPORTS_CSV}")
        return
    df = pd.read_csv(SPORTS_CSV)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce", format="mixed")

    rows = []
    for _, r in df.iterrows():
        if pd.isna(r["event_date"]):
            continue
        rows.append((
            r["event_date"].date(),
            r.get("home_team"),
            r.get("league"),
            r.get("venue"),
            bool(r.get("is_home_game", True)),
        ))

    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE sports_events")
    conn.commit()
    sql = """
        INSERT INTO sports_events (event_date, team, league, venue, is_home_game)
        VALUES (%s, %s, %s, %s, %s)
    """
    cur.executemany(sql, rows)
    conn.commit()
    print(f"sports_events: truncated + inserted {len(rows):,} rows (safe to re-run)")
    cur.close()


def load_delays(conn):
    if not os.path.exists(DELAYS_CSV):
        print(f"Skipped delays — file not found: {DELAYS_CSV}")
        return

    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE delays")
    conn.commit()
    cur.close()

    df = pd.read_csv(DELAYS_CSV, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")

    rows = []
    skipped = 0
    for _, r in df.iterrows():
        if pd.isna(r["date"]):
            skipped += 1
            continue
        rows.append((
            r["date"].date(),
            r.get("time"),
            r.get("network"),
            r.get("route_or_line"),
            r.get("location"),
            r.get("code"),           # incident_code: raw code (subway) or
                                       # short text reason (streetcar/bus)
            None,                     # incident_description: no reliable free-text
                                       # available per Eric's finding, left NULL
            r.get("delay_category"),
            r.get("min_delay") if pd.notna(r.get("min_delay")) else None,
            r.get("min_gap") if pd.notna(r.get("min_gap")) else None,
            r.get("direction"),
            r.get("vehicle"),
            bool(r.get("is_rush_hour", False)),
        ))

    cur = conn.cursor()
    sql = """
        INSERT INTO delays (delay_date, delay_time, network, route_or_line, location,
                             incident_code, incident_description, delay_category,
                             min_delay, min_gap, direction, vehicle_number, is_rush_hour)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    # Batch insert to avoid one giant statement on large delay tables
    BATCH = 5000
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i:i + BATCH])
        conn.commit()
        print(f"  ...inserted {min(i + BATCH, len(rows)):,} / {len(rows):,}")

    print(f"delays: inserted {len(rows):,} rows ({skipped:,} skipped for missing date)")
    cur.close()


def main():
    print("Connecting to MySQL...")
    conn = get_connection()
    print(f"Connected to database: {DB_CONFIG['database']}\n")

    start, end = collect_date_range()
    print(f"Date range across all processed files: {start} to {end}\n")

    date_rows = build_date_dim(start, end)
    load_date_dim(conn, date_rows)

    load_weather(conn)
    load_sports_events(conn)
    load_delays(conn)

    conn.close()
    print("\nDone. Run a quick SELECT COUNT(*) on each table to sanity check.")


if __name__ == "__main__":
    main()