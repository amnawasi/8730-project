"""
Extract TTC Delay data (subway, streetcar, AND bus) from Toronto Open
Data (CKAN API). Pulls the 2023-2026 yearly files for each of the
three networks, harmonizes their differing column names onto one
schema, tags each row with which network it came from, and saves a
single combined table to data/raw/.

Package IDs are hardcoded (not searched) because they were verified
directly in a browser AND by successfully running this script:
ttc-subway-delay-data, ttc-streetcar-delay-data, and ttc-bus-delay-data
all returned real 2023/2024/"since 2025" files with real row counts.
(Note: an automated page fetch earlier showed these as "Retired" —
that was a false read caused by the page requiring JavaScript to
render; a live browser and a live script run both confirm real data
exists under these IDs.)

Adds a `network` column (subway/streetcar/bus) required by schema.sql's
delays table (network ENUM('subway','streetcar','bus')) — matches the
team's agreed single-unified-table design rather than per-network files.

Usage:
    python etl/extract_ttc_delays.py
"""

import os
import io
import requests
import pandas as pd

BASE_URL = "https://ckan0.cf.opendata.inter.prod-toronto.ca"

# One CKAN package per network. Verified directly (browser + live run).
PACKAGES = {
    "subway": "ttc-subway-delay-data",
    "streetcar": "ttc-streetcar-delay-data",
    "bus": "ttc-bus-delay-data",
}

# Includes 2026 — don't leave recent months out, per Ahmad's flag.
WANTED_YEARS = ["2023", "2024", "2025", "2026"]

OUTPUT_PATH = os.path.join("data", "raw", "ttc_all_networks_delays_2023_2026.csv")


def sniff_real_format(content):
    """
    Detect the actual file type from its magic bytes rather than only
    trusting the declared format string from the API (which can be
    wrong/misleading, as seen earlier with the CKAN xlsx/csv mismatch).
    """
    if content[:2] == b"PK":
        return "xlsx"
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"
    return "csv"


def read_any_table(content, declared_format):
    """
    Try reading a downloaded file as a table. Sniffs the real format
    from file content first, tries that, then falls back to the
    declared format — reporting every attempt's real error.
    """
    real_format = sniff_real_format(content)
    ordered_formats = [real_format] + [f for f in [declared_format] if f != real_format]

    errors = []
    for fmt in ordered_formats:
        try:
            if fmt == "xlsx":
                df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
            elif fmt == "xls":
                df = pd.read_excel(io.BytesIO(content), engine="xlrd")
            else:
                df = pd.read_csv(io.BytesIO(content))
            print(f"      (read using: {fmt}, sniffed real format: {real_format})")
            return df
        except Exception as e:
            errors.append(f"{fmt}: {type(e).__name__}: {e}")

    error_detail = "\n       ".join(errors)
    raise RuntimeError(
        f"Could not read file (declared '{declared_format}', sniffed "
        f"'{real_format}'). Attempts:\n       {error_detail}"
    )


def harmonize_columns(df, network):
    """
    Bus and streetcar datasets use different column names than subway
    for the same concepts (Location instead of Station, Incident as a
    readable description instead of Code as a short code). This maps
    everything onto subway's column names so all three networks share
    one schema. The free-text "Incident" description is kept in its
    own column rather than forced into "Code" — it can't be matched
    against the official short-code dictionary and shouldn't be
    disguised as if it could.
    """
    if network == "subway":
        return df

    rename_map = {"Location": "Station", "Route": "Line", "Direction": "Bound"}
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "Incident" in df.columns:
        df["incident_description_raw"] = df["Incident"]
        if "Code" not in df.columns:
            df["Code"] = None

    return df


def pick_one_resource_per_year(resources, wanted_years):
    """
    Some resources are offered in multiple formats (xlsx/csv/xml/json)
    for the same underlying data. Picks exactly ONE per wanted year,
    preferring xlsx then csv, skipping xml/json.
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


def get_package(package_id):
    url = BASE_URL + "/api/3/action/package_show"
    r = requests.get(url, params={"id": package_id}, timeout=60)
    r.raise_for_status()
    return r.json()["result"]


def find_and_save_code_descriptions(network, package_id, resources):
    """
    Look for a 'Code Description'-type resource within this network's
    package (subway has one; worth checking if streetcar/bus do too).
    If found, save it so transform.py can build a real code lookup
    instead of guessing.
    """
    code_res = next(
        (r for r in resources if "code" in (r.get("name") or "").lower()
         and "description" in (r.get("name") or "").lower()
         and (r.get("format") or "").lower() == "csv"),
        None
    )
    if not code_res:
        print(f"   No 'Code Description' resource found for {network} "
              f"(expected for bus, since its Incident field is free text)")
        return None

    name = code_res.get("name", "")
    print(f"   Found code description resource: {name} — downloading")
    resp = requests.get(code_res["url"], timeout=60)
    resp.raise_for_status()
    df = read_any_table(resp.content, code_res.get("format", "").lower())

    out_path = os.path.join("data", "raw", f"ttc_{network}_code_descriptions.csv")
    df.to_csv(out_path, index=False)
    print(f"   Saved: {out_path}")
    return out_path


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

        find_and_save_code_descriptions(network, package_id, resources)

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
            df = harmonize_columns(df, network)
            df["network"] = network
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