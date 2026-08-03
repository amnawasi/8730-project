"""
Extract daily historical weather data from Environment and Climate Change
Canada (ECCC) for Toronto Pearson International Airport, matching the
TTC delay date range (2023-2026).

Station: TORONTO INTL A (Pearson Airport), StationID = 51459
Switched from the original "TORONTO CITY CENTRE" station (48549) because
that station reports ZERO snow-on-ground / total-snow data across the
whole 2023-2026 range — many downtown automated stations don't have
snow-depth sensors. Pearson is ECCC's primary full-element station for
the Toronto area and is what's typically used for snow accumulation
records (e.g. widely reported "Toronto (YYZ)" snowfall totals).

If this station also comes back with gaps for a given field, that's
worth noting explicitly in the report's Dataset Validation section
rather than silently working around it again.

Usage:
    python etl/extract_weather.py
"""
import os
import io
import time
import requests
import pandas as pd

BASE_URL = "https://climate.weather.gc.ca/climate_data/bulk_data_e.html"
STATION_ID = 51459          # Toronto Pearson Intl A (was 48549 / City Centre)
WANTED_YEARS = [2023, 2024, 2025, 2026]
OUTPUT_PATH = os.path.join("data", "raw", "toronto_weather_2023_2026.csv")


def fetch_year(year):
    """Download one year of daily weather data as a DataFrame."""
    params = {
        "format": "csv",
        "stationID": STATION_ID,
        "Year": year,
        "Month": 1,
        "Day": 1,
        "timeframe": 2,   # 2 = daily data
        "submit": "Download Data",
    }
    r = requests.get(BASE_URL, params=params, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df["source_year"] = year
    return df


def main():
    frames = []
    for year in WANTED_YEARS:
        print(f"Downloading weather data for {year}...")
        df = fetch_year(year)
        print(f"   -> {len(df):,} rows")
        frames.append(df)
        time.sleep(1)  # be polite to the server between requests

    combined = pd.concat(frames, ignore_index=True)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    combined.to_csv(OUTPUT_PATH, index=False)

    print("\n==============================")
    print(f"DONE. Combined rows: {len(combined):,}")
    print(f"Saved to: {OUTPUT_PATH}")
    print("Columns:", list(combined.columns))

    # Quick sanity check on the field that was previously empty
    if "Snow on Grnd (cm)" in combined.columns:
        n_populated = combined["Snow on Grnd (cm)"].notna().sum()
        print(f"\nSnow on Grnd (cm) populated for {n_populated:,} of {len(combined):,} rows "
              f"({'looks good' if n_populated > 0 else 'STILL EMPTY — station may not report this either'})")

    print("\nFirst 3 rows:")
    print(combined.head(3).to_string())


if __name__ == "__main__":
    main()
