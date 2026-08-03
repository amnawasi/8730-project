"""
Diagnostic analysis: weather vs. temporal patterns vs. major sports
events, compared for their relationship to TTC delays across all three
networks (subway/streetcar/bus), broken down by delay category.

Produces one combined figure per analysis area (not one chart per
variable) per the professor's feedback on the last project — related
variables are shown together so the reader isn't stitching separate
charts together mentally. Key thresholds are labeled directly on the
charts, not just described in text.

Requires (beyond requirements.txt): pip install kaleido
(kaleido is what lets plotly export static PNG images for the report)

Usage:
    python analysis/diagnostic_analysis.py
"""

import os
import pandas as pd
import mysql.connector
from dotenv import load_dotenv
import plotly.graph_objects as go
from plotly.subplots import make_subplots

load_dotenv()

OUT_DIR = os.path.join("analysis", "outputs")
os.makedirs(OUT_DIR, exist_ok=True)

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE", "ttc_delays"),
}

NETWORK_COLORS = {"subway": "#1f77b4", "streetcar": "#d62728", "bus": "#2ca02c"}


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def run_query(conn, sql):
    return pd.read_sql(sql, conn)


# ---------------------------------------------------------------------
# Shared base view (created once; safe to re-run)
# ---------------------------------------------------------------------
DAILY_DELAYS_VIEW = """
CREATE OR REPLACE VIEW daily_delays AS
SELECT
    delay_date, network,
    COUNT(*) AS delay_count,
    SUM(min_delay) AS total_delay_minutes,
    AVG(min_delay) AS avg_delay_minutes
FROM delays
GROUP BY delay_date, network;
"""


# ---------------------------------------------------------------------
# ANALYSIS 1: WEATHER
# ---------------------------------------------------------------------
def analyze_weather(conn):
    temp_q = """
        SELECT network,
            CASE WHEN w.mean_temp_c < -10 THEN '< -10C'
                 WHEN w.mean_temp_c < 0   THEN '-10 to 0C'
                 WHEN w.mean_temp_c < 15  THEN '0 to 15C'
                 ELSE '> 15C' END AS bucket,
            AVG(d.delay_count) AS avg_daily_delays
        FROM daily_delays d JOIN weather w ON d.delay_date = w.date
        GROUP BY network, bucket
    """
    snow_q = """
        SELECT network,
            CASE WHEN w.snow_on_grnd_cm IS NULL OR w.snow_on_grnd_cm = 0 THEN 'No snow'
                 WHEN w.snow_on_grnd_cm < 5  THEN '1-5cm'
                 WHEN w.snow_on_grnd_cm < 15 THEN '5-15cm'
                 ELSE '15cm+' END AS bucket,
            AVG(d.delay_count) AS avg_daily_delays
        FROM daily_delays d JOIN weather w ON d.delay_date = w.date
        GROUP BY network, bucket
    """
    precip_q = """
        SELECT network,
            CASE WHEN w.total_precip_mm IS NULL OR w.total_precip_mm = 0 THEN 'None'
                 WHEN w.total_precip_mm < 5  THEN 'Light'
                 WHEN w.total_precip_mm < 15 THEN 'Moderate'
                 ELSE 'Heavy' END AS bucket,
            AVG(d.delay_count) AS avg_daily_delays
        FROM daily_delays d JOIN weather w ON d.delay_date = w.date
        GROUP BY network, bucket
    """
    temp_order = ['< -10C', '-10 to 0C', '0 to 15C', '> 15C']
    snow_order = ['No snow', '1-5cm', '5-15cm', '15cm+']
    precip_order = ['None', 'Light', 'Moderate', 'Heavy']

    temp_df = run_query(conn, temp_q)
    snow_df = run_query(conn, snow_q)
    precip_df = run_query(conn, precip_q)

    fig = make_subplots(rows=1, cols=3, subplot_titles=(
        "Temperature", "Snow on ground", "Precipitation"))

    for i, (df, order, col) in enumerate(
        [(temp_df, temp_order, 1), (snow_df, snow_order, 2), (precip_df, precip_order, 3)]
    ):
        for network in NETWORK_COLORS:
            sub = df[df["network"] == network].set_index("bucket").reindex(order)
            fig.add_trace(
                go.Bar(x=order, y=sub["avg_daily_delays"], name=network,
                       marker_color=NETWORK_COLORS[network],
                       showlegend=(i == 0)),
                row=1, col=col
            )

    fig.update_layout(
        title="Weather vs. Average Daily Delays, by Network",
        barmode="group", height=450, width=1200,
        annotations=list(fig.layout.annotations) + [
            dict(text="Threshold: 15cm+ snow on ground marks heaviest winter conditions",
                 xref="paper", yref="paper", x=0.5, y=-0.15, showarrow=False, font=dict(size=10))
        ]
    )
    fig.write_image(os.path.join(OUT_DIR, "chart_weather_vs_delays.png"))
    print(f"Saved: {os.path.join(OUT_DIR, 'chart_weather_vs_delays.png')}")

    combined = pd.concat([
        temp_df.assign(factor="temperature"),
        snow_df.assign(factor="snow_on_ground"),
        precip_df.assign(factor="precipitation"),
    ])
    combined.to_csv(os.path.join(OUT_DIR, "weather_vs_delays.csv"), index=False)
    return combined


