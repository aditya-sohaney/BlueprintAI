"""Catalog all PDFs in data/raw/ with metadata and classification."""

import json
import os
import sys
from pathlib import Path

import fitz  # PyMuPDF


# Keywords that directly identify ADOT drawings
ADOT_KEYWORDS = {"ARIZONA", "ADOT", "TRACS", "H8827", "LOOP 202",
                 "RECORD DRAWING", "FINAL RECORD"}
ENGINEERING_KEYWORDS = {
    "DEPARTMENT", "TRANSPORTATION", "PROJECT", "ROUTE", "SHEET",
    "DRAWING", "PLAN", "SECTION", "DETAIL", "BRIDGE", "ROADWAY",
    "RETAINING", "WALL", "DRAINAGE", "TRAFFIC", "DESIGN",
    "ENGINEER", "REVISION", "FINAL", "INITIAL", "RFC",
    "CONSTRUCTION", "HIGHWAY", "INTERSTATE", "FREEWAY",
    "CADD", "DGN", "SEGMENT",
}


def catalog_pdfs(raw_dir: str = None, output_path: str = None) -> list:
    """Scan all PDFs in raw_dir and extract metadata + classification.

    Args:
        raw_dir: Path to directory containing PDFs.
        output_path: Path to save JSON inventory.

    Returns:
        List of dicts with PDF metadata.
    """
    if raw_dir is None:
        raw_dir = Path(__file__).parent.parent / "data" / "raw"
    if output_path is None:
        output_path = Path(__file__).parent.parent / "data" / "catalog" / "pdf_inventory.json"

    raw_dir = Path(raw_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(raw_dir.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files in {raw_dir}\n")

    inventory = []

    for i, pdf_path in enumerate(pdf_files):
        entry = {
            "filename": pdf_path.name,
            "filepath": str(pdf_path),
            "file_size_mb": round(pdf_path.stat().st_size / (1024 * 1024), 2),
            "page_count": 0,
            "page1_width_pts": 0,
            "page1_height_pts": 0,
            "has_selectable_text": False,
            "text_sample_page1": "",
            "text_sample_middle": "",
            "likely_adot": False,
            "likely_garbage": False,
            "error": None,
        }

        try:
            doc = fitz.open(str(pdf_path))
            try:
                entry["page_count"] = doc.page_count

                # Page 1 dimensions
                if doc.page_count > 0:
                    page1 = doc[0]
                    entry["page1_width_pts"] = round(page1.rect.width, 1)
                    entry["page1_height_pts"] = round(page1.rect.height, 1)

                    # Text from page 1
                    text1 = page1.get_text("text")
                    entry["text_sample_page1"] = text1[:500].strip()

                # Text from middle page
                if doc.page_count > 2:
                    mid_idx = doc.page_count // 2
                    mid_page = doc[mid_idx]
                    text_mid = mid_page.get_text("text")
                    entry["text_sample_middle"] = text_mid[:500].strip()

                # Combine text for classification
                all_text = (entry["text_sample_page1"] + " " + entry["text_sample_middle"]).upper()
                entry["has_selectable_text"] = len(all_text.strip()) > 100

                # Classification
                entry["likely_adot"] = any(kw in all_text for kw in ADOT_KEYWORDS)

                if not all_text.strip():
                    entry["likely_garbage"] = True
                elif not entry["likely_adot"]:
                    has_eng = any(kw in all_text for kw in ENGINEERING_KEYWORDS)
                    if not has_eng:
                        entry["likely_garbage"] = True

            finally:
                doc.close()

        except Exception as e:
            entry["error"] = str(e)
            entry["likely_garbage"] = True

        inventory.append(entry)
        print(f"  [{i+1}/{len(pdf_files)}] {pdf_path.name}: "
              f"{entry['page_count']} pages, {entry['file_size_mb']} MB"
              f"{' [ERROR: ' + entry['error'] + ']' if entry['error'] else ''}")

    # Save inventory
    with open(output_path, "w") as f:
        json.dump(inventory, f, indent=2)
    print(f"\nInventory saved to {output_path}")

    # Print summary table
    print(f"\n{'='*100}")
    print(f"{'Filename':<60} {'Pages':>6} {'Size MB':>8} {'Text?':>6} {'ADOT?':>6} {'Garb?':>6}")
    print(f"{'-'*100}")

    total_pages = 0
    valid_count = 0
    garbage_count = 0

    for entry in inventory:
        total_pages += entry["page_count"]
        if entry["likely_adot"]:
            valid_count += 1
        if entry["likely_garbage"]:
            garbage_count += 1

        text_flag = "Yes" if entry["has_selectable_text"] else "No"
        adot_flag = "Yes" if entry["likely_adot"] else "No"
        garb_flag = "Yes" if entry["likely_garbage"] else "No"

        name = entry["filename"]
        if len(name) > 58:
            name = name[:55] + "..."

        print(f"{name:<60} {entry['page_count']:>6} {entry['file_size_mb']:>8.1f} "
              f"{text_flag:>6} {adot_flag:>6} {garb_flag:>6}")

    print(f"{'='*100}")
    print(f"\nTOTAL: {len(inventory)} PDFs, {total_pages:,} pages")
    print(f"  Likely valid ADOT: {valid_count}")
    print(f"  Likely garbage:    {garbage_count}")
    print(f"  Unclassified:      {len(inventory) - valid_count - garbage_count}")

    # List likely valid
    print(f"\n--- LIKELY VALID ADOT DRAWINGS ---")
    for e in inventory:
        if e["likely_adot"] and not e["likely_garbage"]:
            print(f"  {e['filename']} ({e['page_count']} pages)")

    # List likely garbage
    print(f"\n--- LIKELY GARBAGE ---")
    for e in inventory:
        if e["likely_garbage"]:
            reason = "Error" if e["error"] else ("No text" if not e["has_selectable_text"] else "No ADOT/engineering keywords")
            print(f"  {e['filename']} — {reason}")

    return inventory


if __name__ == "__main__":
    catalog_pdfs()
