"""
TTC Delay Analytics Dashboard.
Reads the pre-aggregated summary file (small, git/deploy-friendly)
built by dashboard/build_summary.py — not the full 349K-row file.

Run:
    streamlit run dashboard/app.py
"""

import os
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------------------
# Page config + design tokens
# ---------------------------------------------------------------------
st.set_page_config(page_title="TTC Delay Analytics", layout="wide", initial_sidebar_state="expanded")

BG = "#0B0F14"
SURFACE = "#131A22"
SURFACE_2 = "#1A2330"
TEXT = "#E8EDF2"
TEXT_MUTED = "#7C8B9A"
BORDER = "#232E3C"

PALETTE_MAROON = "#7A0C0C"
PALETTE_RED = "#C41E3A"
PALETTE_CREAM = "#FBE8CC"
PALETTE_NAVY = "#0B3554"
PALETTE_STEEL = "#6D96B5"

TTC_RED = PALETTE_RED

CATEGORY_COLORS = {
    "crowding": PALETTE_RED,
    "mechanical": PALETTE_MAROON,
    "operational": PALETTE_STEEL,
    "weather": PALETTE_CREAM,
    "uncategorized": PALETTE_NAVY,
}
NETWORK_COLORS = {"subway": PALETTE_RED, "streetcar": PALETTE_CREAM, "bus": PALETTE_STEEL}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700;800;900&family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    background-color: {BG};
    color: {TEXT};
}}
.stApp {{ background-color: {BG}; }}
section[data-testid="stSidebar"] {{ background-color: {SURFACE}; border-right: 1px solid {BORDER}; }}

h1, h2, h3 {{ font-family: 'Space Grotesk', sans-serif; color: {TEXT}; }}
h1 {{ font-weight: 900; letter-spacing: -0.02em; font-size: 3rem !important; }}
h2, h3 {{ font-weight: 800; font-size: 1.7rem !important; }}
p, span, div {{ font-weight: 600; }}

.kpi-card {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-left: 4px solid {TTC_RED};
    border-radius: 8px;
    padding: 20px 22px;
}}
.kpi-label {{ font-size: 0.85rem; color: {TEXT_MUTED}; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }}
.kpi-value {{ font-family: 'Space Grotesk', sans-serif; font-size: 2.6rem; font-weight: 900; color: {TEXT}; margin-top: 4px; }}

.section-eyebrow {{ color: {TTC_RED}; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 800; }}