# ---------------------------------------------------------------------
# ANALYSIS 2: TEMPORAL PATTERNS
# ---------------------------------------------------------------------
def analyze_temporal(conn):
    rush_q = """
        SELECT network, is_rush_hour, COUNT(*) AS incident_count
        FROM delays GROUP BY network, is_rush_hour
    """
    weekend_q = """
        SELECT dd.network, dt.is_weekend, AVG(dd.delay_count) AS avg_daily_delays
        FROM daily_delays dd JOIN date_dim dt ON dd.delay_date = dt.date
        GROUP BY dd.network, dt.is_weekend
    """
    holiday_q = """
        SELECT dd.network, dt.is_holiday, AVG(dd.delay_count) AS avg_daily_delays
        FROM daily_delays dd JOIN date_dim dt ON dd.delay_date = dt.date
        GROUP BY dd.network, dt.is_holiday
    """
    season_q = """
        SELECT dd.network, dt.season, AVG(dd.delay_count) AS avg_daily_delays
        FROM daily_delays dd JOIN date_dim dt ON dd.delay_date = dt.date
        GROUP BY dd.network, dt.season
    """
    rush_df = run_query(conn, rush_q)
    weekend_df = run_query(conn, weekend_q)
    holiday_df = run_query(conn, holiday_q)
    season_df = run_query(conn, season_q)

    season_order = ["Winter", "Spring", "Summer", "Fall"]

    fig = make_subplots(rows=1, cols=4, subplot_titles=(
        "Rush hour share of incidents (%)", "Weekday vs Weekend",
        "Holiday vs Non-holiday", "By season"))

    for network in NETWORK_COLORS:
        sub = rush_df[rush_df["network"] == network]
        total = sub["incident_count"].sum()
        rush_pct = sub[sub["is_rush_hour"] == 1]["incident_count"].sum() / total * 100
        fig.add_trace(go.Bar(x=[network], y=[rush_pct], marker_color=NETWORK_COLORS[network],
                              name=network, legendgroup=network, showlegend=True), row=1, col=1)

        sub = weekend_df[weekend_df["network"] == network].set_index("is_weekend")
        fig.add_trace(go.Bar(x=["Weekday", "Weekend"],
                              y=[sub.loc[0, "avg_daily_delays"] if 0 in sub.index else 0,
                                 sub.loc[1, "avg_daily_delays"] if 1 in sub.index else 0],
                              marker_color=NETWORK_COLORS[network], name=network,
                              legendgroup=network, showlegend=False), row=1, col=2)

        sub = holiday_df[holiday_df["network"] == network].set_index("is_holiday")
        fig.add_trace(go.Bar(x=["Non-holiday", "Holiday"],
                              y=[sub.loc[0, "avg_daily_delays"] if 0 in sub.index else 0,
                                 sub.loc[1, "avg_daily_delays"] if 1 in sub.index else 0],
                              marker_color=NETWORK_COLORS[network], name=network,
                              legendgroup=network, showlegend=False), row=1, col=3)

        sub = season_df[season_df["network"] == network].set_index("season").reindex(season_order)
        fig.add_trace(go.Bar(x=season_order, y=sub["avg_daily_delays"],
                              marker_color=NETWORK_COLORS[network], name=network,
                              legendgroup=network, showlegend=False), row=1, col=4)

    fig.update_layout(title="Temporal Patterns vs. Delays, by Network",
                       barmode="group", height=450, width=1400)
    fig.write_image(os.path.join(OUT_DIR, "chart_temporal_vs_delays.png"))
    print(f"Saved: {os.path.join(OUT_DIR, 'chart_temporal_vs_delays.png')}")

    rush_df.to_csv(os.path.join(OUT_DIR, "temporal_rush_hour.csv"), index=False)
    weekend_df.to_csv(os.path.join(OUT_DIR, "temporal_weekend.csv"), index=False)
    holiday_df.to_csv(os.path.join(OUT_DIR, "temporal_holiday.csv"), index=False)
    season_df.to_csv(os.path.join(OUT_DIR, "temporal_season.csv"), index=False)
    return {"rush": rush_df, "weekend": weekend_df, "holiday": holiday_df, "season": season_df}


