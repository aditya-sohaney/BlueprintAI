"""Parallel VLM extraction for firm names from title blocks.

Uses multiprocessing with configurable workers. Each worker crops the
firm_area region and sends it to Qwen2.5-VL for firm name extraction.

Usage:
    python run_vlm_firms.py --workers 8
    python run_vlm_firms.py --workers 4 --limit 10  # test run
"""

import sys
import time
import sqlite3
import argparse
from pathlib import Path
from multiprocessing import Pool

import fitz
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from core.title_block import TitleBlockExtractor

DB_PATH = Path("data/database/adot_drawings.db")
PDF_DIR = Path("data/raw")

FIRM_PROMPT = """Look at this image from an ADOT engineering drawing title block.
What is the name of the engineering firm or contractor shown?
Look for company logos, firm names, or "DESIGNED BY" / "PREPARED BY" text.

Return ONLY valid JSON:
{"firm_name": "FIRM NAME or null", "confidence": 0.0-1.0}"""


def render_page(pdf_path, page_num, dpi=200):
    doc = fitz.open(str(pdf_path))
    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def call_ollama(image, prompt, model="qwen2.5vl"):
    import base64, io, json, re, requests

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
        "options": {"temperature": 0.0, "num_predict": 256},
    }

    resp = requests.post(
        "http://localhost:11434/api/generate",
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    text = resp.json().get("response", "")

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


def process_firm_page(args):
    """Worker: extract firm name for one page."""
    row_id, pdf_filename, page_num, counter, total = args
    pdf_path = PDF_DIR / pdf_filename
    if not pdf_path.exists():
        return {"id": row_id, "status": "skip", "firm": None}

    try:
        tb = TitleBlockExtractor()
        page_img = render_page(pdf_path, page_num)
        firm_img = tb.crop_region(page_img, "firm_area")

        parsed = call_ollama(firm_img, FIRM_PROMPT)

        firm_name = parsed.get("firm_name")
        if firm_name in (None, "null", "None", "", "N/A", "n/a", "NOT_FOUND", "NONE"):
            firm_name = None
        if firm_name:
            firm_name = firm_name.strip().upper()

        if firm_name:
            conn = sqlite3.connect(str(DB_PATH), timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("UPDATE drawings SET firm = ? WHERE id = ?", (firm_name, row_id))
            conn.commit()
            conn.close()

        return {"id": row_id, "status": "ok", "firm": firm_name}

    except Exception as e:
        return {"id": row_id, "status": "error", "error": str(e), "firm": None}


def get_pending_pages(limit=None):
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT id, pdf_filename, page_number FROM drawings "
        "WHERE firm IS NULL OR firm = '' "
        "ORDER BY pdf_filename, page_number"
    ).fetchall()
    conn.close()
    if limit:
        rows = rows[:limit]
    return rows


def main():
    parser = argparse.ArgumentParser(description="Parallel VLM firm extraction")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    # Enable WAL
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.close()

    pages = get_pending_pages(limit=args.limit)
    total = len(pages)
    workers = args.workers

    print(f"\n{'='*60}", flush=True)
    print(f"VLM firm extraction — {total} pages, {workers} workers", flush=True)
    print(f"{'='*60}\n", flush=True)

    tasks = [(row_id, pdf, pn, i, total) for i, (row_id, pdf, pn) in enumerate(pages, 1)]

    start = time.time()
    completed = 0
    errors = 0
    extracted = 0

    with Pool(processes=workers) as pool:
        for i, result in enumerate(pool.imap_unordered(process_firm_page, tasks), 1):
            if result["status"] == "ok":
                completed += 1
                if result.get("firm"):
                    extracted += 1
            elif result["status"] == "error":
                errors += 1
                print(f"  ERROR id={result['id']}: {result.get('error', '?')}", flush=True)

            if i % 10 == 0 or i == total:
                elapsed = time.time() - start
                rate = elapsed / i
                eta = rate * (total - i)
                print(
                    f"  [{i}/{total}] {elapsed:.0f}s elapsed, ETA {eta:.0f}s "
                    f"| ok={completed} err={errors} firms={extracted}",
                    flush=True,
                )

    elapsed_total = time.time() - start
    print(f"\nDONE: {completed} processed, {errors} errors, {elapsed_total:.0f}s total", flush=True)
    print(f"  Firms extracted: {extracted}", flush=True)
    print(f"  Avg: {elapsed_total/max(completed,1):.1f}s/page", flush=True)


if __name__ == "__main__":
    main()
