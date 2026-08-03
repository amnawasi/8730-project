"""
Clean + transform step for all raw datasets (TTC delays x3 networks,
weather, sports events). Cleaning happens first (fix/remove bad rows),
then transform/enrichment (derive new columns) happens on the cleaned
data. Every cleaning action prints what it did — nothing is silently
dropped.

TTC delay files use different column names per network (confirmed by
schema.sql comments): subway uses "Station"/"Code"/"Line", while
streetcar/bus typically use "Location"/"Incident"/"Route". This script
normalizes all three to one common schema before combining them, and
tags each row with its network so cross-network comparison doesn't
need extra joins.

Code dictionary source (for delay_category):
Official TTC "Code Descriptions" resource, retrieved via the Toronto
Open Data CKAN API. Subway has a verified code->category mapping
(CODE_TO_BUCKET below). Streetcar/bus use a different code scheme —
if their own Code Descriptions resource can't be reliably matched,
this script falls back to keyword matching on the incident
description text itself, and reports what fraction of rows landed in
"uncategorized" so nothing is silently misclassified.

Usage:
    python etl/transform.py

Inputs (data/raw/):
    ttc_all_networks_delays_2023_2026.csv   (all three networks combined,
                                              tagged with a 'network' column
                                              by etl/extract_ttc_delays.py —
                                              split back out here)
    toronto_weather_2023_2026.csv
    toronto_sports_events_2023_2025.csv

Outputs (data/processed/):
    ttc_delays_transformed.csv       (all three networks combined)
    toronto_weather_cleaned.csv
    toronto_sports_events_cleaned.csv
    unmapped_codes_report.csv
    cleaning_report.txt
"""

import os
import pandas as pd

RAW_DIR = os.path.join("data", "raw")
OUT_DIR = os.path.join("data", "processed")

TTC_IN = os.path.join(RAW_DIR, "ttc_all_networks_delays_2023_2026.csv")
NETWORKS = ["subway", "streetcar", "bus"]
WEATHER_IN = os.path.join(RAW_DIR, "toronto_weather_2023_2026.csv")
SPORTS_IN = os.path.join(RAW_DIR, "toronto_sports_events_2023_2025.csv")

TTC_OUT = os.path.join(OUT_DIR, "ttc_delays_transformed.csv")
WEATHER_OUT = os.path.join(OUT_DIR, "toronto_weather_cleaned.csv")
SPORTS_OUT = os.path.join(OUT_DIR, "toronto_sports_events_cleaned.csv")
UNMAPPED_REPORT = os.path.join(OUT_DIR, "unmapped_codes_report.csv")
CLEANING_REPORT = os.path.join(OUT_DIR, "cleaning_report.txt")

report_lines = []


def log(msg):
    print(msg)
    report_lines.append(msg)


# ---------------------------------------------------------------------
# Column normalization: map each network's raw column names to one
# common set. Add/adjust aliases here if a real file has different
# headers than expected — print a clear error rather than guess.
# ---------------------------------------------------------------------
COLUMN_ALIASES = {
    "date": ["Date"],
    "time": ["Time"],
    "location": ["Station", "Location"],
    "code": ["Code", "Incident"],
    "min_delay": ["Min Delay"],
    "min_gap": ["Min Gap"],
    "direction": ["Bound", "Direction"],
    "route_or_line": ["Line", "Route"],
    "vehicle": ["Vehicle"],
}


def normalize_columns(df):
    """Rename/combine alias columns to one canonical name per field.

    IMPORTANT: some networks' concatenated files have MULTIPLE alias
    columns present at once (e.g. both 'Station' and 'Location'), because
    older and newer yearly files use different column names for the same
    field. Picking just one would silently drop real data for whichever
    years used the other name. This coalesces all present aliases,
    preferring the first non-null value per row.
    """
    missing = []
    for canonical, aliases in COLUMN_ALIASES.items():
        present = [a for a in aliases if a in df.columns]
        if not present:
            missing.append(canonical)
            continue

        if len(present) == 1:
            df[canonical] = df[present[0]]
        else:
            combined = df[present[0]]
            for col in present[1:]:
                combined = combined.combine_first(df[col])
            df[canonical] = combined
            log(f"  Coalesced columns {present} -> '{canonical}' "
                f"(multiple alias columns present, likely from different "
                f"years using different column names — combined so no rows lost)")

    if missing:
        log(f"  WARNING: columns not found for: {missing} "
            f"(available columns: {list(df.columns)}) — check the raw file's headers")
    return df


