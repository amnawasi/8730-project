"""
Extract TTC Delay data (subway, streetcar, bus) from Toronto Open Data (CKAN API).

Unlike a hardcoded package-ID approach, this script SEARCHES the CKAN
catalogue for delay datasets by keyword, because Toronto Open Data has
renamed/retired packages before (e.g. the old "ttc-bus-delay-data"
package is now marked Retired — bus data appears to live under a
newer package, likely a combined "surface" delay package covering
both bus and streetcar). Searching avoids silently pulling nothing
from a dead package ID.

Usage:
    python etl/extract_ttc_delays.py
"""

import os
import io
import requests
import pandas as pd

BASE_URL = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
WANTED_YEARS = ["2023", "2024", "2025", "2026"]  # include 2026 - don't leave recent months out

# Keywords used to find each network's delay package by searching the
# catalogue, rather than trusting a specific package ID that may be stale.
NETWORK_SEARCH_TERMS = {
    "subway": ["ttc subway delay"],
    "streetcar": ["ttc streetcar delay"],
    "bus": ["ttc bus delay", "ttc surface delay"],  # try both old + likely new naming
}

OUTPUT_DIR = os.path.join("data", "raw")


def search_packages(keywords):
    """Search the CKAN catalogue and return matching package IDs (deduped)."""
    url = BASE_URL + "/api/3/action/package_search"
    found = {}
    for kw in keywords:
        r = requests.get(url, params={"q": kw, "rows": 10}, timeout=60)
        r.raise_for_status()
        for pkg in r.json()["result"]["results"]:
            found[pkg["id"]] = pkg
    return list(found.values())


def get_package(package_id):
    url = BASE_URL + "/api/3/action/package_show"
    r = requests.get(url, params={"id": package_id}, timeout=60)
    r.raise_for_status()
    return r.json()["result"]


def sniff_real_format(content):
    """Detect the actual file type from its magic bytes rather than trusting
    the (sometimes wrong) declared format string from the API. xlsx/xls are
    zip-based binary files (PK.. signature); anything readable as UTF-8 text
    starting with typical CSV-ish characters is probably CSV."""
    if content[:2] == b"PK":
        return "xlsx"
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"  # old OLE2 binary Excel format
    return "csv"


def read_any_table(content, declared_format):
    """Try reading a downloaded file as a table. Sniffs the real format from
    file content first (declared format from the API can be wrong), then
    tries that, then falls back to the declared format, reporting every
    attempt's real error instead of masking it."""
    real_format = sniff_real_format(content)
    ordered_formats = [real_format] + [f for f in [declared_format] if f != real_format]

    errors = []
    for fmt in ordered_formats:
        try:
            if fmt in ("xlsx",):
                df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
            elif fmt in ("xls",):
                df = pd.read_excel(io.BytesIO(content), engine="xlrd")
            else:
                df = pd.read_csv(io.BytesIO(content))
            print(f"     (read using: {fmt}, sniffed real format was: {real_format})")
            return df
        except Exception as e:
            errors.append(f"{fmt}: {type(e).__name__}: {e}")

    error_detail = "\n       ".join(errors)
    raise RuntimeError(
        f"Could not read file with any method (declared format was '{declared_format}', "
        f"sniffed real format was '{real_format}'). Attempts:\n       {error_detail}"
    )


def pick_one_resource_per_year(resources, wanted_years):
    """Pick exactly one resource per wanted year, preferring xlsx then csv."""
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


def find_and_save_code_descriptions(network, package_id):
    """Look inside this network's package for a 'Code Description'-type
    resource (subway has one; streetcar/bus likely do too, since TTC
    documents delay codes per mode). If found, download it so transform.py
    can build a real code->description lookup instead of guessing from
    cryptic codes alone."""
    pkg = get_package(package_id)
    code_res = next(
        (r for r in pkg["resources"] if "code" in (r.get("name") or "").lower()
         and "description" in (r.get("name") or "").lower()),
        None
    )
    if not code_res:
        # try a looser match, just "code" in the name
        code_res = next(
            (r for r in pkg["resources"] if "code" in (r.get("name") or "").lower()),
            None
        )
    if not code_res:
        print(f"  No Code Description resource found for {network} — "
              f"will rely on keyword matching only for this network")
        return None

    name = code_res.get("name", "")
    fmt = (code_res.get("format") or "").lower()
    dl_url = code_res.get("url")
    print(f"  Found code description resource: {name} ({fmt}) — downloading")
    resp = requests.get(dl_url, timeout=60)
    resp.raise_for_status()
    df = read_any_table(resp.content, fmt)

    out_path = os.path.join(OUTPUT_DIR, f"ttc_{network}_code_descriptions.csv")
    df.to_csv(out_path, index=False)
    print(f"  Saved: {out_path}  (columns: {list(df.columns)})")
    return out_path


def extract_network(network):
    print(f"\n{'='*60}\nSearching for '{network}' delay dataset(s)...")
    candidates = search_packages(NETWORK_SEARCH_TERMS[network])
    if not candidates:
        print(f"  No packages found for {network}. Skipping — flag this to the team.")
        return None

    print(f"  Found {len(candidates)} candidate package(s):")
    for c in candidates:
        print(f"    - {c['id']}  |  {c.get('title')}")

    # Use the first candidate whose resources actually match our wanted years.
    chosen_package_id = None
    for candidate in candidates:
        pkg = get_package(candidate["id"])
        picked = pick_one_resource_per_year(pkg["resources"], WANTED_YEARS)
        if picked:
            print(f"  Using package: {candidate['id']} ({len(picked)} year-file(s) matched)")
            chosen_package_id = candidate["id"]
            break
    else:
        print(f"  None of the candidate packages had files matching {WANTED_YEARS}. "
              f"Manual check needed for {network}.")
        return None

    find_and_save_code_descriptions(network, chosen_package_id)

    frames = []
    for res in picked:
        name = res.get("name", "")
        fmt = (res.get("format") or "").lower()
        dl_url = res.get("url")
        print(f"  Downloading: {name} ({fmt})")
        resp = requests.get(dl_url, timeout=120)
        resp.raise_for_status()
        df = read_any_table(resp.content, fmt)
        df["source_file"] = name
        frames.append(df)
        print(f"     -> {len(df):,} rows")

    combined = pd.concat(frames, ignore_index=True)
    out_path = os.path.join(OUTPUT_DIR, f"ttc_{network}_delays_2023_2026.csv")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    combined.to_csv(out_path, index=False)

    print(f"  DONE. {network}: {len(combined):,} rows -> {out_path}")
    print(f"  Columns: {list(combined.columns)}")
    return out_path


def main():
    results = {}
    for network in NETWORK_SEARCH_TERMS:
        results[network] = extract_network(network)

    print(f"\n{'='*60}\nSUMMARY")
    for network, path in results.items():
        status = path if path else "FAILED — needs manual check"
        print(f"  {network:10s}: {status}")


if __name__ == "__main__":
    main()
