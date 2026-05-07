"""SQLite database for storing extraction results."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS drawings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pdf_filename TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    drawing_title TEXT,
    location TEXT,
    route TEXT,
    project_number TEXT,
    sheet_number TEXT,
    total_sheets TEXT,
    initial_date DATE,
    initial_designer TEXT,
    final_date DATE,
    final_drafter TEXT,
    rfc_date DATE,
    rfc_checker TEXT,
    rw_number TEXT,
    tracs_number TEXT,
    engineer_stamp_name TEXT,
    firm TEXT,
    structure_number TEXT,
    milepost TEXT,
    is_bridge_drawing BOOLEAN,
    design_duration_days INTEGER,
    rfc_duration_days INTEGER,
    division TEXT,
    extraction_confidence REAL,
    extraction_mode TEXT DEFAULT 'tier1',
    quality_grade TEXT,
    is_adot_drawing BOOLEAN DEFAULT 1,
    is_blank_page BOOLEAN DEFAULT 0,
    extraction_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pdf_filename, page_number)
);

CREATE TABLE IF NOT EXISTS extraction_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drawing_id INTEGER REFERENCES drawings(id),
    field_name TEXT NOT NULL,
    tier1_value TEXT,
    tier1_confidence REAL,
    tier2_value TEXT,
    tier2_confidence REAL,
    final_value TEXT,
    extraction_method TEXT
);
"""