# ---------------------------------------------------------------------
# Subway code -> analysis bucket (verified against official TTC Code
# Descriptions). Kept from the original subway-only script.
# ---------------------------------------------------------------------
SUBWAY_CODE_TO_BUCKET = {
    "EUAC": "mechanical", "EUAL": "mechanical", "EUATC": "mechanical",
    "EUBK": "mechanical", "EUBO": "mechanical", "EUCA": "mechanical",
    "EUCC": "mechanical", "EUCD": "mechanical", "EUCH": "mechanical",
    "EUCO": "mechanical", "EUDO": "mechanical", "EUECD": "mechanical",
    "EUHV": "mechanical", "EULT": "mechanical", "EULV": "mechanical",
    "EUME": "operational", "EUNEA": "mechanical", "EUNT": "mechanical",
    "EUO": "mechanical", "EUOE": "operational", "EUOPO": "mechanical",
    "EUPI": "mechanical", "EUSC": "mechanical", "EUTL": "mechanical",
    "EUTM": "mechanical", "EUTR": "mechanical", "EUTRD": "mechanical",
    "EUVA": "mechanical", "EUVE": "mechanical", "EUYRD": "mechanical",
    "MUATC": "operational", "MUCL": "operational", "MUCP": "operational",
    "MUCSA": "operational", "MUCU": "operational", "MUD": "crowding",
    "MUDD": "operational", "MUEC": "operational", "MUESA": "operational",
    "MUFM": "weather", "MUFS": "operational", "MUGD": "uncategorized",
    "MUI": "crowding", "MUIE": "operational", "MUIR": "crowding",
    "MUIRS": "crowding", "MUIS": "crowding", "MULD": "operational",
    "MUNCA": "operational", "MUNOA": "operational", "MUO": "uncategorized",
    "MUODC": "mechanical", "MUPAA": "crowding", "MUPF": "mechanical",
    "MUPLA": "operational", "MUPLB": "operational", "MUPLC": "operational",
    "MUPR1": "crowding", "MUSAN": "crowding", "MUSC": "mechanical",
    "MUTD": "operational", "MUTO": "operational", "MUWEA": "weather",
    "MUWR": "operational",
    "PUATC": "mechanical", "PUCBI": "mechanical", "PUCSC": "mechanical",
    "PUCSS": "mechanical", "PUDCS": "mechanical", "PUEME": "operational",
    "PUEO": "mechanical", "PUEWZ": "operational", "PUMEL": "crowding",
    "PUMO": "operational", "PUMST": "crowding", "PUOPO": "mechanical",
    "PUSAC": "mechanical", "PUSBE": "mechanical", "PUSCA": "mechanical",
    "PUSCR": "mechanical", "PUSEA": "crowding", "PUSI": "mechanical",
    "PUSIO": "mechanical", "PUSIS": "weather", "PUSLC": "mechanical",
    "PUSNT": "mechanical", "PUSO": "mechanical", "PUSRA": "mechanical",
    "PUSSW": "mechanical", "PUSTC": "mechanical", "PUSTP": "mechanical",
    "PUSTS": "mechanical", "PUSWZ": "operational", "PUSZC": "mechanical",
    "PUT0": "mechanical", "PUTCD": "operational", "PUTD": "operational",
    "PUTDN": "operational", "PUTIJ": "mechanical", "PUTIS": "weather",
    "PUTNT": "mechanical", "PUTOE": "operational", "PUTR": "mechanical",
    "PUTS": "mechanical", "PUTSC": "mechanical", "PUTSM": "mechanical",
    "PUTTC": "mechanical", "PUTTP": "mechanical", "PUTWZ": "operational",
    "SUAE": "crowding", "SUAP": "crowding", "SUBT": "crowding",
    "SUCOL": "crowding", "SUDP": "crowding", "SUEAS": "crowding",
    "SUG": "crowding", "SUO": "crowding", "SUPOL": "crowding",
    "SUROB": "crowding", "SUSA": "crowding", "SUSP": "crowding",
    "SUUT": "crowding",
    "TUATC": "operational", "TUCC": "operational", "TUDOE": "operational",
    "TUKEY": "operational", "TUML": "operational", "TUMVS": "operational",
    "TUNCA": "operational", "TUNIP": "operational", "TUNOA": "operational",
    "TUO": "operational", "TUOPO": "operational", "TUOS": "operational",
    "TUS": "operational", "TUSC": "operational", "TUSET": "operational",
    "TUST": "weather", "TUSUP": "operational", "TUUR": "operational",
}

# ---------------------------------------------------------------------
# Streetcar/bus use a DIFFERENT code scheme than subway. Rather than
# guess a fabricated code list, fall back to keyword matching against
# the incident text itself. This is a heuristic, not a verified
# official mapping — flagged clearly in the report so the team knows
# to double check it (and ideally replace with the real streetcar/bus
# Code Descriptions resource if time allows).
# ---------------------------------------------------------------------
KEYWORD_BUCKETS = {
    "weather": ["snow", "ice", "weather", "rain", "fog", "wind"],
    "mechanical": ["mechanical", "door", "brake", "motor", "equipment",
                   "signal", "track", "rail", "switch", "collision",
                   "derail", "vehicle fault", "breakdown"],
    "crowding": ["passenger", "crowd", "assistance", "disorderly",
                 "medical", "injury", "security", "escalator", "elevator",
                 "unsanitary", "cleaning", "fare", "trespasser"],
    "operational": ["operator", "operational", "operations", "schedule",
                     "diversion", "held", "investigation", "staffing",
                     "management", "utilized off route", "road",
                     "construction", "traffic", "police", "emergency services"],
}


