"""Validation, normalization, and derived field computation."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse MM/DD/YYYY date string."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except ValueError:
        return None


def _fuzzy_match_name(name: str, known_names: dict) -> Optional[str]:
    """Match an extracted name against known engineers using fuzzy matching."""
    if not name:
        return None
    name_upper = name.upper().strip()
    for canonical, info in known_names.items():
        if name_upper == canonical.upper():
            return canonical
        for alias in info.get("aliases", []):
            if name_upper == alias.upper():
                return canonical
    return name  # Return as-is if no match


class Validator:
    """Validate extracted fields and compute derived values."""

    def __init__(self, engineers_path: str = None, firms_path: str = None):
        base = Path(__file__).parent.parent / "config"

        if engineers_path is None:
            engineers_path = base / "engineers_lookup.json"
        if firms_path is None:
            firms_path = base / "firms_lookup.json"

        with open(engineers_path) as f:
            self.engineers = json.load(f)
        with open(firms_path) as f:
            self.firms = json.load(f)

    def validate_date(self, value: str) -> tuple:
        """Validate MM/DD/YYYY format and reasonable date range.

        Returns:
            (is_valid, normalized_value_or_error_message)
        """
        if not value:
            return (False, "Empty date")

        dt = _parse_date(value)
        if dt is None:
            return (False, f"Invalid date format: {value}")

        # Reasonable range for ADOT drawings
        if dt.year < 2000 or dt.year > 2030:
            return (False, f"Date out of range: {value}")

        return (True, value.strip())

    def validate_project_number(self, value: str) -> tuple:
        """Validate project number format (e.g., 202-D-I200IS)."""
        if not value:
            return (False, "Empty project number")
        pattern = r'^\d{3}-[A-Z]-[A-Z(]\d{3,4}[A-Z)]*[A-Z]?$'
        if re.match(pattern, value):
            return (True, value)
        return (False, f"Invalid project number format: {value}")

    def validate_rw_number(self, value: str) -> tuple:
        """Validate RW number format (e.g., RW-003.107)."""
        if not value:
            return (False, "Empty RW number")
        pattern = r'^RW-\d{3}\.\d{3}$'
        if re.match(pattern, value):
            return (True, value)
        return (False, f"Invalid RW number format: {value}")

    def validate_all(self, merged_fields: dict) -> list:
        """Run all validations on merged fields.

        Args:
            merged_fields: Dict of field_name -> MergedField.

        Returns:
            List of (field_name, issue_description) for any validation failures.
        """
        issues = []

        # Validate dates
        for date_field in ["initial_date", "final_date", "rfc_date"]:
            if date_field in merged_fields and merged_fields[date_field].value:
                valid, msg = self.validate_date(merged_fields[date_field].value)
                if not valid:
                    issues.append((date_field, msg))

        # Validate project number
        if "project_number" in merged_fields and merged_fields["project_number"].value:
            valid, msg = self.validate_project_number(merged_fields["project_number"].value)
            if not valid:
                issues.append(("project_number", msg))

        # Validate RW number
        if "rw_number" in merged_fields and merged_fields["rw_number"].value:
            valid, msg = self.validate_rw_number(merged_fields["rw_number"].value)
            if not valid:
                issues.append(("rw_number", msg))

        # Cross-field: date ordering
        initial = _parse_date(
            merged_fields.get("initial_date", type("", (), {"value": None})).value
        )
        final = _parse_date(
            merged_fields.get("final_date", type("", (), {"value": None})).value
        )
        rfc = _parse_date(
            merged_fields.get("rfc_date", type("", (), {"value": None})).value
        )

        if initial and final and final < initial:
            issues.append(("final_date", f"Final date {final} is before initial date {initial}"))
        if initial and rfc and rfc < initial:
            issues.append(("rfc_date", f"RFC date {rfc} is before initial date {initial}"))

        # Normalize engineer stamp name
        if "engineer_stamp_name" in merged_fields and merged_fields["engineer_stamp_name"].value:
            normalized = _fuzzy_match_name(
                merged_fields["engineer_stamp_name"].value,
                self.engineers.get("engineers", {})
            )
            merged_fields["engineer_stamp_name"].value = normalized

        return issues

    def compute_derived_fields(self, merged_fields: dict) -> dict:
        """Compute derived/analytical fields from extracted data.

        Args:
            merged_fields: Dict of field_name -> MergedField.

        Returns:
            Dict with derived field values.
        """
        derived = {}

        # is_bridge_drawing
        title = merged_fields.get("drawing_title")
        if title and title.value:
            upper = title.value.upper()
            bridge_keywords = ["BRIDGE", "STRUCTURE", "SPAN"]
            wall_keywords = ["RETAINING WALL", "NOISE WALL"]
            derived["is_bridge_drawing"] = any(kw in upper for kw in bridge_keywords) and \
                not any(kw in upper for kw in wall_keywords)
        else:
            derived["is_bridge_drawing"] = None

        # design_duration_days = final_date - initial_date
        initial = _parse_date(
            merged_fields.get("initial_date", type("", (), {"value": None})).value
        )
        final = _parse_date(
            merged_fields.get("final_date", type("", (), {"value": None})).value
        )
        rfc = _parse_date(
            merged_fields.get("rfc_date", type("", (), {"value": None})).value
        )

        if initial and final:
            derived["design_duration_days"] = (final - initial).days
        else:
            derived["design_duration_days"] = None

        # rfc_duration_days = rfc_date - initial_date
        if initial and rfc:
            derived["rfc_duration_days"] = (rfc - initial).days
        else:
            derived["rfc_duration_days"] = None

        # division (may already be extracted via regex)
        division = merged_fields.get("division")
        if division and division.value:
            derived["division"] = division.value
        else:
            derived["division"] = None

        return derived

    def cross_page_consistency(self, all_pages: list) -> list:
        """Check that project-level fields are consistent across pages.

        Args:
            all_pages: List of (page_number, merged_fields dict) tuples.

        Returns:
            List of issue descriptions.
        """
        issues = []
        consistent_fields = ["project_number", "route", "tracs_number", "location"]

        for field_name in consistent_fields:
            values = set()
            for page_num, fields in all_pages:
                f = fields.get(field_name)
                if f and f.value:
                    values.add(f.value.strip().upper())
            if len(values) > 1:
                issues.append(
                    f"{field_name} varies across pages: {values}"
                )

        return issues
