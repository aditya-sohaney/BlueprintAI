"""BlueprintAI — Engineering Drawing Intelligence Platform"""

import sys
import time
import sqlite3
import json
import re
import io
import base64
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# App config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="BlueprintAI",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Color palette — single source of truth
# ---------------------------------------------------------------------------
C = {
    "bg":           "#0b1120",
    "bg_card":      "#111a2e",
    "bg_sidebar":   "#0a0f1e",
    "border":       "#1c2d4a",
    "teal":         "#38d9a9",
    "teal_dim":     "#1a6b54",
    "blue":         "#4dabf7",
    "navy":         "#1c3a5f",
    "text":         "#d0dce8",
    "text_muted":   "#6b7f99",
    "green":        "#51cf66",
    "yellow":       "#fcc419",
    "orange":       "#ff922b",
    "red":          "#ff6b6b",
    "purple":       "#b197fc",
    "pink":         "#f06595",
}
CHART_SEQ = [C["teal"], C["blue"], C["yellow"], C["pink"],
             C["purple"], C["green"], C["orange"], C["red"]]

# ---------------------------------------------------------------------------
# Global CSS — dark everywhere, no white leaks
# ---------------------------------------------------------------------------
st.markdown(f"""
<style>
/* ---- hide default Streamlit header/toolbar/footer ---- */
header[data-testid="stHeader"] {{ display: none !important; }}
#MainMenu {{ visibility: hidden; }}
div[data-testid="stToolbar"] {{ display: none !important; }}
div[data-testid="stDecoration"] {{ display: none !important; }}
footer {{ visibility: hidden; background: transparent !important; }}
footer[data-testid="stBottom"],
[data-testid="stBottom"],
.stBottom {{
    background-color: {C["bg"]} !important;
    border: none !important;
}}
[data-testid="stBottom"] > div {{
    background-color: {C["bg"]} !important;
    border: none !important;
}}

/* ---- column vertical alignment ---- */
div[data-testid="stHorizontalBlock"] {{
    align-items: flex-start !important;
}}

/* ---- base ---- */
.stApp {{ background: {C["bg"]}; }}
html, body, [data-testid="stAppViewContainer"] {{ background: {C["bg"]}; }}

/* ---- sidebar ---- */
section[data-testid="stSidebar"] {{
    background: {C["bg_sidebar"]};
    border-right: 1px solid {C["border"]};
    min-width: 22rem !important;
}}
section[data-testid="stSidebar"] > div:first-child {{
    width: 22rem !important;
}}
section[data-testid="stSidebar"] * {{ color: {C["text"]}; }}
/* hide collapse/expand buttons — sidebar stays permanently open */
button[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"] {{
    display: none !important;
}}

/* ---- headings ---- */
h1, h2, h3, h4, h5, h6,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
    color: {C["text"]} !important;
}}

/* ---- body text ---- */
p, span, li, label, .stMarkdown {{
    color: {C["text"]};
}}

/* ---- metric cards ---- */
div[data-testid="stMetric"] {{
    background: {C["bg_card"]};
    border: 1px solid {C["border"]};
    border-radius: 10px;
    padding: 18px 16px 14px 16px;
}}
div[data-testid="stMetric"] label {{ color: {C["text_muted"]} !important; font-size: 0.82em; }}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {{ color: {C["teal"]} !important; }}

/* ---- expander ---- */
details {{ background: {C["bg_card"]}; border: 1px solid {C["border"]}; border-radius: 8px; }}
details summary span {{ color: {C["text"]} !important; }}
[data-testid="stExpander"] {{
    background: {C["bg_card"]}; border: 1px solid {C["border"]}; border-radius: 8px;
}}
[data-testid="stExpander"] details {{
    background: {C["bg_card"]} !important;
}}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
    background: {C["bg_card"]} !important;
}}

/* ---- data frames & tables ---- */
.stDataFrame, .stTable {{ border: 1px solid {C["border"]}; border-radius: 8px; }}
[data-testid="stDataFrame"] div {{ color: {C["text"]}; }}
[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"],
[data-testid="stDataFrame"] .dvn-scroller,
[data-testid="stDataFrame"] iframe {{
    background: {C["bg_card"]} !important;
    border-radius: 8px;
}}
/* Glide Data Grid dark theme variables */
.glideDataEditor, .gdg-style, [data-testid="stDataFrame"] > div {{
    --gdg-bg-cell: {C["bg_card"]} !important;
    --gdg-bg-header: {C["bg"]} !important;
    --gdg-bg-header-has-focus: {C["navy"]} !important;
    --gdg-bg-header-hovered: {C["navy"]} !important;
    --gdg-text-dark: {C["text"]} !important;
    --gdg-text-medium: {C["text_muted"]} !important;
    --gdg-text-light: {C["text_muted"]} !important;
    --gdg-text-header: {C["text"]} !important;
    --gdg-border-color: {C["border"]} !important;
    --gdg-bg-cell-medium: {C["bg_card"]} !important;
    --gdg-bg-bubble: {C["navy"]} !important;
    --gdg-bg-icon-header: {C["text_muted"]} !important;
    --gdg-accent-color: {C["teal"]} !important;
    --gdg-accent-light: {C["navy"]} !important;
}}
/* Force all dataframe containers to dark background */
[data-testid="stDataFrame"] > div > div,
[data-testid="stDataFrame"] > div > div > div {{
    background-color: {C["bg_card"]} !important;
}}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; background: transparent; }}
.stTabs [data-baseweb="tab"] {{
    background: {C["bg_card"]}; border-radius: 6px; color: {C["text_muted"]};
    border: 1px solid {C["border"]};
}}
.stTabs [aria-selected="true"] {{
    background: {C["navy"]} !important; color: {C["teal"]} !important;
    border-color: {C["teal"]} !important;
}}

/* ---- buttons ---- */
.stButton > button {{
    background: {C["navy"]}; color: {C["teal"]};
    border: 1px solid {C["teal"]}; border-radius: 6px;
}}
.stButton > button:hover {{ background: #245070; }}

/* ---- inputs ---- */
.stTextInput > div > div, .stSelectbox > div > div,
.stMultiSelect > div > div, .stTextArea > div > div {{
    background: {C["bg_card"]}; border-color: {C["border"]}; color: {C["text"]};
}}

/* ---- chat ---- */
[data-testid="stChatMessage"] {{
    background: {C["bg_card"]}; border: 1px solid {C["border"]}; border-radius: 10px;
}}
[data-testid="stChatInput"] {{
    background: {C["bg"]} !important;
}}
[data-testid="stChatInput"] > div {{
    background: {C["bg_card"]} !important;
    border-color: {C["border"]} !important;
}}
[data-testid="stChatInput"] textarea {{
    background: {C["bg_card"]} !important;
    color: {C["text"]} !important;
}}
[data-testid="stBottomBlockContainer"] {{
    background: {C["bg"]} !important;
    border: none !important;
}}
[data-testid="stBottomBlockContainer"] > div {{
    background: {C["bg"]} !important;
}}

/* ---- file uploader ---- */
[data-testid="stFileUploader"] {{
    background: {C["bg_card"]}; border: 1px dashed {C["border"]}; border-radius: 10px; padding: 20px;
}}
[data-testid="stFileUploader"] label {{ color: {C["text_muted"]} !important; }}
[data-testid="stFileUploader"] button {{
    background: {C["navy"]}; color: {C["teal"]}; border: 1px solid {C["teal"]};
}}
[data-testid="stFileUploader"] section {{
    background: {C["bg_card"]} !important; border: none !important;
}}
[data-testid="stFileUploader"] section > div {{
    background: {C["bg_card"]} !important;
}}
[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] {{
    background: {C["bg_card"]} !important;
    border: 2px dashed {C["border"]} !important;
    border-radius: 10px !important;
}}
[data-testid="stFileUploaderDropzone"] {{
    background: {C["bg_card"]} !important;
    border: 2px dashed {C["border"]} !important;
}}
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] p {{
    color: {C["text_muted"]} !important;
}}
[data-testid="stFileUploaderDropzone"] button {{
    background: {C["navy"]} !important; color: {C["teal"]} !important;
    border: 1px solid {C["teal"]} !important;
}}

/* ---- select radio (sidebar nav) ---- */
div[data-testid="stRadio"] label span {{ color: {C["text"]} !important; }}

/* ---- progress bar ---- */
.stProgress > div > div {{ background: {C["border"]}; }}
.stProgress > div > div > div {{ background: {C["teal"]}; }}

/* ---- separator ---- */
hr {{ border-color: {C["border"]}; }}

/* ---- download button ---- */
.stDownloadButton > button {{
    background: {C["navy"]}; color: {C["teal"]};
    border: 1px solid {C["teal"]};
}}

/* ---- scrollbar ---- */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: {C["bg"]}; }}
::-webkit-scrollbar-thumb {{ background: {C["border"]}; border-radius: 3px; }}

/* ---- chip buttons ---- */
.chip {{
    display: inline-block; padding: 6px 16px; margin: 4px;
    background: {C["bg_card"]}; border: 1px solid {C["border"]};
    border-radius: 20px; color: {C["text_muted"]}; font-size: 0.85em;
    cursor: pointer; transition: all 0.2s;
}}
.chip:hover {{ border-color: {C["teal"]}; color: {C["teal"]}; }}

/* ---- card helper ---- */
.card {{
    background: {C["bg_card"]}; border: 1px solid {C["border"]};
    border-radius: 10px; padding: 20px; margin: 8px 0;
}}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "data" / "database" / "adot_drawings.db"

EXTRACT_FIELDS = [
    "drawing_title", "location", "route", "project_number",
    "sheet_number", "total_sheets", "initial_date", "initial_designer",
    "final_date", "final_drafter", "rfc_date", "rfc_checker",
    "rw_number", "tracs_number", "structure_number", "milepost",
    "division", "engineer_stamp_name",
]


@st.cache_data(ttl=120)
def load_data():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    df = pd.read_sql_query("SELECT * FROM drawings", conn)
    conn.close()
    return df


def run_sql(sql):
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


def field_fill(df, field):
    return (df[field].notna() & (df[field] != "")).sum()


def fill_pct(df, field):
    return field_fill(df, field) / len(df) * 100 if len(df) else 0


def overall_fill(df):
    return sum(fill_pct(df, f) for f in EXTRACT_FIELDS) / len(EXTRACT_FIELDS)


# ── Cached pipeline components (loaded once, stay in memory) ──
@st.cache_resource
def get_ocr_engine():
    """Cache OCREngine + PaddleOCR model across all reruns."""
    from core.ocr_engine import OCREngine
    engine = OCREngine()
    engine._get_paddle()  # Force PaddleOCR model load now
    return engine


@st.cache_resource
def get_pipeline_components():
    """Cache TitleBlockExtractor, RegexExtractor, ResultMerger."""
    from core.title_block import TitleBlockExtractor
    from core.regex_extractor import RegexExtractor
    from core.merger import ResultMerger
    return TitleBlockExtractor(), RegexExtractor(), ResultMerger()


def render_table(dataframe, max_rows=100, max_height="400px"):
    """Render a pandas DataFrame as a styled HTML table with dark theme."""
    show = dataframe.head(max_rows)
    hdr_bg, row_even, row_odd = "#0D7377", "#0A2342", "#112240"
    txt, border = "#E2E8F0", "#1B4F8A"
    html = (
        f"<div style='max-height:{max_height};overflow-y:auto;"
        f"border:1px solid {border};border-radius:8px'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:0.82em'><thead><tr>"
    )
    for col in show.columns:
        html += (
            f"<th style='background:{hdr_bg};color:#fff;padding:10px 8px;"
            f"text-align:left;position:sticky;top:0;z-index:1;"
            f"border-bottom:2px solid {border}'>{col}</th>"
        )
    html += "</tr></thead><tbody>"
    for i, (_, row) in enumerate(show.iterrows()):
        bg = row_even if i % 2 == 0 else row_odd
        html += f"<tr style='background:{bg}'>"
        for col in show.columns:
            val = row[col]
            if pd.isna(val) or str(val) == "nan":
                val = "—"
            html += f"<td style='padding:8px;color:{txt};border-bottom:1px solid {border}'>{val}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    if len(dataframe) > max_rows:
        html += (
            f"<p style='color:#6b7f99;font-size:0.8em;margin-top:4px'>"
            f"Showing {max_rows} of {len(dataframe)} rows</p>"
        )
    st.markdown(html, unsafe_allow_html=True)


def classify_drawing(title):
    """Infer drawing type from title text."""
    if not title or pd.isna(title):
        return "Other"
    t = str(title).upper()
    for keyword, label in [
        # Structural
        ("BRIDGE", "Bridge"), ("GIRDER", "Bridge"), ("ABUTMENT", "Bridge"),
        ("PIER", "Bridge"), ("DECK", "Bridge"), ("BENT", "Bridge"),
        ("DIAPHRAGM", "Bridge"), ("DRILLED SHAFT", "Bridge"),
        # Road geometry
        ("TYPICAL SECTION", "Typical Section"), ("CROSS SECTION", "Cross Section"),
        ("PROFILE", "Profile"), ("ELEVATION", "Elevation"),
        ("GEOMETRY", "Geometry"), ("GEOMETRIC LAYOUT", "Geometry"),
        # Paving & roadway
        ("PAVING", "Paving"), ("ROADWAY", "Paving"),
        # Sidewalk & ramp
        ("SIDEWALK", "Sidewalk/Ramp"), ("RAMP DETAIL", "Sidewalk/Ramp"),
        # Barriers & walls
        ("WALL", "Wall/Barrier"), ("BARRIER", "Wall/Barrier"),
        # Fence
        ("FENCE", "Fence"),
        # Drainage
        ("DRAINAGE", "Drainage"), ("CONDUCTOR", "Drainage"),
        # Signals & traffic
        ("SIGNAL", "Traffic Signal"), ("TRAFFIC", "Traffic"),
        # Lighting & electrical
        ("LIGHTING", "Lighting"), ("ITS", "ITS"),
        # Signing & striping
        ("SIGNING", "Signing"), ("STRIPING", "Striping"),
        # Landscape & environment
        ("LANDSCAPE", "Landscape"),
        # Utilities
        ("UTILITY", "Utility"),
        # Demolition
        ("DEMOLITION", "Demolition"),
        # Plans & layouts
        ("PLAN SHEET", "Plan Sheet"), ("GENERAL PLAN", "Plan Sheet"),
        ("FRONTAGE ROAD", "Frontage Road"),
        # Details & schedules
        ("SCHEDULE", "Schedule"), ("DETAIL", "Detail Sheet"),
        ("NOTES", "Notes"),
    ]:
        if keyword in t:
            return label
    return "Other"


# ---------------------------------------------------------------------------
# Plotly dark layout helper
# ---------------------------------------------------------------------------
def dark_layout(fig, title="", height=400, show_legend=False):
    fig.update_layout(
        title=dict(text=title, font=dict(color=C["text"], size=15), x=0.01),
        paper_bgcolor=C["bg_card"], plot_bgcolor=C["bg_card"],
        font=dict(color=C["text_muted"], size=12),
        height=height, margin=dict(l=10, r=10, t=50, b=10),
        showlegend=show_legend,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=C["text_muted"])),
    )
    fig.update_xaxes(gridcolor=C["border"], zerolinecolor=C["border"])
    fig.update_yaxes(gridcolor=C["border"], zerolinecolor=C["border"])
    return fig


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"""
        <div style="text-align:center; padding:10px 0 6px 0;">
            <span style="font-size:2em; color:{C['teal']}">◆</span>
            <h2 style="margin:0; color:{C['teal']} !important; letter-spacing:2px">BlueprintAI</h2>
            <p style="color:{C['text_muted']}; font-size:0.82em; margin:0">
                Engineering Drawing Intelligence
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")

    page = st.radio(
        "nav",
        ["Dashboard", "Search & Browse", "Engineer Profiles",
         "Upload & Extract", "AI Chat", "Data Quality",
         "Project Timeline", "Bridge Tracker", "Reports"],
        label_visibility="collapsed",
    )

    # Bottom stats
    df_sidebar = load_data()
    st.markdown("---")
    st.markdown(
        f"""
        <div style="text-align:center; font-size:0.8em; color:{C['text_muted']}; line-height:1.9">
            <b style="color:{C['teal']}">{len(df_sidebar):,}</b> pages extracted<br>
            <b style="color:{C['teal']}">{overall_fill(df_sidebar):.1f}%</b> fill rate<br>
            <b style="color:{C['teal']}">{df_sidebar['engineer_stamp_name'].nunique()}</b> engineers
        </div>
        """,
        unsafe_allow_html=True,
    )

# Load data once per render
df = load_data()
df["drawing_type"] = df["drawing_title"].apply(classify_drawing)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE 1 — DASHBOARD                                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝
if page == "Dashboard":
    st.markdown("# Dashboard")
    st.markdown(f"<p style='color:{C['text_muted']}'>Extraction pipeline performance and drawing analytics</p>", unsafe_allow_html=True)

    # ── Helper: clean division name from OCR noise ──
    def clean_division(d):
        if not d or pd.isna(d):
            return None
        du = str(d).upper().replace("\n", " ").strip()
        if "INFRASTRUCTURE" in du:
            return "Infrastructure Delivery & Ops"
        if "ROADWAY" in du:
            return "Roadway Design Services"
        if "TRAFFIC" in du:
            return "Traffic Design Services"
        if "DRAINAGE" in du:
            return "Drainage Design Services"
        if "BRIDGE" in du:
            return "Bridge Group"
        if "DESIGN GROUP" in du:
            return "Design Group"
        return "Other"

    # ── Helper: clean route name from OCR noise ──
    def clean_route(r):
        if not r or pd.isna(r):
            return None
        ru = str(r).upper().replace("\n", " ").strip()
        if "202L" in ru or "202 L" in ru:
            return "SR 202L"
        if "202" in ru:
            return "SR 202"
        if "143" in ru:
            return "SR 143"
        if "101" in ru:
            return "SR 101"
        if "10" in ru:
            return "I-10"
        return ru

    # ── Helper: extract year from MM/DD/YYYY text ──
    def extract_year(date_str):
        if not date_str or pd.isna(date_str) or len(str(date_str)) < 4:
            return None
        try:
            y = int(str(date_str)[-4:])
            return y if 2000 <= y <= 2030 else None
        except (ValueError, TypeError):
            return None

    # ── Prepare year column for filtering ──
    df["_year"] = df["initial_date"].apply(extract_year)
    valid_years = df["_year"].dropna().astype(int)

    # ── Timeline slider ──
    if len(valid_years) > 0:
        yr_min, yr_max = int(valid_years.min()), int(valid_years.max())
        if yr_min < yr_max:
            yr_range = st.slider(
                "Filter by initial design year",
                min_value=yr_min, max_value=yr_max,
                value=(yr_min, yr_max),
                key="dash_year_slider",
            )
            dff = df[(df["_year"] >= yr_range[0]) & (df["_year"] <= yr_range[1])]
        else:
            dff = df.copy()
    else:
        dff = df.copy()

    # ── Stat cards ──
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Pages", f"{len(dff):,}")
    c2.metric("PDFs Processed", dff["pdf_filename"].nunique())
    c3.metric("Unique Engineers", dff["engineer_stamp_name"].nunique())
    c4.metric("Fill Rate", f"{overall_fill(dff):.1f}%")
    c5.metric("Bridge Drawings", int((dff["is_bridge_drawing"] == 1).sum()))
    c6.metric("Unique Routes", dff[dff["route"].notna() & (dff["route"] != "")]["route"].nunique())

    # Primary firm card
    firm_vals = dff["firm"].dropna().replace("", pd.NA).dropna()
    if len(firm_vals) > 0:
        top_firm = firm_vals.value_counts().index[0]
        firm_pct = firm_vals.value_counts().iloc[0] / len(dff) * 100
        st.markdown(
            f"<div class='card' style='text-align:center; margin-top:4px'>"
            f"<span style='color:{C['text_muted']}; font-size:0.85em'>Primary Firm</span>&nbsp;&nbsp;"
            f"<span style='color:{C['teal']}; font-size:1.1em; font-weight:bold'>{top_firm}</span>"
            f"&nbsp;&nbsp;<span style='color:{C['text_muted']}; font-size:0.85em'>({firm_pct:.0f}% of drawings)</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Row 1: fill rates + division ──
    left, right = st.columns([3, 2])

    with left:
        fill_rows = []
        for f in EXTRACT_FIELDS:
            pct = fill_pct(dff, f)
            fill_rows.append({"field": f.replace("_", " ").title(), "pct": pct})
        fill_df = pd.DataFrame(fill_rows).sort_values("pct")

        colors = []
        for p in fill_df["pct"]:
            if p >= 90:
                colors.append(C["green"])
            elif p >= 75:
                colors.append(C["teal"])
            elif p >= 50:
                colors.append(C["orange"])
            else:
                colors.append(C["red"])

        fig = go.Figure(go.Bar(
            x=fill_df["pct"], y=fill_df["field"],
            orientation="h", marker_color=colors,
            text=[f"{v:.0f}%" for v in fill_df["pct"]],
            textposition="outside", textfont=dict(color=C["text_muted"], size=11),
        ))
        fig.add_vline(x=80, line_dash="dot", line_color=C["text_muted"], opacity=0.4,
                      annotation_text="80%", annotation_font_color=C["text_muted"])
        dark_layout(fig, "Field Fill Rates", height=520)
        fig.update_layout(margin=dict(l=10, r=60, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        dff["_clean_div"] = dff["division"].apply(clean_division)
        div_series = dff[dff["_clean_div"].notna()]["_clean_div"].value_counts()

        fig = go.Figure(go.Bar(
            x=div_series.values, y=div_series.index,
            orientation="h", marker_color=CHART_SEQ[:len(div_series)],
            text=div_series.values, textposition="outside",
            textfont=dict(color=C["text_muted"], size=11),
        ))
        dark_layout(fig, "Drawings by Division", height=300)
        fig.update_layout(margin=dict(l=10, r=50, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # Bridge pie
        b_count = int((dff["is_bridge_drawing"] == 1).sum())
        nb_count = len(dff) - b_count
        fig = go.Figure(go.Pie(
            labels=["Bridge / Structure", "Non-Bridge"],
            values=[b_count, nb_count],
            marker=dict(colors=[C["teal"], C["navy"]]),
            hole=0.6, textfont=dict(color=C["text"], size=13),
            textinfo="label+percent",
        ))
        dark_layout(fig, "Bridge vs Non-Bridge", height=200)
        fig.update_layout(margin=dict(l=0, r=0, t=50, b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ── Row 2: top engineers + duration ──
    left2, right2 = st.columns(2)

    with left2:
        eng = dff[dff["engineer_stamp_name"].notna() & (dff["engineer_stamp_name"] != "")
                 ]["engineer_stamp_name"].value_counts().head(10)
        fig = go.Figure(go.Bar(
            y=eng.index[::-1], x=eng.values[::-1],
            orientation="h", marker_color=C["blue"],
            text=eng.values[::-1], textposition="outside",
            textfont=dict(color=C["text_muted"], size=11),
        ))
        dark_layout(fig, "Top 10 Engineers by Drawing Count", height=400)
        fig.update_layout(margin=dict(l=10, r=50, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with right2:
        dur = dff[(dff["design_duration_days"].notna())
                  & (dff["design_duration_days"] > 0)
                  & (dff["design_duration_days"] < 1000)
                  ]["design_duration_days"]
        if len(dur):
            fig = go.Figure(go.Histogram(
                x=dur, nbinsx=20,
                marker_color=C["teal"],
                marker_line=dict(color=C["border"], width=1),
            ))
            dark_layout(fig, f"Design Duration — Avg {dur.mean():.0f} days  ·  Median {dur.median():.0f} days", height=400)
            fig.update_xaxes(title_text="Days (Initial → Final)")
            fig.update_yaxes(title_text="Drawings")
            fig.update_layout(margin=dict(l=40, r=10, t=50, b=40))
            st.plotly_chart(fig, use_container_width=True)

    # ── Row 3: drawing types ──
    st.markdown("---")
    type_counts = dff["drawing_type"].value_counts()
    fig = go.Figure(go.Bar(
        x=type_counts.index, y=type_counts.values,
        marker_color=CHART_SEQ[:len(type_counts)],
        text=type_counts.values, textposition="outside",
        textfont=dict(color=C["text_muted"], size=11),
    ))
    dark_layout(fig, "Drawing Types", height=320)
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=60))
    st.plotly_chart(fig, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════
    #  NEW SECTION: Design Velocity (production over time by rfc_date)
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown(f"### Design Velocity")
    st.markdown(f"<p style='color:{C['text_muted']}'>Drawings completed per year (based on RFC date)</p>", unsafe_allow_html=True)

    dff["_rfc_year"] = dff["rfc_date"].apply(extract_year)
    rfc_yearly = dff[dff["_rfc_year"].notna()].groupby("_rfc_year").size().reset_index(name="drawings_completed")
    rfc_yearly.columns = ["Year", "Drawings Completed"]
    rfc_yearly = rfc_yearly.sort_values("Year")

    if len(rfc_yearly) >= 2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=rfc_yearly["Year"], y=rfc_yearly["Drawings Completed"],
            mode="lines+markers+text",
            line=dict(color=C["teal"], width=3),
            marker=dict(size=10, color=C["teal"]),
            text=rfc_yearly["Drawings Completed"],
            textposition="top center",
            textfont=dict(color=C["text"], size=12),
        ))
        # Add area fill
        fig.add_trace(go.Scatter(
            x=rfc_yearly["Year"], y=rfc_yearly["Drawings Completed"],
            fill="tozeroy", fillcolor="rgba(56,217,169,0.15)",
            line=dict(width=0), showlegend=False,
        ))
        dark_layout(fig, "Drawing Production Over Time (RFC Year)", height=350)
        fig.update_xaxes(dtick=1, gridcolor=C["border"])
        fig.update_yaxes(title_text="Drawings Completed", gridcolor=C["border"])
        fig.update_layout(margin=dict(l=50, r=20, t=50, b=40))
        st.plotly_chart(fig, use_container_width=True)
    elif len(rfc_yearly) == 1:
        st.info(f"Only one year of RFC data: {int(rfc_yearly.iloc[0, 0])} with {int(rfc_yearly.iloc[0, 1])} drawings.")

    # ══════════════════════════════════════════════════════════════════════
    #  NEW SECTION: Project Health Score (A/B/C per PDF)
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown(f"### Project Health Score")
    st.markdown(f"<p style='color:{C['text_muted']}'>Fill rate grade per PDF — A ≥ 90%, B 75-89%, C &lt; 75%</p>", unsafe_allow_html=True)

    health_rows = []
    for pdf_name, grp in dff.groupby("pdf_filename"):
        avg_fill = overall_fill(grp)
        if avg_fill >= 90:
            grade, color = "A", C["green"]
        elif avg_fill >= 75:
            grade, color = "B", C["yellow"]
        else:
            grade, color = "C", C["red"]
        health_rows.append({
            "PDF": pdf_name,
            "Pages": len(grp),
            "Avg Fill %": round(avg_fill, 1),
            "Grade": grade,
            "_color": color,
        })
    health_df = pd.DataFrame(health_rows).sort_values("Avg Fill %", ascending=False)

    # Render as styled HTML table
    health_html = f"""<table style='width:100%;border-collapse:collapse;font-size:0.85rem'>
    <tr style='border-bottom:2px solid {C["teal"]}'>
        <th style='text-align:left;padding:8px;color:{C["teal"]}'>PDF</th>
        <th style='text-align:center;padding:8px;color:{C["teal"]}'>Pages</th>
        <th style='text-align:center;padding:8px;color:{C["teal"]}'>Fill Rate</th>
        <th style='text-align:center;padding:8px;color:{C["teal"]}'>Grade</th>
    </tr>"""
    for _, row in health_df.iterrows():
        grade_badge = (f"<span style='background:{row['_color']};color:#0b1120;"
                       f"padding:2px 10px;border-radius:8px;font-weight:700'>"
                       f"{row['Grade']}</span>")
        health_html += f"""<tr style='border-bottom:1px solid {C["border"]}'>
        <td style='padding:6px 8px;color:{C["text"]}'>{row['PDF'][:60]}</td>
        <td style='text-align:center;padding:6px;color:{C["text"]}'>{row['Pages']}</td>
        <td style='text-align:center;padding:6px;color:{C["text"]}'>{row['Avg Fill %']:.1f}%</td>
        <td style='text-align:center;padding:6px'>{grade_badge}</td>
    </tr>"""
    health_html += "</table>"
    st.markdown(health_html, unsafe_allow_html=True)

    # Summary counts
    grade_counts = health_df["Grade"].value_counts()
    g_a = grade_counts.get("A", 0)
    g_b = grade_counts.get("B", 0)
    g_c = grade_counts.get("C", 0)
    st.markdown(
        f"<p style='color:{C['text_muted']};margin-top:8px'>"
        f"<span style='color:{C['green']}'>● {g_a} Grade A</span> &nbsp; "
        f"<span style='color:{C['yellow']}'>● {g_b} Grade B</span> &nbsp; "
        f"<span style='color:{C['red']}'>● {g_c} Grade C</span></p>",
        unsafe_allow_html=True,
    )

    # ══════════════════════════════════════════════════════════════════════
    #  NEW SECTION: Route-Level Analysis
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown(f"### Route-Level Analysis")
    st.markdown(f"<p style='color:{C['text_muted']}'>Breakdown by cleaned route identifier</p>", unsafe_allow_html=True)

    dff["_clean_route"] = dff["route"].apply(clean_route)
    route_groups = dff[dff["_clean_route"].notna()].groupby("_clean_route")

    route_rows = []
    for rname, rgrp in route_groups:
        valid_dur = rgrp[(rgrp["design_duration_days"] > 0) & (rgrp["design_duration_days"] < 1000)]["design_duration_days"]
        route_rows.append({
            "Route": rname,
            "Total Drawings": len(rgrp),
            "Bridge Drawings": int((rgrp["is_bridge_drawing"] == 1).sum()),
            "Unique Engineers": rgrp["engineer_stamp_name"].nunique(),
            "Avg Design Days": round(valid_dur.mean(), 1) if len(valid_dur) else 0,
        })
    route_df = pd.DataFrame(route_rows).sort_values("Total Drawings", ascending=False)

    if len(route_df):
        route_html = f"""<table style='width:100%;border-collapse:collapse;font-size:0.85rem'>
        <tr style='border-bottom:2px solid {C["teal"]}'>
            <th style='text-align:left;padding:8px;color:{C["teal"]}'>Route</th>
            <th style='text-align:center;padding:8px;color:{C["teal"]}'>Drawings</th>
            <th style='text-align:center;padding:8px;color:{C["teal"]}'>Bridges</th>
            <th style='text-align:center;padding:8px;color:{C["teal"]}'>Engineers</th>
            <th style='text-align:center;padding:8px;color:{C["teal"]}'>Avg Design Days</th>
        </tr>"""
        for _, row in route_df.iterrows():
            route_html += f"""<tr style='border-bottom:1px solid {C["border"]}'>
            <td style='padding:6px 8px;color:{C["text"]};font-weight:600'>{row['Route']}</td>
            <td style='text-align:center;padding:6px;color:{C["text"]}'>{row['Total Drawings']}</td>
            <td style='text-align:center;padding:6px;color:{C["text"]}'>{row['Bridge Drawings']}</td>
            <td style='text-align:center;padding:6px;color:{C["text"]}'>{row['Unique Engineers']}</td>
            <td style='text-align:center;padding:6px;color:{C["text"]}'>{row['Avg Design Days']}</td>
        </tr>"""
        route_html += "</table>"
        st.markdown(route_html, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    #  NEW SECTION: Division Performance Comparison (side-by-side)
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown(f"### Division Performance Comparison")
    st.markdown(f"<p style='color:{C['text_muted']}'>Volume vs speed — same divisions, two perspectives</p>", unsafe_allow_html=True)

    if "_clean_div" not in dff.columns:
        dff["_clean_div"] = dff["division"].apply(clean_division)
    div_perf_groups = dff[dff["_clean_div"].notna() & (dff["_clean_div"] != "Other")].groupby("_clean_div")

    div_perf_rows = []
    for dname, dgrp in div_perf_groups:
        valid_dur = dgrp[(dgrp["design_duration_days"] > 0) & (dgrp["design_duration_days"] < 1000)]["design_duration_days"]
        if len(dgrp) >= 5:
            div_perf_rows.append({
                "Division": dname,
                "Drawings": len(dgrp),
                "Avg Design Days": round(valid_dur.mean(), 1) if len(valid_dur) else 0,
            })
    div_perf_df = pd.DataFrame(div_perf_rows).sort_values("Drawings", ascending=True)

    if len(div_perf_df):
        dp_left, dp_right = st.columns(2)
        with dp_left:
            fig = go.Figure(go.Bar(
                y=div_perf_df["Division"], x=div_perf_df["Drawings"],
                orientation="h", marker_color=C["teal"],
                text=div_perf_df["Drawings"], textposition="outside",
                textfont=dict(color=C["text_muted"], size=11),
            ))
            dark_layout(fig, "Total Drawings by Division", height=350)
            fig.update_layout(margin=dict(l=10, r=50, t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with dp_right:
            fig = go.Figure(go.Bar(
                y=div_perf_df["Division"], x=div_perf_df["Avg Design Days"],
                orientation="h", marker_color=C["blue"],
                text=[f"{v:.0f}d" for v in div_perf_df["Avg Design Days"]],
                textposition="outside",
                textfont=dict(color=C["text_muted"], size=11),
            ))
            dark_layout(fig, "Avg Design Duration by Division", height=350)
            fig.update_layout(margin=dict(l=10, r=70, t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE 2 — SEARCH & BROWSE                                               ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif page == "Search & Browse":
    st.markdown("# Search & Browse")
    st.markdown(f"<p style='color:{C['text_muted']}'>Filter, explore, and export extracted records</p>", unsafe_allow_html=True)

    PDF_DIR = Path(__file__).parent / "data" / "raw"

    # ── Filters ──
    with st.expander("Filters", expanded=True):
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1:
            divs = ["All"] + sorted(set(
                d for d in df["division"].dropna().unique() if d != ""
            ))
            sel_div = st.selectbox("Division", divs)
        with r1c2:
            rts = ["All"] + sorted(set(
                r for r in df["route"].dropna().unique() if r != ""
            ))
            sel_rt = st.selectbox("Route", rts)
        with r1c3:
            engs = ["All"] + sorted(set(
                e for e in df["engineer_stamp_name"].dropna().unique() if e != ""
            ))
            sel_eng = st.selectbox("Engineer", engs)
        with r1c4:
            locs = ["All"] + sorted(set(
                l for l in df["location"].dropna().unique() if l != ""
            ))
            sel_loc = st.selectbox("Location", locs)

        r2c1, r2c2, r2c3, r2c4 = st.columns(4)
        with r2c1:
            types = ["All"] + sorted(df["drawing_type"].unique().tolist())
            sel_type = st.selectbox("Drawing Type", types)
        with r2c2:
            pdfs = ["All"] + sorted(df["pdf_filename"].unique().tolist())
            sel_pdf = st.selectbox("PDF File", pdfs)
        with r2c3:
            sel_bridge = st.selectbox("Structure Filter", ["All", "Bridge Only", "Non-Bridge Only"])
        with r2c4:
            search = st.text_input("Search title / project #", "")

    # ── Apply filters ──
    filt = df.copy()
    if sel_div != "All":
        filt = filt[filt["division"] == sel_div]
    if sel_rt != "All":
        filt = filt[filt["route"] == sel_rt]
    if sel_eng != "All":
        filt = filt[filt["engineer_stamp_name"] == sel_eng]
    if sel_loc != "All":
        filt = filt[filt["location"] == sel_loc]
    if sel_type != "All":
        filt = filt[filt["drawing_type"] == sel_type]
    if sel_pdf != "All":
        filt = filt[filt["pdf_filename"] == sel_pdf]
    if sel_bridge == "Bridge Only":
        filt = filt[filt["is_bridge_drawing"] == 1]
    elif sel_bridge == "Non-Bridge Only":
        filt = filt[filt["is_bridge_drawing"] != 1]
    if search:
        mask = (
            filt["drawing_title"].fillna("").str.contains(search, case=False) |
            filt["project_number"].fillna("").str.contains(search, case=False) |
            filt["tracs_number"].fillna("").str.contains(search, case=False)
        )
        filt = filt[mask]

    st.markdown(
        f"<p style='margin:4px 0'><b style='color:{C['teal']}'>{len(filt)}</b>"
        f" <span style='color:{C['text_muted']}'>of {len(df)} records</span></p>",
        unsafe_allow_html=True,
    )

    # ── Results table ──
    show_cols = [
        "pdf_filename", "page_number", "drawing_title", "drawing_type",
        "location", "route", "project_number", "division",
        "engineer_stamp_name", "initial_date", "rfc_date",
        "structure_number", "milepost", "rw_number", "tracs_number",
        "sheet_number", "total_sheets", "extraction_confidence",
    ]
    show_cols = [c for c in show_cols if c in filt.columns]

    render_table(filt[show_cols].reset_index(drop=True), max_rows=100, max_height="420px")

    # ══════════════════════════════════════════════════════════════════════
    #  DETAIL PANEL — click row to expand
    # ══════════════════════════════════════════════════════════════════════
    if len(filt) > 0:
        if "detail_open" not in st.session_state:
            st.session_state.detail_open = False
        if "detail_row" not in st.session_state:
            st.session_state.detail_row = 0

        st.markdown(f"<p style='color:{C['text_muted']};font-size:0.85rem;margin-top:8px'>"
                    f"Select a row number to inspect its full record and title block image.</p>",
                    unsafe_allow_html=True)

        det_cols = st.columns([1, 1, 2, 6])
        with det_cols[0]:
            row_idx = st.number_input("Row #", min_value=0,
                                      max_value=max(0, len(filt) - 1),
                                      value=st.session_state.detail_row, step=1,
                                      key="sb_row_input")
            st.session_state.detail_row = row_idx
        with det_cols[1]:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Inspect", key="sb_inspect_btn"):
                st.session_state.detail_open = True
        with det_cols[2]:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.session_state.detail_open and st.button("Close", key="sb_close_btn"):
                st.session_state.detail_open = False
                st.rerun()

        if st.session_state.detail_open:
            rec = filt.iloc[row_idx]

            # ── Source badge ──
            st.markdown(
                f"<div style='background:{C['bg_card']};border:1px solid {C['teal']};"
                f"border-radius:8px;padding:12px 16px;margin:8px 0'>"
                f"<span style='color:{C['teal']};font-weight:700'>Source:</span> "
                f"<span style='color:{C['text']}'>{rec.get('pdf_filename', '—')}</span>"
                f" &nbsp;·&nbsp; Page <span style='color:{C['teal']}'>"
                f"{int(rec.get('page_number', 0))}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # ── Title block viewer + field card side-by-side ──
            img_col, field_col = st.columns([1, 1])

            with img_col:
                st.markdown(f"**Title Block Preview**")
                pdf_path = PDF_DIR / str(rec.get("pdf_filename", ""))
                page_num = int(rec.get("page_number", 0))
                if pdf_path.exists() and page_num > 0:
                    try:
                        import fitz
                        from PIL import Image as PILImage
                        from core.title_block import TitleBlockExtractor

                        doc = fitz.open(str(pdf_path))
                        page = doc[page_num - 1]
                        mat = fitz.Matrix(200 / 72, 200 / 72)
                        pix = page.get_pixmap(matrix=mat)
                        page_img = PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        doc.close()

                        tb = TitleBlockExtractor()
                        tb_img = tb.crop_region(page_img, "full_title_block")
                        st.image(tb_img, use_container_width=True)
                    except Exception as e:
                        st.warning(f"Could not render title block: {e}")
                else:
                    st.info("PDF not available for rendering.")

            with field_col:
                st.markdown(f"**Extracted Fields**")
                all_fields = [
                    ("Drawing Title", "drawing_title"),
                    ("Location", "location"),
                    ("Route", "route"),
                    ("Project Number", "project_number"),
                    ("Sheet Number", "sheet_number"),
                    ("Total Sheets", "total_sheets"),
                    ("Initial Date", "initial_date"),
                    ("Initial Designer", "initial_designer"),
                    ("Final Date", "final_date"),
                    ("Final Drafter", "final_drafter"),
                    ("RFC Date", "rfc_date"),
                    ("RFC Checker", "rfc_checker"),
                    ("RW Number", "rw_number"),
                    ("TRACS Number", "tracs_number"),
                    ("Engineer Stamp", "engineer_stamp_name"),
                    ("Division", "division"),
                    ("Structure Number", "structure_number"),
                    ("Milepost", "milepost"),
                ]

                # Build HTML field grid
                field_html = f"<div style='font-size:0.85rem'>"
                for label, key in all_fields:
                    val = rec.get(key)
                    is_empty = pd.isna(val) or val == "" or val is None
                    if is_empty:
                        val_str = "—"
                        val_color = C["text_muted"]
                    else:
                        val_str = str(val)
                        val_color = C["green"]
                    field_html += (
                        f"<div style='display:flex;justify-content:space-between;"
                        f"padding:3px 0;border-bottom:1px solid {C['border']}'>"
                        f"<span style='color:{C['text_muted']}'>{label}</span>"
                        f"<span style='color:{val_color};text-align:right;max-width:60%;"
                        f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>"
                        f"{val_str}</span></div>"
                    )
                # Confidence row
                conf_val = rec.get("extraction_confidence")
                if pd.notna(conf_val):
                    cv = float(conf_val)
                    cc = C["green"] if cv >= 0.9 else C["yellow"] if cv >= 0.7 else C["red"]
                    field_html += (
                        f"<div style='display:flex;justify-content:space-between;"
                        f"padding:3px 0;margin-top:4px'>"
                        f"<span style='color:{C['text_muted']}'>Confidence</span>"
                        f"<span style='color:{cc};font-weight:700'>{cv:.2f}</span></div>"
                    )
                field_html += "</div>"
                st.markdown(field_html, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    #  ANOMALY DETECTION
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown(f"### Anomaly Detection")
    st.markdown(f"<p style='color:{C['text_muted']}'>Flagging suspicious records for manual review</p>", unsafe_allow_html=True)

    anomalies = []

    for idx, row in filt.iterrows():
        row_label = f"{row.get('pdf_filename', '?')} p{int(row.get('page_number', 0))}"

        # 1. Negative duration (RFC before initial)
        dur = row.get("design_duration_days")
        if pd.notna(dur) and dur < 0:
            anomalies.append({
                "Record": row_label,
                "Anomaly": "RFC date before initial date",
                "Detail": f"Duration = {int(dur)} days",
                "id": row.get("id"),
            })

        # 2. Duration > 500 days
        if pd.notna(dur) and dur > 500:
            anomalies.append({
                "Record": row_label,
                "Anomaly": "Design duration > 500 days",
                "Detail": f"Duration = {int(dur)} days",
                "id": row.get("id"),
            })

        # 3. Sheet number > total sheets (only for plausible values < 500)
        sn = row.get("sheet_number")
        ts = row.get("total_sheets")
        if pd.notna(sn) and pd.notna(ts):
            try:
                sn_num = int(float(str(sn)))
                ts_num = int(float(str(ts)))
                if 0 < ts_num < 500 and 0 < sn_num < 500 and sn_num > ts_num:
                    anomalies.append({
                        "Record": row_label,
                        "Anomaly": "Sheet number > total sheets",
                        "Detail": f"Sheet {sn_num} of {ts_num}",
                        "id": row.get("id"),
                    })
            except (ValueError, TypeError):
                pass

        # 4. Has route but missing location
        route_val = row.get("route")
        loc_val = row.get("location")
        has_route = pd.notna(route_val) and str(route_val).strip() != ""
        missing_loc = pd.isna(loc_val) or str(loc_val).strip() == ""
        if has_route and missing_loc:
            anomalies.append({
                "Record": row_label,
                "Anomaly": "Missing location (has route)",
                "Detail": f"Route: {route_val}",
                "id": row.get("id"),
            })

    # 5. Duplicate project numbers across different PDFs
    proj_df = filt[filt["project_number"].notna() & (filt["project_number"] != "")]
    if len(proj_df) > 0:
        proj_pdf_groups = proj_df.groupby("project_number")["pdf_filename"].nunique()
        dup_projects = proj_pdf_groups[proj_pdf_groups > 1]
        for proj_num, pdf_count in dup_projects.items():
            anomalies.append({
                "Record": f"Project {proj_num}",
                "Anomaly": "Duplicate project # across PDFs",
                "Detail": f"Found in {pdf_count} different PDFs",
                "id": None,
            })

    anom_count = len(anomalies)

    if anom_count == 0:
        st.success("No anomalies detected in the current filtered set.")
    else:
        st.markdown(
            f"<p><span style='background:{C['red']};color:#fff;padding:4px 12px;"
            f"border-radius:12px;font-weight:700;font-size:0.85rem'>"
            f"{anom_count} anomalies found</span></p>",
            unsafe_allow_html=True,
        )

        anom_df = pd.DataFrame(anomalies)[["Record", "Anomaly", "Detail"]]

        # Group by anomaly type for summary
        type_counts = anom_df["Anomaly"].value_counts()
        summary_parts = [f"<span style='color:{C['text']}'>{t}</span>: "
                         f"<span style='color:{C['red']}'>{c}</span>"
                         for t, c in type_counts.items()]
        st.markdown(
            f"<p style='color:{C['text_muted']};font-size:0.85rem'>"
            + " &nbsp;·&nbsp; ".join(summary_parts) + "</p>",
            unsafe_allow_html=True,
        )

        # Render anomaly table with red border
        anom_html = (
            f"<div style='border:2px solid {C['red']};border-radius:8px;"
            f"padding:4px;overflow:auto;max-height:400px'>"
            f"<table style='width:100%;border-collapse:collapse;font-size:0.82rem'>"
            f"<tr style='border-bottom:2px solid {C['red']}'>"
            f"<th style='text-align:left;padding:6px 8px;color:{C['red']}'>Record</th>"
            f"<th style='text-align:left;padding:6px 8px;color:{C['red']}'>Anomaly Type</th>"
            f"<th style='text-align:left;padding:6px 8px;color:{C['red']}'>Detail</th>"
            f"</tr>"
        )
        for _, arow in anom_df.iterrows():
            anom_html += (
                f"<tr style='border-bottom:1px solid {C['border']}'>"
                f"<td style='padding:4px 8px;color:{C['text']}'>{arow['Record']}</td>"
                f"<td style='padding:4px 8px;color:{C['orange']}'>{arow['Anomaly']}</td>"
                f"<td style='padding:4px 8px;color:{C['text_muted']}'>{arow['Detail']}</td>"
                f"</tr>"
            )
        anom_html += "</table></div>"
        st.markdown(anom_html, unsafe_allow_html=True)

    # ── Export ──
    st.markdown("---")
    csv = filt[show_cols].to_csv(index=False)
    st.download_button("Export filtered CSV", csv, "blueprintai_export.csv", "text/csv")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE 3 — ENGINEER PROFILES                                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif page == "Engineer Profiles":
    st.markdown("# Engineer Profiles")
    st.markdown(f"<p style='color:{C['text_muted']}'>59 engineers identified across all extracted drawings</p>", unsafe_allow_html=True)

    eng_df = df[df["engineer_stamp_name"].notna() & (df["engineer_stamp_name"] != "")]
    eng_counts = eng_df["engineer_stamp_name"].value_counts()

    # ── Engineer selector ──
    col_sel, col_count = st.columns([3, 1])
    with col_sel:
        options = [f"{name}  ({count} drawings)" for name, count in eng_counts.items()]
        selected = st.selectbox("Select an engineer", options)
        eng_name = selected.split("  (")[0]
    with col_count:
        st.metric("Total Engineers", len(eng_counts))

    st.markdown("---")

    # ── Profile ──
    eng_rows = eng_df[eng_df["engineer_stamp_name"] == eng_name]

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Drawings Stamped", len(eng_rows))

    eng_divs = eng_rows[eng_rows["division"].notna() & (eng_rows["division"] != "")]["division"].nunique()
    p2.metric("Divisions", eng_divs)

    eng_routes = eng_rows[eng_rows["route"].notna() & (eng_rows["route"] != "")]["route"].nunique()
    p3.metric("Routes", eng_routes)

    eng_dur = eng_rows[eng_rows["design_duration_days"].notna() & (eng_rows["design_duration_days"] > 0)]["design_duration_days"]
    p4.metric("Avg Design Time", f"{eng_dur.mean():.0f} days" if len(eng_dur) else "—")

    st.markdown("---")

    # Top-aligned two-column layout using container CSS
    left3, right3 = st.columns(2)

    with left3:
        st.markdown("#### Divisions")
        div_list = eng_rows[eng_rows["division"].notna() & (eng_rows["division"] != "")]["division"].value_counts()
        if len(div_list):
            for d, cnt in div_list.items():
                st.markdown(f"<span style='color:{C['teal']}'>▸</span> {d} ({cnt})", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:{C['text_muted']}'>No division data</span>", unsafe_allow_html=True)

        st.markdown("#### Routes")
        route_list = eng_rows[eng_rows["route"].notna() & (eng_rows["route"] != "")]["route"].value_counts()
        if len(route_list):
            for r, cnt in route_list.head(10).items():
                st.markdown(f"<span style='color:{C['blue']}'>▸</span> {r} ({cnt})", unsafe_allow_html=True)
            if len(route_list) > 10:
                st.markdown(f"<span style='color:{C['text_muted']}; font-size:0.85em'>+ {len(route_list) - 10} more routes</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:{C['text_muted']}'>No route data</span>", unsafe_allow_html=True)

    with right3:
        st.markdown("#### Drawing Type Specialization")
        type_counts = eng_rows["drawing_type"].value_counts()
        if len(type_counts):
            fig = go.Figure(go.Pie(
                labels=type_counts.index, values=type_counts.values,
                marker=dict(colors=CHART_SEQ[:len(type_counts)]),
                hole=0.5, textfont=dict(color=C["text"], size=11),
                textinfo="label+value",
            ))
            dark_layout(fig, "", height=300)
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── All drawings table with human-readable columns ──
    st.markdown("#### All Drawings")
    col_map = {
        "page_number": "Page",
        "pdf_filename": "PDF File",
        "drawing_title": "Drawing Title",
        "drawing_type": "Drawing Type",
        "route": "Route",
        "division": "Division",
        "initial_date": "Initial Date",
        "rfc_date": "RFC Date",
        "structure_number": "Structure No.",
        "design_duration_days": "Duration (days)",
    }
    eng_show = [c for c in col_map.keys() if c in eng_rows.columns]

    # Pagination
    PAGE_SIZE = 50
    total_eng_rows = len(eng_rows)
    if f"eng_page_{eng_name}" not in st.session_state:
        st.session_state[f"eng_page_{eng_name}"] = 0
    current_page = st.session_state[f"eng_page_{eng_name}"]
    total_pages = max(1, (total_eng_rows + PAGE_SIZE - 1) // PAGE_SIZE)
    start_idx = current_page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_eng_rows)

    show_df = eng_rows[eng_show].iloc[start_idx:end_idx].reset_index(drop=True)
    show_df = show_df.rename(columns=col_map)
    render_table(show_df, max_rows=PAGE_SIZE, max_height="400px")

    # Pagination controls
    if total_pages > 1:
        pg_left, pg_info, pg_right = st.columns([1, 3, 1])
        with pg_left:
            if st.button("← Previous", disabled=(current_page == 0), key="eng_prev"):
                st.session_state[f"eng_page_{eng_name}"] = current_page - 1
                st.rerun()
        with pg_info:
            st.markdown(
                f"<p style='text-align:center;color:{C['text_muted']};margin-top:8px'>"
                f"Page {current_page + 1} of {total_pages} · "
                f"Showing {start_idx + 1}–{end_idx} of {total_eng_rows} drawings</p>",
                unsafe_allow_html=True,
            )
        with pg_right:
            if st.button("Next →", disabled=(current_page >= total_pages - 1), key="eng_next"):
                st.session_state[f"eng_page_{eng_name}"] = current_page + 1
                st.rerun()
    else:
        st.markdown(
            f"<p style='color:{C['text_muted']};font-size:0.85em'>"
            f"Showing all {total_eng_rows} drawings</p>",
            unsafe_allow_html=True,
        )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE 4 — UPLOAD & EXTRACT                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif page == "Upload & Extract":
    st.markdown("# Upload & Extract")
    st.markdown(f"<p style='color:{C['text_muted']}'>Upload an ADOT engineering drawing PDF for automated field extraction</p>", unsafe_allow_html=True)

    # ── Upload flow ──
    uploaded = st.file_uploader("Choose a PDF file", type=["pdf"], label_visibility="collapsed")

    if uploaded is None:
        st.markdown(f"""
        <div class="card">
            <h3 style="color:{C['teal']}; margin-top:0">How it works</h3>
            <ol style="color:{C['text']}; line-height:2">
                <li>Upload any ADOT engineering drawing PDF</li>
                <li>Each page is rendered at 200 DPI and the title block is cropped</li>
                <li>Ensemble OCR (PaddleOCR + Tesseract) reads text from 7 regions</li>
                <li>Regex patterns extract 18 structured fields per page</li>
                <li>Results are displayed live with confidence scores for verification</li>
            </ol>
            <p style="color:{C['text_muted']}; font-size:0.9em; margin-bottom:0">
                Estimated speed: ~18 seconds per page (OCR + regex extraction)
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        tmp_dir = Path("data/uploads")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / uploaded.name
        tmp_path.write_bytes(uploaded.getvalue())

        st.markdown(
            f"<div class='card'>"
            f"<b>{uploaded.name}</b> — {uploaded.size/1024:.0f} KB"
            f"<span style='color:{C['text_muted']}; margin-left:20px'>"
            f"~18 sec/page estimated</span></div>",
            unsafe_allow_html=True,
        )

        # Session state for extraction results persistence
        if "upload_results" not in st.session_state:
            st.session_state.upload_results = None
        if "upload_tb_images" not in st.session_state:
            st.session_state.upload_tb_images = None
        if "upload_filename" not in st.session_state:
            st.session_state.upload_filename = None
        if "upload_saved" not in st.session_state:
            st.session_state.upload_saved = False

        ALL_DISPLAY_FIELDS = [
            ("Drawing Title", "drawing_title"),
            ("Location", "location"),
            ("Route", "route"),
            ("Project #", "project_number"),
            ("Division", "division"),
            ("Engineer", "engineer_stamp_name"),
            ("Initial Date", "initial_date"),
            ("Initial Designer", "initial_designer"),
            ("Final Date", "final_date"),
            ("Final Drafter", "final_drafter"),
            ("RFC Date", "rfc_date"),
            ("RFC Checker", "rfc_checker"),
            ("Structure #", "structure_number"),
            ("Milepost", "milepost"),
            ("RW Number", "rw_number"),
            ("TRACS #", "tracs_number"),
            ("Sheet", "sheet_number"),
            ("Total Sheets", "total_sheets"),
        ]

        def render_confidence_badge(conf):
            """Return HTML badge for a confidence score."""
            if conf is None:
                return ""
            cv = float(conf)
            if cv >= 0.8:
                bg, fg = C["green"], "#0b1120"
            elif cv >= 0.5:
                bg, fg = C["yellow"], "#0b1120"
            else:
                bg, fg = C["red"], "#fff"
            return (f"<span style='background:{bg};color:{fg};padding:1px 6px;"
                    f"border-radius:6px;font-size:0.7rem;margin-left:6px;"
                    f"font-weight:600'>{cv:.0%}</span>")

        def render_field_card(result, tb_image):
            """Render a before/after card: title block left, fields right."""
            img_col, field_col = st.columns([1, 1])

            with img_col:
                st.markdown("**Title Block**")
                if tb_image is not None:
                    st.image(tb_image, use_container_width=True)
                else:
                    st.info("Title block image not available")

            with field_col:
                st.markdown("**Extracted Fields**")
                field_html = "<div style='font-size:0.85rem'>"
                filled_count = 0
                for label, key in ALL_DISPLAY_FIELDS:
                    val = result.get(key)
                    conf = result.get(f"_conf_{key}")
                    is_empty = val is None or (isinstance(val, float) and pd.isna(val)) or str(val).strip() == ""

                    if is_empty:
                        val_str = "—"
                        val_color = C["text_muted"]
                        badge = ""
                    else:
                        val_str = str(val)
                        filled_count += 1
                        # Color by confidence
                        if conf is not None:
                            cv = float(conf)
                            val_color = C["green"] if cv >= 0.8 else C["yellow"] if cv >= 0.5 else C["red"]
                        else:
                            val_color = C["green"]
                        badge = render_confidence_badge(conf)

                    field_html += (
                        f"<div style='display:flex;justify-content:space-between;"
                        f"align-items:center;padding:3px 0;"
                        f"border-bottom:1px solid {C['border']}'>"
                        f"<span style='color:{C['text_muted']}'>{label}</span>"
                        f"<span style='color:{val_color};text-align:right;"
                        f"max-width:55%;overflow:hidden;text-overflow:ellipsis;"
                        f"white-space:nowrap'>{val_str}{badge}</span></div>"
                    )

                fill_pct_val = filled_count / len(ALL_DISPLAY_FIELDS) * 100
                fill_color = C["green"] if fill_pct_val >= 80 else C["yellow"] if fill_pct_val >= 50 else C["red"]
                field_html += (
                    f"<div style='margin-top:6px;padding:4px 0;text-align:right'>"
                    f"<span style='color:{C['text_muted']}'>Fill rate: </span>"
                    f"<span style='color:{fill_color};font-weight:700'>"
                    f"{filled_count}/{len(ALL_DISPLAY_FIELDS)} ({fill_pct_val:.0f}%)</span>"
                    f"</div>"
                )
                field_html += "</div>"
                st.markdown(field_html, unsafe_allow_html=True)

        # ── Run extraction ──
        if st.button("Run Extraction Pipeline", type="primary"):
            st.session_state.upload_saved = False
            sys.path.insert(0, str(Path(__file__).parent))

            progress_bar = st.progress(0)
            status_text = st.empty()
            eta_text = st.empty()
            live_results_area = st.container()

            try:
                from core.pdf_loader import load_pdf, render_page_to_image

                status_text.markdown(
                    f"<p style='color:{C['teal']}'>Loading PDF and OCR models...</p>",
                    unsafe_allow_html=True,
                )
                pdf_doc = load_pdf(str(tmp_path))
                total_pages = len(pdf_doc.pages)

                # Use cached components — PaddleOCR stays in memory
                ocr = get_ocr_engine()
                tb, regex, merger = get_pipeline_components()

                all_results = []
                title_block_images = []
                start_time = time.time()

                for pg in range(1, total_pages + 1):
                    page_start = time.time()
                    progress_bar.progress(pg / total_pages)

                    elapsed = time.time() - start_time
                    if pg > 1:
                        avg_per_page = elapsed / (pg - 1)
                        remaining = avg_per_page * (total_pages - pg + 1)
                        eta_str = f" — ETA {remaining:.0f}s remaining"
                    else:
                        eta_str = ""

                    status_text.markdown(
                        f"<p style='color:{C['teal']}'>"
                        f"Processing page {pg}/{total_pages}{eta_str}</p>",
                        unsafe_allow_html=True,
                    )

                    try:
                        page_image = render_page_to_image(str(tmp_path), pg, dpi=200)
                        tb_img = tb.crop_region(page_image, "full_title_block")
                        title_block_images.append(tb_img)

                        preprocessed = tb.get_preprocessed_regions(page_image, pg)
                        ocr_results = ocr.ocr_all_regions(preprocessed)
                        tier1 = regex.extract_all_tier1(ocr_results)

                        page_info = pdf_doc.pages[pg - 1]
                        embedded = regex.extract_from_embedded(
                            page_info.embedded_text, page_info.embedded_words
                        )
                        merged = merger.merge_page_results(tier1, embedded, [])

                        page_data = {"page": pg}
                        for fname, mf in merged.items():
                            if hasattr(mf, "value"):
                                page_data[fname] = mf.value
                                page_data[f"_conf_{fname}"] = (
                                    mf.confidence if hasattr(mf, "confidence") else None
                                )
                            else:
                                page_data[fname] = mf

                        all_results.append(page_data)

                        # Live render this page's result
                        page_elapsed = time.time() - page_start
                        title = page_data.get("drawing_title", "Untitled") or "Untitled"
                        with live_results_area:
                            with st.expander(
                                f"Page {pg} — {title}  ({page_elapsed:.1f}s)",
                                expanded=(pg == 1 or total_pages <= 3),
                            ):
                                render_field_card(page_data, tb_img)

                    except Exception as e:
                        all_results.append({"page": pg, "_error": str(e)})
                        title_block_images.append(None)
                        with live_results_area:
                            st.error(f"Page {pg}: {e}")

                total_elapsed = time.time() - start_time
                progress_bar.progress(1.0)
                ok_count = sum(1 for r in all_results if "_error" not in r)
                err_count = sum(1 for r in all_results if "_error" in r)

                status_text.markdown(
                    f"<p style='color:{C['green']}'>"
                    f"Extraction complete — {ok_count} page{'s' if ok_count != 1 else ''} "
                    f"processed in {total_elapsed:.0f}s"
                    f"{f', {err_count} error(s)' if err_count else ''}</p>",
                    unsafe_allow_html=True,
                )
                eta_text.empty()

                # Store results in session state for save/discard
                st.session_state.upload_results = all_results
                st.session_state.upload_tb_images = title_block_images
                st.session_state.upload_filename = uploaded.name

            except Exception as e:
                st.error(f"Pipeline error: {e}")

        # ── Save / Discard buttons (persist after extraction) ──
        if (st.session_state.upload_results is not None
                and st.session_state.upload_filename == uploaded.name
                and not st.session_state.upload_saved):

            all_results = st.session_state.upload_results
            ok_count = sum(1 for r in all_results if "_error" not in r)

            st.markdown("---")
            st.markdown(
                f"<p style='color:{C['text']};font-size:1.05rem'>"
                f"<b>{ok_count}</b> page{'s' if ok_count != 1 else ''} ready to save</p>",
                unsafe_allow_html=True,
            )

            save_col, discard_col, spacer_col = st.columns([1, 1, 3])
            with save_col:
                if st.button("Save to Database", type="primary", key="save_db_btn"):
                    conn = sqlite3.connect(str(DB_PATH))
                    saved = 0
                    for result in all_results:
                        if "_error" in result:
                            continue
                        cols_to_save = {
                            k: v for k, v in result.items()
                            if not k.startswith("_") and k != "page"
                        }
                        cols_to_save["pdf_filename"] = uploaded.name
                        cols_to_save["page_number"] = result["page"]
                        cols_to_save["extraction_mode"] = "tier1"
                        cols_to_save["extraction_timestamp"] = (
                            datetime.now().isoformat()
                        )

                        col_names = ", ".join(cols_to_save.keys())
                        placeholders = ", ".join(["?"] * len(cols_to_save))
                        conn.execute(
                            f"INSERT OR REPLACE INTO drawings ({col_names}) "
                            f"VALUES ({placeholders})",
                            list(cols_to_save.values()),
                        )
                        saved += 1
                    conn.commit()
                    conn.close()
                    load_data.clear()
                    st.session_state.upload_saved = True
                    st.success(
                        f"Saved {saved} records to database. "
                        f"They will appear in Search & Browse and Dashboard."
                    )

            with discard_col:
                if st.button("Discard Results", key="discard_btn"):
                    st.session_state.upload_results = None
                    st.session_state.upload_tb_images = None
                    st.session_state.upload_filename = None
                    st.info("Results discarded — nothing was saved.")
                    st.rerun()

        elif st.session_state.upload_saved and st.session_state.upload_filename == uploaded.name:
            st.success("Results have been saved to the database.")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE 5 — AI CHAT                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif page == "AI Chat":
    import plotly.express as px

    st.markdown("# AI Chat")

    # ── Session state init ──
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chat_mode" not in st.session_state:
        st.session_state.chat_mode = "fast"

    # ── Mode toggle + temperature badge ──
    mode_labels = {"fast": "Fast Mode", "thinking": "Thinking Mode"}
    selected_mode = st.radio(
        "Mode",
        ["fast", "thinking"],
        format_func=lambda x: mode_labels[x],
        index=0 if st.session_state.chat_mode == "fast" else 1,
        horizontal=True,
        label_visibility="collapsed",
    )
    if selected_mode != st.session_state.chat_mode:
        st.session_state.chat_mode = selected_mode
        st.rerun()

    mode = st.session_state.chat_mode
    if mode == "fast":
        temp_val, model_name = 0.1, "mistral:7b"
        badge_color, badge_label = C["teal"], "Fast"
        subtitle = "Fast answers from structured data"
    else:
        temp_val, model_name = 0.35, "qwen2.5:7b"
        badge_color, badge_label = C["purple"], "Thinking"
        subtitle = "Deeper analysis with a reasoning model"

    st.markdown(
        f"<div style='display:flex;align-items:center;gap:12px;margin-top:-8px'>"
        f"<span style='background:{badge_color};color:#0b1120;padding:4px 14px;"
        f"border-radius:14px;font-size:0.78rem;font-weight:600;white-space:nowrap'>"
        f"{badge_label} · {model_name} · temp {temp_val}</span>"
        f"<span style='color:{C['text_muted']};font-size:0.85em'>{subtitle}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Schema description (updated to 1,327 rows) ──
    SCHEMA_DESC = """Table: drawings (1,327 rows from 37 PDFs)
Columns: id, pdf_filename, page_number, drawing_title, location, route, project_number,
sheet_number, total_sheets, initial_date (MM/DD/YYYY), initial_designer, final_date,
final_drafter, rfc_date, rfc_checker, rw_number, tracs_number, engineer_stamp_name,
firm, structure_number, milepost, is_bridge_drawing (0/1), design_duration_days,
rfc_duration_days, division, extraction_confidence (0-1), quality_grade,
is_adot_drawing (0/1), is_blank_page (0/1), extraction_timestamp.

Key facts: 116 unique engineers, 58 bridge drawings, 3 routes (I-10, SR-202L, SR-143).
The 'firm' column contains engineering firm names extracted via VLM. The primary contractor is 'CONNECT 202 PARTNERS' (1,101 of 1,332 pages). 231 pages have NULL firm (blank pages or no visible logo). When asked about firms, contractors, or companies, query the firm column.
Dates are stored as text in MM/DD/YYYY format. To extract the year use substr(initial_date, -4).
IMPORTANT: design_duration_days has bad values from date parsing errors. ALWAYS filter with:
  WHERE design_duration_days > 0 AND design_duration_days < 1000
Division values have OCR noise prefixes. To get clean divisions use this CASE expression:
  CASE
    WHEN division LIKE '%BRIDGE GROUP%' THEN 'BRIDGE GROUP'
    WHEN division LIKE '%ROADWAY DESIGN%' THEN 'ROADWAY DESIGN SERVICES'
    WHEN division LIKE '%TRAFFIC DESIGN%' THEN 'TRAFFIC DESIGN SERVICES'
    WHEN division LIKE '%INFRASTRUCTURE%' THEN 'INFRASTRUCTURE DELIVERY AND OPERATIONS'
    WHEN division LIKE '%DRAINAGE DESIGN%' THEN 'DRAINAGE DESIGN SERVICES'
    WHEN division LIKE '%DESIGN GROUP%' THEN 'DESIGN GROUP'
    ELSE division
  END as clean_division
There are 6 main divisions after cleanup."""

    # ── Pre-built SQL helpers for tricky queries ──
    SQL_DESIGN_TIME_BY_YEAR = """SELECT substr(initial_date, -4) as year,
       COUNT(*) as drawings,
       ROUND(AVG(design_duration_days), 1) as avg_design_days
FROM drawings
WHERE initial_date IS NOT NULL AND initial_date != ''
  AND design_duration_days > 0 AND design_duration_days < 1000
GROUP BY substr(initial_date, -4)
ORDER BY year;"""

    SQL_DIVISION_BREAKDOWN = """SELECT
  CASE
    WHEN division LIKE '%BRIDGE GROUP%' THEN 'BRIDGE GROUP'
    WHEN division LIKE '%ROADWAY DESIGN%' THEN 'ROADWAY DESIGN SERVICES'
    WHEN division LIKE '%TRAFFIC DESIGN%' THEN 'TRAFFIC DESIGN SERVICES'
    WHEN division LIKE '%INFRASTRUCTURE%' THEN 'INFRASTRUCTURE DELIVERY AND OPERATIONS'
    WHEN division LIKE '%DRAINAGE DESIGN%' THEN 'DRAINAGE DESIGN SERVICES'
    WHEN division LIKE '%DESIGN GROUP%' THEN 'DESIGN GROUP'
    ELSE division
  END as division,
  COUNT(*) as drawings
FROM drawings
WHERE division IS NOT NULL AND division != ''
GROUP BY 1
HAVING COUNT(*) >= 5
ORDER BY drawings DESC;"""

    SQL_DIVISION_PRODUCTIVITY = """SELECT
  CASE
    WHEN division LIKE '%BRIDGE GROUP%' THEN 'BRIDGE GROUP'
    WHEN division LIKE '%ROADWAY DESIGN%' THEN 'ROADWAY DESIGN SERVICES'
    WHEN division LIKE '%TRAFFIC DESIGN%' THEN 'TRAFFIC DESIGN SERVICES'
    WHEN division LIKE '%INFRASTRUCTURE%' THEN 'INFRASTRUCTURE DELIVERY AND OPERATIONS'
    WHEN division LIKE '%DRAINAGE DESIGN%' THEN 'DRAINAGE DESIGN SERVICES'
    WHEN division LIKE '%DESIGN GROUP%' THEN 'DESIGN GROUP'
    ELSE division
  END as division,
  COUNT(*) as drawings,
  COUNT(DISTINCT engineer_stamp_name) as engineers,
  ROUND(AVG(CASE WHEN design_duration_days > 0 AND design_duration_days < 1000 THEN design_duration_days END), 1) as avg_design_days
FROM drawings
WHERE division IS NOT NULL AND division != ''
GROUP BY 1
HAVING COUNT(*) >= 5
ORDER BY drawings DESC;"""

    SQL_TOP_FIRMS = """SELECT firm, COUNT(*) as drawings,
  COUNT(DISTINCT engineer_stamp_name) as engineers,
  COUNT(DISTINCT route) as routes
FROM drawings
WHERE firm IS NOT NULL AND firm != ''
GROUP BY firm
ORDER BY drawings DESC;"""

    # ── LLM call function ──
    def call_ollama_chat(prompt, model=None, temperature=None):
        """Call Ollama text LLM. Model/temp driven by current chat mode."""
        _model = model or model_name
        _temp = temperature if temperature is not None else temp_val
        try:
            opts = {"temperature": _temp}
            # Reasoning models need more tokens so the answer isn't cut off
            # during the <think> block
            if _model and "qwen" in _model.lower():
                opts["num_predict"] = 4096
            resp = __import__("requests").post(
                "http://localhost:11434/api/generate",
                json={
                    "model": _model,
                    "prompt": prompt,
                    "stream": False,
                    "options": opts,
                },
                timeout=120,
            )
            text = resp.json().get("response", "")
            # Strip <think>…</think> blocks produced by reasoning models
            text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
            # Handle truncated think blocks (no closing tag due to token limit)
            text = re.sub(r"<think>[\s\S]*", "", text).strip()
            return text
        except Exception:
            return None

    # ── SQL generation ──
    def match_prebuilt_query(question):
        """Match question to a pre-built SQL query for tricky cases."""
        q = question.lower()
        # Year / trend / "over the years" / "changed" + design time
        if any(w in q for w in ("over the year", "by year", "changed", "trend")) and \
           any(w in q for w in ("design", "time", "duration")):
            return SQL_DESIGN_TIME_BY_YEAR
        # Division productivity / comparison
        if "division" in q and any(w in q for w in ("compare", "productivity", "workload", "versus", "vs")):
            return SQL_DIVISION_PRODUCTIVITY
        # Division breakdown / count
        if "division" in q and any(w in q for w in ("breakdown", "most", "count", "how many", "all", "rank")):
            return SQL_DIVISION_BREAKDOWN
        # Firm / contractor queries
        if any(w in q for w in ("firm", "contractor", "company", "companies")):
            return SQL_TOP_FIRMS
        return None

    def generate_sql(question, history_context=""):
        """Convert natural language to SQL via Ollama, with pre-built query shortcuts."""
        # Check pre-built queries first for tricky cases
        prebuilt = match_prebuilt_query(question)
        if prebuilt:
            return prebuilt

        prompt = f"""You are a SQL assistant. Given this database schema:

{SCHEMA_DESC}

{f"Previous conversation context:{chr(10)}{history_context}" if history_context else ""}

Convert this question to a SQLite query. Return ONLY the SQL query, no explanation.
If the question asks about a count or total, use COUNT(*).
If the question asks about rankings, use ORDER BY ... DESC LIMIT 10.
Keep it simple and correct.

Question: {question}
SQL:"""

        llm_response = call_ollama_chat(prompt)
        if llm_response:
            sql = llm_response.strip()
            sql = re.sub(r"```sql\s*", "", sql)
            sql = re.sub(r"```\s*", "", sql)
            sql = sql.strip().rstrip(";") + ";"
            if sql.upper().lstrip().startswith("SELECT"):
                return sql
        return None

    # ── Answer formatting ──
    def format_answer(question, result_df, sql):
        """Use Ollama to format the SQL result as a natural answer."""
        data_preview = result_df.head(20).to_string(index=False)
        prompt = f"""Given this data result from a database query about ADOT engineering drawings:

Question: {question}
Result:
{data_preview}

Write a concise, clear answer in 1-3 sentences. If it's a single number, state it naturally.
If it's a list, summarize the top items. Be conversational but professional.
NEVER include SQL in your answer. Answer:"""

        llm_response = call_ollama_chat(prompt)
        return llm_response if llm_response else None

    # ── Chart detection and generation ──
    def detect_chart_type(question, result_df):
        """Detect if a chart should be shown and what type."""
        if result_df is None or len(result_df) <= 1:
            return None
        q = question.lower()
        ncols = len(result_df.columns)
        nrows = len(result_df)

        # Rankings / "most" / "top" → horizontal bar
        if any(w in q for w in ("most", "top", "rank", "best", "least", "fewest", "bottom")):
            if ncols >= 2 and nrows >= 2:
                return "bar"
        # Breakdowns / distributions → pie (small groups) or bar (many)
        if any(w in q for w in ("breakdown", "distribution", "by division", "by route", "by firm", "percentage")):
            if ncols >= 2 and 2 <= nrows <= 8:
                return "pie"
            elif ncols >= 2 and nrows > 8:
                return "bar"
        # Trends / over time → line
        if any(w in q for w in ("trend", "over time", "by year", "by month", "timeline", "growth", "changed", "over the year")):
            if ncols >= 2 and nrows >= 2:
                return "line"
        # Compare → grouped bar
        if any(w in q for w in ("compare", "comparison", "vs", "versus", "across", "productivity")):
            if ncols >= 2:
                return "bar"
        # Default: if it's a ranked list with numeric column, show bar
        if nrows >= 3 and ncols >= 2:
            last_col = result_df.columns[-1]
            if pd.api.types.is_numeric_dtype(result_df[last_col]):
                return "bar"
        return None

    def render_chart(result_df, chart_type):
        """Render a Plotly chart matching the navy/teal theme."""
        if result_df is None or len(result_df) < 2:
            return
        cols = result_df.columns.tolist()
        label_col = cols[0]
        value_col = cols[-1] if len(cols) >= 2 else cols[0]

        layout_kwargs = dict(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=C["text"], size=12),
            margin=dict(l=10, r=10, t=30, b=10),
            height=350,
        )

        if chart_type == "bar":
            fig = px.bar(
                result_df.head(15), x=value_col, y=label_col,
                orientation="h",
                color_discrete_sequence=[C["teal"]],
            )
            fig.update_layout(**layout_kwargs)
            fig.update_yaxes(autorange="reversed", gridcolor=C["border"])
            fig.update_xaxes(gridcolor=C["border"])
            st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "pie":
            fig = px.pie(
                result_df.head(8), values=value_col, names=label_col,
                color_discrete_sequence=CHART_SEQ,
                hole=0.4,
            )
            fig.update_layout(**layout_kwargs)
            fig.update_traces(textfont_color=C["text"])
            st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "line":
            fig = px.line(
                result_df, x=label_col, y=value_col,
                color_discrete_sequence=[C["teal"]],
                markers=True,
            )
            fig.update_layout(**layout_kwargs)
            fig.update_xaxes(gridcolor=C["border"], dtick=1)
            fig.update_yaxes(gridcolor=C["border"])
            st.plotly_chart(fig, use_container_width=True)

    # ── Fallback answers ──
    def fallback_answer(question):
        """Keyword-based fallback when Ollama is unavailable."""
        q = question.lower()
        total_rows = len(load_data())
        try:
            if "most" in q and "engineer" in q:
                return run_sql("SELECT engineer_stamp_name, COUNT(*) as drawings FROM drawings WHERE engineer_stamp_name IS NOT NULL AND engineer_stamp_name != '' GROUP BY engineer_stamp_name ORDER BY drawings DESC LIMIT 10"), "Top engineers by drawing count:"
            elif "bridge" in q and ("how many" in q or "count" in q):
                r = run_sql("SELECT COUNT(*) as count FROM drawings WHERE is_bridge_drawing = 1")
                return r, f"There are **{r.iloc[0,0]}** bridge drawings in the database."
            elif "division" in q:
                return run_sql(SQL_DIVISION_BREAKDOWN.rstrip(";")), "Division breakdown:"
            elif "average" in q and ("time" in q or "duration" in q or "design" in q):
                r = run_sql("SELECT ROUND(AVG(design_duration_days),1) as avg_days FROM drawings WHERE design_duration_days > 0 AND design_duration_days < 1000")
                return r, f"The average design duration is **{r.iloc[0,0]} days**."
            elif "route" in q:
                if "most" in q or "engineer" in q:
                    return run_sql("SELECT engineer_stamp_name, COUNT(DISTINCT route) as routes FROM drawings WHERE engineer_stamp_name IS NOT NULL AND route IS NOT NULL AND route != '' GROUP BY engineer_stamp_name ORDER BY routes DESC LIMIT 10"), "Engineers by number of routes:"
                return run_sql("SELECT route, COUNT(*) as pages FROM drawings WHERE route IS NOT NULL AND route != '' GROUP BY route ORDER BY pages DESC"), "Route breakdown:"
            elif "fill" in q or "accuracy" in q:
                rows = []
                for f in EXTRACT_FIELDS:
                    r = run_sql(f"SELECT COUNT(*) FROM drawings WHERE {f} IS NOT NULL AND {f} != ''")
                    rows.append({"Field": f, "Filled": r.iloc[0,0], "Rate": f"{r.iloc[0,0]/total_rows*100:.1f}%"})
                return pd.DataFrame(rows).sort_values("Filled", ascending=False), "Field fill rates:"
            elif "how many" in q:
                if "page" in q or "drawing" in q or "record" in q:
                    return run_sql("SELECT COUNT(*) as total FROM drawings"), f"There are **{total_rows}** drawing pages in the database."
                elif "pdf" in q:
                    r = run_sql("SELECT COUNT(DISTINCT pdf_filename) as pdfs FROM drawings")
                    return r, f"There are **{r.iloc[0,0]}** PDFs processed."
                elif "engineer" in q:
                    r = run_sql("SELECT COUNT(DISTINCT engineer_stamp_name) as engineers FROM drawings WHERE engineer_stamp_name IS NOT NULL AND engineer_stamp_name != ''")
                    return r, f"There are **{r.iloc[0,0]}** unique engineers."
            elif "longest" in q or "slowest" in q:
                return run_sql("SELECT drawing_title, project_number, design_duration_days FROM drawings WHERE design_duration_days > 0 ORDER BY design_duration_days DESC LIMIT 10"), "Drawings with longest design duration:"
            return None, "I couldn't find an answer to that question. Try rephrasing or ask about engineers, divisions, routes, bridge counts, or design durations."
        except Exception as e:
            return None, f"Error: {e}"

    # ── Conversation memory: build context from last 5 exchanges ──
    def build_memory_context():
        """Build context string from last 5 user-assistant exchanges."""
        history = st.session_state.chat_history
        exchanges = []
        i = len(history) - 1
        while i >= 0 and len(exchanges) < 10:
            msg = history[i]
            exchanges.append(msg)
            i -= 1
        exchanges.reverse()
        # Keep last 5 exchanges (up to 10 messages)
        ctx_parts = []
        for msg in exchanges[-10:]:
            if msg["role"] == "user":
                ctx_parts.append(f"User: {msg['content']}")
            else:
                ctx_parts.append(f"Assistant: {msg['content'][:200]}")
        return "\n".join(ctx_parts)

    # ── Mode-specific suggested questions ──
    FAST_CHIPS = [
        "How many drawings are in the database?",
        "Who designed the most drawings?",
        "How many bridge drawings are there?",
        "Which division has the most pages?",
        "What is the average design time?",
        "How many unique engineers?",
    ]
    THINKING_CHIPS = [
        "Compare the workload across all divisions",
        "Which engineers worked on bridge drawings?",
        "Breakdown of drawings by route and division",
        "What is the trend of design durations?",
        "Which firms have the most diverse projects?",
        "Rank engineers by number of routes worked",
    ]

    chips = FAST_CHIPS if mode == "fast" else THINKING_CHIPS

    # ── Suggested chips (show only when no history) ──
    if not st.session_state.chat_history:
        # Inject CSS for consistent chip button height
        st.markdown(
            f"""<style>
            div[data-testid="stHorizontalBlock"] .stButton > button {{
                height: 62px;
                display: flex;
                align-items: center;
                justify-content: center;
                text-align: center;
                white-space: normal;
                line-height: 1.3;
            }}
            </style>""",
            unsafe_allow_html=True,
        )
        chip_cols = st.columns(3)
        for i, sug in enumerate(chips):
            with chip_cols[i % 3]:
                if st.button(sug, key=f"chip_{i}"):
                    st.session_state.chat_history.append({"role": "user", "content": sug})
                    st.rerun()

    # ── Chat history display ──
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"], unsafe_allow_html=True)
            if msg.get("chart_type") and msg.get("dataframe") is not None:
                render_chart(msg["dataframe"], msg["chart_type"])
            elif msg.get("show_table") and msg.get("dataframe") is not None:
                render_table(msg["dataframe"], max_rows=50, max_height="350px")

    # ── Input ──
    placeholder = "Quick question..." if mode == "fast" else "Ask something that needs deeper analysis..."
    if prompt := st.chat_input(placeholder):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

    # ── Process last unanswered message ──
    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
        question = st.session_state.chat_history[-1]["content"]

        with st.chat_message("assistant"):
            spinner_text = "Thinking..." if mode == "fast" else "Analyzing deeply..."
            with st.spinner(spinner_text):
                # Build memory context from last 5 exchanges
                history_ctx = build_memory_context()

                # Generate SQL
                sql = generate_sql(question, history_ctx)
                result_df = None
                answer_text = None
                chart_type = None
                show_table = False

                if sql:
                    try:
                        result_df = run_sql(sql.rstrip(";"))

                        is_scalar = (len(result_df) == 1 and len(result_df.columns) <= 2)
                        is_list = (len(result_df) > 1 and len(result_df.columns) >= 2)

                        answer_text = format_answer(question, result_df, sql)

                        if is_scalar:
                            if not answer_text:
                                val = result_df.iloc[0, 0]
                                answer_text = f"The answer is **{val}**."
                            show_table = False
                        elif is_list:
                            if not answer_text:
                                answer_text = f"Here are the results ({len(result_df)} rows):"
                            # Detect chart opportunity
                            chart_type = detect_chart_type(question, result_df)
                            show_table = chart_type is None  # show table if no chart
                        else:
                            if not answer_text:
                                answer_text = f"Here are the results ({len(result_df)} rows):"
                            show_table = len(result_df) > 1
                    except Exception:
                        sql = None

                if sql is None:
                    fb_result, fb_text = fallback_answer(question)
                    if isinstance(fb_result, pd.DataFrame) and len(fb_result) > 0:
                        result_df = fb_result
                        answer_text = fb_text
                        chart_type = detect_chart_type(question, result_df)
                        show_table = chart_type is None and len(fb_result) > 1 and len(fb_result.columns) >= 2
                    elif fb_text:
                        answer_text = fb_text
                    else:
                        answer_text = "I couldn't find an answer. Try rephrasing or ask about engineers, divisions, routes, bridge counts, or design durations."

                st.markdown(answer_text, unsafe_allow_html=True)

                # Render chart or table
                if chart_type and result_df is not None and len(result_df) > 1:
                    render_chart(result_df, chart_type)
                elif show_table and result_df is not None and len(result_df) > 0:
                    render_table(result_df, max_rows=50, max_height="350px")

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": answer_text,
                    "dataframe": result_df if result_df is not None else None,
                    "show_table": show_table,
                    "chart_type": chart_type,
                })

    # ── Export + Clear ──
    if st.session_state.chat_history:
        st.markdown("---")
        exp_col, clr_col, _ = st.columns([1, 1, 4])
        with exp_col:
            conv_text = "\n\n".join(
                f"{'You' if m['role']=='user' else 'BlueprintAI'}: {m['content']}"
                for m in st.session_state.chat_history
            )
            st.download_button("Export conversation", conv_text, "blueprintai_chat.txt", "text/plain")
        with clr_col:
            if st.button("Clear chat"):
                st.session_state.chat_history = []
                st.rerun()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE 6 — DATA QUALITY                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif page == "Data Quality":
    st.markdown("# Data Quality")
    st.markdown(f"<p style='color:{C['text_muted']}'>Extraction health, coverage gaps, and records needing review</p>", unsafe_allow_html=True)

    # ── Overall health grade ──
    avg = overall_fill(df)
    if avg >= 85:
        grade, grade_color, grade_label = "A", C["green"], "Excellent"
    elif avg >= 70:
        grade, grade_color, grade_label = "B", C["teal"], "Good"
    elif avg >= 55:
        grade, grade_color, grade_label = "C", C["yellow"], "Fair"
    else:
        grade, grade_color, grade_label = "D", C["red"], "Poor"

    gc1, gc2, gc3, gc4 = st.columns(4)
    gc1.markdown(
        f"<div class='card' style='text-align:center'>"
        f"<p style='color:{C['text_muted']}; margin:0'>Health Grade</p>"
        f"<p style='color:{grade_color}; font-size:3em; margin:0; font-weight:bold'>{grade}</p>"
        f"<p style='color:{grade_color}; margin:0'>{grade_label}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )
    gc2.metric("Overall Fill Rate", f"{avg:.1f}%")
    fields_above_80 = sum(1 for f in EXTRACT_FIELDS if fill_pct(df, f) >= 80)
    gc3.metric("Fields ≥ 80%", f"{fields_above_80} / {len(EXTRACT_FIELDS)}")
    avg_conf = df["extraction_confidence"].mean() if df["extraction_confidence"].notna().any() else 0
    gc4.metric("Avg Confidence", f"{avg_conf:.1%}")

    st.markdown("---")

    # ── Per-field fill rates with tier labels ──
    st.markdown("### Field Coverage")
    field_rows = []
    for f in EXTRACT_FIELDS:
        pct = fill_pct(df, f)
        filled = field_fill(df, f)
        missing = len(df) - filled
        if pct >= 90:
            tier = "Excellent"
        elif pct >= 75:
            tier = "Good"
        elif pct >= 60:
            tier = "Fair"
        else:
            tier = "Needs Work"
        field_rows.append({
            "Field": f.replace("_", " ").title(),
            "Filled": filled,
            "Missing": missing,
            "Fill %": f"{pct:.1f}%",
            "Status": tier,
        })

    fq_df = pd.DataFrame(field_rows).sort_values("Filled", ascending=False)
    render_table(fq_df, max_rows=20, max_height="500px")

    st.markdown("---")

    # ── PDFs with most missing fields ──
    left_q, right_q = st.columns(2)

    with left_q:
        st.markdown("### PDFs with Most Missing Data")
        pdf_quality = []
        for pdf_name, grp in df.groupby("pdf_filename"):
            missing_total = sum(len(grp) - field_fill(grp, f) for f in EXTRACT_FIELDS)
            avg_missing = missing_total / len(grp)
            pdf_quality.append({
                "PDF": pdf_name,
                "Pages": len(grp),
                "Avg Missing Fields": round(avg_missing, 1),
            })
        pdf_q_df = pd.DataFrame(pdf_quality).sort_values("Avg Missing Fields", ascending=False)
        render_table(pdf_q_df.head(15), max_rows=15, max_height="350px")

    with right_q:
        st.markdown("### Low Confidence Records")
        low_conf = df[df["extraction_confidence"] < 0.95].sort_values("extraction_confidence")
        if len(low_conf) > 0:
            lc_show = ["pdf_filename", "page_number", "drawing_title", "extraction_confidence"]
            render_table(low_conf[lc_show].head(20).reset_index(drop=True), max_rows=20, max_height="350px")
        else:
            st.markdown(f"<p style='color:{C['green']}'>All records have confidence ≥ 0.95</p>", unsafe_allow_html=True)

    st.markdown("---")

    # ── Records needing manual review ──
    st.markdown("### Records Needing Manual Review")
    st.markdown(f"<p style='color:{C['text_muted']}'>Pages missing 5+ critical fields</p>", unsafe_allow_html=True)

    critical_fields = ["drawing_title", "project_number", "route", "rw_number",
                       "division", "engineer_stamp_name", "initial_date", "rfc_date"]
    review_rows = []
    for _, row in df.iterrows():
        missing = [f for f in critical_fields
                   if pd.isna(row.get(f)) or row.get(f) == ""]
        if len(missing) >= 5:
            review_rows.append({
                "PDF": row["pdf_filename"],
                "Page": row["page_number"],
                "Title": row.get("drawing_title") or "—",
                "Missing Fields": ", ".join(missing),
                "# Missing": len(missing),
            })
    if review_rows:
        review_df = pd.DataFrame(review_rows).sort_values("# Missing", ascending=False)
        render_table(review_df.head(30), max_rows=30, max_height="300px")
        st.markdown(
            f"<p style='color:{C['text_muted']}'>{len(review_rows)} records need review out of {len(df)} total</p>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<p style='color:{C['green']}'>No records missing 5+ critical fields — data quality is solid.</p>",
            unsafe_allow_html=True,
        )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE 7 — PROJECT TIMELINE                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif page == "Project Timeline":
    st.markdown("# Project Timeline")
    st.markdown(f"<p style='color:{C['text_muted']}'>Design duration analysis — from initial design to RFC completion</p>", unsafe_allow_html=True)

    # ── Helper: parse dates ──
    def parse_date(d):
        if not d or pd.isna(d):
            return None
        try:
            return pd.to_datetime(str(d), format="%m/%d/%Y")
        except Exception:
            try:
                return pd.to_datetime(str(d))
            except Exception:
                return None

    # ── Fuzzy dedup for engineer names (merge OCR variants) ──
    from difflib import SequenceMatcher as _SM

    def _dedup_engineer_names(names_series):
        """Merge OCR variants into most-common spelling. Returns mapping dict."""
        counts = names_series.value_counts().to_dict()
        sorted_names = sorted(counts.keys(), key=lambda n: -counts[n])
        canonical_map = {}  # variant -> canonical
        for name in sorted_names:
            if name in canonical_map:
                continue
            canonical_map[name] = name  # self-map for canonical
            for other in sorted_names:
                if other in canonical_map:
                    continue
                if _SM(None, name.upper(), other.upper()).ratio() > 0.88:
                    canonical_map[other] = name
        return canonical_map

    # ── Build timeline dataframe ──
    timeline_rows = []
    for _, row in df.iterrows():
        start = parse_date(row.get("initial_date"))
        end = parse_date(row.get("rfc_date"))
        if start and end and end > start and (end - start).days < 1000:
            eng_raw = row.get("engineer_stamp_name")
            # Filter out NULL / empty / "Unknown" engineers
            if not eng_raw or pd.isna(eng_raw) or str(eng_raw).strip() == "" or str(eng_raw).strip().upper() == "UNKNOWN":
                eng_name = None
            else:
                eng_name = str(eng_raw).strip()
            # Clean division
            div_raw = row.get("division", "")
            du = str(div_raw).upper() if div_raw and not pd.isna(div_raw) else ""
            if "BRIDGE" in du:
                div = "Bridge Group"
            elif "ROADWAY" in du:
                div = "Roadway Design"
            elif "INFRASTRUCTURE" in du:
                div = "Infrastructure"
            elif "TRAFFIC" in du:
                div = "Traffic Design"
            elif "DRAINAGE" in du:
                div = "Drainage Design"
            else:
                div = "Other"
            timeline_rows.append({
                "title": row.get("drawing_title") or f"Page {row['page_number']}",
                "start": start,
                "end": end,
                "days": (end - start).days,
                "division": div,
                "engineer": eng_name,
                "route": row.get("route") or "—",
                "pdf": row.get("pdf_filename") or "—",
            })

    if not timeline_rows:
        st.warning("No drawings with valid initial_date → rfc_date ranges found.")
    else:
        tl_df = pd.DataFrame(timeline_rows)

        # Drop rows with no engineer (NULL/empty/Unknown already set to None above)
        tl_df = tl_df.dropna(subset=["engineer"]).reset_index(drop=True)

        # Apply fuzzy dedup to merge OCR spelling variants
        eng_map = _dedup_engineer_names(tl_df["engineer"])
        tl_df["engineer"] = tl_df["engineer"].map(eng_map)

        # ── Filters (empty = show all) ──
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            div_opts = sorted(tl_df["division"].unique())
            sel_div = st.multiselect("Division", div_opts, default=[], key="tl_div",
                                     placeholder="All divisions")
        with fc2:
            eng_opts = sorted(tl_df["engineer"].unique())
            sel_eng = st.multiselect("Engineer", eng_opts, default=[], key="tl_eng",
                                     placeholder="All engineers")
        with fc3:
            route_opts = sorted(tl_df["route"].unique())
            sel_route = st.multiselect("Route", route_opts, default=[], key="tl_route",
                                       placeholder="All routes")

        tl_filt = tl_df.copy()
        if sel_div:
            tl_filt = tl_filt[tl_filt["division"].isin(sel_div)]
        if sel_eng:
            tl_filt = tl_filt[tl_filt["engineer"].isin(sel_eng)]
        if sel_route:
            tl_filt = tl_filt[tl_filt["route"].isin(sel_route)]

        if len(tl_filt) == 0:
            st.info("No drawings match the selected filters.")
        else:
            # ── Summary cards ──
            tc1, tc2, tc3, tc4 = st.columns(4)
            tc1.metric("Drawings", f"{len(tl_filt):,}")
            tc2.metric("Avg Duration", f"{tl_filt['days'].mean():.0f} days")
            tc3.metric("Shortest", f"{tl_filt['days'].min()} days")
            tc4.metric("Longest", f"{tl_filt['days'].max()} days")

            # ── Average Design Duration by Engineer (top 30) ──
            eng_dur = (
                tl_filt.groupby(["engineer", "division"])["days"]
                .mean()
                .reset_index()
                .rename(columns={"days": "avg_days"})
            )
            # Keep top 30 engineers by drawing count
            eng_counts = tl_filt["engineer"].value_counts().head(30).index.tolist()
            eng_dur = eng_dur[eng_dur["engineer"].isin(eng_counts)]
            # For engineers in multiple divisions, take the one with most drawings
            eng_primary_div = (
                tl_filt.groupby(["engineer", "division"]).size()
                .reset_index(name="n")
                .sort_values("n", ascending=False)
                .drop_duplicates("engineer")
            )
            eng_chart = (
                tl_filt.groupby("engineer")["days"]
                .mean()
                .reset_index()
                .rename(columns={"days": "avg_days"})
            )
            eng_chart = eng_chart[eng_chart["engineer"].isin(eng_counts)]
            eng_chart = eng_chart.merge(
                eng_primary_div[["engineer", "division"]], on="engineer", how="left"
            )
            eng_chart = eng_chart.sort_values("avg_days", ascending=True)

            div_colors = {
                "Bridge Group": C["blue"], "Roadway Design": C["teal"],
                "Infrastructure": C["green"], "Traffic Design": C["yellow"],
                "Drainage Design": C["purple"], "Other": C["text_muted"],
            }
            eng_chart["color"] = eng_chart["division"].map(div_colors).fillna(C["text_muted"])

            fig = go.Figure()
            for div_name in eng_chart["division"].unique():
                subset = eng_chart[eng_chart["division"] == div_name]
                fig.add_trace(go.Bar(
                    y=subset["engineer"],
                    x=subset["avg_days"].round(1),
                    orientation="h",
                    name=div_name,
                    marker_color=div_colors.get(div_name, C["text_muted"]),
                    text=subset["avg_days"].round(0).astype(int).astype(str) + "d",
                    textposition="outside",
                    textfont=dict(color=C["text"], size=10),
                ))

            chart_h = max(400, len(eng_chart) * 28)
            fig.update_layout(
                title=dict(
                    text="Average Design Duration by Engineer",
                    font=dict(color=C["text"], size=15), x=0.01,
                ),
                paper_bgcolor=C["bg_card"], plot_bgcolor=C["bg_card"],
                font=dict(color=C["text_muted"], size=11),
                height=chart_h,
                margin=dict(l=10, r=60, t=50, b=50),
                barmode="stack",
                xaxis=dict(
                    title="Avg Days", gridcolor=C["border"],
                    zerolinecolor=C["border"],
                ),
                yaxis=dict(
                    gridcolor=C["border"],
                    categoryorder="array",
                    categoryarray=eng_chart["engineer"].tolist(),
                ),
                legend=dict(
                    bgcolor="rgba(0,0,0,0)",
                    font=dict(color=C["text_muted"]),
                    orientation="h", y=-0.05, x=0.5, xanchor="center",
                    yanchor="top",
                ),
                showlegend=True,
            )
            st.plotly_chart(fig, use_container_width=True)

            # ── Duration distribution by division ──
            st.markdown("### Duration by Division")
            div_stats = tl_filt.groupby("division")["days"].agg(["mean", "median", "count"]).reset_index()
            div_stats.columns = ["Division", "Avg Days", "Median Days", "Count"]
            div_stats = div_stats.sort_values("Count", ascending=False)

            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=div_stats["Division"], y=div_stats["Avg Days"],
                name="Avg", marker_color=C["teal"],
            ))
            fig2.add_trace(go.Bar(
                x=div_stats["Division"], y=div_stats["Median Days"],
                name="Median", marker_color=C["blue"],
            ))
            dark_layout(fig2, "Avg vs Median Design Duration by Division", 350, show_legend=True)
            st.plotly_chart(fig2, use_container_width=True)

            # ── Full table ──
            with st.expander("View all timeline data"):
                show_cols = ["title", "start", "end", "days", "division", "engineer", "route"]
                tl_show = tl_filt[show_cols].sort_values("start").copy()
                tl_show["start"] = tl_show["start"].dt.strftime("%m/%d/%Y")
                tl_show["end"] = tl_show["end"].dt.strftime("%m/%d/%Y")
                render_table(tl_show, max_rows=100, max_height="400px")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE 8 — BRIDGE DRAWING TRACKER                                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif page == "Bridge Tracker":
    st.markdown("# Bridge Drawing Tracker")
    st.markdown(f"<p style='color:{C['text_muted']}'>Dedicated view for bridge and structure drawings with structural details</p>", unsafe_allow_html=True)

    # ── Identify bridge drawings (title keywords + is_bridge_drawing flag only) ──
    bridge_mask = (
        df["drawing_title"].fillna("").str.upper().str.contains("BRIDGE|GIRDER|ABUTMENT|BENT|PIER|DECK", regex=True) |
        (df["is_bridge_drawing"] == 1) |
        (df["is_bridge_drawing"] == "1") |
        (df["is_bridge_drawing"] == True) |
        (df["is_bridge_drawing"] == "True")
    )
    bdf = df[bridge_mask].copy()
    bdf["_drawing_type"] = bdf["drawing_title"].apply(classify_drawing)

    # ── Filters first (empty = show all, reactive on change) ──
    bf1, bf2, bf3 = st.columns(3)
    with bf1:
        struct_opts = sorted(bdf["structure_number"].dropna().replace("", pd.NA).dropna().astype(str).unique())
        sel_struct = st.multiselect("Structure #", struct_opts, default=[], key="bt_struct",
                                    placeholder="All structures")
    with bf2:
        b_eng_opts = sorted(bdf["engineer_stamp_name"].dropna().replace("", pd.NA).dropna().unique())
        sel_b_eng = st.multiselect("Engineer", b_eng_opts, default=[], key="bt_eng",
                                   placeholder="All engineers")
    with bf3:
        b_type_opts = sorted(bdf["_drawing_type"].unique())
        sel_b_type = st.multiselect("Drawing Type", b_type_opts, default=[], key="bt_type",
                                    placeholder="All types")

    # Apply filters — empty selection means show all
    bdf_filt = bdf.copy()
    if sel_struct:
        bdf_filt = bdf_filt[bdf_filt["structure_number"].astype(str).isin(sel_struct)]
    if sel_b_eng:
        bdf_filt = bdf_filt[bdf_filt["engineer_stamp_name"].isin(sel_b_eng)]
    if sel_b_type:
        bdf_filt = bdf_filt[bdf_filt["_drawing_type"].isin(sel_b_type)]

    non_bridge_count = len(df) - len(bdf)

    st.markdown("---")

    # ── Summary cards (driven by bdf_filt) ──
    bc1, bc2, bc3, bc4 = st.columns(4)
    bc1.markdown(
        f"<div class='card' style='text-align:center'>"
        f"<p style='color:{C['text_muted']}; margin:0'>Bridge Drawings</p>"
        f"<p style='color:{C['blue']}; font-size:2.2em; margin:0; font-weight:bold'>{len(bdf_filt)}</p>"
        f"</div>", unsafe_allow_html=True,
    )
    bc2.metric("Unique Structures", bdf_filt["structure_number"].dropna().replace("", pd.NA).dropna().nunique())
    bc3.metric("Bridge Engineers", bdf_filt["engineer_stamp_name"].dropna().replace("", pd.NA).dropna().nunique())
    bc4.metric("% of All Drawings", f"{len(bdf_filt)/max(len(df),1)*100:.1f}%")

    st.markdown("---")

    # ── Bridge vs non-bridge comparison (driven by bdf_filt) ──
    st.markdown("### Bridge vs Non-Bridge Comparison")
    cmp1, cmp2 = st.columns(2)
    with cmp1:
        fig_cmp = go.Figure(data=[go.Pie(
            labels=["Bridge (filtered)", "Other Bridge", "Non-Bridge"],
            values=[len(bdf_filt), len(bdf) - len(bdf_filt), non_bridge_count],
            marker=dict(colors=[C["blue"], C["navy"], C["teal"]]),
            hole=0.5,
            textinfo="label+value",
            textfont=dict(color=C["text"]),
        )])
        dark_layout(fig_cmp, "Drawing Distribution", 300)
        st.plotly_chart(fig_cmp, use_container_width=True)

    with cmp2:
        def safe_avg_duration(frame):
            vals = frame["design_duration_days"].dropna()
            vals = vals[(vals > 0) & (vals < 1000)]
            return vals.mean() if len(vals) > 0 else 0

        bridge_dur = safe_avg_duration(bdf_filt)
        other_dur = safe_avg_duration(df[~bridge_mask])
        fig_dur = go.Figure(data=[go.Bar(
            x=["Bridge (filtered)", "Non-Bridge"],
            y=[bridge_dur, other_dur],
            marker_color=[C["blue"], C["teal"]],
            text=[f"{bridge_dur:.0f}d", f"{other_dur:.0f}d"],
            textposition="outside", textfont=dict(color=C["text"]),
        )])
        dark_layout(fig_dur, "Avg Design Duration (days)", 300)
        st.plotly_chart(fig_dur, use_container_width=True)

    st.markdown("---")

    # ── Structure breakdown (driven by bdf_filt) ──
    st.markdown("### Drawings per Structure")
    struct_series = bdf_filt["structure_number"].dropna().replace("", pd.NA).dropna().astype(str)
    if len(struct_series) > 0:
        struct_counts = struct_series.value_counts().reset_index()
        struct_counts.columns = ["structure_number", "count"]
        struct_counts = struct_counts.head(15)
        # Reverse so largest is at top of horizontal bar chart
        struct_counts = struct_counts.iloc[::-1]
        # Force labels to categorical strings
        labels = struct_counts["structure_number"].tolist()
        counts = struct_counts["count"].tolist()

        fig_s = go.Figure(data=[go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color=C["blue"],
            text=counts,
            textposition="outside", textfont=dict(color=C["text"]),
        )])
        dark_layout(fig_s, "Top Structures by Drawing Count", max(350, len(labels) * 28))
        fig_s.update_layout(
            yaxis=dict(type="category", categoryorder="array", categoryarray=labels),
            xaxis=dict(dtick=1),
            margin=dict(l=10, r=50, t=50, b=10),
        )
        st.plotly_chart(fig_s, use_container_width=True)
    else:
        st.info("No structures found for the current filter selection.")

    # ── Bridge drawings table (driven by bdf_filt) — HTML for full dark theme control ──
    st.markdown("### Bridge Drawing Details")
    table_cols = ["drawing_title", "structure_number", "milepost",
                  "engineer_stamp_name", "route", "initial_date", "rfc_date",
                  "design_duration_days"]
    table_avail = [c for c in table_cols if c in bdf_filt.columns]
    table_df = bdf_filt[table_avail].copy()
    for col in table_df.columns:
        table_df[col] = table_df[col].fillna("—").astype(str)
    if "structure_number" in table_df.columns:
        table_df = table_df.sort_values("structure_number").reset_index(drop=True)

    headers = {
        "drawing_title": "Drawing Title", "structure_number": "Structure #",
        "milepost": "Milepost", "engineer_stamp_name": "Engineer",
        "route": "Route", "initial_date": "Initial Date",
        "rfc_date": "RFC Date", "design_duration_days": "Duration",
    }
    max_rows = 50
    show_df = table_df.head(max_rows)

    # Build HTML table
    html = (
        f"<div style='max-height:500px;overflow-y:auto;border:1px solid {C['border']};border-radius:8px'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:0.82em'>"
        f"<thead><tr>"
    )
    for col in table_avail:
        html += (
            f"<th style='background:#0D7377;color:#fff;padding:10px 8px;"
            f"text-align:left;position:sticky;top:0;z-index:1;border-bottom:2px solid {C['border']}'>"
            f"{headers.get(col, col)}</th>"
        )
    html += "</tr></thead><tbody>"

    row_bg_even = C["bg_card"]
    row_bg_odd = "#0f1f38"
    for i, (_, row) in enumerate(show_df.iterrows()):
        bg = row_bg_even if i % 2 == 0 else row_bg_odd
        html += f"<tr style='background:{bg}'>"
        for col in table_avail:
            val = row[col] if row[col] != "nan" else "—"
            html += f"<td style='padding:8px;color:#E2E8F0;border-bottom:1px solid {C['border']}'>{val}</td>"
        html += "</tr>"

    html += "</tbody></table></div>"

    if len(table_df) > max_rows:
        html += (
            f"<p style='color:{C['text_muted']};font-size:0.82em;margin-top:6px'>"
            f"Showing {max_rows} of {len(table_df)} bridge drawings — use filters to narrow results</p>"
        )
    else:
        html += (
            f"<p style='color:{C['text_muted']};font-size:0.82em;margin-top:6px'>"
            f"Showing {len(table_df)} of {len(bdf)} bridge drawings</p>"
        )

    st.markdown(html, unsafe_allow_html=True)

    # ── Title block viewer for selected bridge drawing ──
    if len(bdf_filt) > 0:
        st.markdown("---")
        st.markdown("### View Title Block")
        sel_idx = st.selectbox(
            "Select a bridge drawing",
            range(len(bdf_filt)),
            format_func=lambda i: f"{bdf_filt.iloc[i]['drawing_title'] or 'Untitled'} — {str(bdf_filt.iloc[i]['structure_number'] or 'No struct #')} (pg {bdf_filt.iloc[i]['page_number']})",
            key="bt_view",
        )
        if st.button("Show Title Block", key="bt_show"):
            row = bdf_filt.iloc[sel_idx]
            pdf_path = Path(__file__).parent / "data" / "raw" / row["pdf_filename"]
            if pdf_path.exists():
                import fitz
                doc = fitz.open(str(pdf_path))
                pg = doc[int(row["page_number"]) - 1]
                pix = pg.get_pixmap(matrix=fitz.Matrix(200/72, 200/72))
                from PIL import Image as PILImage
                img = PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)
                doc.close()
                tb, _, _ = get_pipeline_components()
                tb_img = tb.crop_region(img, "full_title_block")
                st.image(tb_img, caption=f"Title block — {row['drawing_title']}", use_container_width=True)
            else:
                st.error(f"PDF not found: {row['pdf_filename']}")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PAGE 9 — REPORTS                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝
elif page == "Reports":
    st.markdown("# Reports")
    st.markdown(f"<p style='color:{C['text_muted']}'>Generate downloadable reports from extracted data</p>", unsafe_allow_html=True)

    report_type = st.selectbox("Report Type", [
        "Full Dataset Report",
        "Engineer Performance Report",
        "Route Summary Report",
    ])

    st.markdown("---")

    def generate_report_text(title, lines):
        """Build a plain-text report with header."""
        sep = "=" * 70
        header = f"{sep}\n  {title}\n  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{sep}\n"
        return header + "\n".join(lines) + "\n"

    if report_type == "Full Dataset Report":
        st.markdown("### Full Dataset Report")
        st.markdown(f"<p style='color:{C['text_muted']}'>Summary statistics across all {len(df):,} extracted drawings</p>", unsafe_allow_html=True)

        lines = [
            f"\nTotal pages extracted: {len(df):,}",
            f"Unique PDFs: {df['pdf_filename'].nunique()}",
            f"Overall fill rate: {overall_fill(df):.1f}%",
            f"Unique engineers: {df['engineer_stamp_name'].nunique()}",
            "",
            "FIELD FILL RATES",
            "-" * 40,
        ]
        for f in EXTRACT_FIELDS:
            pct = fill_pct(df, f)
            filled = field_fill(df, f)
            lines.append(f"  {f:<28s}  {filled:>5d} / {len(df)}  ({pct:5.1f}%)")

        # Division breakdown
        lines += ["", "DIVISION BREAKDOWN", "-" * 40]
        div_counts = df["division"].fillna("").replace("", "(empty)").value_counts()
        for d, c in div_counts.head(10).items():
            lines.append(f"  {d:<40s}  {c:>5d}")

        # Route breakdown
        lines += ["", "ROUTE BREAKDOWN", "-" * 40]
        route_counts = df["route"].fillna("").replace("", "(empty)").value_counts()
        for r, c in route_counts.head(10).items():
            lines.append(f"  {r:<40s}  {c:>5d}")

        # Firm breakdown
        if "firm" in df.columns:
            firm_vals = df["firm"].fillna("").replace("", pd.NA).dropna()
            if len(firm_vals) > 0:
                lines += ["", "TOP FIRMS", "-" * 40]
                for f_name, c in firm_vals.value_counts().head(10).items():
                    lines.append(f"  {f_name:<40s}  {c:>5d}")

        report_text = generate_report_text("FULL DATASET REPORT — BlueprintAI", lines)

        st.text(report_text)
        st.download_button(
            "Download Report (.txt)",
            data=report_text,
            file_name=f"blueprintai_full_report_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
        )

    elif report_type == "Engineer Performance Report":
        st.markdown("### Engineer Performance Report")

        engineers = df["engineer_stamp_name"].dropna().replace("", pd.NA).dropna().unique()
        engineers = sorted(engineers)

        if len(engineers) == 0:
            st.warning("No engineers found in the data.")
        else:
            sel_eng = st.selectbox("Select Engineer", ["All Engineers"] + list(engineers), key="rpt_eng")

            if sel_eng == "All Engineers":
                eng_df = df[df["engineer_stamp_name"].notna() & (df["engineer_stamp_name"] != "")]
            else:
                eng_df = df[df["engineer_stamp_name"] == sel_eng]

            lines = [f"\nEngineer: {sel_eng}", f"Total drawings: {len(eng_df):,}", ""]

            # Per-engineer stats
            eng_grouped = eng_df.groupby("engineer_stamp_name")
            lines += ["ENGINEER STATS", "-" * 60]
            lines.append(f"  {'Name':<30s}  {'Drawings':>8s}  {'Avg Days':>8s}  {'Divisions':>10s}")
            for name, grp in sorted(eng_grouped, key=lambda x: -len(x[1])):
                dur_vals = grp["design_duration_days"].dropna()
                dur_vals = dur_vals[(dur_vals > 0) & (dur_vals < 1000)]
                avg_d = f"{dur_vals.mean():.0f}" if len(dur_vals) > 0 else "—"
                divs = grp["division"].nunique()
                lines.append(f"  {name:<30s}  {len(grp):>8d}  {avg_d:>8s}  {divs:>10d}")

            # Drawing types
            lines += ["", "DRAWING TYPES", "-" * 40]
            types = eng_df["drawing_title"].apply(classify_drawing).value_counts()
            for t, c in types.head(10).items():
                lines.append(f"  {t:<30s}  {c:>5d}")

            report_text = generate_report_text(f"ENGINEER REPORT — {sel_eng}", lines)
            st.text(report_text)
            st.download_button(
                "Download Report (.txt)",
                data=report_text,
                file_name=f"blueprintai_engineer_report_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain",
            )

    elif report_type == "Route Summary Report":
        st.markdown("### Route Summary Report")

        routes = df["route"].dropna().replace("", pd.NA).dropna().unique()
        routes = sorted(routes)

        if len(routes) == 0:
            st.warning("No routes found in the data.")
        else:
            sel_route = st.selectbox("Select Route", ["All Routes"] + list(routes), key="rpt_route")

            if sel_route == "All Routes":
                rt_df = df[df["route"].notna() & (df["route"] != "")]
            else:
                rt_df = df[df["route"] == sel_route]

            lines = [f"\nRoute: {sel_route}", f"Total drawings: {len(rt_df):,}", ""]

            # Per-route stats
            rt_grouped = rt_df.groupby("route")
            lines += ["ROUTE STATS", "-" * 60]
            lines.append(f"  {'Route':<25s}  {'Drawings':>8s}  {'Engineers':>9s}  {'Structures':>10s}  {'Avg Days':>8s}")
            for rname, grp in sorted(rt_grouped, key=lambda x: -len(x[1])):
                eng_count = grp["engineer_stamp_name"].nunique()
                struct_count = grp["structure_number"].nunique()
                dur_vals = grp["design_duration_days"].dropna()
                dur_vals = dur_vals[(dur_vals > 0) & (dur_vals < 1000)]
                avg_d = f"{dur_vals.mean():.0f}" if len(dur_vals) > 0 else "—"
                lines.append(f"  {rname:<25s}  {len(grp):>8d}  {eng_count:>9d}  {struct_count:>10d}  {avg_d:>8s}")

            # Drawing types on this route
            lines += ["", "DRAWING TYPES", "-" * 40]
            types = rt_df["drawing_title"].apply(classify_drawing).value_counts()
            for t, c in types.head(10).items():
                lines.append(f"  {t:<30s}  {c:>5d}")

            # Engineers on this route
            lines += ["", "ENGINEERS ON ROUTE", "-" * 40]
            eng_counts = rt_df["engineer_stamp_name"].dropna().replace("", pd.NA).dropna().value_counts()
            for e, c in eng_counts.head(15).items():
                lines.append(f"  {e:<30s}  {c:>5d}")

            report_text = generate_report_text(f"ROUTE REPORT — {sel_route}", lines)
            st.text(report_text)
            st.download_button(
                "Download Report (.txt)",
                data=report_text,
                file_name=f"blueprintai_route_report_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain",
            )
