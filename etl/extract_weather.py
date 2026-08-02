"""
Extract daily historical weather data from Environment and Climate Change
Canada (ECCC) for the Toronto City Centre station, matching the TTC delay
date range (2023-2025).

Station: TORONTO CITY CENTRE, StationID = 48549
Data confirmed available for 2023-2026 on climate.weather.gc.ca.

Usage:
    python etl/extract_weather.py
"""

import os
import io
import time
import requests
import pandas as pd

BASE_URL = "https://climate.weather.gc.ca/climate_data/bulk_data_e.html"
STATION_ID = 48549          # Toronto City Centre
WANTED_YEARS = [2023, 2024, 2025]

OUTPUT_PATH = os.path.join("data", "raw", "toronto_weather_2023_2025.csv")


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
    print("\nFirst 3 rows:")
    print(combined.head(3).to_string())


if __name__ == "__main__":
    main()