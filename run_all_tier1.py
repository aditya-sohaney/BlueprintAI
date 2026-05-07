"""Batch runner: process all PDFs in data/raw/ with tier1 mode.

Samples up to MAX_PAGES_PER_PDF pages per PDF (spread evenly) to keep
total runtime manageable. Exports results to CSV when done.
"""

import json
import sys
import time
import traceback
from pathlib import Path

from main import process_pdf

MAX_PAGES_PER_PDF = 10  # Sample up to this many pages per PDF


def pick_pages(num_pages: int, max_sample: int) -> list:
    """Pick evenly-spread pages from a PDF."""
    if num_pages <= max_sample:
        return list(range(1, num_pages + 1))
    # Always include first and last, spread the rest evenly
    pages = [1]
    step = (num_pages - 1) / (max_sample - 1)
    for i in range(1, max_sample - 1):
        pages.append(round(1 + i * step))
    pages.append(num_pages)
    return sorted(set(pages))


def main():
    raw_dir = Path("data/raw")
    catalog_path = Path("data/catalog/pdf_inventory.json")

    # Load catalog if available
    if catalog_path.exists():
        with open(catalog_path) as f:
            catalog = json.load(f)
        # Sort: smaller PDFs first for faster initial results
        catalog.sort(key=lambda x: x["page_count"])
        pdf_list = [(raw_dir / p["filename"], p["page_count"], p.get("likely_garbage", False))
                    for p in catalog]
    else:
        # Fallback: just glob all PDFs
        pdf_list = [(p, None, False) for p in sorted(raw_dir.glob("*.pdf"))]

    total_pdfs = len(pdf_list)
    total_pages_processed = 0
    total_errors = 0
    start_time = time.time()

    print(f"=" * 70)
    print(f"BATCH TIER1 EXTRACTION: {total_pdfs} PDFs")
    print(f"Max {MAX_PAGES_PER_PDF} pages per PDF")
    print(f"=" * 70)
    print()

    for i, (pdf_path, page_count, is_garbage) in enumerate(pdf_list):
        if not pdf_path.exists():
            print(f"[{i+1}/{total_pdfs}] SKIP (not found): {pdf_path.name}")
            continue

        if is_garbage:
            print(f"[{i+1}/{total_pdfs}] SKIP (garbage): {pdf_path.name}")
            continue

        # Determine pages to process
        if page_count and page_count > 0:
            pages = pick_pages(page_count, MAX_PAGES_PER_PDF)
        else:
            pages = list(range(1, MAX_PAGES_PER_PDF + 1))

        elapsed_total = time.time() - start_time
        print(f"[{i+1}/{total_pdfs}] {pdf_path.name} ({page_count or '?'} pages, sampling {len(pages)}) "
              f"[{elapsed_total/60:.0f}m elapsed]")

        try:
            results = process_pdf(
                str(pdf_path),
                pages=pages,
                mode="tier1",
                verbose=False,
                export=None,
            )
            n = len(results)
            total_pages_processed += n
            print(f"  -> {n} pages processed OK")
        except Exception as e:
            total_errors += 1
            print(f"  -> ERROR: {e}")
            traceback.print_exc()

    # Export CSV
    elapsed = time.time() - start_time
    print()
    print(f"=" * 70)
    print(f"DONE: {total_pages_processed} pages from {total_pdfs} PDFs in {elapsed/60:.1f} min")
    print(f"Errors: {total_errors}")

    from core.database import DrawingDatabase
    db = DrawingDatabase()
    csv_path = db.export_to_csv()
    print(f"CSV exported: {csv_path}")
    db.close()


if __name__ == "__main__":
    main()
