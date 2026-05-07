"""Parallel VLM extraction for structure_number, milepost, and engineer stamps.

Uses multiprocessing with configurable workers to parallelize image rendering
and VLM calls. Each worker gets its own SQLite connection for safe writes.

Usage:
    python run_vlm_parallel.py --mode fields          # structure_number + milepost
    python run_vlm_parallel.py --mode stamps          # engineer_stamp_name
    python run_vlm_parallel.py --mode both            # all three
    python run_vlm_parallel.py --mode fields --workers 4 --limit 10  # test run
    python run_vlm_parallel.py --mode fields --new-only  # only pages from recent PDFs
"""

import sys
import time
import sqlite3
import argparse
from pathlib import Path
from multiprocessing import Pool, Manager

import fitz
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from core.title_block import TitleBlockExtractor

DB_PATH = Path("data/database/adot_drawings.db")
PDF_DIR = Path("data/raw")

FIELDS_PROMPT = """Look at this engineering drawing title block image. Extract these two fields:

1. structure_number: The structure/bridge identification number. Usually in format like "S-202.107" or "STRUCTURE NO. 1234" or a number near the word "STRUCTURE". If this is not a bridge/structure drawing, return null.

2. milepost: The station or milepost value. Look for text like "STA 3079+00 TO STA 3093+00" or "MP 148.2" or any station range. Return the full station range if present (e.g. "3079+00 TO 3093+00").

Return ONLY valid JSON in this exact format:
{"structure_number": "value or null", "milepost": "value or null"}"""

STAMP_PROMPT = """Examine this image of a professional engineer's stamp/seal from an ADOT (Arizona Department of Transportation) engineering drawing.

The stamp is a circular seal containing the engineer's name arranged in an arc.

Known engineers who appear on these drawings:
- BRIAN A. GRIMALDI
- MICHAEL A. MCVICKERS
- JAMES O. LANCE
- JOHN M. LANE
- BRIAN P. DAVIS
- KORY KRAMER

Extract the engineer's full name. Respond with JSON only:
{"engineer_name": "FULL NAME", "confidence": 0.0-1.0}"""


# ---------- NEW-ONLY FILTER: 4 recently processed PDFs ----------
NEW_PDFS = [
    "H882701C_vol1(pgs1to250of 7108)RecDwgs-2021.pdf",
    "H882701C_vol1(pgs1501to1751of 7108)RecDwgs-2021.pdf",
    "H882701C_vol1(pgs4002to4201of 7108)RecDwgs-2021.pdf",
    "H882701C_vol1(pgs6202to6501of 7108)RecDwgs-2021.pdf",
]


def render_page(pdf_path, page_num, dpi=200):
    """Render a PDF page to PIL Image."""
    doc = fitz.open(str(pdf_path))
    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def normalize_null(val):
    """Normalize null-like strings to None."""
    if val in (None, "null", "None", "", "N/A", "n/a", "NOT_FOUND"):
        return None
    return val


