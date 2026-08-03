"""
Advanced diagnostic visualizations — deeper, evidence-backing charts to
complement analysis/diagnostic_analysis.py. Adds:
    1. Scatter + trend line: snow/precip (continuous, not bucketed) vs
       daily delay count, per network, with Pearson correlation reported.
       The trend line is a simple descriptive/visual aid only (linear
       fit), NOT a predictive model — consistent with the diagnostic,
       non-predictive framing required for this project.
    2. Time series: daily delay counts over the full date range, with
       major snow events labeled directly on the chart (not just in a
       caption).
    3. Delay category composition: 100% stacked bar showing what TYPE
       of delay dominates each network (mechanical/weather/operational/
       crowding) — a categorical finding not covered by the other charts.
    4. Bubble chart: monthly view tying temperature, snowfall, and delay
       volume together in one figure, per network.

Usage:
    python analysis/advanced_visualizations.py
"""

import os
import pandas as pd
import mysql.connector
from dotenv import load_dotenv
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats

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
# 1. SCATTER + TREND LINE: continuous weather vs delays, with real
#    correlation stats (not just bucket comparisons)
# ---------------------------------------------------------------------
def scatter_weather_correlation(conn):
    q = """
        SELECT d.delay_date, d.network, d.delay_count,
               w.snow_on_grnd_cm, w.total_precip_mm, w.mean_temp_c
        FROM daily_delays d JOIN weather w ON d.delay_date = w.date
    """
    df = run_query(conn, q)

    print("\n=== Pearson correlation: snow on ground vs daily delay count ===")
    correlations = []
    for network in NETWORK_COLORS:
        sub = df[df["network"] == network].dropna(subset=["snow_on_grnd_cm", "delay_count"])
        if len(sub) > 2:
            r, p = stats.pearsonr(sub["snow_on_grnd_cm"], sub["delay_count"])
            correlations.append({"network": network, "r": r, "p_value": p, "n": len(sub)})
            sig = "significant" if p < 0.05 else "not significant"
            print(f"  {network:10s}  r={r:.3f}  p={p:.4f}  (n={len(sub)}, {sig} at α=0.05)")

    pd.DataFrame(correlations).to_csv(os.path.join(OUT_DIR, "snow_delay_correlation.csv"), index=False)

    fig = px.scatter(
        df, x="snow_on_grnd_cm", y="delay_count", color="network",
        facet_col="network", trendline="ols",
        color_discrete_map=NETWORK_COLORS,
        labels={"snow_on_grnd_cm": "Snow on ground (cm)", "delay_count": "Daily delay count"},
        title="Snow on Ground vs. Daily Delays (each point = one day)"
    )
    fig.update_layout(
        height=480, width=1200, showlegend=False,
        margin=dict(b=110),
        annotations=list(fig.layout.annotations) + [
            dict(text="Trend line is a simple linear fit shown for visual pattern only — "
                      "not a predictive model.",
                 xref="paper", yref="paper", x=0.5, y=-0.28, showarrow=False, font=dict(size=10))
        ]
    )
    fig.write_image(os.path.join(OUT_DIR, "chart_scatter_snow_correlation.png"))
    print(f"Saved: {os.path.join(OUT_DIR, 'chart_scatter_snow_correlation.png')}")
    return df


# ---------------------------------------------------------------------
# 2. TIME SERIES with major snow events labeled directly on the chart
# ---------------------------------------------------------------------
def time_series_with_events(conn):
    delay_q = "SELECT delay_date, network, delay_count FROM daily_delays ORDER BY delay_date"
    weather_q = "SELECT date, snow_on_grnd_cm, total_precip_mm FROM weather ORDER BY date"

    delay_df = run_query(conn, delay_q)
    weather_df = run_query(conn, weather_q)

    # Pick distinct storms with enough separation to be readable on a ~4-year-wide
    # chart. 14 days apart is enough to be different STORMS, but not enough to be
    # visually separated as TEXT LABELS on a timeline this compressed — need a much
    # wider gap (90 days) purely for label readability.
    candidates = weather_df.dropna(subset=["snow_on_grnd_cm"]).sort_values(
        "snow_on_grnd_cm", ascending=False)
    top_snow_days = []
    for _, row in candidates.iterrows():
        if len(top_snow_days) >= 3:
            break
        row_date = pd.to_datetime(row["date"])
        if all(abs((row_date - pd.to_datetime(d["date"])).days) >= 90 for d in top_snow_days):
            top_snow_days.append(row)
    top_snow_days = pd.DataFrame(top_snow_days)

    fig = go.Figure()
    for network in NETWORK_COLORS:
        sub = delay_df[delay_df["network"] == network].sort_values("delay_date")
        # 7-day rolling average to make the trend readable (raw daily is noisy)
        sub = sub.set_index("delay_date")
        sub["rolling"] = sub["delay_count"].rolling(7, min_periods=1).mean()
        fig.add_trace(go.Scatter(
            x=sub.index, y=sub["rolling"], mode="lines", name=network,
            line=dict(color=NETWORK_COLORS[network], width=1.5)
        ))

    for _, row in top_snow_days.iterrows():
        fig.add_vline(x=row["date"], line_dash="dot", line_color="gray", opacity=0.6)
        fig.add_annotation(
            x=row["date"], y=1.02, yref="paper", showarrow=False,
            text=f"{row['date']}<br>{row['snow_on_grnd_cm']:.0f}cm snow",
            font=dict(size=9), textangle=0
        )

    fig.update_layout(
        title="Daily Delays Over Time (7-day rolling average), with Major Snow Events Labeled",
        xaxis_title="Date", yaxis_title="7-day avg daily delay count",
        height=550, width=1300, margin=dict(t=90, b=80),
        legend=dict(orientation="h", yanchor="top", y=-0.15)
    )
    fig.write_image(os.path.join(OUT_DIR, "chart_timeseries_with_events.png"))
    print(f"Saved: {os.path.join(OUT_DIR, 'chart_timeseries_with_events.png')}")


