"""Anchor-based regex extraction from OCR text."""

import re
import json
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class FieldExtraction:
    """A single extracted field value with metadata."""
    field_name: str
    value: Optional[str]
    confidence: float       # 0.0 - 1.0
    source: str             # 'ocr_regex', 'embedded_text', 'ocr_regex_fallback'
    raw_match: str = ""     # The actual string matched


# Common OCR character substitutions for correction
OCR_SUBSTITUTIONS = {
    "l": "I", "|": "I", "!": "I",
    "O": "0", "o": "0",
    "S": "5", "s": "5",
    "B": "8",
    "Z": "2", "z": "2",
}


def _clean_ocr_text(text: str) -> str:
    """Basic OCR text cleanup - normalize whitespace."""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _try_ocr_corrections(text: str, pattern: str) -> Optional[re.Match]:
    """Try common OCR character substitutions to find a pattern match."""
    for old, new in OCR_SUBSTITUTIONS.items():
        corrected = text.replace(old, new)
        match = re.search(pattern, corrected)
        if match:
            return match
    return None


class RegexExtractor:
    """Extract structured fields from OCR text using anchor-based regex patterns."""

    def __init__(self, fields_config_path: str = None):
        if fields_config_path is None:
            fields_config_path = Path(__file__).parent.parent / "config" / "fields.json"
        with open(fields_config_path) as f:
            self.config = json.load(f)
        self.fields = self.config["fields"]

    # ---- Individual field extractors ----

    def extract_project_number(self, text: str) -> FieldExtraction:
        """Extract project number like 202-D-I200IS or 202-D-(200)S or 202-D-(2001S."""
        # Try multiple patterns from most specific to least
        # Include [A-Z0-9]? at end to catch PaddleOCR rendering S as 5
        patterns = [
            r'(\d{3}-[A-Z]-\([A-Z]?\d{3,4}\)[A-Z0-9]?)',   # 202-D-(200)S or 202-D-(200)5
            r'(\d{3}-[A-Z]-[A-Z(]\d{3,4}[A-Z)]*[A-Z0-9]?)',  # 202-D-I200IS
            r'(\d{3}-[A-Z]-\(\d{3,4}\)?[A-Z0-9]?)',          # 202-D-(2001S OCR variant
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = match.group(1)
                # Normalize common OCR errors
                value = re.sub(r'\((\d{3})1([A-Z])', r'(\1)\2', value)  # (2001S -> (200)S
                # PaddleOCR: trailing 5 -> S (e.g., 202-D-(200)5 -> 202-D-(200)S)
                value = re.sub(r'\)5$', ')S', value)
                return FieldExtraction("project_number", value, 0.90,
                                       "ocr_regex", match.group(0))
        # Try with OCR corrections
        for pattern in patterns:
            match = _try_ocr_corrections(text, pattern)
            if match:
                value = match.group(1)
                value = re.sub(r'\)5$', ')S', value)
                return FieldExtraction("project_number", value, 0.70,
                                       "ocr_regex_corrected", match.group(0))
        return FieldExtraction("project_number", None, 0.0, "ocr_regex")

    def extract_route(self, text: str) -> FieldExtraction:
        """Extract state route like SR 202L."""
        pattern = r'(SR\s*\d{3}[A-Z]?)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return FieldExtraction("route", match.group(1).upper().strip(), 0.90,
                                   "ocr_regex", match.group(0))
        return FieldExtraction("route", None, 0.0, "ocr_regex")

    def extract_location(self, text: str) -> FieldExtraction:
        """Extract location like 'I-10 (MARICOPA) - I-10 (PAPAGO)'.

        OCR often renders 'I-10' as '1-10', '|-10', '[-10', or '(-10'.
        Handle all variants from both Tesseract and PaddleOCR.
        """
        # I-variant: I, 1, |, [, ( — all observed in OCR output
        i_var = r'[I1|\[\](]'
        pattern = rf'({i_var}-\d+\s*\([^)]+\)\s*-\s*{i_var}-\d+\s*\([^)]+\))'
        match = re.search(pattern, text)
        if match:
            # Normalize all I-variants back to I
            value = re.sub(r'[1|\[\](]-(\d+)', r'I-\1', match.group(1))
            return FieldExtraction("location", value.strip(), 0.85,
                                   "ocr_regex", match.group(0))
        return FieldExtraction("location", None, 0.0, "ocr_regex")

    def extract_rw_number(self, text: str) -> FieldExtraction:
        """Extract RW/identifier number like RW-003.107, S-202.107, C-101.005A.

        ADOT uses various prefix formats:
            RW-003.107   (Right of Way)
            S-202.107    (Structure)
            C-101.005    (Contract)
            NB-202.015   (Northbound)
            L-202.003    (Lighting)
            D-202.001    (Drainage)
        """
        # General pattern: 1-2 letter prefix + dash + 3 digits + dot/space + 3 digits + optional letter
        pattern = r'([A-Z]{1,2}-\d{3}[.\s]\d{3}[A-Z]?)'
        match = re.search(pattern, text)
        if match:
            value = match.group(1).replace(" ", ".")
            return FieldExtraction("rw_number", value, 0.90,
                                   "ocr_regex", match.group(0))
        # Fallback: just RW with looser format
        pattern = r'(RW[\s-]*\d{3}[.\s]\d{3})'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = re.sub(r'[\s]+', '', match.group(1))
            value = re.sub(r'RW', 'RW-', value) if '-' not in value else value
            return FieldExtraction("rw_number", value, 0.80,
                                   "ocr_regex", match.group(0))
        return FieldExtraction("rw_number", None, 0.0, "ocr_regex")

    def extract_tracs_number(self, text: str) -> FieldExtraction:
        """Extract TRACS number like H8827 OIC."""
        pattern = r'(?:TRACS\s*(?:NO\.?)?\s*)?([A-Z]\d{4}\s*[A-Z]{2,3})'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return FieldExtraction("tracs_number", match.group(1).strip().upper(), 0.88,
                                   "ocr_regex", match.group(0))
        return FieldExtraction("tracs_number", None, 0.0, "ocr_regex")

    def extract_drawing_title(self, text: str) -> FieldExtraction:
        """Extract the drawing title by finding specific components.

        Strategy: Extract individual title components (road name, type, station)
        using targeted patterns, then assemble them. This avoids OCR noise
        contaminating the title.

        Typical titles:
            SR 202L RETAINING WALL PLAN SHEET STA 3079+00 TO STA 3093+00
            ELLIOT RD RETAINING WALL PLAN STA 3025+00 TO STA 3040+00
            RETAINING WALL PLAN SHEET STA 3374+00 TO STA 3387+00
            RETAINING WALL ELEVATION
            PAVING PLAN SHEET
            GEOMETRY PLAN SHEET
            CONDUCTOR SCHEDULE
            GIRDER DETAILS
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        all_text = text.replace('\n', ' ')

        # 1. Extract the drawing type (core of the title)
        # Try most specific patterns first, then broader ones
        type_patterns = [
            # Wall types
            re.compile(r'((?:RETAINING\s+)?WALL\s+(?:PLAN\s+(?:SHEET)?|ELEVATION|TRANSITION|INSTALL)(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'((?:NOISE|SOUND)\s+WALL\s+\w+(?:\s+SHEET)?)', re.IGNORECASE),
            # Bridge types
            re.compile(r'(BRIDGE\s+(?:PLAN|ELEVATION|DETAILS?|LAYOUT|GENERAL|DECK|EB|WB|NB|SB)(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'((?:EXPANSION\s+)?JOINT\s+DETAILS?)', re.IGNORECASE),
            re.compile(r'(GIRDER\s+DETAILS?(?:\s+\d)?)', re.IGNORECASE),
            re.compile(r'(ABUTMENT\s+(?:PLAN|DETAILS?|ELEVATION))', re.IGNORECASE),
            re.compile(r'((?:BENT|PIER)\s+(?:PLAN|DETAILS?|ELEVATION)\s*\d?)', re.IGNORECASE),
            # Roadway types
            re.compile(r'((?:PAVING|GEOMETRY|GRADING|DRAINAGE|EROSION\s+CONTROL)\s+PLAN(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'((?:ROADWAY\s+)?LIGHTING\s+PLAN(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'((?:SIGNING|STRIPING|PAVEMENT\s+MARKING)\s+PLAN(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'(LANDSCAPE\s+(?:PLAN|DETAILS?)(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'(TRAFFIC\s+(?:SIGNAL|CONTROL)\s+(?:PLAN|DETAILS?)(?:\s+SHEET)?)', re.IGNORECASE),
            # ITS/Electrical types
            re.compile(r'(CONDUCTOR\s+SCHEDULE)', re.IGNORECASE),
            re.compile(r'((?:ITS|DMS|CCTV|RAMP\s+METER)\s+(?:PLAN|DETAILS?|LAYOUT)(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'((?:CONDUIT|PULL\s+BOX|JUNCTION\s+BOX)\s+(?:PLAN|DETAILS?|LAYOUT|SCHEDULE))', re.IGNORECASE),
            # General types
            re.compile(r'((?:GENERAL|TYPICAL)\s+(?:PLAN|DETAILS?|NOTES|SECTION)(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'((?:PROFILE|CROSS\s+SECTION|ELEVATION)(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'((?:UTILITY|WATER|SEWER|STORM\s+DRAIN)\s+(?:PLAN|DETAILS?|PROFILE)(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'((?:TEMPORARY|CONSTRUCTION)\s+(?:BARRIER|TRAFFIC\s+CONTROL)(?:\s+PLAN)?)', re.IGNORECASE),
            re.compile(r'(DEMOLITION\s+PLAN(?:\s+SHEET)?)', re.IGNORECASE),
            re.compile(r'((?:DURANGO|SANTAN|PECOS)\s+(?:CONNECTOR|FREEWAY))', re.IGNORECASE),
            # Catch-all for PLAN/DETAILS/SCHEDULE with a qualifier
            re.compile(r'((?:[A-Z]+\s+){1,2}(?:PLAN|DETAILS?|SCHEDULE|LAYOUT)(?:\s+SHEET)?)', re.IGNORECASE),
        ]

        type_match = None
        for pattern in type_patterns:
            type_match = pattern.search(all_text)
            if type_match:
                break

        if not type_match:
            return FieldExtraction("drawing_title", None, 0.0, "ocr_regex")

        type_str = type_match.group(1).upper().strip()
        # Normalize spacing
        type_str = re.sub(r'\s+', ' ', type_str)

        # 2. Extract station range (may be on same line or separate line)
        station_pattern = re.compile(
            r'STA[\s_]+(\d{3,4}\+\d{2})\s+TO\s+STA[\s_]+(\d{3,4}\+\d{2})',
            re.IGNORECASE
        )
        station_match = station_pattern.search(all_text)
        station_str = ""
        if station_match:
            station_str = f"STA {station_match.group(1)} TO STA {station_match.group(2)}"

        # 3. Look for road name prefix near the title type
        # Search lines near the wall type keyword AND the full text
        road_name = ""
        noise_prefixes = {"REMOVED", "ZONE", "EXCLUSION", "NEW", "EXISTING"}
        address_noise = {"CAMELBACK", "CAMEBACK", "CEMEBACK", "SUITE",
                         "PHOENIX", "ARIZONA", "BROADWAY", "RAMP",
                         "NICOLAI", "OLIDEN", "THOMPSON", "SANDY"}

        type_line_idx = None
        for idx, line in enumerate(lines):
            if type_str.split()[0] in line.upper():
                type_line_idx = idx
                break

        # Build search candidates: nearby lines + regex over all_text
        search_candidates = []
        if type_line_idx is not None:
            search_lines = lines[max(0, type_line_idx - 3):type_line_idx + 1]
            search_candidates.extend(reversed(search_lines))
        # Also search all_text directly — handles PaddleOCR where road name
        # may be on a line mixed with unrelated text
        search_candidates.append(all_text)

        for sline in search_candidates:
            upper_line = sline.upper().strip()
            road_match = re.search(
                r'\b((?:[A-Z]+\s+)*(?:RD|ROAD|AVE|BLVD|DR|HWY))\b',
                upper_line
            )
            if road_match:
                candidate = road_match.group(1).strip()
                # Skip if it contains address/person name words
                if any(n in candidate.upper() for n in address_noise):
                    continue
                # Strip noise prefixes
                words = candidate.split()
                while words and words[0].upper() in noise_prefixes:
                    words.pop(0)
                candidate = " ".join(words)
                # Must be a valid road name (2+ words, 5+ chars)
                if len(candidate) > 4 and len(candidate.split()) >= 2:
                    road_name = candidate
                    break

        # 4. Check if route (SR 202L) is integral to the title
        # Only include if it appears right before the type on the same line
        route_prefix = ""
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for line in lines:
            if type_str.split()[0] in line.upper() and re.search(r'SR\s+\d{3}[A-Z]?', line, re.IGNORECASE):
                route_m = re.search(r'(SR\s+\d{3}[A-Z]?)', line, re.IGNORECASE)
                if route_m:
                    route_prefix = route_m.group(1).upper()
                break

        # 5. Assemble title
        parts = []
        if route_prefix and not road_name:
            # Only include route if there's no road name (avoids "SR 202L ELLIOT RD...")
            parts.append(route_prefix)
        if road_name:
            parts.append(road_name)
        parts.append(type_str)
        if station_str:
            parts.append(station_str)

        title = " ".join(parts)
        title = re.sub(r'\s+', ' ', title).strip()

        return FieldExtraction("drawing_title", title, 0.82, "ocr_regex", title)

    def extract_sheet_info(self, text: str) -> tuple:
        """Extract sheet number and total sheets.

        Returns:
            Tuple of (sheet_number FieldExtraction, total_sheets FieldExtraction)
        """
        # Pattern: "SHEET 5252" and "TOTAL SHEETS 7108" or just "5252 7101"
        sheet_match = re.search(r'(?:SHEET\s*(?:NO\.?)?\s*)(\d{4})', text, re.IGNORECASE)
        total_match = re.search(r'(?:TOTAL\s*(?:SHEETS?)?\s*)(\d{4})', text, re.IGNORECASE)

        if sheet_match and total_match:
            return (
                FieldExtraction("sheet_number", sheet_match.group(1), 0.90,
                                "ocr_regex", sheet_match.group(0)),
                FieldExtraction("total_sheets", total_match.group(1), 0.90,
                                "ocr_regex", total_match.group(0))
            )

        # Fallback: two 4-digit numbers near each other
        pattern = r'(\d{4})\s+(\d{4})'
        match = re.search(pattern, text)
        if match:
            return (
                FieldExtraction("sheet_number", match.group(1), 0.75,
                                "ocr_regex", match.group(0)),
                FieldExtraction("total_sheets", match.group(2), 0.75,
                                "ocr_regex", match.group(0))
            )

        return (
            FieldExtraction("sheet_number", None, 0.0, "ocr_regex"),
            FieldExtraction("total_sheets", None, 0.0, "ocr_regex")
        )

    def extract_revision_row(self, text: str, row_label: str,
                              description: str = None) -> dict:
        """Extract date and name columns from a revision table row.

        ADOT revision table format (actual OCR output varies):
            A  INITIAL    08/23/2016  DESIGN  JDJ  11 /16
            B  FINAL      06/02/2017  DRAWN   NRD  11 /16
            D  RFC        06/23/2017  CHECKED BAG  11 /16
        Note: OCR sometimes reads 'D' as 'O' or '0'.

        Args:
            text: Full revision table OCR text.
            row_label: Row identifier ('A', 'B', 'D').
            description: Row description ('INITIAL', 'FINAL', 'RFC').

        Returns:
            Dict with 'date' and 'name' if found.
        """
        result = {}
        lines = text.strip().split('\n')

        # Build multiple match patterns for this row
        # OCR can misread D as O or 0
        label_variants = [row_label]
        if row_label == "D":
            label_variants.extend(["O", "0"])

        for line in lines:
            line_upper = line.upper().strip()
            # Match by description keyword
            is_match = False
            if description and description.upper() in line_upper:
                is_match = True
            else:
                # Match by row label at start of line
                for variant in label_variants:
                    if re.match(rf'^\s*{re.escape(variant)}\s', line_upper):
                        is_match = True
                        break
                # Also match patterns like "|A|" or "[A]" from table OCR
                if not is_match:
                    for variant in label_variants:
                        if re.search(rf'[|\[]\s*{re.escape(variant)}\s*[|\]]', line_upper):
                            is_match = True
                            break

            if is_match:
                # Extract all dates from this line
                dates = re.findall(r'(\d{2}/\d{2}/\d{4})', line)
                if dates:
                    result["date"] = dates[0]

                # Extract initials (2-4 uppercase letters not part of a longer word)
                skip_words = {"INITIAL", "FINAL", "RFC", "NOC", "NDC", "DESIGN",
                              "DRAWN", "CHECKED", "CKCKD", "CKCD", "DESN",
                              "RECORD", "DRAWING", "REDLINE", "DESCRIPTION",
                              "RELEASE", "DATE", "NAME", "DESTEN", "ENTIRE",
                              "SHEET", "REPLACED", "CO28",
                              # False positives from OCR artifacts
                              "RD", "RFI", "REI", "INAL", "DES", "DRAN",
                              "NAL", "DESI", "APPR", "CORR",
                              "INC", "LLC", "FIRM", "NOTE", "NEED",
                              "PIPE", "PIER", "RCP", "RCBC"}
                initials = re.findall(r'\b([A-Z]{2,4})\b', line)
                initials = [i for i in initials if i not in skip_words
                            and not re.match(r'^\d', i)]
                if initials:
                    result["name"] = initials[0]

                break

        return result

    def _fix_garbled_date(self, text: str) -> Optional[str]:
        """Try to fix OCR-garbled dates like '0872572017' -> '08/25/2017'.

        Common OCR errors in dates:
        - Missing slashes: 08232016 -> 08/23/2016
        - Substituted chars: 0872572017 (slash becomes digit 7 or 1)
        """
        # Already a proper date
        m = re.match(r'(\d{2})/(\d{2})/(\d{4})', text)
        if m:
            return text

        # 8-digit run (no slashes): 08232016 -> 08/23/2016
        m = re.match(r'(\d{2})(\d{2})(\d{4})', text)
        if m:
            month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31 and 2010 <= year <= 2025:
                return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"

        # 10-char garbled with digit separators: 0872572017 -> 08/25/2017
        # OCR often renders "/" as "7" or "1" in date strings
        # Format: MM[sep]DD[sep]YYYY where [sep] is any single char
        m = re.match(r'(\d{2}).(\d{2}).(\d{4})', text)
        if m:
            month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31 and 2010 <= year <= 2025:
                return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"

        return None

    def _extract_dates_proximity(self, text: str) -> dict:
        """Extract dates and names using proximity matching across lines.

        In sparse OCR mode (psm 11), the revision table renders as:
            INITIAL
            08/23/2016
            DESIGN
            JDJ
            ...
            FINAL
            06/02/2017
            DRAWN
            NRD
            ...
            RFC
            06/23/2017
            CHECKED
            BAG

        This method finds keywords and then looks at nearby lines for dates/initials.
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        results = {}

        # Map keywords to field names
        keyword_map = {
            "INITIAL": ("initial_date", "initial_designer"),
            "FINAL": ("final_date", "final_drafter"),
            "RFC": ("rfc_date", "rfc_checker"),
        }

        # Known role labels that appear between date and initials
        role_labels = {"DESIGN", "DESN", "DRAWN", "ORAWN", "CHECKED", "CKCKD",
                       "CKCD", "DESTEN"}

        skip_words = {"INITIAL", "FINAL", "RFC", "NOC", "NDC", "DESIGN",
                      "DRAWN", "ORAWN", "CHECKED", "CKCKD", "CKCD", "DESN",
                      "RECORD", "DRAWING", "REDLINE", "DESCRIPTION",
                      "RELEASE", "DATE", "NAME", "DESTEN", "ENTIRE",
                      "SHEET", "REPLACED", "DEPARTMENT", "TRANSPORTATION",
                      "INFRASTRUCTURE", "DELIVERY", "OPERATIONS", "DIVISION",
                      "BRIDGE", "GROUP", "ROADWAY", "SERVICES", "ARIZONA",
                      "CONNECT", "PARTNERS", "SALT", "RIVER", "SEGMENT",
                      "LOCATION", "ROUTE", "MILEPOST", "STRUCTURE",
                      "TRACS", "PROJECT", "TOTAL", "SHEETS", "RECORD",
                      "WALL", "PLAN", "RETAINING", "BRIAN", "GRIMALDI",
                      "STANLEY", "CONSULTANTS", "THOMPSON", "SANDY",
                      # False positives from OCR artifacts and document codes
                      "RD", "RFI", "REI", "INAL", "DES", "DRAN", "NAL",
                      "DESI", "APPR", "CORR", "INC", "LLC", "FIRM",
                      "NOTE", "NEED", "PIPE", "PIER", "RCP", "RCBC",
                      "TRAFFIC", "DRAINAGE"}

        for i, line in enumerate(lines):
            upper = line.upper().strip()
            for keyword, (date_field, name_field) in keyword_map.items():
                # Match keyword as a standalone word to avoid partial matches
                if not re.search(r'\b' + keyword + r'\b', upper):
                    continue
                if date_field in results:
                    continue
                # Skip "FINAL RECORD DRAWING" - it's a stamp, not a revision row
                if keyword == "FINAL" and "RECORD" in upper:
                    continue
                if keyword == "FINAL":
                    # Check nearby lines for "RECORD DRAWING"
                    context = " ".join(lines[max(0, i-1):min(len(lines), i+3)]).upper()
                    if "RECORD DRAWING" in context or "RECORD" in upper:
                        continue

                # Look in nearby lines (within 5 lines) for date and initials
                nearby = lines[max(0, i-1):min(len(lines), i+6)]
                nearby_text = " ".join(nearby)

                # Find dates (standard format), preferring 2014-2019 range
                dates = re.findall(r'(\d{2}/\d{2}/\d{4})', nearby_text)
                design_dates = [d for d in dates
                                if 2014 <= int(d.split('/')[-1]) <= 2019]
                if design_dates:
                    results[date_field] = design_dates[0]
                elif dates:
                    results[date_field] = dates[0]
                else:
                    # Try garbled date patterns in nearby lines
                    for nearby_line in nearby:
                        # Look for date-like strings with OCR errors
                        # Use . to match any separator (including digits that
                        # OCR produced instead of /)
                        garbled = re.findall(r'(\d{2}.?\d{2}.?\d{4})', nearby_line)
                        for g in garbled:
                            fixed = self._fix_garbled_date(g)
                            if fixed:
                                year = int(fixed.split('/')[-1])
                                if 2014 <= year <= 2019:
                                    results[date_field] = fixed
                                    break
                        if date_field in results:
                            break

                # Find initials (2-4 uppercase, not a known label)
                for j in range(i+1, min(len(lines), i+6)):
                    line_j = lines[j]
                    # Skip lines from RECORD DRAWING stamps
                    if re.search(r'RECORD\s+DRAW', line_j, re.IGNORECASE):
                        continue
                    if re.search(r'FINAL\s+RECORD', line_j, re.IGNORECASE):
                        continue
                    words = re.findall(r'\b([A-Z]{2,4})\b', line_j)
                    for w in words:
                        if w not in skip_words and w not in role_labels:
                            if name_field not in results:
                                results[name_field] = w
                            break
                    if name_field in results:
                        break

        return results

    def extract_dates_and_names(self, revision_text: str) -> list:
        """Extract all date/name fields from the revision table.

        Uses two strategies:
        1. Single-line matching (for structured table OCR with psm 6)
        2. Proximity matching (for sparse OCR with psm 11 where fields span lines)

        Returns:
            List of FieldExtraction objects for initial/final/RFC dates and names.
        """
        results = []

        # Strategy 1: Try single-line matching
        initial = self.extract_revision_row(revision_text, "A", "INITIAL")
        final = self.extract_revision_row(revision_text, "B", "FINAL")
        rfc = self.extract_revision_row(revision_text, "D", "RFC")

        # Strategy 2: If single-line failed, try proximity matching
        proximity = self._extract_dates_proximity(revision_text)

        # Merge: prefer single-line (higher confidence) but fill gaps with proximity
        field_map = [
            ("initial_date", initial.get("date"), proximity.get("initial_date")),
            ("initial_designer", initial.get("name"), proximity.get("initial_designer")),
            ("final_date", final.get("date"), proximity.get("final_date")),
            ("final_drafter", final.get("name"), proximity.get("final_drafter")),
            ("rfc_date", rfc.get("date"), proximity.get("rfc_date")),
            ("rfc_checker", rfc.get("name"), proximity.get("rfc_checker")),
        ]

        for field_name, line_val, prox_val in field_map:
            if line_val:
                results.append(FieldExtraction(field_name, line_val, 0.85,
                                               "ocr_regex", str(line_val)))
            elif prox_val:
                results.append(FieldExtraction(field_name, prox_val, 0.78,
                                               "ocr_regex", str(prox_val)))
            else:
                results.append(FieldExtraction(field_name, None, 0.0, "ocr_regex"))

        # Fallback for initial_date: if not found, use earliest date in the text
        initial_ext = next((r for r in results if r.field_name == "initial_date"), None)
        if initial_ext and initial_ext.value is None:
            all_dates = re.findall(r'(\d{2}/\d{2}/\d{4})', revision_text)
            valid_dates = []
            for d in all_dates:
                parts = d.split('/')
                month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                if 1 <= month <= 12 and 1 <= day <= 31 and 2010 <= year <= 2030:
                    valid_dates.append(d)
            if valid_dates:
                # Sort chronologically and use earliest as initial_date
                from datetime import datetime
                sorted_dates = sorted(valid_dates,
                                      key=lambda x: datetime.strptime(x, "%m/%d/%Y"))
                earliest = sorted_dates[0]
                # Replace the None extraction with the fallback
                for i, r in enumerate(results):
                    if r.field_name == "initial_date":
                        results[i] = FieldExtraction("initial_date", earliest, 0.65,
                                                     "ocr_regex_fallback", earliest)
                        break

        # Fallback for initial_designer: if we have initial_date but no designer,
        # look for initials near the earliest date in the text
        designer_ext = next((r for r in results if r.field_name == "initial_designer"), None)
        date_ext = next((r for r in results if r.field_name == "initial_date"), None)
        if designer_ext and designer_ext.value is None and date_ext and date_ext.value:
            lines = [l.strip() for l in revision_text.split('\n') if l.strip()]
            # Strict skip set for fallback — only the most common false positives
            fb_skip = {"INITIAL", "FINAL", "RFC", "DESIGN", "DRAWN", "CHECKED",
                       "RECORD", "DRAWING", "REDLINE", "RD", "RFI", "INAL",
                       "DES", "NAL", "REI", "DESN", "CKCKD", "CKCD", "DESTEN",
                       "DATE", "NAME", "ORAWN", "SHEET", "DESCRIPTION", "RELEASE"}
            found_designer = False
            for idx, line in enumerate(lines):
                if found_designer:
                    break
                if date_ext.value in line:
                    # Search this line and next 3 lines for 2-3 letter initials
                    for nearby in lines[idx:min(len(lines), idx+4)]:
                        if re.search(r'RECORD\s+DRAW', nearby, re.IGNORECASE):
                            continue
                        candidates = re.findall(r'\b([A-Z]{2,3})\b', nearby)
                        for c in candidates:
                            if c not in fb_skip:
                                for i, r in enumerate(results):
                                    if r.field_name == "initial_designer" and r.value is None:
                                        results[i] = FieldExtraction(
                                            "initial_designer", c, 0.60,
                                            "ocr_regex_fallback", c)
                                        found_designer = True
                                        break
                                break
                        if found_designer:
                            break
                    break

        return results

    def extract_structure_number(self, text: str) -> FieldExtraction:
        """Extract structure number from bridge/structure drawings.

        Formats:
            S-202.107    (Structure prefix)
            STR NO. 1234
            STRUCTURE NO. 1234
            BRIDGE NO. 1234
            #1234
        """
        # S-XXX.XXX format (most common on ADOT bridge drawings)
        pattern = r'(S-\d{3}[.\s]\d{3}[A-Z]?)'
        match = re.search(pattern, text)
        if match:
            value = match.group(1).replace(" ", ".")
            return FieldExtraction("structure_number", value, 0.92,
                                   "ocr_regex", match.group(0))
        # "STRUCTURE NO" or "STR NO" or "BRIDGE NO" followed by digits
        pattern = r'(?:STRUCTURE|STR|BRIDGE)\s*(?:NO\.?|#)\s*(\d{3,5}[A-Z]?)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return FieldExtraction("structure_number", match.group(1), 0.85,
                                   "ocr_regex", match.group(0))
        # Standalone "STRUCTURE" keyword near a number pattern
        pattern = r'STRUCTURE\s+(\d{3,5})'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return FieldExtraction("structure_number", match.group(1), 0.75,
                                   "ocr_regex", match.group(0))
        return FieldExtraction("structure_number", None, 0.0, "ocr_regex")

    def extract_division(self, text: str) -> FieldExtraction:
        """Extract ADOT division name from title block text.

        Known ADOT divisions:
            INFRASTRUCTURE DELIVERY AND OPERATIONS DIVISION
            ROADWAY DESIGN SERVICES
            TRAFFIC DESIGN SERVICES
            DRAINAGE DESIGN SERVICES
            BRIDGE GROUP
            BUILDER GROUP
        """
        upper = text.upper()
        # Match "INFRASTRUCTURE DELIVERY AND OPERATIONS DIVISION"
        if re.search(r'INFRASTRUCTURE\s+DELIVERY\s+AND\s+OPERATIONS', upper):
            return FieldExtraction("division",
                                   "INFRASTRUCTURE DELIVERY AND OPERATIONS DIVISION",
                                   0.90, "ocr_regex",
                                   "INFRASTRUCTURE DELIVERY AND OPERATIONS DIVISION")
        # Match any "X DESIGN SERVICES" pattern
        m = re.search(r'(\w+(?:\s+\w+)?)\s+DESIGN\s+SERVICES', upper)
        if m:
            name = m.group(0).strip()
            return FieldExtraction("division", name, 0.88, "ocr_regex", name)
        # Match any "X GROUP" pattern
        m = re.search(r'(\w+)\s+GROUP', upper)
        if m:
            name = m.group(0).strip()
            return FieldExtraction("division", name, 0.85, "ocr_regex", name)
        return FieldExtraction("division", None, 0.0, "ocr_regex")

    def extract_milepost(self, text: str) -> FieldExtraction:
        """Extract milepost/station from drawing title.

        Formats:
            'STA 3079+00 TO STA 3093+00' -> '3079+00 TO 3093+00'
            'STA 79+00 TO STA 93+00' -> '79+00 TO 93+00'
            'MILEPOST 148.2 TO 152.7' -> '148.2 TO 152.7'
            'MP 148.2' -> '148.2'
        """
        # Station range (2-4 digit stations)
        pattern = r'STA[\s_.]+(\d{2,4}\+\d{2})\s+TO\s+STA[\s_.]+(\d{2,4}\+\d{2})'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = f"{match.group(1)} TO {match.group(2)}"
            return FieldExtraction("milepost", value, 0.88,
                                   "ocr_regex", match.group(0))
        # Decimal milepost range
        pattern = r'(?:MILEPOST|MP)[\s:]+(\d{1,4}\.?\d*)\s+TO\s+(\d{1,4}\.?\d*)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = f"{match.group(1)} TO {match.group(2)}"
            return FieldExtraction("milepost", value, 0.85,
                                   "ocr_regex", match.group(0))
        # Single station (2-4 digits)
        pattern = r'STA[\s_.]+(\d{2,4}\+\d{2})'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return FieldExtraction("milepost", match.group(1), 0.80,
                                   "ocr_regex", match.group(0))
        # Single decimal milepost
        pattern = r'(?:MILEPOST|MP)[\s:]+(\d{1,4}\.\d+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return FieldExtraction("milepost", match.group(1), 0.78,
                                   "ocr_regex", match.group(0))
        return FieldExtraction("milepost", None, 0.0, "ocr_regex")

    def extract_all_tier1(self, ocr_results: dict) -> list:
        """Run all Tier 1 extractions across OCR results from multiple regions.

        Args:
            ocr_results: Dict of region_name -> OCRResult.

        Returns:
            List of FieldExtraction objects.
        """
        extractions = []

        # Top-right grid: project_number, sheet info
        if "top_right_grid" in ocr_results:
            text = ocr_results["top_right_grid"].raw_text
            extractions.append(self.extract_project_number(text))
            sheet, total = self.extract_sheet_info(text)
            extractions.extend([sheet, total])

        # Revision table: dates and names
        if "revision_table" in ocr_results:
            text = ocr_results["revision_table"].raw_text
            extractions.extend(self.extract_dates_and_names(text))

        # Division/title area: drawing title, division, location, route, milepost
        if "division_title" in ocr_results:
            text = ocr_results["division_title"].raw_text
            extractions.append(self.extract_drawing_title(text))
            extractions.append(self.extract_division(text))
            extractions.append(self.extract_milepost(text))
            # Route and location are also in this region
            extractions.append(self.extract_route(text))
            extractions.append(self.extract_location(text))

        # Bottom info bar: TRACS, route, project number (secondary source)
        if "bottom_info_bar" in ocr_results:
            text = ocr_results["bottom_info_bar"].raw_text
            extractions.append(self.extract_tracs_number(text))
            # Also try route from bottom bar as backup
            route_ext = self.extract_route(text)
            if route_ext.value:
                route_ext.confidence *= 0.85  # slightly lower since backup
                extractions.append(route_ext)

        # RW number
        if "rw_number_area" in ocr_results:
            text = ocr_results["rw_number_area"].raw_text
            extractions.append(self.extract_rw_number(text))
            extractions.append(self.extract_structure_number(text))

        # Structure number from division_title as well (bridge drawings)
        if "division_title" in ocr_results:
            text = ocr_results["division_title"].raw_text
            struct_ext = self.extract_structure_number(text)
            if struct_ext.value:
                extractions.append(struct_ext)

        # Fallback: try full title block for any missing fields
        if "full_title_block" in ocr_results:
            fb_text = ocr_results["full_title_block"].raw_text
            field_extractors = {
                "project_number": self.extract_project_number,
                "route": self.extract_route,
                "location": self.extract_location,
                "rw_number": self.extract_rw_number,
                "tracs_number": self.extract_tracs_number,
                "drawing_title": self.extract_drawing_title,
                "milepost": self.extract_milepost,
                "division": self.extract_division,
                "structure_number": self.extract_structure_number,
                "sheet_number": lambda t: self.extract_sheet_info(t)[0],
                "total_sheets": lambda t: self.extract_sheet_info(t)[1],
            }

            existing = {e.field_name for e in extractions if e.value is not None}
            for field_name, extractor in field_extractors.items():
                if field_name not in existing:
                    fb_result = extractor(fb_text)
                    if fb_result.value:
                        fb_result.confidence *= 0.7
                        fb_result.source = "ocr_regex_fallback"
                        extractions.append(fb_result)

            # Try dates from full title block for any individual date fields
            # that the revision table failed to extract
            date_fields = {"initial_date", "final_date", "rfc_date",
                           "initial_designer", "final_drafter", "rfc_checker"}
            missing_dates = date_fields - existing
            if missing_dates:
                fb_dates = self.extract_dates_and_names(fb_text)
                for ext in fb_dates:
                    if ext.value and ext.field_name in missing_dates:
                        ext.confidence *= 0.7
                        ext.source = "ocr_regex_fallback"
                        extractions.append(ext)

        return extractions

    def extract_from_embedded(self, embedded_text: str,
                               embedded_words: list) -> list:
        """Extract fields from the sparse embedded text layer.

        The embedded text typically only has sheet numbers and stamp info.

        Args:
            embedded_text: Full page embedded text.
            embedded_words: List of (x0, y0, x1, y1, word) tuples.

        Returns:
            List of FieldExtraction objects.
        """
        extractions = []

        if not embedded_text.strip():
            return extractions

        # Sheet number is often in embedded text
        sheet_match = re.search(r'(\d{4})\s+(\d{4})', embedded_text)
        if sheet_match:
            extractions.append(FieldExtraction(
                "sheet_number", sheet_match.group(1), 0.95,
                "embedded_text", sheet_match.group(0)
            ))
            extractions.append(FieldExtraction(
                "total_sheets", sheet_match.group(2), 0.95,
                "embedded_text", sheet_match.group(0)
            ))

        return extractions
