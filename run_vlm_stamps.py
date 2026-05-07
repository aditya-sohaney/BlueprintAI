"""VLM stamp extraction for all pages missing engineer_stamp_name.

Resumable: only processes pages where engineer_stamp_name IS NULL or empty.
Commits each result immediately after extraction.
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime

import fitz
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from core.title_block import TitleBlockExtractor
from core.vlm_engine import VLMEngine

# Setup logging to both file and stdout
LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "vlm_stamp_run.log"

logger = logging.getLogger("vlm_stamps")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")

fh = logging.FileHandler(LOG_FILE, mode="a")
fh.setFormatter(formatter)
logger.addHandler(fh)

sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
logger.addHandler(sh)

PDF_DIR = Path("data/raw")


def get_pending_pages():
    """Get all pages where engineer_stamp_name is NULL or empty."""
    import sqlite3
    db_path = Path("data/database/adot_drawings.db")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("""
        SELECT id, pdf_filename, page_number
        FROM drawings
        WHERE engineer_stamp_name IS NULL OR engineer_stamp_name = ''
        ORDER BY pdf_filename, page_number
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def update_engineer_stamp(row_id, engineer_name, confidence):
    """Update a single row with the extracted engineer name."""
    import sqlite3
    db_path = Path("data/database/adot_drawings.db")
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        UPDATE drawings
        SET engineer_stamp_name = ?, extraction_confidence = ?
        WHERE id = ?
    """, (engineer_name, confidence, row_id))
    conn.commit()
    conn.close()


def render_page(pdf_path, page_num, dpi=200):
    """Render a PDF page to PIL Image."""
    doc = fitz.open(str(pdf_path))
    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def main():
    logger.info("=" * 60)
    logger.info("VLM Stamp Extraction Run (resumable)")
    logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Get pending pages
    pending = get_pending_pages()
    total = len(pending)
    logger.info(f"Pages pending: {total}")

    if total == 0:
        logger.info("Nothing to do — all pages have engineer_stamp_name.")
        return

    # Initialize VLM
    logger.info("Initializing Qwen2.5-VL via Ollama...")
    engine = VLMEngine(backend="ollama")
    tb = TitleBlockExtractor()
    logger.info(f"Model: {engine.model_name}")
    logger.info("")

    completed = 0
    errors = 0
    start_time = time.time()

    for i, (row_id, pdf_filename, page_num) in enumerate(pending, 1):
        pdf_path = PDF_DIR / pdf_filename

        if not pdf_path.exists():
            logger.info(f"Page {i} of {total} — {pdf_filename} p{page_num} — SKIPPED (file not found)")
            continue

        try:
            # Render and crop
            page_img = render_page(pdf_path, page_num)
            stamp_img = tb.crop_region(page_img, "stamp_area")

            # Extract
            t0 = time.time()
            extraction = engine.extract_engineer_stamp(stamp_img)
            elapsed = time.time() - t0

            engineer = extraction.value or "(none)"
            conf = extraction.confidence

            # Commit immediately
            update_engineer_stamp(row_id, extraction.value or "", conf)
            completed += 1

            logger.info(
                f"Page {i} of {total} — {pdf_filename} p{page_num} "
                f"— Engineer: {engineer} (conf={conf:.2f}, {elapsed:.1f}s)"
            )

        except Exception as e:
            errors += 1
            logger.info(f"Page {i} of {total} — {pdf_filename} p{page_num} — ERROR: {e}")

    # Summary
    elapsed_total = time.time() - start_time
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"COMPLETE: {completed} extracted, {errors} errors, {elapsed_total:.0f}s total")
    logger.info(f"Avg per page: {elapsed_total/max(completed,1):.1f}s")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
