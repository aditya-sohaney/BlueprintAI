"""Automated Exploratory Data Analysis on extracted drawing data."""

import pandas as pd
import numpy as np
from pathlib import Path

from core.database import DrawingDatabase


def load_data(db_path: str = None) -> pd.DataFrame:
    """Load all extraction data from the database."""
    db = DrawingDatabase(db_path)
    df = db.export_to_dataframe()
    db.close()

    # Convert date columns
    for col in ["initial_date", "final_date", "rfc_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%m/%d/%Y", errors="coerce")

    return df


def summary_statistics(df: pd.DataFrame) -> dict:
    """Compute summary statistics for the extracted data.

    Returns:
        Dict with various statistical summaries.
    """
    stats = {}

    stats["total_pages"] = len(df)
    stats["unique_pdfs"] = df["pdf_filename"].nunique()

    # Field completeness
    field_cols = [
        "drawing_title", "location", "route", "project_number",
        "sheet_number", "total_sheets", "initial_date", "initial_designer",
        "final_date", "final_drafter", "rfc_date", "rfc_checker",
        "rw_number", "tracs_number", "engineer_stamp_name", "firm"
    ]
    completeness = {}
    for col in field_cols:
        if col in df.columns:
            non_null = df[col].notna().sum()
            completeness[col] = {
                "filled": int(non_null),
                "total": len(df),
                "pct": round(non_null / len(df) * 100, 1) if len(df) > 0 else 0
            }
    stats["field_completeness"] = completeness

    # Drawing type breakdown
    if "is_bridge_drawing" in df.columns:
        stats["bridge_vs_wall"] = {
            "bridge": int(df["is_bridge_drawing"].sum()),
            "wall": int((~df["is_bridge_drawing"].astype(bool)).sum()),
        }

    # Firm distribution
    if "firm" in df.columns:
        stats["firm_distribution"] = df["firm"].value_counts().to_dict()

    # Engineer distribution
    if "engineer_stamp_name" in df.columns:
        stats["engineer_distribution"] = (
            df["engineer_stamp_name"].dropna().value_counts().to_dict()
        )

    # Division distribution
    if "division" in df.columns:
        stats["division_distribution"] = (
            df["division"].dropna().value_counts().to_dict()
        )

    # Duration statistics
    if "design_duration_days" in df.columns:
        dur = df["design_duration_days"].dropna()
        if len(dur) > 0:
            stats["design_duration"] = {
                "mean": round(dur.mean(), 1),
                "median": round(dur.median(), 1),
                "min": int(dur.min()),
                "max": int(dur.max()),
                "std": round(dur.std(), 1),
            }

    if "rfc_duration_days" in df.columns:
        dur = df["rfc_duration_days"].dropna()
        if len(dur) > 0:
            stats["rfc_duration"] = {
                "mean": round(dur.mean(), 1),
                "median": round(dur.median(), 1),
                "min": int(dur.min()),
                "max": int(dur.max()),
                "std": round(dur.std(), 1),
            }

    # Date range
    for date_col in ["initial_date", "final_date", "rfc_date"]:
        if date_col in df.columns:
            dates = df[date_col].dropna()
            if len(dates) > 0:
                stats[f"{date_col}_range"] = {
                    "earliest": str(dates.min().date()),
                    "latest": str(dates.max().date()),
                }

    return stats


