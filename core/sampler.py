"""Smart sampling from cataloged PDFs for training/validation splits."""

import json
import random
import sys
import time
from pathlib import Path

import fitz
from PIL import Image


def sample_pdfs(inventory_path: str = None, output_dir: str = None,
                manifest_path: str = None, max_pages: int = 200,
                seed: int = 42) -> dict:
    """Sample pages from valid ADOT PDFs for training and validation.

    Args:
        inventory_path: Path to pdf_inventory.json from catalog.
        output_dir: Directory to save crops and OCR text files.
        manifest_path: Path to save sample_manifest.json.
        max_pages: Maximum total pages to sample.
        seed: Random seed for reproducibility.

    Returns:
        Dict with training_set and validation_set lists.
    """
    base = Path(__file__).parent.parent
    if inventory_path is None:
        inventory_path = base / "data" / "catalog" / "pdf_inventory.json"
    if output_dir is None:
        output_dir = base / "data" / "samples"
    if manifest_path is None:
        manifest_path = base / "data" / "samples" / "sample_manifest.json"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(seed)

    with open(inventory_path) as f:
        inventory = json.load(f)

    # Filter to likely_adot PDFs only, skip garbage
    valid_pdfs = [e for e in inventory if e.get("likely_adot") and not e.get("likely_garbage")]
    skipped = [e for e in inventory if not e.get("likely_adot") or e.get("likely_garbage")]

    print(f"Valid ADOT PDFs: {len(valid_pdfs)}")
    print(f"Skipped (garbage/unclassified): {len(skipped)}")
    for s in skipped:
        print(f"  SKIP: {s['filename']}")
    print()

    # Determine sample counts per PDF
    sample_plan = []
    total_planned = 0
    for entry in valid_pdfs:
        n_pages = entry["page_count"]
        if n_pages < 50:
            n_samples = min(5, n_pages)
        elif n_pages <= 500:
            n_samples = min(8, n_pages)
        else:
            n_samples = min(10, n_pages)

        if total_planned + n_samples > max_pages:
            n_samples = max(0, max_pages - total_planned)
        if n_samples == 0:
            continue

        sample_plan.append((entry, n_samples))
        total_planned += n_samples

    print(f"Sampling plan: {total_planned} pages from {len(sample_plan)} PDFs (cap={max_pages})")
    print()

    # Initialize OCR engine (lazy — will init PaddleOCR on first use)
    from core.title_block import TitleBlockExtractor
    from core.ocr_engine import OCREngine
    tb_extractor = TitleBlockExtractor()
    ocr_engine = OCREngine(engine="tesseract")

    all_samples = []

    for pdf_idx, (entry, n_samples) in enumerate(sample_plan):
        filename = entry["filename"]
        filepath = entry["filepath"]
        n_pages = entry["page_count"]

        print(f"Processing {filename} ({pdf_idx+1}/{len(sample_plan)})...", end=" ", flush=True)
        start = time.time()

        try:
            doc = fitz.open(filepath)
        except Exception as e:
            print(f"ERROR opening: {e}")
            continue

        try:
            # Select pages: first, last, spread evenly
            pages = _select_pages(n_pages, n_samples)

            # Filter out blank pages
            filtered_pages = []
            for pg in pages:
                try:
                    page = doc[pg - 1]
                    text = page.get_text("text")
                    if "SHEET INTENTIONALLY LEFT BLANK" in text.upper():
                        continue
                    filtered_pages.append(pg)
                except Exception:
                    continue

            sampled_count = 0
            for pg in filtered_pages:
                try:
                    # Render page at 300 DPI
                    page = doc[pg - 1]
                    mat = fitz.Matrix(300 / 72, 300 / 72)
                    pix = page.get_pixmap(matrix=mat)
                    page_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                    # Crop title block
                    crop = tb_extractor.crop_region(page_image, "full_title_block")

                    # Clean filename for saving
                    safe_name = filename.replace(".pdf", "").replace(" ", "_")
                    safe_name = "".join(c if c.isalnum() or c in "_-()" else "_" for c in safe_name)
                    crop_name = f"{safe_name}_page{pg:04d}_crop.png"
                    ocr_name = f"{safe_name}_page{pg:04d}_ocr.txt"

                    # Save crop
                    crop.save(output_dir / crop_name)

                    # Run OCR on crop
                    ocr_result = ocr_engine.ocr_region(crop, region_name="full_title_block")
                    with open(output_dir / ocr_name, "w") as f:
                        f.write(ocr_result.raw_text)

                    all_samples.append({
                        "pdf_filename": filename,
                        "pdf_filepath": filepath,
                        "page_number": pg,
                        "total_pages": n_pages,
                        "crop_file": crop_name,
                        "ocr_file": ocr_name,
                    })
                    sampled_count += 1

                except Exception as e:
                    print(f"\n  WARNING: page {pg} failed: {e}")
                    continue

            elapsed = time.time() - start
            print(f"sampled {sampled_count} pages in {elapsed:.1f}s")

        finally:
            doc.close()

    print(f"\nTotal sampled: {len(all_samples)} pages")

    # 70/30 split
    random.shuffle(all_samples)
    split_idx = int(len(all_samples) * 0.7)
    training_set = all_samples[:split_idx]
    validation_set = all_samples[split_idx:]

    manifest = {
        "total_samples": len(all_samples),
        "training_count": len(training_set),
        "validation_count": len(validation_set),
        "max_pages": max_pages,
        "seed": seed,
        "training_set": training_set,
        "validation_set": validation_set,
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest saved to {manifest_path}")
    print(f"  Training:   {len(training_set)} pages")
    print(f"  Validation: {len(validation_set)} pages")

    return manifest


def _select_pages(total_pages: int, n_samples: int) -> list:
    """Select pages: first, last, then evenly spread between."""
    if n_samples >= total_pages:
        return list(range(1, total_pages + 1))
    if n_samples == 1:
        return [1]
    if n_samples == 2:
        return [1, total_pages]

    pages = [1, total_pages]
    remaining = n_samples - 2
    step = total_pages / (remaining + 1)
    for i in range(1, remaining + 1):
        pg = max(2, min(total_pages - 1, round(step * i)))
        if pg not in pages:
            pages.append(pg)

    # If we need more (due to duplicates), add random
    while len(pages) < n_samples:
        pg = random.randint(2, total_pages - 1)
        if pg not in pages:
            pages.append(pg)

    return sorted(pages)[:n_samples]


if __name__ == "__main__":
    sample_pdfs()
