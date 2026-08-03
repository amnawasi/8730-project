"""
Extract TTC Delay data (subway, streetcar, AND bus) from Toronto Open
Data (CKAN API). Pulls the 2023, 2024, and 2025 yearly files for each
of the three networks, tags each row with which network it came from,
stacks everything into one table, and saves to data/raw/.

Adds a `network` column (subway/streetcar/bus) required by schema.sql's
delays table (network ENUM('subway','streetcar','bus')).

Usage:
    python etl/extract_ttc_delays.py
"""

import os
import io
import requests
import pandas as pd

BASE_URL = "https://ckan0.cf.opendata.inter.prod-toronto.ca"

# One CKAN package per network. Each publishes the same yearly-file
# pattern (2023, 2024, "since 2025") as the subway dataset.
PACKAGES = {
    "subway": "ttc-subway-delay-data",
    "streetcar": "ttc-streetcar-delay-data",
    "bus": "ttc-bus-delay-data",
}

WANTED_YEARS = ["2023", "2024", "2025"]

OUTPUT_PATH = os.path.join("data", "raw", "ttc_all_networks_delays_2023_2025.csv")


def read_any_table(content, declared_format):
    """
    Try to read a downloaded file as a table, even if its declared
    format (xlsx/csv) doesn't quite match what pandas expects.
    """
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
            print(f"      (read using: {label})")
            return df
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(f"Could not read file with any method. Last error: {last_error}")


def pick_one_resource_per_year(resources, wanted_years):
    """
    Some Toronto Open Data resources are offered in multiple formats
    (xlsx, csv, xml, json) for the *same* underlying data. This picks
    exactly ONE resource per wanted year, preferring xlsx then csv,
    and skipping xml/json entirely.
    """
    FORMAT_PRIORITY = ["xlsx", "xls", "csv"]
    chosen = {}
    for res in resources:
        name = res.get("name", "")
        fmt = (res.get("format") or "").lower()
        if fmt not in FORMAT_PRIORITY:
            continue
        for year in wanted_years:
            if year in name:
                current = chosen.get(year)
                if current is None or FORMAT_PRIORITY.index(fmt) < FORMAT_PRIORITY.index(
                    (current.get("format") or "").lower()
                ):
                    chosen[year] = res
    return [chosen[y] for y in wanted_years if y in chosen]


def get_resource_list(package_id):
    url = BASE_URL + "/api/3/action/package_show"
    r = requests.get(url, params={"id": package_id}, timeout=60)
    r.raise_for_status()
    return r.json()["result"]["resources"]


def main():
    frames = []

    for network, package_id in PACKAGES.items():
        print(f"\n=== {network.upper()} ({package_id}) ===")
        resources = get_resource_list(package_id)
        print(f"Found {len(resources)} files total.")

        picked = pick_one_resource_per_year(resources, WANTED_YEARS)
        print(f"Selected {len(picked)} file(s) to download (one per year):")
        for res in picked:
            print(f"   - {res.get('name')}  ({res.get('format')})")

        for res in picked:
            name = res.get("name", "")
            fmt = (res.get("format") or "").lower()
            dl_url = res.get("url")
            print(f"Downloading: {name}  ({fmt})")
            resp = requests.get(dl_url, timeout=120)
            resp.raise_for_status()

            df = read_any_table(resp.content, fmt)
            df["network"] = network        # tag every row with its network
            df["source_file"] = name
            frames.append(df)
            print(f"   -> {len(df):,} rows")

    if not frames:
        print("No data collected from any network.")
        return

    combined = pd.concat(frames, ignore_index=True)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    combined.to_csv(OUTPUT_PATH, index=False)

    print("\n==============================")
    print(f"DONE. Combined rows: {len(combined):,}")
    print(f"Saved to: {OUTPUT_PATH}")
    print("Columns:", list(combined.columns))
    print("\nRows by network:")
    print(combined["network"].value_counts())
    print("\nFirst 3 rows:")
    print(combined.head(3).to_string())


if __name__ == "__main__":
    main()