def answer_analysis_questions(df: pd.DataFrame) -> dict:
    """Answer the specific analysis questions from the spec.

    Returns:
        Dict with answers to each question.
    """
    answers = {}

    # Q1: Which drawings are bridge drawings vs retaining walls?
    if "is_bridge_drawing" in df.columns:
        bridges = df[df["is_bridge_drawing"] == True]
        walls = df[df["is_bridge_drawing"] == False]
        answers["bridge_vs_wall"] = {
            "bridges": len(bridges),
            "walls": len(walls),
            "bridge_titles": bridges["drawing_title"].tolist() if len(bridges) > 0 else [],
        }

    # Q2: Average time to design from initial to RFC date?
    if "rfc_duration_days" in df.columns:
        dur = df["rfc_duration_days"].dropna()
        answers["avg_design_to_rfc_days"] = round(dur.mean(), 1) if len(dur) > 0 else None

    # Q3 & Q4: Engineer with shortest/longest design time
    if "engineer_stamp_name" in df.columns and "design_duration_days" in df.columns:
        eng_dur = df.groupby("engineer_stamp_name")["design_duration_days"].mean().dropna()
        if len(eng_dur) > 0:
            answers["fastest_engineer"] = {
                "name": eng_dur.idxmin(),
                "avg_days": round(eng_dur.min(), 1)
            }
            answers["slowest_engineer"] = {
                "name": eng_dur.idxmax(),
                "avg_days": round(eng_dur.max(), 1)
            }

    # Q5: Which firm handles the most bridge work?
    if "firm" in df.columns and "is_bridge_drawing" in df.columns:
        bridge_firms = df[df["is_bridge_drawing"] == True]["firm"].value_counts()
        if len(bridge_firms) > 0:
            answers["top_bridge_firm"] = {
                "firm": bridge_firms.index[0],
                "count": int(bridge_firms.iloc[0])
            }

    # Q6: Geographic distribution (from milepost/station)
    if "milepost" in df.columns:
        answers["station_range"] = df["milepost"].dropna().tolist()

    # Q7: Seasonal patterns in RFC dates
    if "rfc_date" in df.columns:
        rfc_dates = df["rfc_date"].dropna()
        if len(rfc_dates) > 0:
            monthly = rfc_dates.dt.month.value_counts().sort_index()
            answers["rfc_monthly_pattern"] = {
                int(month): int(count) for month, count in monthly.items()
            }

    # Q8: Engineer-firm pairs
    if "engineer_stamp_name" in df.columns and "firm" in df.columns:
        pairs = df.groupby(["engineer_stamp_name", "firm"]).size().reset_index(name="count")
        pairs = pairs.sort_values("count", ascending=False)
        answers["engineer_firm_pairs"] = [
            {"engineer": row["engineer_stamp_name"], "firm": row["firm"],
             "count": int(row["count"])}
            for _, row in pairs.head(10).iterrows()
        ]

    return answers


def print_eda_report(stats: dict, answers: dict):
    """Print a formatted EDA report to the console."""
    print("=" * 70)
    print("EXPLORATORY DATA ANALYSIS REPORT")
    print("=" * 70)

    print(f"\nTotal Pages Analyzed: {stats.get('total_pages', 0)}")
    print(f"Unique PDFs: {stats.get('unique_pdfs', 0)}")

    print("\n--- Field Completeness ---")
    for field, info in stats.get("field_completeness", {}).items():
        bar = "#" * int(info["pct"] / 5) + "." * (20 - int(info["pct"] / 5))
        print(f"  {field:<25} [{bar}] {info['pct']}% ({info['filled']}/{info['total']})")

    if "firm_distribution" in stats:
        print("\n--- Firm Distribution ---")
        for firm, count in stats["firm_distribution"].items():
            print(f"  {firm}: {count}")

    if "engineer_distribution" in stats:
        print("\n--- Engineer Distribution ---")
        for eng, count in stats["engineer_distribution"].items():
            print(f"  {eng}: {count}")

    if "design_duration" in stats:
        d = stats["design_duration"]
        print(f"\n--- Design Duration (days) ---")
        print(f"  Mean: {d['mean']}, Median: {d['median']}, "
              f"Min: {d['min']}, Max: {d['max']}")

    print("\n--- Analysis Questions ---")
    for key, value in answers.items():
        print(f"\n  {key}:")
        if isinstance(value, dict):
            for k, v in value.items():
                print(f"    {k}: {v}")
        elif isinstance(value, list):
            for item in value[:5]:
                print(f"    {item}")
        else:
            print(f"    {value}")
