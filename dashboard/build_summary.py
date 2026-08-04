"""
Build a small, dashboard-ready summary from the full transformed delay
data — small enough to commit to GitHub and deploy on Streamlit Cloud,
instead of pushing the ~80MB row-level file.

Usage:
    python dashboard/build_summary.py
Output:
    data/processed/dashboard_summary.csv   (~a few hundred KB)
"""

import os
import pandas as pd

IN_PATH = os.path.join("data", "processed", "ttc_delays_transformed.csv")
OUT_PATH = os.path.join("data", "processed", "dashboard_summary.csv")

KEEP_COLS = ["date", "network", "delay_category", "is_weekend", "is_rush_hour"]


def main():
    df = pd.read_csv(IN_PATH, low_memory=False, usecols=lambda c: c in KEEP_COLS)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # one row per (date, network, delay_category) with a count — this is
    # all the dashboard's charts actually need; drops the 349K individual
    # incident rows down to a few thousand summary rows.
    summary = (df.dropna(subset=["date"])
               .groupby(["date", "network", "delay_category", "is_weekend", "is_rush_hour"])
               .size().reset_index(name="count"))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    summary.to_csv(OUT_PATH, index=False)

    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"DONE. Summary rows: {len(summary):,} (from {len(df):,} raw rows)")
    print(f"Saved to: {OUT_PATH}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()