"""Accuracy evaluation against ground truth data."""

import json
import re
from pathlib import Path
from difflib import SequenceMatcher


def _normalize(value: str) -> str:
    """Normalize a value for comparison: uppercase, strip, collapse whitespace."""
    if value is None:
        return ""
    return re.sub(r'\s+', ' ', str(value).strip().upper())


def _similarity(a: str, b: str) -> float:
    """Compute string similarity ratio (0.0 - 1.0)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


class ExtractionBenchmark:
    """Evaluate extraction accuracy against ground truth."""

    def __init__(self, ground_truth_path: str = None):
        if ground_truth_path is None:
            ground_truth_path = Path(__file__).parent / "ground_truth.json"
        with open(ground_truth_path) as f:
            self.ground_truth = json.load(f)
        self.gt_pages = self.ground_truth["pages"]

    def evaluate_page(self, page_num: int, merged_fields: dict) -> dict:
        """Compare extraction against ground truth for one page.

        Args:
            page_num: 1-indexed page number.
            merged_fields: Dict of field_name -> MergedField.

        Returns:
            Dict with per-field evaluation results.
        """
        page_key = str(page_num)
        if page_key not in self.gt_pages:
            return {"error": f"No ground truth for page {page_num}"}

        gt = self.gt_pages[page_key]
        results = {}

        for field_name, gt_value in gt.items():
            extracted = merged_fields.get(field_name)
            extracted_value = extracted.value if extracted else None

            # Handle booleans - compare semantically (False == 0 == "0" == "false")
            if isinstance(gt_value, bool):
                gt_bool = gt_value
                if extracted_value is None:
                    ext_bool = None
                elif isinstance(extracted_value, bool):
                    ext_bool = extracted_value
                elif isinstance(extracted_value, (int, float)):
                    ext_bool = bool(extracted_value)
                elif str(extracted_value).upper() in ("TRUE", "1", "YES"):
                    ext_bool = True
                elif str(extracted_value).upper() in ("FALSE", "0", "NO"):
                    ext_bool = False
                else:
                    ext_bool = None
                exact_match = gt_bool == ext_bool
                similarity = 1.0 if exact_match else 0.0
            else:
                gt_str = str(gt_value) if gt_value is not None else ""
                ext_str = str(extracted_value) if extracted_value is not None else ""
                exact_match = _normalize(gt_str) == _normalize(ext_str)
                similarity = _similarity(gt_str, ext_str)

            results[field_name] = {
                "ground_truth": gt_value,
                "extracted": extracted_value,
                "exact_match": exact_match,
                "similarity": round(similarity, 3),
                "confidence": extracted.confidence if extracted else 0.0,
            }

        return results

    def evaluate_all(self, all_results: list) -> dict:
        """Run evaluation across all ground truth pages.

        Args:
            all_results: List of (page_number, merged_fields, derived_fields) tuples.

        Returns:
            Dict with aggregate metrics.
        """
        page_evaluations = {}
        field_stats = {}

        # Build merged_fields lookup by page number
        results_by_page = {}
        for page_num, merged, derived in all_results:
            # Add derived fields to merged for evaluation
            from core.merger import MergedField
            combined = dict(merged)
            for key, val in derived.items():
                if key not in combined:
                    combined[key] = MergedField(
                        field_name=key, value=str(val) if val is not None else None,
                        confidence=1.0 if val is not None else 0.0,
                        source="derived"
                    )
            results_by_page[page_num] = combined

        for page_key in self.gt_pages:
            page_num = int(page_key)
            if page_num not in results_by_page:
                continue

            page_eval = self.evaluate_page(page_num, results_by_page[page_num])
            page_evaluations[page_num] = page_eval

            for field_name, result in page_eval.items():
                if field_name == "error":
                    continue
                if field_name not in field_stats:
                    field_stats[field_name] = {
                        "total": 0, "exact_matches": 0,
                        "similarities": [], "confidences": []
                    }
                field_stats[field_name]["total"] += 1
                if result["exact_match"]:
                    field_stats[field_name]["exact_matches"] += 1
                field_stats[field_name]["similarities"].append(result["similarity"])
                field_stats[field_name]["confidences"].append(result["confidence"])

        # Compute aggregate metrics
        field_accuracy = {}
        for field_name, stats in field_stats.items():
            field_accuracy[field_name] = {
                "accuracy": stats["exact_matches"] / stats["total"] if stats["total"] > 0 else 0,
                "avg_similarity": sum(stats["similarities"]) / len(stats["similarities"]) if stats["similarities"] else 0,
                "avg_confidence": sum(stats["confidences"]) / len(stats["confidences"]) if stats["confidences"] else 0,
                "total_pages": stats["total"],
                "exact_matches": stats["exact_matches"],
            }

        # Overall accuracy
        total_fields = sum(s["total"] for s in field_stats.values())
        total_matches = sum(s["exact_matches"] for s in field_stats.values())
        overall_accuracy = total_matches / total_fields if total_fields > 0 else 0

        return {
            "overall_accuracy": round(overall_accuracy, 3),
            "total_fields_evaluated": total_fields,
            "total_exact_matches": total_matches,
            "per_field_accuracy": field_accuracy,
            "per_page_evaluations": page_evaluations,
        }

    def print_report(self, evaluation: dict):
        """Print a formatted accuracy report."""
        print("=" * 70)
        print("EXTRACTION ACCURACY REPORT")
        print("=" * 70)
        print(f"\nOverall Accuracy: {evaluation['overall_accuracy']:.1%}")
        print(f"Fields Evaluated: {evaluation['total_fields_evaluated']}")
        print(f"Exact Matches: {evaluation['total_exact_matches']}")

        print(f"\n{'Field':<25} {'Accuracy':>10} {'Avg Sim':>10} {'Avg Conf':>10} {'N':>5}")
        print("-" * 65)

        for field_name, stats in sorted(
            evaluation["per_field_accuracy"].items(),
            key=lambda x: x[1]["accuracy"], reverse=True
        ):
            print(f"{field_name:<25} {stats['accuracy']:>9.1%} "
                  f"{stats['avg_similarity']:>9.3f} "
                  f"{stats['avg_confidence']:>9.3f} "
                  f"{stats['total_pages']:>5}")

        print(f"\n{'=' * 70}")
        print("PER-PAGE DETAILS")
        print("=" * 70)

        for page_num, page_eval in sorted(evaluation["per_page_evaluations"].items()):
            matches = sum(1 for r in page_eval.values()
                          if isinstance(r, dict) and r.get("exact_match"))
            total = sum(1 for r in page_eval.values()
                        if isinstance(r, dict) and "exact_match" in r)
            print(f"\nPage {page_num}: {matches}/{total} exact matches")
            for field_name, result in sorted(page_eval.items()):
                if not isinstance(result, dict) or "exact_match" not in result:
                    continue
                status = "OK" if result["exact_match"] else "MISS"
                marker = "  " if result["exact_match"] else ">>"
                print(f"  {marker} [{status}] {field_name}: "
                      f"got '{result['extracted']}' "
                      f"(expected '{result['ground_truth']}') "
                      f"sim={result['similarity']:.2f}")