def load_code_descriptions(network):
    """If extract_ttc_delays.py found and saved an official Code
    Descriptions resource for this network, load it as a code -> text
    lookup dict. Returns {} if none was found (keyword-on-code-string
    fallback will be used instead)."""
    path = os.path.join(RAW_DIR, f"ttc_{network}_code_descriptions.csv")
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path)
    except Exception as e:
        log(f"  Could not read code descriptions file for {network}: {e}")
        return {}

    # Guess which columns hold the code and its description — TTC's own
    # files vary in header naming, so try a few common patterns.
    code_col = next((c for c in df.columns if c.strip().lower() in
                      ("code", "sub rmenu code", "code description")), None)
    desc_col = next((c for c in df.columns if "desc" in c.strip().lower()), None)

    if not code_col or not desc_col:
        log(f"  Code descriptions file for {network} found but columns unclear "
            f"({list(df.columns)}) — falling back to keyword-on-code matching")
        return {}

    lookup = dict(zip(df[code_col].astype(str).str.strip().str.upper(),
                       df[desc_col].astype(str)))
    log(f"  Loaded {len(lookup):,} official code descriptions for {network}")
    return lookup


def keyword_bucket(text):
    if not isinstance(text, str):
        return "uncategorized"
    t = text.lower()
    for bucket, keywords in KEYWORD_BUCKETS.items():
        if any(kw in t for kw in keywords):
            return bucket
    return "uncategorized"


def map_code_to_bucket(network, code, code_desc_lookup=None):
    if network == "subway":
        return SUBWAY_CODE_TO_BUCKET.get(code, "uncategorized")

    # streetcar/bus: prefer the official description text if we have a
    # lookup for this code, otherwise keyword-match on the code/phrase itself
    if code_desc_lookup and code in code_desc_lookup:
        return keyword_bucket(code_desc_lookup[code])
    return keyword_bucket(code)


# ---------------------------------------------------------------------
# CLEANING (network-agnostic, works on normalized column names)
# ---------------------------------------------------------------------

def clean_ttc(df, network):
    log(f"\n--- Cleaning {network} delay data ({len(df):,} rows in) ---")
    start = len(df)

    before = len(df)
    df = df.drop_duplicates()
    log(f"  Dropped {before - len(df):,} exact duplicate rows")

    before = len(df)
    df = df.dropna(subset=["date", "time"])
    log(f"  Dropped {before - len(df):,} rows missing date/time")

    before = len(df)
    df = df[df["min_delay"].fillna(0) >= 0]
    log(f"  Dropped {before - len(df):,} rows with negative min_delay")

    df["location"] = df["location"].astype(str).str.strip().str.upper()
    df["code"] = df["code"].astype(str).str.strip().str.upper()

    log(f"  Result: {len(df):,} rows kept ({start - len(df):,} removed total)")
    return df


def clean_weather(df):
    log(f"\n--- Cleaning weather data ({len(df):,} rows in) ---")
    start = len(df)

    before = len(df)
    df = df.drop_duplicates(subset=["Date/Time"])
    log(f"  Dropped {before - len(df):,} duplicate-date rows")

    bad_temp = df["Min Temp (\u00b0C)"] > df["Max Temp (\u00b0C)"]
    if bad_temp.any():
        log(f"  Flagged {bad_temp.sum()} rows where Min Temp > Max Temp (kept, worth a manual look)")

    missing_rain = df["Total Rain (mm)"].isna().sum()
    missing_snow = df["Total Snow (cm)"].isna().sum()
    log(f"  Note: {missing_rain:,} rows missing Total Rain, {missing_snow:,} missing "
        f"Total Snow (ECCC does not always split these from Total Precip — left as-is)")

    log(f"  Result: {len(df):,} rows kept ({start - len(df):,} removed total)")
    return df


def clean_sports(df):
    log(f"\n--- Cleaning sports events data ({len(df):,} rows in) ---")
    start = len(df)

    before = len(df)
    df = df.drop_duplicates(subset=["event_date", "home_team", "away_team"])
    log(f"  Dropped {before - len(df):,} duplicate game rows")

    before = len(df)
    df = df.dropna(subset=["event_date", "home_team"])
    log(f"  Dropped {before - len(df):,} rows missing date or home team")

    log(f"  Result: {len(df):,} rows kept ({start - len(df):,} removed total)")
    return df