# ---------------------------------------------------------------------
# ANALYSIS 3: SPORTS EVENTS
# ---------------------------------------------------------------------
def analyze_events(conn):
    event_q = """
        SELECT dd.network,
               CASE WHEN se.event_date IS NOT NULL THEN 'Event day' ELSE 'No event' END AS day_type,
               AVG(dd.delay_count) AS avg_daily_delays
        FROM daily_delays dd
        LEFT JOIN (SELECT DISTINCT event_date FROM sports_events) se
            ON dd.delay_date = se.event_date
        GROUP BY dd.network, day_type
    """
    league_q = """
        SELECT dd.network, se.league, AVG(dd.delay_count) AS avg_daily_delays
        FROM daily_delays dd JOIN sports_events se ON dd.delay_date = se.event_date
        GROUP BY dd.network, se.league
    """
    event_df = run_query(conn, event_q)
    league_df = run_query(conn, league_q)

    fig = make_subplots(rows=1, cols=2, subplot_titles=(
        "Any event day vs. no event", "By league"))

    for network in NETWORK_COLORS:
        sub = event_df[event_df["network"] == network].set_index("day_type")
        fig.add_trace(go.Bar(
            x=["No event", "Event day"],
            y=[sub.loc["No event", "avg_daily_delays"] if "No event" in sub.index else 0,
               sub.loc["Event day", "avg_daily_delays"] if "Event day" in sub.index else 0],
            marker_color=NETWORK_COLORS[network], name=network,
            showlegend=True), row=1, col=1)

        sub = league_df[league_df["network"] == network]
        fig.add_trace(go.Bar(x=sub["league"], y=sub["avg_daily_delays"],
                              marker_color=NETWORK_COLORS[network], showlegend=False), row=1, col=2)

    fig.update_layout(
        title="Major Sports Events vs. Delays, by Network",
        barmode="group", height=450, width=1000,
        annotations=list(fig.layout.annotations) + [
            dict(text="Note: city-wide comparison, not filtered by proximity to venue/route",
                 xref="paper", yref="paper", x=0.5, y=-0.15, showarrow=False, font=dict(size=10))
        ]
    )
    fig.write_image(os.path.join(OUT_DIR, "chart_events_vs_delays.png"))
    print(f"Saved: {os.path.join(OUT_DIR, 'chart_events_vs_delays.png')}")

    event_df.to_csv(os.path.join(OUT_DIR, "events_vs_delays.csv"), index=False)
    league_df.to_csv(os.path.join(OUT_DIR, "events_by_league.csv"), index=False)
    return {"event": event_df, "league": league_df}


