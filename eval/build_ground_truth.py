"""Generate ground truth using Claude API on validation set pages."""

import base64
import io
import json
import sys
import time
from pathlib import Path

import anthropic
import fitz
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

EXTRACTION_PROMPT = """You are analyzing an ADOT (Arizona Department of Transportation) engineering drawing. I'm showing you the full page and a cropped title block region.

Extract ALL fields below. Provide the exact value as it appears, or NOT_FOUND if you cannot read it. Be precise with dates, names, and numbers. If this is not an ADOT engineering drawing, set is_adot_drawing to false and leave all other fields as NOT_FOUND.

Respond ONLY with this JSON, no other text:
{
  "drawing_title": "",
  "location": "",
  "route": "",
  "project_number": "",
  "sheet_number": "",
  "total_sheets": "",
  "initial_date": "",
  "initial_designer": "",
  "final_date": "",
  "final_drafter": "",
  "rfc_date": "",
  "rfc_checker": "",
  "rw_number": "",
  "tracs_number": "",
  "engineer_stamp_name": "",
  "engineer_stamp_date": "",
  "firm": "",
  "structure_number": "",
  "milepost": "",
  "division": "",
  "is_bridge_drawing": false,
  "is_blank_page": false,
  "is_adot_drawing": true
}"""


def _image_to_base64(image: Image.Image, max_dim: int = 1568) -> str:
    """Convert PIL Image to base64, resizing if needed to stay within API limits."""
    w, h = image.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def _parse_json_response(text: str) -> dict:
    """Parse JSON from VLM response, handling markdown code blocks."""
    import re
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
    match = re.search(r'\{[^{}]*("drawing_title"|"is_adot_drawing")[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def build_ground_truth(manifest_path: str = None, output_path: str = None,
                       cost_limit: float = 8.0) -> dict:
    """Generate ground truth by sending validation pages to Claude API.

    Args:
        manifest_path: Path to sample_manifest.json.
        output_path: Path to save ground_truth_full.json.
        cost_limit: Stop if accumulated cost exceeds this.

    Returns:
        Dict with ground truth data and cost info.
    """
    base = Path(__file__).parent.parent
    if manifest_path is None:
        manifest_path = base / "data" / "samples" / "sample_manifest.json"
    if output_path is None:
        output_path = base / "eval" / "ground_truth_full.json"

    samples_dir = base / "data" / "samples"

    with open(manifest_path) as f:
        manifest = json.load(f)

    validation_set = manifest["validation_set"]
    print(f"Processing {len(validation_set)} validation pages for ground truth\n")

    client = anthropic.Anthropic()

    ground_truth = {
        "generated_by": "claude-sonnet-4-5-20250929",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pages": {},
        "cost_tracking": [],
    }

    total_cost = 0.0
    failures = 0
    current_pdf = None
    current_doc = None

    try:
        for i, sample in enumerate(validation_set):
            # Cost check
            if total_cost > cost_limit:
                print(f"\n*** COST LIMIT REACHED: ${total_cost:.2f} > ${cost_limit:.2f}. Stopping. ***")
                break

            pdf_path = sample["pdf_filepath"]
            page_num = sample["page_number"]
            crop_file = sample["crop_file"]
            page_key = f"{sample['pdf_filename']}:page{page_num}"

            # Open PDF (reuse if same file)
            if pdf_path != current_pdf:
                if current_doc:
                    current_doc.close()
                try:
                    current_doc = fitz.open(pdf_path)
                    current_pdf = pdf_path
                except Exception as e:
                    print(f"  [{i+1}/{len(validation_set)}] ERROR opening {sample['pdf_filename']}: {e}")
                    failures += 1
                    continue

            try:
                # Render full page
                page = current_doc[page_num - 1]
                mat = fitz.Matrix(150 / 72, 150 / 72)  # 150 DPI for full page (smaller)
                pix = page.get_pixmap(matrix=mat)
                full_page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # Load title block crop
                crop_path = samples_dir / crop_file
                crop_img = Image.open(crop_path)

                # Convert to base64
                full_b64 = _image_to_base64(full_page_img)
                crop_b64 = _image_to_base64(crop_img)

                # Call Claude API
                start = time.time()
                response = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=1024,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": "image/png", "data": full_b64}
                            },
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": "image/png", "data": crop_b64}
                            },
                            {"type": "text", "text": EXTRACTION_PROMPT}
                        ]
                    }]
                )
                elapsed = time.time() - start

                # Calculate cost (Sonnet pricing: $3/MTok input, $15/MTok output)
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                page_cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)
                total_cost += page_cost

                # Parse response
                result_text = response.content[0].text
                parsed = _parse_json_response(result_text)

                if not parsed:
                    print(f"  [{i+1}/{len(validation_set)}] PARSE FAIL: {page_key} — raw: {result_text[:100]}")
                    failures += 1
                    ground_truth["cost_tracking"].append({
                        "page_key": page_key, "cost": page_cost,
                        "input_tokens": input_tokens, "output_tokens": output_tokens,
                        "status": "parse_failure"
                    })
                    continue

                # Store result
                ground_truth["pages"][page_key] = parsed
                ground_truth["cost_tracking"].append({
                    "page_key": page_key, "cost": round(page_cost, 4),
                    "input_tokens": input_tokens, "output_tokens": output_tokens,
                    "elapsed_s": round(elapsed, 1), "status": "success"
                })

                status = "OK"
                if not parsed.get("is_adot_drawing", True):
                    status = "NOT_ADOT"
                elif parsed.get("is_blank_page", False):
                    status = "BLANK"

                print(f"  [{i+1}/{len(validation_set)}] {status} {page_key} — "
                      f"${page_cost:.3f} ({elapsed:.1f}s, {input_tokens}+{output_tokens} tok)")

                # Progress cost report every 10 pages
                if (i + 1) % 10 == 0:
                    print(f"  --- Running total: ${total_cost:.2f} after {i+1} pages ---")

            except Exception as e:
                print(f"  [{i+1}/{len(validation_set)}] ERROR on {page_key}: {e}")
                failures += 1
                continue

    finally:
        if current_doc:
            current_doc.close()

    # Save ground truth
    ground_truth["summary"] = {
        "total_pages_processed": len(ground_truth["pages"]),
        "total_pages_attempted": len(validation_set),
        "failures": failures,
        "total_cost": round(total_cost, 4),
        "avg_cost_per_page": round(total_cost / max(1, len(ground_truth["pages"])), 4),
    }

    with open(output_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    print(f"\n{'='*60}")
    print(f"GROUND TRUTH GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Pages processed: {len(ground_truth['pages'])}/{len(validation_set)}")
    print(f"  Failures:        {failures}")
    print(f"  Total cost:      ${total_cost:.2f}")
    print(f"  Avg cost/page:   ${total_cost / max(1, len(ground_truth['pages'])):.3f}")
    print(f"  Saved to:        {output_path}")
    print(f"{'='*60}")

    return ground_truth


if __name__ == "__main__":
    build_ground_truth()
