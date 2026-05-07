"""Generate visual accuracy reports using Plotly."""

import json
from pathlib import Path

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


def generate_accuracy_charts(evaluation: dict, output_dir: str = None):
    """Generate interactive Plotly charts from evaluation results.

    Args:
        evaluation: Output from ExtractionBenchmark.evaluate_all().
        output_dir: Directory to save HTML charts.
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "data" / "exports"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    field_accuracy = evaluation["per_field_accuracy"]

    # Chart 1: Per-field accuracy bar chart
    fields = sorted(field_accuracy.keys())
    accuracies = [field_accuracy[f]["accuracy"] for f in fields]
    similarities = [field_accuracy[f]["avg_similarity"] for f in fields]

    fig = make_subplots(rows=1, cols=1)
    fig.add_trace(go.Bar(
        x=fields, y=accuracies, name="Exact Match Accuracy",
        marker_color=["green" if a >= 0.8 else "orange" if a >= 0.5 else "red"
                       for a in accuracies]
    ))
    fig.update_layout(
        title="Per-Field Extraction Accuracy",
        xaxis_title="Field Name",
        yaxis_title="Accuracy",
        yaxis_range=[0, 1.05],
        xaxis_tickangle=-45,
        height=500
    )
    fig.write_html(str(output_dir / "field_accuracy.html"))

    # Chart 2: Per-page completeness heatmap
    page_evals = evaluation["per_page_evaluations"]
    if page_evals:
        pages = sorted(page_evals.keys())
        all_fields = sorted(set(
            f for p in page_evals.values()
            for f in p if isinstance(p[f], dict) and "similarity" in p[f]
        ))

        z_data = []
        for f in all_fields:
            row = []
            for p in pages:
                if f in page_evals[p] and isinstance(page_evals[p][f], dict):
                    row.append(page_evals[p][f]["similarity"])
                else:
                    row.append(0)
            z_data.append(row)

        fig2 = go.Figure(data=go.Heatmap(
            z=z_data,
            x=[f"Page {p}" for p in pages],
            y=all_fields,
            colorscale="RdYlGn",
            zmin=0, zmax=1
        ))
        fig2.update_layout(
            title="Extraction Similarity Heatmap (Page x Field)",
            height=600
        )
        fig2.write_html(str(output_dir / "extraction_heatmap.html"))

    # Chart 3: Confidence distribution
    all_confs = []
    all_field_names = []
    for page_eval in page_evals.values():
        for field_name, result in page_eval.items():
            if isinstance(result, dict) and "confidence" in result:
                all_confs.append(result["confidence"])
                all_field_names.append(field_name)

    if all_confs:
        fig3 = go.Figure(data=go.Histogram(
            x=all_confs, nbinsx=20,
            marker_color="steelblue"
        ))
        fig3.update_layout(
            title="Extraction Confidence Distribution",
            xaxis_title="Confidence Score",
            yaxis_title="Count"
        )
        fig3.write_html(str(output_dir / "confidence_distribution.html"))

    print(f"Charts saved to {output_dir}/")
    return output_dir
