"""
Transform step: map each TTC delay's raw incident `Code` into one of the
four analysis categories from the proposal — mechanical, weather,
operational, crowding — plus derived temporal features (day of week,
rush hour, season).

Code dictionary source:
Official TTC "Code Descriptions" resource, retrieved via the Toronto
Open Data CKAN API (package: ttc-subway-delay-data, resource:
"Code Descriptions.csv"). This is the authoritative TTC-published
code-to-meaning list — NOT a community-compiled guess. All 140 codes
in that file are categorized below based on their official description.

Category judgment calls (documented for transparency):
  - EU* (Equipment/Rail Cars & Shops) -> mostly mechanical (physical
    equipment faults); a few human-error entries -> operational
  - PU* (Plant/Signals/Track) -> mostly mechanical (infrastructure
    faults); weather-related entries (ice/snow, "track weather related")
    -> weather; work-zone/contractor entries -> operational
  - MU* (Miscellaneous/Transportation-subway) -> mixed: passenger
    injuries/incidents -> crowding; crew/staffing/closures -> operational;
    explicit weather/force-majeure -> weather
  - SU* (Security) -> all crowding (every code is a passenger/security
    incident: assault, disorderly patron, bomb threat, etc.)
  - TU* (Transportation/operator-related) -> mostly operational (crew
    and operator behaviour); "Storm Trains" -> weather
  - A few genuinely ambiguous "Other"/"Miscellaneous" entries are left
    as "uncategorized" rather than force-fit into a bucket.

Usage:
    python etl/transform.py
Input:  data/raw/ttc_subway_delays_2023_2025.csv
Output: data/processed/ttc_subway_delays_transformed.csv
        data/processed/unmapped_codes_report.csv (should be near-empty now)
"""

import os
import pandas as pd

INPUT_PATH = os.path.join("data", "raw", "ttc_subway_delays_2023_2025.csv")
OUTPUT_PATH = os.path.join("data", "processed", "ttc_subway_delays_transformed.csv")
UNMAPPED_REPORT_PATH = os.path.join("data", "processed", "unmapped_codes_report.csv")

