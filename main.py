"""ADOT Engineering Drawing Extraction Pipeline - Main Orchestrator.

Main functionality : PDF → Load → Crop → OCR → Extract → (VLM) → Merge → Validate → Database


Usage:
    python main.py data/raw/testFile1HDR.pdf
    python main.py data/raw/testFile1HDR.pdf --pages 1 2 4
    python main.py data/raw/testFile1HDR.pdf --mode tier1
    python main.py data/raw/testFile1HDR.pdf --mode dual --export csv
    python main.py data/raw/testFile1HDR.pdf --mode vlm_only

Modes:
    tier1    - OCR + regex only (free, fast, ~29s/page)
    dual     - OCR + regex first, then VLM fills gaps (recommended)
    vlm_only - VLM extracts all fields (most expensive)
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from core.pdf_loader import load_pdf, render_page_to_image
from core.title_block import TitleBlockExtractor
from core.ocr_engine import OCREngine
from core.regex_extractor import RegexExtractor
from core.merger import ResultMerger
from core.validator import Validator
from core.database import DrawingDatabase


def process_page(page_num: int, pdf_path: str, pdf_doc, tb_extractor,
                 ocr_engine, regex_extractor, vlm_engine, merger, validator,
                 mode: str = "tier1", verbose: bool = True) -> tuple:
    """Process a single page through the extraction pipeline.

    Args:
        mode: 'tier1' (OCR+regex only), 'dual' (OCR+regex then VLM),
              or 'vlm_only' (VLM extracts all fields).

    Returns:
        Tuple of (merged_fields dict, derived_fields dict, issues list,
                  vlm_usage dict, vlm_metadata dict)
    """
    start = time.time()
    vlm_usage = {}
    vlm_metadata = {}

    # Step 1: Render page to image at 300 DPI
    if verbose:
        print(f"  [1/6] Rendering page {page_num} at 300 DPI...")
    page_image = render_page_to_image(pdf_path, page_num, dpi=300)

    # Step 2: Crop and preprocess title block sub-regions
    if verbose:
        print(f"  [2/6] Cropping title block regions...")
    preprocessed = tb_extractor.get_preprocessed_regions(page_image, page_num)
    raw_regions = tb_extractor.extract_all_regions(page_image, page_num, save=False)

    if mode == "vlm_only":
        # VLM-only: skip OCR, send full page + title block to VLM
        if verbose:
            print(f"  [3/6] Skipping OCR (vlm_only mode)...")
            print(f"  [4/6] Skipping regex (vlm_only mode)...")
            print(f"  [5/6] Running full VLM extraction...")

        tier1_results = []
        embedded_results = []
        vlm_results = []

        if vlm_engine:streamlit run app.py --server.port 8502

            tb_image = raw_regions.get("full_title_block", page_image)
            vlm_results, vlm_usage, vlm_metadata = vlm_engine.extract_all_fields(
                page_image, tb_image
            )

        if verbose:
            print(f"  [6/6] Merging and validating...")
        merged = merger.merge_page_results(tier1_results, embedded_results, vlm_results)

    else:
        # Step 3: Run OCR
        if verbose:
            print(f"  [3/6] Running OCR on regions...")
        ocr_results = ocr_engine.ocr_all_regions(preprocessed)

        # Step 4: Tier 1 extraction (regex on OCR text)
        if verbose:
            print(f"  [4/6] Extracting Tier 1 fields (regex)...")
        tier1_results = regex_extractor.extract_all_tier1(ocr_results)

        # Embedded text supplement
        page_info = pdf_doc.pages[page_num - 1]
        embedded_results = regex_extractor.extract_from_embedded(
            page_info.embedded_text, page_info.embedded_words
        )

        if mode == "dual" and vlm_engine:
            # Dual-pass: OCR first, then VLM fills gaps
            if verbose:
                print(f"  [5/6] Running VLM extraction (dual-pass)...")
            tb_image = raw_regions.get("full_title_block", page_image)
            vlm_results, vlm_usage, vlm_metadata = vlm_engine.extract_all_fields(
                page_image, tb_image
            )
            if verbose:
                print(f"  [6/6] Merging dual-pass results...")
            merged = merger.merge_dual_pass(tier1_results, embedded_results, vlm_results)
        elif mode == "tier1" or not vlm_engine:
            # Tier 1 only
            if verbose:
                print(f"  [5/6] Skipping VLM extraction (tier1 mode)...")
                print(f"  [6/6] Merging and validating...")
            merged = merger.merge_page_results(tier1_results, embedded_results, [])
        else:
            # Legacy: --skip-vlm not used, mode not specified, but VLM available
            if verbose:
                print(f"  [5/6] Extracting Tier 2 fields (VLM)...")
            tier2_results = vlm_engine.extract_all_tier2(raw_regions)
            if verbose:
                print(f"  [6/6] Merging and validating...")
            merged = merger.merge_page_results(tier1_results, embedded_results, tier2_results)

    # Validate and compute derived fields
    issues = validator.validate_all(merged)
    derived = validator.compute_derived_fields(merged)

    elapsed = (time.time() - start) * 1000
    if verbose:
        print(f"  Done in {elapsed:.0f}ms")

    return merged, derived, issues, vlm_usage, vlm_metadata


def process_pdf(pdf_path: str, pages: list = None, skip_vlm: bool = False,
                mode: str = "tier1", verbose: bool = True,
                export: str = None) -> list:
    """Process an entire PDF through the extraction pipeline.

    Args:
        pdf_path: Path to the PDF file.
        pages: Specific page numbers to process (1-indexed). None = all pages.
        skip_vlm: Skip VLM extraction (legacy flag, use mode instead).
        mode: 'tier1', 'dual', or 'vlm_only'.
        verbose: Print progress info.
        export: Export format after processing ('csv', 'excel', or None).

    Returns:
        List of (page_number, merged_fields, derived_fields) tuples.
    """
    load_dotenv()

    # Legacy compat: --skip-vlm forces tier1 mode
    if skip_vlm:
        mode = "tier1"

    if verbose:
        print(f"Loading PDF: {pdf_path}")
        print(f"Extraction mode: {mode}")

    # Initialize pipeline components
    pdf_doc = load_pdf(pdf_path)
    tb_extractor = TitleBlockExtractor()
    ocr_engine = OCREngine()
    regex_extractor = RegexExtractor()
    merger = ResultMerger()
    validator = Validator()
    db = DrawingDatabase()

    # VLM engine (needed for dual and vlm_only modes)
    vlm_engine = None
    if mode in ("dual", "vlm_only"):
        try:
            from core.vlm_engine import VLMEngine
            vlm_engine = VLMEngine()
            if verbose:
                print(f"VLM backend: {vlm_engine.backend}")
        except Exception as e:
            if verbose:
                print(f"Warning: VLM unavailable ({e}). Falling back to tier1 mode.")
            mode = "tier1"

    if verbose:
        print(f"PDF has {pdf_doc.num_pages} pages")
        if pdf_doc.pages:
            print(f"Page dimensions: {pdf_doc.pages[0].width_pts} x {pdf_doc.pages[0].height_pts} pts")
        print()

    # Determine pages to process
    pages_to_process = pages or list(range(1, pdf_doc.num_pages + 1))
    pdf_filename = Path(pdf_path).name

    all_results = []
    all_page_fields = []
    total_vlm_cost = 0.0

    for i, page_num in enumerate(pages_to_process):
        if page_num < 1 or page_num > pdf_doc.num_pages:
            print(f"Warning: Page {page_num} out of range (1-{pdf_doc.num_pages}), skipping.")
            continue

        if verbose:
            print(f"=== Page {page_num}/{pdf_doc.num_pages} ({i+1}/{len(pages_to_process)}) ===")

        try:
            merged, derived, issues, vlm_usage, vlm_metadata = process_page(
                page_num, pdf_path, pdf_doc, tb_extractor, ocr_engine,
                regex_extractor, vlm_engine, merger, validator, mode, verbose
            )
        except Exception as e:
            if verbose:
                print(f"  ERROR processing page {page_num}: {e}")
            continue

        # Track VLM costs
        if vlm_usage:
            page_cost = vlm_usage.get("cost", 0.0)
            total_vlm_cost += page_cost
            if verbose:
                print(f"  VLM cost: ${page_cost:.4f} (total: ${total_vlm_cost:.4f})")

        # Compute overall confidence
        confidences = [mf.confidence for mf in merged.values() if mf.value is not None]
        overall_conf = sum(confidences) / len(confidences) if confidences else 0.0

        # Store in database
        db.upsert_page(pdf_filename, page_num, merged, derived,
                       overall_conf, extraction_mode=mode,
                       metadata=vlm_metadata)

        all_results.append((page_num, merged, derived))
        all_page_fields.append((page_num, merged))

        # Print summary
        if verbose:
            filled = sum(1 for mf in merged.values() if mf.value is not None)
            total = len(merged)
            flagged = sum(1 for mf in merged.values() if mf.flagged)
            print(f"  Fields: {filled}/{total} extracted, {flagged} flagged")
            print(f"  Confidence: {overall_conf:.2f}")

            if issues:
                print(f"  Validation issues:")
                for field, msg in issues:
                    print(f"    - {field}: {msg}")

            # Print key fields
            for name in ["drawing_title", "project_number", "route", "rw_number",
                         "initial_date", "final_date", "rfc_date",
                         "engineer_stamp_name", "firm"]:
                mf = merged.get(name)
                if mf and mf.value:
                    flag = " [FLAGGED]" if mf.flagged else ""
                    print(f"  {name}: {mf.value} (conf={mf.confidence:.2f}){flag}")
            print()

    # Cross-page consistency check
    if len(all_page_fields) > 1:
        consistency_issues = validator.cross_page_consistency(all_page_fields)
        if consistency_issues and verbose:
            print("=== Cross-Page Consistency Issues ===")
            for issue in consistency_issues:
                print(f"  - {issue}")
            print()

    # Export if requested
    if export:
        if export == "csv":
            path = db.export_to_csv()
            if verbose:
                print(f"Exported to CSV: {path}")
        elif export == "excel":
            path = db.export_to_excel()
            if verbose:
                print(f"Exported to Excel: {path}")

    db.close()

    if verbose:
        print(f"=== Complete: {len(all_results)} pages processed ===")
        if total_vlm_cost > 0:
            print(f"Total VLM cost: ${total_vlm_cost:.4f}")
        print(f"Database: data/database/adot_drawings.db")

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="ADOT Engineering Drawing Extraction Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py data/raw/testFile1HDR.pdf
  python main.py data/raw/testFile1HDR.pdf --pages 1 2 4
  python main.py data/raw/testFile1HDR.pdf --mode dual
  python main.py data/raw/testFile1HDR.pdf --mode tier1 --export csv
        """
    )
    parser.add_argument("pdf_path", help="Path to the PDF file to process")
    parser.add_argument("--pages", nargs="+", type=int,
                        help="Specific pages to process (1-indexed)")
    parser.add_argument("--mode", choices=["tier1", "dual", "vlm_only"],
                        default="tier1",
                        help="Extraction mode (default: tier1)")
    parser.add_argument("--skip-vlm", action="store_true",
                        help="Skip VLM extraction (legacy, same as --mode tier1)")
    parser.add_argument("--export", choices=["csv", "excel"],
                        help="Export results after processing")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress progress output")

    args = parser.parse_args()

    if not Path(args.pdf_path).exists():
        print(f"Error: PDF not found: {args.pdf_path}")
        sys.exit(1)

    process_pdf(
        args.pdf_path,
        pages=args.pages,
        skip_vlm=args.skip_vlm,
        mode=args.mode,
        verbose=not args.quiet,
        export=args.export
    )


if __name__ == "__main__":
    main()
 