"""VLM extraction for structure_number and milepost on all 319 pages.

Uses Qwen2.5-VL via Ollama to read the title block image directly.
Only updates structure_number and milepost — leaves all other fields unchanged.
"""

import sys
import time
import sqlite3
import signal
from pathlib import Path

import fitz
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from core.vlm_engine import VLMEngine
from core.title_block import TitleBlockExtractor

DB_PATH = Path("data/database/adot_drawings.db")
PDF_DIR = Path("data/raw")

PROMPT = """Look at this engineering drawing title block image. Extract these two fields:

1. structure_number: The structure/bridge identification number. Usually in format like "S-202.107" or "STRUCTURE NO. 1234" or a number near the word "STRUCTURE". If this is not a bridge/structure drawing, return null.

2. milepost: The station or milepost value. Look for text like "STA 3079+00 TO STA 3093+00" or "MP 148.2" or any station range. Return the full station range if present (e.g. "3079+00 TO 3093+00").

Return ONLY valid JSON in this exact format:
{"structure_number": "value or null", "milepost": "value or null"}"""


class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("VLM call timed out")


def get_pages_needing_vlm():
    """Get pages where both structure_number and milepost are still NULL/empty."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("""
        SELECT id, pdf_filename, page_number
        FROM drawings
        ORDER BY pdf_filename, page_number
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def update_fields(row_id, structure_number, milepost):
    conn = sqlite3.connect(str(DB_PATH))
    # Only update if VLM found a value (don't overwrite regex results with null)
    updates = []
    values = []
    if structure_number:
        updates.append("structure_number = ?")
        values.append(structure_number)
    if milepost:
        updates.append("milepost = ?")
        values.append(milepost)
    if updates:
        values.append(row_id)
        sql = f"UPDATE drawings SET {', '.join(updates)} WHERE id = ?"
        conn.execute(sql, values)
        conn.commit()
    conn.close()


def render_page(pdf_path, page_num, dpi=200):
    doc = fitz.open(str(pdf_path))
    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def main():
    pages = get_pages_needing_vlm()
    total = len(pages)
    print(f"VLM extraction for structure_number + milepost on {total} pages...", flush=True)
    print(flush=True)

    engine = VLMEngine(backend="ollama")
    tb = TitleBlockExtractor()
    print(f"Model: {engine.model_name}", flush=True)
    print(flush=True)

    completed = 0
    errors = 0
    updated_struct = 0
    updated_mp = 0
    start_time = time.time()

    for i, (row_id, pdf_filename, page_num) in enumerate(pages, 1):
        pdf_path = PDF_DIR / pdf_filename
        if not pdf_path.exists():
            continue

        try:
            # Set 60s timeout per page
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(60)

            # Render and crop title block
            page_img = render_page(pdf_path, page_num)
            tb_img = tb.crop_region(page_img, "full_title_block")

            # Call VLM
            response = engine._call_ollama(tb_img, PROMPT)
            parsed = engine._parse_json_response(response)

            signal.alarm(0)  # Cancel timeout

            struct_val = parsed.get("structure_number")
            mp_val = parsed.get("milepost")

            # Normalize null strings
            if struct_val in (None, "null", "None", "", "N/A", "n/a"):
                struct_val = None
            if mp_val in (None, "null", "None", "", "N/A", "n/a"):
                mp_val = None

            update_fields(row_id, struct_val, mp_val)
            completed += 1
            if struct_val:
                updated_struct += 1
            if mp_val:
                updated_mp += 1

            if i % 10 == 0 or i == total:
                elapsed = time.time() - start_time
                rate = elapsed / i
                eta = rate * (total - i)
                print(f"  [{i}/{total}] {elapsed:.0f}s elapsed, ETA {eta:.0f}s | struct={updated_struct} mp={updated_mp}", flush=True)

        except Exception as e:
            signal.alarm(0)
            errors += 1
            print(f"  [{i}/{total}] ERROR {pdf_filename} p{page_num}: {e}", flush=True)

    elapsed_total = time.time() - start_time
    print(flush=True)
    print(f"DONE: {completed} processed, {errors} errors, {elapsed_total:.0f}s total", flush=True)
    print(f"  structure_number: {updated_struct} values extracted", flush=True)
    print(f"  milepost: {updated_mp} values extracted", flush=True)
    print(f"  Avg: {elapsed_total/max(completed,1):.1f}s/page", flush=True)


if __name__ == "__main__":
    main()