hr {{ border-color: {BORDER}; }}
[data-testid="stMetricValue"] {{ color: {TEXT}; }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Data loading — reads the small pre-aggregated summary, not the raw file
# ---------------------------------------------------------------------
DATA_PATH = os.path.join("data", "processed", "dashboard_summary.csv")
WEATHER_PATH = os.path.join("data", "processed", "toronto_weather_cleaned.csv")

@st.cache_data
def load_data():
    df = pd.read_csv(DATA_PATH)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df

@st.cache_data
def load_weather():
    if not os.path.exists(WEATHER_PATH):
        return None
    w = pd.read_csv(WEATHER_PATH, low_memory=False)
    date_col = "Date/Time" if "Date/Time" in w.columns else ("date" if "date" in w.columns else None)
    if date_col is None:
        return None
    w = w.rename(columns={date_col: "date"})
    w["date"] = pd.to_datetime(w["date"], errors="coerce")
    return w

if not os.path.exists(DATA_PATH):
    st.error(f"Data file not found: {DATA_PATH}. Run dashboard/build_summary.py first "
             f"(after etl/transform.py has produced ttc_delays_transformed.csv).")
    st.stop()

df = load_data()
weather = load_weather()

required = ["network", "delay_category", "count"]
missing = [c for c in required if c not in df.columns]
if missing:
    st.error(f"Missing expected columns: {missing}. Available: {list(df.columns)}")
    st.stop()

# ---------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------
st.sidebar.markdown("### Filters")

networks_available = sorted(df["network"].dropna().unique())
selected_networks = st.sidebar.multiselect("Network", networks_available, default=networks_available)

if df["date"].notna().any():
    min_d, max_d = df["date"].min().date(), df["date"].max().date()
    date_range = st.sidebar.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
else:
    date_range = None

filtered = df[df["network"].isin(selected_networks)]
if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[(filtered["date"].dt.date >= start) & (filtered["date"].dt.date <= end)]

# ---------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------
st.markdown('<div class="section-eyebrow">TTC OPERATIONS ANALYTICS</div>', unsafe_allow_html=True)
st.markdown("# What Drives Transit Delays Most?")
st.markdown(
    f'<p style="color:{TEXT_MUTED}; font-size:1.05rem; max-width:720px;">'
    "A diagnostic comparison of weather, temporal patterns, and major sports events "
    "against TTC subway, streetcar, and bus delays (2023–2026).</p>",
    unsafe_allow_html=True,
)
st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# KPI row (all weighted by the 'count' column, not row count)
# ---------------------------------------------------------------------
total = filtered["count"].sum()
crowding_pct = (filtered.loc[filtered["delay_category"] == "crowding", "count"].sum() / total * 100) if total else 0
rush_pct = (filtered.loc[filtered["is_rush_hour"] == True, "count"].sum() / total * 100) if total and "is_rush_hour" in filtered.columns else None
n_networks = filtered["network"].nunique()

k1, k2, k3, k4 = st.columns(4)
kpis = [
    (k1, "Total Delays", f"{total:,.0f}"),
    (k2, "Networks Shown", f"{n_networks}"),
    (k3, "Caused by Crowding", f"{crowding_pct:.0f}%"),
    (k4, "During Rush Hour", f"{rush_pct:.0f}%" if rush_pct is not None else "n/a"),
]
for col, label, value in kpis:
    col.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Hero chart: which factor drives delays most (category share)
# ---------------------------------------------------------------------
st.markdown('<div class="section-eyebrow">KEY FINDING</div>', unsafe_allow_html=True)
st.markdown("### Which Cause Drives Delays Most?")

cat_counts = filtered.groupby("delay_category")["count"].sum()
cat_counts = (cat_counts / cat_counts.sum() * 100).round(1)
cat_counts = cat_counts.reindex(["crowding", "mechanical", "operational", "weather", "uncategorized"]).dropna()

fig_hero = go.Figure(go.Bar(
    x=cat_counts.values,
    y=[c.capitalize() for c in cat_counts.index],
    orientation="h",
    marker_color=[CATEGORY_COLORS.get(c, PALETTE_NAVY) for c in cat_counts.index],
    text=[f"{v}%" for v in cat_counts.values],
    textposition="outside",
    textfont=dict(color=TEXT, size=16, family="Inter"),
))
fig_hero.update_layout(
    plot_bgcolor=BG, paper_bgcolor=BG,
    font=dict(color=TEXT, family="Inter", size=14),
    xaxis=dict(title="% of delays", gridcolor=BORDER, color=TEXT_MUTED, range=[0, max(cat_counts.values) * 1.25]),
    yaxis=dict(color=TEXT, autorange="reversed"),
    margin=dict(l=10, r=10, t=10, b=10),
    height=280,
)
st.plotly_chart(fig_hero, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Category composition by network
# ---------------------------------------------------------------------
st.markdown('<div class="section-eyebrow">BY NETWORK</div>', unsafe_allow_html=True)
st.markdown("### Delay Cause Composition")

comp = filtered.groupby(["network", "delay_category"])["count"].sum().reset_index()
comp["pct"] = comp.groupby("network")["count"].transform(lambda x: x / x.sum() * 100)

fig_comp = px.bar(
    comp, x="network", y="pct", color="delay_category",
    color_discrete_map=CATEGORY_COLORS,
    labels={"pct": "% of delays", "network": "", "delay_category": "Cause"},
)
fig_comp.update_layout(
    plot_bgcolor=BG, paper_bgcolor=BG,
    font=dict(color=TEXT, family="Inter", size=14),
    xaxis=dict(color=TEXT, gridcolor=BORDER),
    yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
    margin=dict(l=10, r=10, t=10, b=10),
    height=380,
    barmode="stack",
)
st.plotly_chart(fig_comp, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Daily delays over time (line chart)
# ---------------------------------------------------------------------
if filtered["date"].notna().any():
    st.markdown('<div class="section-eyebrow">OVER TIME</div>', unsafe_allow_html=True)
    st.markdown("### Daily Delays — 7-Day Rolling Average")

    daily = filtered.dropna(subset=["date"]).groupby("date")["count"].sum().reset_index()
    daily = daily.sort_values("date")
    daily["rolling"] = daily["count"].rolling(7, min_periods=1).mean()

    fig_ts = go.Figure()
    fig_ts.add_trace(go.Scatter(
        x=daily["date"], y=daily["rolling"], mode="lines",
        line=dict(color=TTC_RED, width=2), name="7-day avg delays",
        fill="tozeroy", fillcolor="rgba(196,30,58,0.10)",
    ))

    if len(daily) > 7:
        peak = daily.loc[daily["rolling"].idxmax()]
        fig_ts.add_annotation(
            x=peak["date"], y=peak["rolling"],
            text=f"Peak: {peak['date'].date()}",
            showarrow=True, arrowcolor=TEXT_MUTED, font=dict(color=TEXT, size=11),
            arrowhead=2, ay=-35,
        )

    fig_ts.update_layout(
        plot_bgcolor=BG, paper_bgcolor=BG,
        font=dict(color=TEXT, family="Inter", size=14),
        xaxis=dict(color=TEXT_MUTED, gridcolor=BORDER),
        yaxis=dict(title="Delays/day (7-day avg)", color=TEXT_MUTED, gridcolor=BORDER),
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
        showlegend=False,
    )
    st.plotly_chart(fig_ts, use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Weather correlation: snow-on-ground vs daily delay count (scatter)
# ---------------------------------------------------------------------
if weather is not None:
    snow_col = next((c for c in weather.columns if "snow on grnd" in c.lower()), None)
    if snow_col and filtered["date"].notna().any():
        st.markdown('<div class="section-eyebrow">WEATHER SIGNAL</div>', unsafe_allow_html=True)
        st.markdown("### Snow on Ground vs. Daily Delays")

        daily_net = filtered.dropna(subset=["date"]).groupby(["date", "network"])["count"].sum().reset_index()
        merged = daily_net.merge(weather[["date", snow_col]], on="date", how="left").dropna(subset=[snow_col])

        if len(merged) > 5:
            fig_scatter = px.scatter(
                merged, x=snow_col, y="count", color="network",
                color_discrete_map=NETWORK_COLORS, trendline="ols",
                labels={snow_col: "Snow on ground (cm)", "count": "Delays that day"},
                opacity=0.55,
            )
            fig_scatter.update_layout(
                plot_bgcolor=BG, paper_bgcolor=BG,
                font=dict(color=TEXT, family="Inter", size=14),
                xaxis=dict(color=TEXT_MUTED, gridcolor=BORDER),
                yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER),
                legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
                margin=dict(l=10, r=10, t=10, b=10),
                height=380,
            )
            st.plotly_chart(fig_scatter, use_container_width=True)
            st.caption("Line is a simple linear fit shown for visual pattern only — not a predictive model.")
            st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# Weekday vs weekend, per network (grouped bar)
# ---------------------------------------------------------------------
if "is_weekend" in filtered.columns:
    st.markdown('<div class="section-eyebrow">TEMPORAL PATTERN</div>', unsafe_allow_html=True)
    st.markdown("### Weekday vs. Weekend Delays, by Network")

    wk = filtered.groupby(["network", "is_weekend"])["count"].sum().reset_index()
    wk["day_type"] = wk["is_weekend"].map({True: "Weekend", False: "Weekday"})

    fig_wk = px.bar(
        wk, x="network", y="count", color="day_type", barmode="group",
        color_discrete_map={"Weekday": TTC_RED, "Weekend": PALETTE_STEEL},
        labels={"count": "Total delays", "network": "", "day_type": ""},
    )
    fig_wk.update_layout(
        plot_bgcolor=BG, paper_bgcolor=BG,
        font=dict(color=TEXT, family="Inter", size=14),
        xaxis=dict(color=TEXT, gridcolor=BORDER),
        yaxis=dict(color=TEXT_MUTED, gridcolor=BORDER),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
        margin=dict(l=10, r=10, t=10, b=10),
        height=350,
    )
    st.plotly_chart(fig_wk, use_container_width=True)

# ---------------------------------------------------------------------
# Raw data (collapsed) — shows the aggregated summary, not row-level data
# ---------------------------------------------------------------------
with st.expander("View data summary sample"):
    st.dataframe(filtered.head(200), use_container_width=True)