# ---------------------------------------------------------------------
# Official TTC code -> analysis bucket (mechanical / weather /
# operational / crowding / uncategorized).
# Source: TTC "Code Descriptions" CSV, Toronto Open Data CKAN API.
# ---------------------------------------------------------------------
CODE_TO_BUCKET = {
    # EU* — Equipment / Rail Cars & Shops
    "EUAC": "mechanical", "EUAL": "mechanical", "EUATC": "mechanical",
    "EUBK": "mechanical", "EUBO": "mechanical", "EUCA": "mechanical",
    "EUCC": "mechanical", "EUCD": "mechanical", "EUCH": "mechanical",
    "EUCO": "mechanical", "EUDO": "mechanical", "EUECD": "mechanical",
    "EUHV": "mechanical", "EULT": "mechanical", "EULV": "mechanical",
    "EUME": "operational",  # maintenance human error, not an equipment fault
    "EUNEA": "mechanical", "EUNT": "mechanical", "EUO": "mechanical",
    "EUOE": "operational",  # operator error (signal violation/overshoot)
    "EUOPO": "mechanical", "EUPI": "mechanical", "EUSC": "mechanical",
    "EUTL": "mechanical", "EUTM": "mechanical", "EUTR": "mechanical",
    "EUTRD": "mechanical", "EUVA": "mechanical", "EUVE": "mechanical",
    "EUYRD": "mechanical",

    # MU* — Miscellaneous / Transportation (subway)
    "MUATC": "operational", "MUCL": "operational", "MUCP": "operational",
    "MUCSA": "operational", "MUCU": "operational",
    "MUD": "crowding",   # door problems, passenger-related
    "MUDD": "operational",  # door problems, debris-related
    "MUEC": "operational",
    "MUESA": "operational",
    "MUFM": "weather",   # explicit: "Force Majeure... re: Weather or Major Event"
    "MUFS": "operational",  # fire/smoke, external source
    "MUGD": "uncategorized",  # too vague ("miscellaneous general delays")
    "MUI": "crowding", "MUIE": "operational",  # employee injury, not passenger
    "MUIR": "crowding", "MUIRS": "crowding", "MUIS": "crowding",
    "MULD": "operational", "MUNCA": "operational", "MUNOA": "operational",
    "MUO": "uncategorized",  # "miscellaneous other"
    "MUODC": "mechanical", "MUPAA": "crowding",  # passenger alarm
    "MUPF": "mechanical",  # external power failure
    "MUPLA": "operational", "MUPLB": "operational", "MUPLC": "operational",
    "MUPR1": "crowding",  # train in contact with a person
    "MUSAN": "crowding",  # unsanitary vehicle (passenger-caused)
    "MUSC": "mechanical", "MUTD": "operational", "MUTO": "operational",
    "MUWEA": "weather", "MUWR": "operational",

    # PU* — Plant / Signals / Track
    "PUATC": "mechanical", "PUCBI": "mechanical", "PUCSC": "mechanical",
    "PUCSS": "mechanical", "PUDCS": "mechanical",
    "PUEME": "operational",  # electrical maintenance error (human)
    "PUEO": "mechanical", "PUEWZ": "operational",  # work zone = planned work
    "PUMEL": "crowding",  # escalator/elevator incident involving a person
    "PUMO": "operational",
    "PUMST": "crowding",  # stairway incident involving a person
    "PUOPO": "mechanical", "PUSAC": "mechanical", "PUSBE": "mechanical",
    "PUSCA": "mechanical", "PUSCR": "mechanical",
    "PUSEA": "crowding",  # emergency alarm station (passenger-triggered)
    "PUSI": "mechanical", "PUSIO": "mechanical",
    "PUSIS": "weather",  # "signals track weather related issues"
    "PUSLC": "mechanical", "PUSNT": "mechanical", "PUSO": "mechanical",
    "PUSRA": "mechanical", "PUSSW": "mechanical", "PUSTC": "mechanical",
    "PUSTP": "mechanical", "PUSTS": "mechanical",
    "PUSWZ": "operational",  # work zone
    "PUSZC": "mechanical", "PUT0": "mechanical", "PUTCD": "operational",
    "PUTD": "operational",   # debris at track level, controllable
    "PUTDN": "operational",  # debris at track level, non-controllable
    "PUTIJ": "mechanical",
    "PUTIS": "weather",  # ice/snow related problem
    "PUTNT": "mechanical",
    "PUTOE": "operational",  # operator-related (violations, overshoots)
    "PUTR": "mechanical", "PUTS": "mechanical", "PUTSC": "mechanical",
    "PUTSM": "mechanical", "PUTTC": "mechanical", "PUTTP": "mechanical",
    "PUTWZ": "operational",  # work zones, track

    # SU* — Security (all passenger/security incidents)
    "SUAE": "crowding", "SUAP": "crowding", "SUBT": "crowding",
    "SUCOL": "crowding", "SUDP": "crowding", "SUEAS": "crowding",
    "SUG": "crowding", "SUO": "crowding", "SUPOL": "crowding",
    "SUROB": "crowding", "SUSA": "crowding", "SUSP": "crowding",
    "SUUT": "crowding",

    # TU* — Transportation / operator-related
    "TUATC": "operational", "TUCC": "operational", "TUDOE": "operational",
    "TUKEY": "operational", "TUML": "operational", "TUMVS": "operational",
    "TUNCA": "operational", "TUNIP": "operational", "TUNOA": "operational",
    "TUO": "operational", "TUOPO": "operational", "TUOS": "operational",
    "TUS": "operational", "TUSC": "operational", "TUSET": "operational",
    "TUST": "weather",  # "Storm Trains"
    "TUSUP": "operational", "TUUR": "operational",
}


def map_code_to_bucket(code):
    return CODE_TO_BUCKET.get(code, "uncategorized")


def main():
    if not os.path.exists(INPUT_PATH):
        print(f"Input file not found: {INPUT_PATH}")
        print("Run etl/extract_ttc_delays.py first.")
        return

    df = pd.read_csv(INPUT_PATH)
    print(f"Loaded {len(df):,} rows from {INPUT_PATH}")

    # --- derived temporal features (free — computed from existing columns) ---
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

    # --- code -> category mapping (official TTC dictionary) ---
    df["delay_category"] = df["Code"].apply(map_code_to_bucket)

    # --- report any codes still unmapped (should be near-zero now) ---
    unmapped = df[df["delay_category"] == "uncategorized"]
    unmapped_summary = unmapped["Code"].value_counts().reset_index()
    unmapped_summary.columns = ["Code", "row_count"]

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    unmapped_summary.to_csv(UNMAPPED_REPORT_PATH, index=False)

    print("\n==============================")
    print(f"DONE. Transformed rows: {len(df):,}")
    print(f"Saved to: {OUTPUT_PATH}")
    print("\nDelay category breakdown:")
    print(df["delay_category"].value_counts())
    print(f"\nRush hour rows: {df['is_rush_hour'].sum():,} of {len(df):,}")
    print(f"\nUnmapped/unknown codes: {len(unmapped_summary)} distinct codes "
          f"({len(unmapped):,} rows, {len(unmapped)/len(df)*100:.1f}% of data)")
    if len(unmapped_summary) > 0:
        print(unmapped_summary.head(15).to_string(index=False))


if __name__ == "__main__":
    main()