"""Interactive Plotly/Streamlit dashboards for extraction analytics."""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pathlib import Path

from core.database import DrawingDatabase


def create_overview_dashboard(df: pd.DataFrame, output_dir: str = None):
    """Create a comprehensive HTML dashboard with multiple charts.

    Args:
        df: DataFrame from DrawingDatabase.export_to_dataframe().
        output_dir: Directory to save the HTML dashboard.
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "data" / "exports"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert dates
    for col in ["initial_date", "final_date", "rfc_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%m/%d/%Y", errors="coerce")

    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=(
            "Firm Distribution", "Engineer Distribution",
            "Design Duration by Engineer", "RFC Timeline",
            "Field Completeness", "Division Breakdown"
        ),
        specs=[
            [{"type": "pie"}, {"type": "pie"}],
            [{"type": "bar"}, {"type": "scatter"}],
            [{"type": "bar"}, {"type": "pie"}]
        ],
        vertical_spacing=0.12
    )

    # 1. Firm distribution pie chart
    if "firm" in df.columns:
        firm_counts = df["firm"].dropna().value_counts()
        fig.add_trace(go.Pie(
            labels=firm_counts.index.tolist(),
            values=firm_counts.values.tolist(),
            name="Firms"
        ), row=1, col=1)

    # 2. Engineer distribution pie chart
    if "engineer_stamp_name" in df.columns:
        eng_counts = df["engineer_stamp_name"].dropna().value_counts()
        fig.add_trace(go.Pie(
            labels=eng_counts.index.tolist(),
            values=eng_counts.values.tolist(),
            name="Engineers"
        ), row=1, col=2)

    # 3. Design duration by engineer
    if "engineer_stamp_name" in df.columns and "design_duration_days" in df.columns:
        eng_dur = df.groupby("engineer_stamp_name")["design_duration_days"].mean().dropna()
        fig.add_trace(go.Bar(
            x=eng_dur.index.tolist(),
            y=eng_dur.values.tolist(),
            name="Avg Design Days",
            marker_color="steelblue"
        ), row=2, col=1)

    # 4. RFC dates timeline
    if "rfc_date" in df.columns and "rw_number" in df.columns:
        rfc_data = df[df["rfc_date"].notna()].sort_values("rfc_date")
        fig.add_trace(go.Scatter(
            x=rfc_data["rfc_date"],
            y=rfc_data["rw_number"],
            mode="markers+text",
            text=rfc_data["rw_number"],
            name="RFC Dates"
        ), row=2, col=2)

    # 5. Field completeness
    field_cols = [
        "drawing_title", "location", "route", "project_number",
        "sheet_number", "initial_date", "final_date", "rfc_date",
        "rw_number", "tracs_number", "engineer_stamp_name", "firm"
    ]
    completeness = []
    for col in field_cols:
        if col in df.columns:
            pct = df[col].notna().mean() * 100
            completeness.append({"field": col, "pct": pct})
    if completeness:
        comp_df = pd.DataFrame(completeness)
        fig.add_trace(go.Bar(
            x=comp_df["field"].tolist(),
            y=comp_df["pct"].tolist(),
            name="Completeness %",
            marker_color=["green" if p >= 80 else "orange" if p >= 50 else "red"
                          for p in comp_df["pct"]]
        ), row=3, col=1)

    # 6. Division breakdown
    if "division" in df.columns:
        div_counts = df["division"].dropna().value_counts()
        fig.add_trace(go.Pie(
            labels=div_counts.index.tolist(),
            values=div_counts.values.tolist(),
            name="Divisions"
        ), row=3, col=2)

    fig.update_layout(
        title_text="ADOT Drawing Extraction Dashboard",
        height=1200,
        showlegend=False
    )

    output_path = output_dir / "dashboard.html"
    fig.write_html(str(output_path))
    print(f"Dashboard saved to {output_path}")
    return output_path


def run_streamlit_dashboard():
    """Launch a Streamlit interactive dashboard.

    Run with: streamlit run analytics/dashboards.py
    """
    try:
        import streamlit as st
    except ImportError:
        print("Streamlit not available. Use create_overview_dashboard() instead.")
        return

    st.set_page_config(page_title="ADOT Drawing Analytics", layout="wide")
    st.title("ADOT Engineering Drawing Extraction Analytics")

    db = DrawingDatabase()
    df = db.export_to_dataframe()
    db.close()

    if df.empty:
        st.warning("No data in database. Run the extraction pipeline first.")
        return

    for col in ["initial_date", "final_date", "rfc_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%m/%d/%Y", errors="coerce")

    # Sidebar filters
    st.sidebar.header("Filters")
    if "firm" in df.columns:
        firms = st.sidebar.multiselect("Firm", df["firm"].dropna().unique())
        if firms:
            df = df[df["firm"].isin(firms)]

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Pages", len(df))
    col2.metric("Unique Engineers", df["engineer_stamp_name"].nunique())
    col3.metric("Unique Firms", df["firm"].nunique())
    if "design_duration_days" in df.columns:
        avg_dur = df["design_duration_days"].dropna().mean()
        col4.metric("Avg Design Days", f"{avg_dur:.0f}" if pd.notna(avg_dur) else "N/A")

    # Charts
    col_left, col_right = st.columns(2)

    with col_left:
        if "firm" in df.columns:
            fig = px.pie(df, names="firm", title="Firm Distribution")
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        if "engineer_stamp_name" in df.columns:
            fig = px.pie(df, names="engineer_stamp_name", title="Engineer Distribution")
            st.plotly_chart(fig, use_container_width=True)

    # Data table
    st.subheader("Extracted Data")
    st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    run_streamlit_dashboard()