# ---------------------------------------------------------------------
# 3. DELAY CATEGORY COMPOSITION — 100% stacked bar per network
# ---------------------------------------------------------------------
def category_composition(conn):
    q = """
        SELECT network, delay_category, COUNT(*) AS n
        FROM delays
        WHERE delay_category != 'uncategorized'
        GROUP BY network, delay_category
    """
    df = run_query(conn, q)
    totals = df.groupby("network")["n"].transform("sum")
    df["pct"] = df["n"] / totals * 100

    category_colors = {
        "mechanical": "#636efa", "weather": "#00cc96",
        "operational": "#ab63fa", "crowding": "#ffa15a"
    }

    fig = px.bar(
        df, x="network", y="pct", color="delay_category",
        color_discrete_map=category_colors,
        labels={"pct": "% of categorized incidents", "network": "Network"},
        title="Delay Category Composition by Network (uncategorized excluded)",
        text=df["pct"].round(1).astype(str) + "%"
    )
    fig.update_layout(barmode="stack", height=500, width=700)
    fig.write_image(os.path.join(OUT_DIR, "chart_category_composition.png"))
    print(f"Saved: {os.path.join(OUT_DIR, 'chart_category_composition.png')}")
    df.to_csv(os.path.join(OUT_DIR, "category_composition.csv"), index=False)


# ---------------------------------------------------------------------
# 4. BUBBLE CHART: monthly temp + snow + delay volume, per network
# ---------------------------------------------------------------------
def bubble_monthly_summary(conn):
    q = """
        SELECT YEAR(d.delay_date) AS yr, MONTH(d.delay_date) AS mo,
               d.network,
               AVG(w.mean_temp_c) AS avg_temp,
               SUM(w.snow_on_grnd_cm) AS total_snow_cm_days,
               SUM(d.delay_count) AS total_delays
        FROM daily_delays d JOIN weather w ON d.delay_date = w.date
        GROUP BY yr, mo, d.network
    """
    df = run_query(conn, q)
    df["year_month"] = df["yr"].astype(str) + "-" + df["mo"].astype(str).str.zfill(2)
    df = df.dropna(subset=["avg_temp", "total_snow_cm_days", "total_delays"])
    df["total_snow_cm_days"] = df["total_snow_cm_days"].clip(lower=0.1)  # bubble size can't be 0/negative

    fig = px.scatter(
        df, x="avg_temp", y="total_delays", size="total_snow_cm_days",
        color="network", color_discrete_map=NETWORK_COLORS,
        hover_data=["year_month"],
        labels={"avg_temp": "Avg monthly temperature (C)",
                "total_delays": "Total monthly delays",
                "total_snow_cm_days": "Cumulative snow-on-ground (cm-days)"},
        title="Monthly View: Temperature, Snow, and Delay Volume Together (bubble size = snow)"
    )
    fig.update_layout(height=550, width=1000)
    fig.write_image(os.path.join(OUT_DIR, "chart_bubble_monthly.png"))
    print(f"Saved: {os.path.join(OUT_DIR, 'chart_bubble_monthly.png')}")
    df.to_csv(os.path.join(OUT_DIR, "monthly_summary.csv"), index=False)


def main():
    conn = get_connection()

    print("=== Scatter + correlation: snow vs delays ===")
    scatter_weather_correlation(conn)

    print("\n=== Time series with event labels ===")
    time_series_with_events(conn)

    print("\n=== Delay category composition ===")
    category_composition(conn)

    print("\n=== Bubble chart: monthly temp/snow/delays ===")
    bubble_monthly_summary(conn)

    conn.close()
    print(f"\nAll outputs saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
