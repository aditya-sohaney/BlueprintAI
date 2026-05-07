"""Discover document types, layout variants, and keyword patterns from sampled OCR text."""

import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path


# Keyword categories to detect
DIVISIONS = [
    "BUILDER GROUP", "ROADWAY DESIGN SERVICES", "BRIDGE GROUP",
    "TRAFFIC ENGINEERING", "DRAINAGE", "ELECTRICAL", "SIGNING", "LANDSCAPE",
    "UTILITIES", "ENVIRONMENTAL", "RIGHT OF WAY", "SURVEY",
]

FIRMS = [
    "CONNECT", "ethos", "Stantec", "NF Res", "AECOM", "WSP", "HDR",
    "Jacobs", "Kimley-Horn", "T.Y. Lin", "Parsons", "HNTB",
    "Stanley", "SALT RIVER", "PAPAGO",
]

DOC_TYPES = [
    "RETAINING WALL", "BRIDGE", "ROADWAY", "DRAINAGE",
    "TRAFFIC CONTROL", "SIGNING", "STRIPING", "NOISE WALL", "SOUND WALL",
    "GRADING", "UTILITY", "LANDSCAPE", "LIGHTING", "SIGNAL",
    "PAVEMENT", "BARRIER", "GUARDRAIL", "CULVERT", "CHANNEL",
    "CROSS SECTION", "PROFILE", "TYPICAL SECTION", "GENERAL NOTES",
    "TITLE SHEET", "INDEX", "LEGEND", "DETAIL",
]

ADOT_ANCHORS = [
    "ARIZONA DEPARTMENT", "DESCRIPTION OF RELEASE",
    "INITIAL", "FINAL", "RFC", "PROJECT NO", "ROUTE", "TRACS",
    "SHEET", "RECORD DRAWING", "MARICOPA", "PAPAGO",
]


