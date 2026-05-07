"""Quality Assessment for extracted drawing data.

Grades each page's extraction quality:
    A  — High confidence, all critical fields present, no conflicts
    B  — Moderate confidence, most fields present, minor issues
    C  — Low confidence, many fields missing or conflicting
    NOT_ADOT  — Page is not an ADOT engineering drawing
    CORRUPTED — Page could not be processed (OCR failure, blank, etc.)
"""

import logging

logger = logging.getLogger(__name__)

# Fields required for a valid ADOT drawing extraction
CRITICAL_FIELDS = {
    "drawing_title", "project_number", "route", "rw_number", "sheet_number",
}

IMPORTANT_FIELDS = {
    "initial_date", "final_date", "rfc_date", "tracs_number", "location",
}

# Keywords that indicate this is an ADOT engineering drawing
ADOT_ANCHORS = {
    "ARIZONA", "ADOT", "TRACS", "H8827", "SR 202L", "LOOP 202",
    "DEPARTMENT OF TRANSPORTATION", "RECORD DRAWING", "FINAL RECORD",
}


class QAAssessor:
    """Assess extraction quality and assign grades."""

    def assess_page(self, merged_fields: dict, ocr_texts: dict = None,
                    vlm_metadata: dict = None) -> dict:
        """Grade a single page's extraction quality.

        Args:
            merged_fields: Dict of field_name -> MergedField.
            ocr_texts: Optional dict of region_name -> raw OCR text (for NOT_ADOT check).
            vlm_metadata: Optional dict with is_adot_drawing, is_blank_page flags from VLM.

        Returns:
            Dict with grade, reasons, and field statistics.
        """
        ocr_texts = ocr_texts or {}
        vlm_metadata = vlm_metadata or {}

        # Check for blank page
        if vlm_metadata.get("is_blank_page", False):
            return self._result("CORRUPTED", ["VLM flagged as blank page"])

        # Check for non-ADOT drawing
        if vlm_metadata.get("is_adot_drawing") is False:
            return self._result("NOT_ADOT", ["VLM flagged as non-ADOT drawing"])

        # OCR-based NOT_ADOT check (when VLM wasn't used)
        if ocr_texts and not vlm_metadata:
            if not self._has_adot_anchors(ocr_texts):
                return self._result("NOT_ADOT", ["No ADOT keywords found in OCR text"])

        # Check for CORRUPTED (no meaningful extraction)
        filled_count = sum(
            1 for mf in merged_fields.values()
            if mf.value is not None and mf.field_name in CRITICAL_FIELDS | IMPORTANT_FIELDS
        )
        total_ocr_text = " ".join(ocr_texts.values()) if ocr_texts else ""
        if filled_count == 0 and len(total_ocr_text.strip()) < 50:
            return self._result("CORRUPTED", ["No fields extracted, minimal OCR text"])

        # Grade based on field coverage and confidence
        reasons = []

        # Critical fields
        critical_present = 0
        for f in CRITICAL_FIELDS:
            mf = merged_fields.get(f)
            if mf and mf.value is not None:
                critical_present += 1
            else:
                reasons.append(f"Missing critical field: {f}")

        # Important fields
        important_present = 0
        for f in IMPORTANT_FIELDS:
            mf = merged_fields.get(f)
            if mf and mf.value is not None:
                important_present += 1

        # Confidence stats
        confidences = [
            mf.confidence for mf in merged_fields.values()
            if mf.value is not None and mf.confidence > 0
        ]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        # Conflict count
        flagged = sum(1 for mf in merged_fields.values() if mf.flagged)
        if flagged > 0:
            reasons.append(f"{flagged} field(s) have conflicting sources")

        # Grading logic
        critical_ratio = critical_present / len(CRITICAL_FIELDS)
        important_ratio = important_present / len(IMPORTANT_FIELDS)

        if critical_ratio >= 0.8 and avg_conf >= 0.6 and flagged <= 2:
            grade = "A"
        elif critical_ratio >= 0.6 and avg_conf >= 0.4:
            grade = "B"
            if critical_ratio < 0.8:
                reasons.append(f"Only {critical_present}/{len(CRITICAL_FIELDS)} critical fields")
            if avg_conf < 0.6:
                reasons.append(f"Low average confidence: {avg_conf:.2f}")
        else:
            grade = "C"
            if critical_ratio < 0.6:
                reasons.append(f"Only {critical_present}/{len(CRITICAL_FIELDS)} critical fields")
            if avg_conf < 0.4:
                reasons.append(f"Very low average confidence: {avg_conf:.2f}")

        return self._result(grade, reasons, {
            "critical_fields": f"{critical_present}/{len(CRITICAL_FIELDS)}",
            "important_fields": f"{important_present}/{len(IMPORTANT_FIELDS)}",
            "avg_confidence": round(avg_conf, 3),
            "flagged_count": flagged,
            "total_filled": sum(1 for mf in merged_fields.values() if mf.value is not None),
            "total_fields": len(merged_fields),
        })

    def _has_adot_anchors(self, ocr_texts: dict) -> bool:
        """Check if OCR text contains ADOT-specific keywords."""
        combined = " ".join(ocr_texts.values()).upper()
        matches = sum(1 for kw in ADOT_ANCHORS if kw in combined)
        return matches >= 2  # Require at least 2 anchors

    def _result(self, grade: str, reasons: list, stats: dict = None) -> dict:
        return {
            "quality_grade": grade,
            "reasons": reasons,
            "stats": stats or {},
        }

    def assess_pdf(self, all_pages: list, all_ocr_texts: dict = None) -> dict:
        """Assess quality across all pages of a PDF.

        Args:
            all_pages: List of (page_num, merged_fields) tuples.
            all_ocr_texts: Optional dict of page_num -> {region_name -> raw text}.

        Returns:
            Dict with per-page grades and summary.
        """
        all_ocr_texts = all_ocr_texts or {}
        grades = {}
        grade_counts = {"A": 0, "B": 0, "C": 0, "NOT_ADOT": 0, "CORRUPTED": 0}

        for page_num, merged_fields in all_pages:
            ocr_texts = all_ocr_texts.get(page_num, {})
            result = self.assess_page(merged_fields, ocr_texts)
            grades[page_num] = result
            grade_counts[result["quality_grade"]] += 1

        total = len(all_pages)
        return {
            "per_page": grades,
            "summary": {
                "total_pages": total,
                "grade_counts": grade_counts,
                "grade_a_pct": round(grade_counts["A"] / total * 100, 1) if total else 0,
                "grade_b_pct": round(grade_counts["B"] / total * 100, 1) if total else 0,
                "grade_c_pct": round(grade_counts["C"] / total * 100, 1) if total else 0,
                "not_adot_pct": round(grade_counts["NOT_ADOT"] / total * 100, 1) if total else 0,
                "corrupted_pct": round(grade_counts["CORRUPTED"] / total * 100, 1) if total else 0,
            },
        }
