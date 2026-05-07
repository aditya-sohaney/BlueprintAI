"""Confidence-based field merging from multiple extraction sources."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MergedField:
    """A single field after merging results from all extraction tiers."""
    field_name: str
    value: Optional[str]
    confidence: float
    source: str
    alternatives: list = field(default_factory=list)  # Other values from other sources
    flagged: bool = False   # True if sources conflict


ALL_FIELDS = [
    "drawing_title", "location", "route", "project_number",
    "sheet_number", "total_sheets", "initial_date", "initial_designer",
    "final_date", "final_drafter", "rfc_date", "rfc_checker",
    "rw_number", "tracs_number", "engineer_stamp_name", "firm",
    "structure_number", "milepost", "division"
]

# Source priority multipliers - higher = more trusted
SOURCE_PRIORITY = {
    "embedded_text": 1.0,
    "ocr_regex": 0.90,
    "claude_vlm": 0.85,
    "qwen_vlm": 0.80,
    "ocr_regex_corrected": 0.70,
    "ocr_regex_fallback": 0.60,
}


def _effective_confidence(confidence: float, source: str) -> float:
    """Compute effective confidence = raw confidence * source priority."""
    priority = SOURCE_PRIORITY.get(source, 0.5)
    return confidence * priority


def _values_match(v1: str, v2: str) -> bool:
    """Check if two values are essentially the same (case-insensitive, whitespace-normalized)."""
    if v1 is None or v2 is None:
        return v1 == v2
    return v1.strip().upper() == v2.strip().upper()


class ResultMerger:
    """Merge results from OCR/regex, embedded text, and VLM into unified extractions."""

    def merge_page_results(self, tier1_results: list, embedded_results: list,
                           tier2_results: list) -> dict:
        """Merge all extraction results for a single page.

        Priority: embedded_text > ocr_regex > vlm > fallback.
        When multiple sources provide the same field, pick highest effective confidence.
        Flag fields where sources disagree.

        Args:
            tier1_results: List of FieldExtraction from regex_extractor.
            embedded_results: List of FieldExtraction from embedded text.
            tier2_results: List of VLMExtraction from vlm_engine.

        Returns:
            Dict of field_name -> MergedField.
        """
        # Group all results by field name
        field_candidates = {}

        for ext in tier1_results:
            if ext.value is not None:
                field_candidates.setdefault(ext.field_name, []).append({
                    "value": ext.value,
                    "confidence": ext.confidence,
                    "source": ext.source,
                })

        for ext in embedded_results:
            if ext.value is not None:
                field_candidates.setdefault(ext.field_name, []).append({
                    "value": ext.value,
                    "confidence": ext.confidence,
                    "source": ext.source,
                })

        for ext in tier2_results:
            if ext.value is not None:
                field_candidates.setdefault(ext.field_name, []).append({
                    "value": ext.value,
                    "confidence": ext.confidence,
                    "source": ext.source,
                })

        # For each field, pick the best candidate
        merged = {}
        for field_name, candidates in field_candidates.items():
            # Sort by effective confidence (descending)
            candidates.sort(
                key=lambda c: _effective_confidence(c["confidence"], c["source"]),
                reverse=True
            )

            best = candidates[0]
            alternatives = candidates[1:]

            # Check for conflicts
            flagged = False
            if len(candidates) > 1:
                for alt in alternatives:
                    if not _values_match(best["value"], alt["value"]):
                        flagged = True
                        break

            merged[field_name] = MergedField(
                field_name=field_name,
                value=best["value"],
                confidence=_effective_confidence(best["confidence"], best["source"]),
                source=best["source"],
                alternatives=[
                    {"value": a["value"], "confidence": a["confidence"], "source": a["source"]}
                    for a in alternatives
                ],
                flagged=flagged
            )

        # Ensure all expected fields exist (even if None)
        for f in ALL_FIELDS:
            if f not in merged:
                merged[f] = MergedField(
                    field_name=f, value=None, confidence=0.0,
                    source="none", flagged=False
                )

        return merged

    def merge_dual_pass(self, tier1_results: list, embedded_results: list,
                        vlm_results: list) -> dict:
        """Dual-pass merge: OCR+regex (Pass 1) then VLM (Pass 2).

        VLM results fill in any fields that Pass 1 missed or had low confidence.
        When both passes have a value, use confidence-weighted selection with
        conflict flagging.

        Args:
            tier1_results: List of FieldExtraction from regex_extractor.
            embedded_results: List of FieldExtraction from embedded text.
            vlm_results: List of VLMExtraction from vlm_engine.extract_all_fields().

        Returns:
            Dict of field_name -> MergedField.
        """
        # Pass 1: Merge OCR + embedded (same as single-pass)
        pass1 = self.merge_page_results(tier1_results, embedded_results, [])

        # Pass 2: Overlay VLM results
        for ext in vlm_results:
            if ext.value is None:
                continue

            field_name = ext.field_name
            eff_conf = _effective_confidence(ext.confidence, ext.source)
            existing = pass1.get(field_name)

            if existing is None or existing.value is None:
                # VLM fills a gap
                pass1[field_name] = MergedField(
                    field_name=field_name,
                    value=ext.value,
                    confidence=eff_conf,
                    source=ext.source,
                    flagged=False,
                )
            else:
                # Both have values — pick higher effective confidence, flag conflicts
                existing_eff = _effective_confidence(existing.confidence, existing.source)
                conflict = not _values_match(existing.value, ext.value)

                if eff_conf > existing_eff:
                    # VLM wins
                    pass1[field_name] = MergedField(
                        field_name=field_name,
                        value=ext.value,
                        confidence=eff_conf,
                        source=ext.source,
                        alternatives=[{
                            "value": existing.value,
                            "confidence": existing.confidence,
                            "source": existing.source,
                        }] + existing.alternatives,
                        flagged=conflict,
                    )
                else:
                    # OCR wins — add VLM as alternative
                    if conflict:
                        existing.flagged = True
                    existing.alternatives.append({
                        "value": ext.value,
                        "confidence": ext.confidence,
                        "source": ext.source,
                    })

        # Ensure all fields present
        for f in ALL_FIELDS:
            if f not in pass1:
                pass1[f] = MergedField(
                    field_name=f, value=None, confidence=0.0,
                    source="none", flagged=False
                )

        return pass1