def discover_layouts(manifest_path: str = None, output_dir: str = None) -> dict:
    """Analyze OCR text from training set to discover document types and layouts.

    Args:
        manifest_path: Path to sample_manifest.json.
        output_dir: Directory for layout examples.

    Returns:
        Dict with discovery results.
    """
    base = Path(__file__).parent.parent
    if manifest_path is None:
        manifest_path = base / "data" / "samples" / "sample_manifest.json"
    if output_dir is None:
        output_dir = base / "data" / "samples" / "layout_examples"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = base / "data" / "samples"

    with open(manifest_path) as f:
        manifest = json.load(f)

    training_set = manifest["training_set"]
    print(f"Analyzing {len(training_set)} training pages\n")

    # Counters
    division_counts = Counter()
    firm_counts = Counter()
    doc_type_counts = Counter()
    anchor_counts = Counter()
    pages_by_type = defaultdict(list)
    not_adot_pages = []
    keyword_signatures = defaultdict(list)

    for sample in training_set:
        ocr_path = samples_dir / sample["ocr_file"]
        if not ocr_path.exists():
            continue

        text = ocr_path.read_text()
        text_upper = text.upper()
        page_id = f"{sample['pdf_filename']}:p{sample['page_number']}"

        # Detect keywords
        found_divisions = []
        for div in DIVISIONS:
            if div.upper() in text_upper:
                division_counts[div] += 1
                found_divisions.append(div)

        found_firms = []
        for firm in FIRMS:
            if firm.upper() in text_upper:
                firm_counts[firm] += 1
                found_firms.append(firm)

        found_types = []
        for dtype in DOC_TYPES:
            if dtype.upper() in text_upper:
                doc_type_counts[dtype] += 1
                found_types.append(dtype)

        found_anchors = []
        for anchor in ADOT_ANCHORS:
            if anchor.upper() in text_upper:
                anchor_counts[anchor] += 1
                found_anchors.append(anchor)

        # NOT_ADOT check: zero ADOT anchors
        if not found_anchors:
            not_adot_pages.append({
                "page_id": page_id,
                "pdf": sample["pdf_filename"],
                "page": sample["page_number"],
                "text_preview": text[:200].strip(),
                "crop_file": sample["crop_file"],
            })

        # Classify page by primary document type
        primary_type = found_types[0] if found_types else "UNKNOWN"
        pages_by_type[primary_type].append(page_id)

        # Build keyword signature for clustering
        sig_parts = sorted(set(found_types[:2] + found_divisions[:1]))
        sig = " | ".join(sig_parts) if sig_parts else "UNCLASSIFIED"
        keyword_signatures[sig].append({
            "page_id": page_id,
            "crop_file": sample["crop_file"],
        })

    # Save one example crop per variant
    print("Saving layout examples...")
    for sig, pages in keyword_signatures.items():
        if pages:
            src = samples_dir / pages[0]["crop_file"]
            safe_sig = sig.replace(" | ", "_").replace(" ", "_")[:50]
            dst = output_dir / f"variant_{safe_sig}.png"
            if src.exists():
                shutil.copy2(src, dst)

    # Print report
    print(f"\n{'='*80}")
    print("LAYOUT DISCOVERY REPORT")
    print(f"{'='*80}")

    print(f"\n--- DOCUMENT TYPES FOUND ({len(doc_type_counts)}) ---")
    for dtype, count in doc_type_counts.most_common():
        pct = count / len(training_set) * 100
        print(f"  {dtype:<30} {count:>4} pages ({pct:>5.1f}%)")

    print(f"\n--- DIVISIONS FOUND ({len(division_counts)}) ---")
    for div, count in division_counts.most_common():
        pct = count / len(training_set) * 100
        print(f"  {div:<30} {count:>4} pages ({pct:>5.1f}%)")

    print(f"\n--- FIRMS FOUND ({len(firm_counts)}) ---")
    for firm, count in firm_counts.most_common():
        pct = count / len(training_set) * 100
        print(f"  {firm:<30} {count:>4} pages ({pct:>5.1f}%)")

    print(f"\n--- ADOT ANCHOR KEYWORDS ---")
    for anchor, count in anchor_counts.most_common():
        pct = count / len(training_set) * 100
        print(f"  {anchor:<30} {count:>4} pages ({pct:>5.1f}%)")

    print(f"\n--- LAYOUT VARIANTS (keyword clusters) ---")
    for sig, pages in sorted(keyword_signatures.items(), key=lambda x: -len(x[1])):
        print(f"  [{len(pages):>3} pages] {sig}")

    print(f"\n--- PAGES BY PRIMARY DOCUMENT TYPE ---")
    for dtype, pages in sorted(pages_by_type.items(), key=lambda x: -len(x[1])):
        print(f"  {dtype:<30} {len(pages):>4} pages")

    print(f"\n--- NOT_ADOT PAGES ({len(not_adot_pages)}) ---")
    if not_adot_pages:
        for p in not_adot_pages:
            preview = p["text_preview"][:80].replace("\n", " ")
            print(f"  {p['page_id']}: \"{preview}\"")
    else:
        print("  (none — all pages contain at least one ADOT anchor)")

    print(f"\n{'='*80}")
    print(f"SUMMARY:")
    print(f"  Total training pages analyzed: {len(training_set)}")
    print(f"  Document types found:          {len(doc_type_counts)}")
    print(f"  Layout variants:               {len(keyword_signatures)}")
    print(f"  Divisions found:               {len(division_counts)}")
    print(f"  Firms found:                   {len(firm_counts)}")
    print(f"  NOT_ADOT pages:                {len(not_adot_pages)}")
    print(f"{'='*80}")

    results = {
        "total_pages": len(training_set),
        "doc_type_counts": dict(doc_type_counts),
        "division_counts": dict(division_counts),
        "firm_counts": dict(firm_counts),
        "anchor_counts": dict(anchor_counts),
        "layout_variants": {k: len(v) for k, v in keyword_signatures.items()},
        "not_adot_pages": not_adot_pages,
        "pages_by_type": {k: len(v) for k, v in pages_by_type.items()},
    }

    results_path = output_dir / "discovery_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {results_path}")

    return results


if __name__ == "__main__":
    discover_layouts()