class DrawingDatabase:
    """SQLite database interface for ADOT drawing extractions."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "database" / "adot_drawings.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_page(self, pdf_filename: str, page_number: int,
                    merged_fields: dict, derived_fields: dict,
                    overall_confidence: float = 0.0,
                    extraction_mode: str = "tier1",
                    quality_grade: str = None,
                    metadata: dict = None):
        """Insert or update extraction results for a single page.

        Args:
            pdf_filename: Name of the source PDF.
            page_number: 1-indexed page number.
            merged_fields: Dict of field_name -> MergedField.
            derived_fields: Dict of derived field values.
            overall_confidence: Average confidence across all fields.
            extraction_mode: 'tier1', 'dual', or 'vlm_only'.
            quality_grade: QA grade ('A', 'B', 'C', 'NOT_ADOT', 'CORRUPTED').
            metadata: Optional dict with is_adot_drawing, is_blank_page flags.
        """
        metadata = metadata or {}

        # Build column values from merged fields
        field_values = {}
        for name, mf in merged_fields.items():
            field_values[name] = mf.value

        # Add derived fields
        field_values.update(derived_fields)

        self.conn.execute("""
            INSERT INTO drawings (
                pdf_filename, page_number, drawing_title, location, route,
                project_number, sheet_number, total_sheets,
                initial_date, initial_designer, final_date, final_drafter,
                rfc_date, rfc_checker, rw_number, tracs_number,
                engineer_stamp_name, firm, structure_number, milepost,
                is_bridge_drawing, design_duration_days, rfc_duration_days,
                division, extraction_confidence, extraction_mode,
                quality_grade, is_adot_drawing, is_blank_page,
                extraction_timestamp
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(pdf_filename, page_number) DO UPDATE SET
                drawing_title = excluded.drawing_title,
                location = excluded.location,
                route = excluded.route,
                project_number = excluded.project_number,
                sheet_number = excluded.sheet_number,
                total_sheets = excluded.total_sheets,
                initial_date = excluded.initial_date,
                initial_designer = excluded.initial_designer,
                final_date = excluded.final_date,
                final_drafter = excluded.final_drafter,
                rfc_date = excluded.rfc_date,
                rfc_checker = excluded.rfc_checker,
                rw_number = excluded.rw_number,
                tracs_number = excluded.tracs_number,
                engineer_stamp_name = excluded.engineer_stamp_name,
                firm = excluded.firm,
                structure_number = excluded.structure_number,
                milepost = excluded.milepost,
                is_bridge_drawing = excluded.is_bridge_drawing,
                design_duration_days = excluded.design_duration_days,
                rfc_duration_days = excluded.rfc_duration_days,
                division = excluded.division,
                extraction_confidence = excluded.extraction_confidence,
                extraction_mode = excluded.extraction_mode,
                quality_grade = excluded.quality_grade,
                is_adot_drawing = excluded.is_adot_drawing,
                is_blank_page = excluded.is_blank_page,
                extraction_timestamp = excluded.extraction_timestamp
        """, (
            pdf_filename, page_number,
            field_values.get("drawing_title"),
            field_values.get("location"),
            field_values.get("route"),
            field_values.get("project_number"),
            field_values.get("sheet_number"),
            field_values.get("total_sheets"),
            field_values.get("initial_date"),
            field_values.get("initial_designer"),
            field_values.get("final_date"),
            field_values.get("final_drafter"),
            field_values.get("rfc_date"),
            field_values.get("rfc_checker"),
            field_values.get("rw_number"),
            field_values.get("tracs_number"),
            field_values.get("engineer_stamp_name"),
            field_values.get("firm"),
            field_values.get("structure_number"),
            field_values.get("milepost"),
            field_values.get("is_bridge_drawing"),
            field_values.get("design_duration_days"),
            field_values.get("rfc_duration_days"),
            field_values.get("division"),
            overall_confidence,
            extraction_mode,
            quality_grade,
            metadata.get("is_adot_drawing", True),
            metadata.get("is_blank_page", False),
            datetime.now().isoformat()
        ))

        # Get the drawing ID for extraction details
        cursor = self.conn.execute(
            "SELECT id FROM drawings WHERE pdf_filename = ? AND page_number = ?",
            (pdf_filename, page_number)
        )
        drawing_id = cursor.fetchone()[0]

        # Store extraction details for audit trail
        self.conn.execute(
            "DELETE FROM extraction_details WHERE drawing_id = ?",
            (drawing_id,)
        )
        for name, mf in merged_fields.items():
            # Determine tier1 vs tier2 values
            tier1_val = mf.value if "ocr" in mf.source or "embedded" in mf.source else None
            tier1_conf = mf.confidence if tier1_val else None
            tier2_val = mf.value if "vlm" in mf.source else None
            tier2_conf = mf.confidence if tier2_val else None

            # Check alternatives for the other tier
            for alt in mf.alternatives:
                if "vlm" in alt.get("source", ""):
                    tier2_val = alt["value"]
                    tier2_conf = alt["confidence"]
                elif "ocr" in alt.get("source", "") or "embedded" in alt.get("source", ""):
                    tier1_val = alt["value"]
                    tier1_conf = alt["confidence"]

            self.conn.execute("""
                INSERT INTO extraction_details
                (drawing_id, field_name, tier1_value, tier1_confidence,
                 tier2_value, tier2_confidence, final_value, extraction_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                drawing_id, name,
                tier1_val, tier1_conf,
                tier2_val, tier2_conf,
                mf.value, mf.source
            ))

        self.conn.commit()

    def get_all_drawings(self, pdf_filename: str = None) -> list:
        """Retrieve all drawing records, optionally filtered by PDF.

        Returns:
            List of dicts (one per page).
        """
        if pdf_filename:
            cursor = self.conn.execute(
                "SELECT * FROM drawings WHERE pdf_filename = ? ORDER BY page_number",
                (pdf_filename,)
            )
        else:
            cursor = self.conn.execute(
                "SELECT * FROM drawings ORDER BY pdf_filename, page_number"
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_extraction_details(self, drawing_id: int) -> list:
        """Get per-field extraction details for a specific drawing."""
        cursor = self.conn.execute(
            "SELECT * FROM extraction_details WHERE drawing_id = ? ORDER BY field_name",
            (drawing_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_flagged_fields(self) -> list:
        """Get fields where tier1 and tier2 values differ."""
        cursor = self.conn.execute("""
            SELECT d.pdf_filename, d.page_number, ed.field_name,
                   ed.tier1_value, ed.tier2_value, ed.final_value
            FROM extraction_details ed
            JOIN drawings d ON d.id = ed.drawing_id
            WHERE ed.tier1_value IS NOT NULL
              AND ed.tier2_value IS NOT NULL
              AND UPPER(TRIM(ed.tier1_value)) != UPPER(TRIM(ed.tier2_value))
            ORDER BY d.page_number
        """)
        return [dict(row) for row in cursor.fetchall()]

    def export_to_dataframe(self) -> "pd.DataFrame":
        """Export all drawing data as a pandas DataFrame."""
        return pd.read_sql_query(
            "SELECT * FROM drawings ORDER BY pdf_filename, page_number",
            self.conn
        )

    def export_to_csv(self, output_path: str = None):
        """Export all data to CSV."""
        if output_path is None:
            output_path = Path(__file__).parent.parent / "data" / "exports" / "drawings.csv"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        df = self.export_to_dataframe()
        df.to_csv(output_path, index=False)
        return output_path

    def export_to_excel(self, output_path: str = None):
        """Export all data to Excel."""
        if output_path is None:
            output_path = Path(__file__).parent.parent / "data" / "exports" / "drawings.xlsx"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        df = self.export_to_dataframe()
        df.to_excel(output_path, index=False, sheet_name="Drawings")
        return output_path

    def close(self):
        """Close the database connection."""
        self.conn.close()
