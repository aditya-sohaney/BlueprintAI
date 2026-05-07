"""Re-run regex extraction on all 319 pages with updated patterns.

Preserves: engineer_stamp_name (VLM result)
Re-extracts: all other fields via OCR + improved regex
"""

import sys
import time
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.pdf_loader import load_pdf, render_page_to_image
from core.title_block import TitleBlockExtractor
from core.ocr_engine import OCREngine
from core.regex_extractor import RegexExtractor
from core.merger import ResultMerger
from core.validator import Validator

DB_PATH = Path("data/database/adot_drawings.db")
PDF_DIR = Path("data/raw")

# Fields to update (everything except engineer_stamp_name which is VLM)
REGEX_FIELDS = [
    "drawing_title", "location", "route", "project_number",
    "sheet_number", "total_sheets", "initial_date", "initial_designer",
    "final_date", "final_drafter", "rfc_date", "rfc_checker",
    "rw_number", "tracs_number", "structure_number", "milepost", "division"
]


def get_all_pages():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("""
        SELECT id, pdf_filename, page_number
        FROM drawings
        ORDER BY pdf_filename, page_number
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def update_fields(row_id, fields_dict):
    conn = sqlite3.connect(str(DB_PATH))
    set_clauses = []
    values = []
    for field in REGEX_FIELDS:
        if field in fields_dict:
            set_clauses.append(f"{field} = ?")
            values.append(fields_dict[field])
    if set_clauses:
        values.append(row_id)
        sql = f"UPDATE drawings SET {', '.join(set_clauses)} WHERE id = ?"
        conn.execute(sql, values)
        conn.commit()
    conn.close()


def main():
    pages = get_all_pages()
    total = len(pages)
    print(f"Re-running regex extraction on {total} pages...")
    print(f"Updated patterns: drawing_title, milepost, rw_number, structure_number, initial_date")
    print()

    tb = TitleBlockExtractor()
    ocr = OCREngine()
    regex = RegexExtractor()
    merger = ResultMerger()
    validator = Validator()

    # Cache PDF documents to avoid re-opening
    pdf_cache = {}
    completed = 0
    errors = 0
    start_time = time.time()

    for i, (row_id, pdf_filename, page_num) in enumerate(pages, 1):
        pdf_path = PDF_DIR / pdf_filename
        if not pdf_path.exists():
            print(f"  [{i}/{total}] SKIP {pdf_filename} p{page_num} (not found)")
            continue

        try:
            # Load PDF (cached)
            if pdf_filename not in pdf_cache:
                pdf_cache[pdf_filename] = load_pdf(str(pdf_path))
            pdf_doc = pdf_cache[pdf_filename]

            # Render page
            page_image = render_page_to_image(str(pdf_path), page_num, dpi=300)

            # Crop and OCR
            preprocessed = tb.get_preprocessed_regions(page_image, page_num)
            ocr_results = ocr.ocr_all_regions(preprocessed)

            # Regex extraction
            tier1_results = regex.extract_all_tier1(ocr_results)

            # Embedded text supplement
            page_info = pdf_doc.pages[page_num - 1]
            embedded_results = regex.extract_from_embedded(
                page_info.embedded_text, page_info.embedded_words
            )

            # Merge
            merged = merger.merge_page_results(tier1_results, embedded_results, [])

            # Update database (only regex fields)
            # merged values are MergedField objects - extract .value
            fields_dict = {}
            for field in REGEX_FIELDS:
                mf = merged.get(field)
                if mf is not None and hasattr(mf, 'value'):
                    fields_dict[field] = mf.value
                else:
                    fields_dict[field] = mf  # may be None or already a string

            update_fields(row_id, fields_dict)
            completed += 1

            if i % 10 == 0 or i == total:
                elapsed = time.time() - start_time
                rate = elapsed / i
                eta = rate * (total - i)
                print(f"  [{i}/{total}] {pdf_filename} p{page_num} — {elapsed:.0f}s elapsed, ETA {eta:.0f}s")

        except Exception as e:
            errors += 1
            print(f"  [{i}/{total}] ERROR {pdf_filename} p{page_num}: {e}")

    elapsed_total = time.time() - start_time
    print()
    print(f"DONE: {completed} updated, {errors} errors, {elapsed_total:.0f}s total")
    print(f"Avg: {elapsed_total/max(completed,1):.1f}s/page")


if __name__ == "__main__":
    main()