# ---------------------------------------------------------------------
# ANALYSIS 4: CROSS-FACTOR RANKING — the headline "which matters most"
# ---------------------------------------------------------------------
def cross_factor_ranking(weather_df, temporal, events_df):
    rows = []

    for network in NETWORK_COLORS:
        # weather: heaviest snow bucket vs no-snow baseline
        snow = weather_df[(weather_df["factor"] == "snow_on_ground") & (weather_df["network"] == network)]
        high = snow[snow["bucket"] == "15cm+"]["avg_daily_delays"]
        base = snow[snow["bucket"] == "No snow"]["avg_daily_delays"]
        if len(high) and len(base) and base.values[0] > 0:
            pct = (high.values[0] - base.values[0]) / base.values[0] * 100
            rows.append({"network": network, "factor": "Heavy snow (15cm+)", "pct_lift": pct})

        # temporal: weekend vs weekday
        wk = temporal["weekend"][temporal["weekend"]["network"] == network].set_index("is_weekend")
        if 0 in wk.index and 1 in wk.index and wk.loc[0, "avg_daily_delays"] > 0:
            pct = (wk.loc[1, "avg_daily_delays"] - wk.loc[0, "avg_daily_delays"]) / wk.loc[0, "avg_daily_delays"] * 100
            rows.append({"network": network, "factor": "Weekend vs weekday", "pct_lift": pct})

        # events: any event day vs no event
        ev = events_df["event"][events_df["event"]["network"] == network].set_index("day_type")
        if "No event" in ev.index and "Event day" in ev.index and ev.loc["No event", "avg_daily_delays"] > 0:
            pct = (ev.loc["Event day", "avg_daily_delays"] - ev.loc["No event", "avg_daily_delays"]) \
                  / ev.loc["No event", "avg_daily_delays"] * 100
            rows.append({"network": network, "factor": "Any sports event day", "pct_lift": pct})

    ranking = pd.DataFrame(rows)
    ranking.to_csv(os.path.join(OUT_DIR, "cross_factor_ranking.csv"), index=False)

    fig = go.Figure()
    for network in NETWORK_COLORS:
        sub = ranking[ranking["network"] == network]
        fig.add_trace(go.Bar(x=sub["factor"], y=sub["pct_lift"], name=network,
                              marker_color=NETWORK_COLORS[network]))
    fig.update_layout(
        title="Which Factor Drives Delays Most? (% change vs. baseline)",
        yaxis_title="% change in avg daily delays vs. baseline",
        barmode="group", height=500, width=900
    )
    fig.write_image(os.path.join(OUT_DIR, "chart_cross_factor_ranking.png"))
    print(f"Saved: {os.path.join(OUT_DIR, 'chart_cross_factor_ranking.png')}")

    print("\n=== CROSS-FACTOR RANKING (% change vs baseline) ===")
    print(ranking.sort_values("pct_lift", ascending=False).to_string(index=False))
    return ranking


def main():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(DAILY_DELAYS_VIEW)
    conn.commit()
    cur.close()
    print("daily_delays view ready.\n")

    print("=== Weather analysis ===")
    weather_df = analyze_weather(conn)

    print("\n=== Temporal analysis ===")
    temporal = analyze_temporal(conn)

    print("\n=== Sports events analysis ===")
    events_df = analyze_events(conn)

    print("\n=== Cross-factor ranking ===")
    cross_factor_ranking(weather_df, temporal, events_df)

    conn.close()
    print(f"\nAll outputs saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
