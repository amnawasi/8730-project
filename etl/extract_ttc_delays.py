"""
Extract TTC Subway Delay data from Toronto Open Data (CKAN API).
Pulls the 2023, 2024, and 2025 yearly files, stacks them into one table,
and saves the combined result to data/raw/.

Usage:
    python etl/extract_ttc_delays.py
"""

import os
import io
import requests
import pandas as pd

BASE_URL = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
PACKAGE_ID = "ttc-subway-delay-data"

# Which years to pull. Post-COVID, clean range — edit here to change it.
WANTED_YEARS = ["2023", "2024", "2025"]

# Save relative to the repo root, matching the repo's data/raw/ convention
OUTPUT_PATH = os.path.join("data", "raw", "ttc_subway_delays_2023_2025.csv")


def read_any_table(content, declared_format):
    """
    Try to read a downloaded file as a table, even if its declared
    format (xlsx/csv) doesn't quite match what pandas expects.
    Tries a few approaches in order and uses whichever one works.
    """
    attempts = []

    if declared_format in ("xlsx", "xls"):
        attempts = [
            ("excel (openpyxl)", lambda: pd.read_excel(io.BytesIO(content), engine="openpyxl")),
            ("excel (xlrd)", lambda: pd.read_excel(io.BytesIO(content), engine="xlrd")),
            ("csv fallback", lambda: pd.read_csv(io.BytesIO(content))),
        ]
    else:
        attempts = [
            ("csv", lambda: pd.read_csv(io.BytesIO(content))),
            ("excel (openpyxl) fallback", lambda: pd.read_excel(io.BytesIO(content), engine="openpyxl")),
        ]

    last_error = None
    for label, fn in attempts:
        try:
            df = fn()
            print(f"   (read using: {label})")
            return df
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"Could not read file with any method. Last error: {last_error}")


def pick_one_resource_per_year(resources, wanted_years):
    """
    Toronto Open Data offers some datasets in multiple formats
    (xlsx, csv, xml, json) for the *same* underlying data. Naively
    matching by year in the name grabs all of them as duplicates.
    This picks exactly ONE resource per wanted year, preferring
    xlsx, then csv, and skipping xml/json entirely.
    """
    FORMAT_PRIORITY = ["xlsx", "xls", "csv"]  # xml/json intentionally excluded

    chosen = {}
    for res in resources:
        name = res.get("name", "")
        fmt = (res.get("format") or "").lower()
        if fmt not in FORMAT_PRIORITY:
            continue  # skip xml/json/readme/etc.

        for year in wanted_years:
            if year in name:
                current = chosen.get(year)
                if current is None or FORMAT_PRIORITY.index(fmt) < FORMAT_PRIORITY.index(
                    (current.get("format") or "").lower()
                ):
                    chosen[year] = res

    # return in a stable year order
    return [chosen[y] for y in wanted_years if y in chosen]


def get_resource_list():
    """Ask the CKAN API for the list of files (resources) in this dataset."""
    url = BASE_URL + "/api/3/action/package_show"
    r = requests.get(url, params={"id": PACKAGE_ID}, timeout=60)
    r.raise_for_status()
    return r.json()["result"]["resources"]


def main():
    print("Asking Toronto Open Data for the list of files...")
    resources = get_resource_list()
    print(f"Found {len(resources)} files total.\n")

    frames = []
    picked = pick_one_resource_per_year(resources, WANTED_YEARS)
    print(f"Selected {len(picked)} file(s) to download (one per year):")
    for res in picked:
        print(f"   - {res.get('name')}  ({res.get('format')})")
    print()

    for res in picked:
        name = res.get("name", "")
        fmt = (res.get("format") or "").lower()
        dl_url = res.get("url")
        print(f"Downloading: {name}  ({fmt})")
        resp = requests.get(dl_url, timeout=120)
        resp.raise_for_status()

        df = read_any_table(resp.content, fmt)

        df["source_file"] = name  # track which yearly file each row came from
        frames.append(df)
        print(f"   -> {len(df):,} rows")

    if not frames:
        print("No matching files found. Check WANTED_YEARS against the file names.")
        return

    combined = pd.concat(frames, ignore_index=True)

    # make sure data/raw/ exists before writing
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