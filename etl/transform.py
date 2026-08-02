"""
Clean + transform step for all three raw datasets (TTC delays, weather,
sports events). Cleaning happens first (fix/remove bad rows), then
transform/enrichment (derive new columns) happens on the cleaned data.
Every cleaning action prints what it did — nothing is silently dropped.

Code dictionary source (for delay_category):
Official TTC "Code Descriptions" resource, retrieved via the Toronto
Open Data CKAN API (package: ttc-subway-delay-data, resource:
"Code Descriptions.csv"). All 140 codes categorized based on their
official description — see comments below for the judgment calls made.

Usage:
    python etl/transform.py

Inputs (data/raw/):
    ttc_subway_delays_2023_2025.csv
    toronto_weather_2023_2025.csv
    toronto_sports_events_2023_2025.csv

Outputs (data/processed/):
    ttc_subway_delays_transformed.csv
    toronto_weather_cleaned.csv
    toronto_sports_events_cleaned.csv
    unmapped_codes_report.csv
    cleaning_report.txt
"""

import os
import pandas as pd

RAW_DIR = os.path.join("data", "raw")
OUT_DIR = os.path.join("data", "processed")

TTC_IN = os.path.join(RAW_DIR, "ttc_subway_delays_2023_2025.csv")
WEATHER_IN = os.path.join(RAW_DIR, "toronto_weather_2023_2025.csv")
SPORTS_IN = os.path.join(RAW_DIR, "toronto_sports_events_2023_2025.csv")

TTC_OUT = os.path.join(OUT_DIR, "ttc_subway_delays_transformed.csv")
WEATHER_OUT = os.path.join(OUT_DIR, "toronto_weather_cleaned.csv")
SPORTS_OUT = os.path.join(OUT_DIR, "toronto_sports_events_cleaned.csv")
UNMAPPED_REPORT = os.path.join(OUT_DIR, "unmapped_codes_report.csv")
CLEANING_REPORT = os.path.join(OUT_DIR, "cleaning_report.txt")

report_lines = []


def log(msg):
    """Print and remember, so the cleaning report captures everything."""
    print(msg)
    report_lines.append(msg)


# ---------------------------------------------------------------------
# Official TTC code -> analysis bucket (mechanical / weather /
# operational / crowding / uncategorized). Source: TTC "Code
# Descriptions" CSV via CKAN API. See prior version's comments for the
# full reasoning behind each judgment call.
# ---------------------------------------------------------------------
CODE_TO_BUCKET = {
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


def map_code_to_bucket(code):
    return CODE_TO_BUCKET.get(code, "uncategorized")


# ---------------------------------------------------------------------
# CLEANING
# ---------------------------------------------------------------------

def clean_ttc(df):
    log(f"\n--- Cleaning TTC delay data ({len(df):,} rows in) ---")
    start = len(df)

    # 1. exact duplicate rows
    before = len(df)
    df = df.drop_duplicates()
    log(f"  Dropped {before - len(df):,} exact duplicate rows")

    # 2. rows missing a Date or Time (can't analyze without them)
    before = len(df)
    df = df.dropna(subset=["Date", "Time"])
    log(f"  Dropped {before - len(df):,} rows missing Date/Time")

    # 3. negative delay minutes are invalid (delay can't be negative)
    before = len(df)
    df = df[df["Min Delay"].fillna(0) >= 0]
    log(f"  Dropped {before - len(df):,} rows with negative Min Delay")

    # 4. standardize Station text (trim whitespace, consistent casing)
    df["Station"] = df["Station"].astype(str).str.strip().str.upper()

    # 5. standardize Code text (trim whitespace so mapping lookups match)
    df["Code"] = df["Code"].astype(str).str.strip().str.upper()

    log(f"  Result: {len(df):,} rows kept ({start - len(df):,} removed total)")
    return df


def clean_weather(df):
    log(f"\n--- Cleaning weather data ({len(df):,} rows in) ---")
    start = len(df)

    before = len(df)
    df = df.drop_duplicates(subset=["Date/Time"])
    log(f"  Dropped {before - len(df):,} duplicate-date rows")

    # sanity check: min temp should not exceed max temp
    bad_temp = df["Min Temp (°C)"] > df["Max Temp (°C)"]
    if bad_temp.any():
        log(f"  Flagged {bad_temp.sum()} rows where Min Temp > Max Temp "
            f"(kept, but worth a manual look)")

    # known gap: Total Rain / Total Snow are often blank on days where
    # only Total Precip was recorded (TTC/ECCC doesn't always separate
    # rain vs snow in winter). We leave these as NaN rather than
    # guessing a split — noted here rather than silently left unexplained.
    missing_rain = df["Total Rain (mm)"].isna().sum()
    missing_snow = df["Total Snow (cm)"].isna().sum()
    log(f"  Note: {missing_rain:,} rows missing Total Rain, "
        f"{missing_snow:,} missing Total Snow (ECCC does not always "
        f"split these from Total Precip — left as-is, not guessed)")

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
# TRANSFORM (derive new columns from the now-clean data)
# ---------------------------------------------------------------------

def transform_ttc(df):
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["day_of_week"] = df["Date"].dt.day_name()
    df["is_weekend"] = df["day_of_week"].isin(["Saturday", "Sunday"])
    df["month"] = df["Date"].dt.month
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
            hour = int(str(row["Time"]).split(":")[0])
        except (ValueError, IndexError):
            return False
        return (7 <= hour < 9) or (16 <= hour < 18)

    df["is_rush_hour"] = df.apply(is_rush_hour, axis=1)
    df["delay_category"] = df["Code"].apply(map_code_to_bucket)
    return df


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # --- TTC ---
    if os.path.exists(TTC_IN):
        ttc = pd.read_csv(TTC_IN)
        ttc = clean_ttc(ttc)
        ttc = transform_ttc(ttc)
        ttc.to_csv(TTC_OUT, index=False)

        unmapped = ttc[ttc["delay_category"] == "uncategorized"]
        unmapped_summary = unmapped["Code"].value_counts().reset_index()
        unmapped_summary.columns = ["Code", "row_count"]
        unmapped_summary.to_csv(UNMAPPED_REPORT, index=False)

        log(f"\nTTC delay_category breakdown:\n{ttc['delay_category'].value_counts()}")
        log(f"Rush hour rows: {ttc['is_rush_hour'].sum():,} of {len(ttc):,}")
        log(f"Unmapped codes: {len(unmapped_summary)} distinct "
            f"({len(unmapped):,} rows, {len(unmapped)/len(ttc)*100:.1f}%)")
        log(f"Saved: {TTC_OUT}")
    else:
        log(f"Skipped TTC — file not found: {TTC_IN}")

    # --- Weather ---
    if os.path.exists(WEATHER_IN):
        weather = pd.read_csv(WEATHER_IN)
        weather = clean_weather(weather)
        weather.to_csv(WEATHER_OUT, index=False)
        log(f"Saved: {WEATHER_OUT}")
    else:
        log(f"Skipped weather — file not found: {WEATHER_IN}")

    # --- Sports ---
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