# ---------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------

def transform_ttc(df, network, code_desc_lookup=None):
    # format='mixed' is critical here: 2023-2024 files use "YYYY-MM-DD HH:MM:SS"
    # while 2025+ files use "YYYY-MM-DD" or ISO "T"-separated timestamps. Without
    # format='mixed', pandas infers ONE format from the first values and silently
    # NaTs every row that doesn't match it — this was previously dropping ~45%
    # of rows across the whole dataset. Caught via row-count reconciliation.
    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    df["day_of_week"] = df["date"].dt.day_name()
    df["is_weekend"] = df["day_of_week"].isin(["Saturday", "Sunday"])
    df["month"] = df["date"].dt.month
    df["season"] = df["month"].map({
        12: "Winter", 1: "Winter", 2: "Winter",
        3: "Spring", 4: "Spring", 5: "Spring",
        6: "Summer", 7: "Summer", 8: "Summer",
        9: "Fall", 10: "Fall", 11: "Fall",
    })

    def is_rush_hour(row):
        if row["is_weekend"]:
            return False
        try:
            hour = int(str(row["time"]).split(":")[0])
        except (ValueError, IndexError):
            return False
        return (7 <= hour < 9) or (16 <= hour < 18)

    df["is_rush_hour"] = df.apply(is_rush_hour, axis=1)
    df["network"] = network
    df["delay_category"] = df.apply(
        lambda r: map_code_to_bucket(network, r["code"], code_desc_lookup), axis=1
    )

    bad_dates = df["date"].isna().sum()
    if bad_dates > 0:
        pct = bad_dates / len(df) * 100
        log(f"  WARNING: {bad_dates:,} rows ({pct:.1f}%) have an unparseable date "
            f"for {network} after transform — these will be dropped downstream. "
            f"{'This is a LOT — investigate before trusting the output.' if pct > 1 else ''}")
    return df


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    all_ttc_frames = []

    if not os.path.exists(TTC_IN):
        log(f"Skipped TTC delays — file not found: {TTC_IN}")
    else:
        raw_all = pd.read_csv(TTC_IN, low_memory=False)
        log(f"Loaded combined TTC delay file: {len(raw_all):,} rows total "
            f"across all networks, from {TTC_IN}")

        for network in NETWORKS:
            df = raw_all[raw_all["network"] == network].copy()
            if df.empty:
                log(f"Skipped {network} — no rows found for this network in {TTC_IN} "
                    f"(available networks in file: {sorted(raw_all['network'].unique())})")
                continue

            code_desc_lookup = load_code_descriptions(network) if network != "subway" else None

            df = normalize_columns(df)
            df = clean_ttc(df, network)
            df = transform_ttc(df, network, code_desc_lookup)
            all_ttc_frames.append(df)

            if network != "subway":
                source = "official code descriptions + keyword matching" if code_desc_lookup \
                    else "keyword matching only (no official code list found)"
                log(f"  NOTE: {network} delay_category used {source} — spot-check before relying on it heavily.")

    if all_ttc_frames:
        combined = pd.concat(all_ttc_frames, ignore_index=True)
        combined.to_csv(TTC_OUT, index=False)

        unmapped = combined[combined["delay_category"] == "uncategorized"]
        unmapped_summary = unmapped.groupby(["network", "code"]).size().reset_index(name="row_count")
        unmapped_summary.to_csv(UNMAPPED_REPORT, index=False)

        log(f"\nCombined delay_category breakdown by network:\n"
            f"{combined.groupby(['network', 'delay_category']).size()}")
        log(f"Rush hour rows: {combined['is_rush_hour'].sum():,} of {len(combined):,}")
        log(f"Uncategorized: {len(unmapped):,} rows ({len(unmapped)/len(combined)*100:.1f}%)")
        log(f"Saved: {TTC_OUT}")
    else:
        log("No TTC delay files found for any network — nothing to save.")

    if os.path.exists(WEATHER_IN):
        weather = pd.read_csv(WEATHER_IN)
        weather = clean_weather(weather)
        weather.to_csv(WEATHER_OUT, index=False)
        log(f"Saved: {WEATHER_OUT}")
    else:
        log(f"Skipped weather — file not found: {WEATHER_IN}")

    if os.path.exists(SPORTS_IN):
        sports = pd.read_csv(SPORTS_IN)
        sports = clean_sports(sports)
        sports.to_csv(SPORTS_OUT, index=False)
        log(f"Saved: {SPORTS_OUT}")
    else:
        log(f"Skipped sports — file not found: {SPORTS_IN}")

    with open(CLEANING_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    log(f"\nFull cleaning report saved to: {CLEANING_REPORT}")


if __name__ == "__main__":
    main()