def call_ollama(image, prompt, model="qwen2.5vl"):
    """Make a single Ollama VLM call. Each worker calls this independently."""
    import base64, io, json, re, requests

    # Resize
    w, h = image.size
    if max(w, h) > 1024:
        scale = 1024 / max(w, h)
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.standard_b64encode(buf.getvalue()).decode()

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 512},
    }

    resp = requests.post(
        "http://localhost:11434/api/generate",
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    text = resp.json().get("response", "")

    # Parse JSON from response
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def process_fields_page(args):
    """Worker function: extract structure_number + milepost for one page."""
    row_id, pdf_filename, page_num, counter, total = args
    pdf_path = PDF_DIR / pdf_filename
    if not pdf_path.exists():
        return {"id": row_id, "status": "skip", "struct": None, "mp": None}

    try:
        tb = TitleBlockExtractor()
        page_img = render_page(pdf_path, page_num)
        tb_img = tb.crop_region(page_img, "full_title_block")

        parsed = call_ollama(tb_img, FIELDS_PROMPT)

        struct_val = normalize_null(parsed.get("structure_number"))
        mp_val = normalize_null(parsed.get("milepost"))

        # Write to DB (each worker opens its own connection)
        updates, values = [], []
        if struct_val:
            updates.append("structure_number = ?")
            values.append(struct_val)
        if mp_val:
            updates.append("milepost = ?")
            values.append(mp_val)
        if updates:
            values.append(row_id)
            conn = sqlite3.connect(str(DB_PATH), timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(f"UPDATE drawings SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
            conn.close()

        return {"id": row_id, "status": "ok", "struct": struct_val, "mp": mp_val}

    except Exception as e:
        return {"id": row_id, "status": "error", "error": str(e), "struct": None, "mp": None}


def process_stamps_page(args):
    """Worker function: extract engineer_stamp_name for one page."""
    row_id, pdf_filename, page_num, counter, total = args
    pdf_path = PDF_DIR / pdf_filename
    if not pdf_path.exists():
        return {"id": row_id, "status": "skip", "name": None}

    try:
        tb = TitleBlockExtractor()
        page_img = render_page(pdf_path, page_num)
        stamp_img = tb.crop_region(page_img, "stamp_area")

        parsed = call_ollama(stamp_img, STAMP_PROMPT)

        name = parsed.get("engineer_name")
        conf = float(parsed.get("confidence", 0.5))

        if name:
            name = name.upper().strip()
        if name in (None, "", "NONE", "NULL", "N/A", "NOT_FOUND"):
            name = None

        # Write to DB
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            "UPDATE drawings SET engineer_stamp_name = ?, extraction_confidence = ? WHERE id = ?",
            (name or "", conf, row_id),
        )
        conn.commit()
        conn.close()

        return {"id": row_id, "status": "ok", "name": name}

    except Exception as e:
        return {"id": row_id, "status": "error", "error": str(e), "name": None}


def get_pages(mode, new_only=False, limit=None):
    """Get pages that need VLM processing."""
    conn = sqlite3.connect(str(DB_PATH))

    if new_only:
        placeholders = ",".join(["?"] * len(NEW_PDFS))
        where_pdf = f"pdf_filename IN ({placeholders})"
    else:
        where_pdf = "1=1"

    if mode == "fields":
        sql = f"SELECT id, pdf_filename, page_number FROM drawings WHERE {where_pdf} ORDER BY pdf_filename, page_number"
    elif mode == "stamps":
        sql = f"SELECT id, pdf_filename, page_number FROM drawings WHERE ({where_pdf}) AND (engineer_stamp_name IS NULL OR engineer_stamp_name = '') ORDER BY pdf_filename, page_number"
    else:
        sql = f"SELECT id, pdf_filename, page_number FROM drawings WHERE {where_pdf} ORDER BY pdf_filename, page_number"

    params = NEW_PDFS if new_only else []
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    if limit:
        rows = rows[:limit]
    return rows


def enable_wal():
    """Enable WAL mode for concurrent writes."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.close()


def run_pool(pages, worker_fn, mode_label, workers):
    """Run a pool of workers and report progress."""
    total = len(pages)
    print(f"\n{'='*60}", flush=True)
    print(f"VLM {mode_label} extraction — {total} pages, {workers} workers", flush=True)
    print(f"{'='*60}\n", flush=True)

    # Add counter info to each task
    tasks = [(row_id, pdf, pn, i, total) for i, (row_id, pdf, pn) in enumerate(pages, 1)]

    start = time.time()
    completed = 0
    errors = 0
    extracted = 0

    with Pool(processes=workers) as pool:
        for i, result in enumerate(pool.imap_unordered(worker_fn, tasks), 1):
            if result["status"] == "ok":
                completed += 1
                # Count non-null extractions
                if mode_label == "fields":
                    if result.get("struct"):
                        extracted += 1
                    if result.get("mp"):
                        extracted += 1
                elif mode_label == "stamps":
                    if result.get("name"):
                        extracted += 1
            elif result["status"] == "error":
                errors += 1
                print(f"  ERROR id={result['id']}: {result.get('error', '?')}", flush=True)

            if i % 10 == 0 or i == total:
                elapsed = time.time() - start
                rate = elapsed / i
                eta = rate * (total - i)
                print(f"  [{i}/{total}] {elapsed:.0f}s elapsed, ETA {eta:.0f}s | ok={completed} err={errors} extracted={extracted}", flush=True)

    elapsed_total = time.time() - start
    print(f"\nDONE: {completed} processed, {errors} errors, {elapsed_total:.0f}s total", flush=True)
    print(f"  Values extracted: {extracted}", flush=True)
    print(f"  Avg: {elapsed_total/max(completed,1):.1f}s/page", flush=True)
    print(f"  Throughput: {completed/max(elapsed_total/60,0.1):.1f} pages/min", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Parallel VLM extraction")
    parser.add_argument("--mode", choices=["fields", "stamps", "both"], required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None, help="Process only first N pages (for testing)")
    parser.add_argument("--new-only", action="store_true", help="Only process pages from the 4 new PDFs")
    args = parser.parse_args()

    enable_wal()

    if args.mode in ("fields", "both"):
        pages = get_pages("fields", new_only=args.new_only, limit=args.limit)
        run_pool(pages, process_fields_page, "fields", args.workers)

    if args.mode in ("stamps", "both"):
        pages = get_pages("stamps", new_only=args.new_only, limit=args.limit)
        run_pool(pages, process_stamps_page, "stamps", args.workers)


if __name__ == "__main__":
    main()
