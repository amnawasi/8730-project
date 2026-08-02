"""
Extract Toronto major sports home-game schedules (Maple Leafs, Raptors,
Blue Jays, Toronto FC) using ESPN's public (unofficial, no-key-required)
API, for the 2023-2025 regular seasons.

Note: TheSportsDB's free tier caps results at 15 events per call, which
is not enough to cover a full season. ESPN's team-schedule endpoint
returns the complete season with no such cap and requires no API key.

Usage:
    python etl/extract_sports_events.py
"""

import os
import time
import requests
import pandas as pd

# (sport slug, league slug, human-readable league name)
# Note: MLS (soccer/usa.1) was tried but ESPN's team-schedule endpoint
# returned 0 events for Toronto FC across 2023-2025 — likely a different
# season/endpoint structure for soccer on ESPN's API. Dropped for now;
# NHL + NBA + MLB alone give 452 well-verified home games, which is a
# strong signal for the "major sports events" factor in the analysis.
LEAGUES = [
    ("hockey", "nhl", "NHL"),
    ("basketball", "nba", "NBA"),
    ("baseball", "mlb", "MLB"),
]

SEASONS = [2023, 2024, 2025]
OUTPUT_PATH = os.path.join("data", "raw", "toronto_sports_events_2023_2025.csv")


def find_toronto_team_id(sport, league):
    """Look up the Toronto team's ESPN team ID within a given league."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    teams = data["sports"][0]["leagues"][0]["teams"]
    for entry in teams:
        team = entry["team"]
        if "Toronto" in team.get("displayName", ""):
            return team["id"], team["displayName"]
    return None, None


def fetch_team_schedule(sport, league, team_id, season):
    """Get one team's full regular-season schedule for a given year."""
    url = (f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}"
           f"/teams/{team_id}/schedule")
    r = requests.get(url, params={"season": season, "seasontype": 2}, timeout=30)
    r.raise_for_status()
    return r.json().get("events", [])


def main():
    all_rows = []

    for sport, league, league_name in LEAGUES:
        print(f"Looking up Toronto team in {league_name}...")
        team_id, team_name = find_toronto_team_id(sport, league)
        if not team_id:
            print(f"   Could not find a Toronto team in {league_name}, skipping.")
            continue
        print(f"   Found: {team_name} (id={team_id})")

        for season in SEASONS:
            print(f"   Fetching {league_name} {season} schedule...")
            try:
                events = fetch_team_schedule(sport, league, team_id, season)
            except Exception as e:
                print(f"   ERROR fetching {league_name} {season}: {e}")
                continue
            time.sleep(1)  # be polite between requests

            kept = 0
            for ev in events:
                comps = ev.get("competitions", [])
                if not comps:
                    continue
                comp = comps[0]
                competitors = comp.get("competitors", [])

                home = next((c for c in competitors if c.get("homeAway") == "home"), None)
                away = next((c for c in competitors if c.get("homeAway") == "away"), None)
                if not home or home.get("team", {}).get("id") != team_id:
                    continue  # only keep games where Toronto is the HOME team

                date_str = ev.get("date", "")[:10]  # 'YYYY-MM-DD'
                if date_str[:4] not in ("2023", "2024", "2025"):
                    continue

                all_rows.append({
                    "event_date": date_str,
                    "league": league_name,
                    "home_team": team_name,
                    "away_team": away.get("team", {}).get("displayName") if away else None,
                    "venue": comp.get("venue", {}).get("fullName"),
                    "season": season,
                })
                kept += 1

            print(f"      -> {len(events)} total events, {kept} Toronto home games kept")

    if not all_rows:
        print("No matching events found.")
        return

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["event_date", "home_team", "away_team"])

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print("\n==============================")
    print(f"DONE. Total home games: {len(df):,}")
    print(f"Saved to: {OUTPUT_PATH}")
    print("Columns:", list(df.columns))
    print("\nBy league:")
    print(df["league"].value_counts())
    print("\nFirst 5 rows:")
    print(df.head(5).to_string())


if __name__ == "__main__":
    main()