"""
Load raw incident text into MongoDB's raw_delay_incidents collection,
linked back to MySQL via delay_id.

Depends on etl/load_mysql.py having already run: that script writes
data/processed/delay_id_mapping.csv, which pairs each MySQL delays.delay_id
with the raw free-text incident description (only available for
streetcar/bus — subway's "Code" field is a short structured code, not
free text, so subway rows have nothing to store here and are skipped).

Run order matters:
    1. python etl/load_mysql.py   (generates delay_id_mapping.csv)
    2. python etl/load_mongo.py   (this script)

Re-runnable: drops and reloads raw_delay_incidents each run, so running
this twice doesn't create duplicates.

Usage:
    python etl/load_mongo.py
"""

import os
from datetime import datetime, timezone
import certifi
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

PROCESSED_DIR = os.path.join("data", "processed")
MAPPING_CSV = os.path.join(PROCESSED_DIR, "delay_id_mapping.csv")


def get_db():
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())
    return client["ttc_delays"]


def load_raw_delay_incidents(db):
    if not os.path.exists(MAPPING_CSV):
        print(f"ERROR: {MAPPING_CSV} not found. Run etl/load_mysql.py first — "
              "it generates this mapping file as part of loading the delays table.")
        return

    df = pd.read_csv(MAPPING_CSV, low_memory=False)

    before = len(df)
    df = df.dropna(subset=["raw_text"])
    skipped_no_text = before - len(df)

    docs = []
    now = datetime.now(timezone.utc)
    missing_route = 0
    for _, r in df.iterrows():
        route = r["route_or_line"]
        if pd.isna(route):
            route = "UNKNOWN"
            missing_route += 1
        docs.append({
            "delay_id": int(r["delay_id"]),
            "delay_date": r["date"],
            "network": r["network"],
            "route_or_line": route,
            "raw_text": r["raw_text"],
            "source": r["source"],
            "ingested_at": now,
        })

    coll = db["raw_delay_incidents"]
    coll.delete_many({})  # safe to re-run: clear before reloading
    if docs:
        coll.insert_many(docs)

    print(f"raw_delay_incidents: loaded {len(docs):,} documents "
          f"({skipped_no_text:,} rows skipped — no raw text available, "
          f"expected for subway since its Code field is structured not free-text; "
          f"{missing_route:,} rows had missing route_or_line, filled with 'UNKNOWN')")


def main():
    print("Connecting to MongoDB...")
    db = get_db()
    print("Connected.\n")

    load_raw_delay_incidents(db)

    print("\nDone. Run a quick count_documents({}) on raw_delay_incidents to sanity check.")


if __name__ == "__main__":
    main()