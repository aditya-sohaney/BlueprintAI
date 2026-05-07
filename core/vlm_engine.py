"""Vision-Language Model engine for Tier 2 field extraction.

Uses Qwen2.5-VL via Ollama for local inference (no API key required).
Falls back to Anthropic Claude API if configured.
"""

import base64
import io
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


@dataclass
class VLMExtraction:
    """A field value extracted by a Vision-Language Model."""
    field_name: str
    value: Optional[str]
    confidence: float
    source: str             # 'ollama_vlm' or 'claude_vlm'
    reasoning: str = ""


class VLMEngine:
    """Extract Tier 2 fields using Vision-Language Models.

    Supports two backends:
        - 'ollama': Local Qwen2.5-VL via Ollama (default, free)
        - 'claude': Anthropic Claude API (requires ANTHROPIC_API_KEY)
    """

    def __init__(self, backend: str = None):
        self.backend = backend or os.getenv("VLM_BACKEND", "ollama")
        self._last_usage = None

        if self.backend == "ollama":
            self._init_ollama()
        elif self.backend == "claude":
            import anthropic
            self.client = anthropic.Anthropic()
        else:
            raise ValueError(f"Unknown VLM backend: {self.backend}")

    def _init_ollama(self):
        """Verify Ollama is running and model is available."""
        self.model_name = os.getenv("OLLAMA_VLM_MODEL", "qwen2.5vl")
        try:
            resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            # Check if our model (or a tagged variant) is available
            if not any(self.model_name in m for m in models):
                raise RuntimeError(
                    f"Model '{self.model_name}' not found in Ollama. "
                    f"Available: {models}. Run: ollama pull {self.model_name}"
                )
        except requests.ConnectionError:
            raise RuntimeError(
                "Cannot connect to Ollama. Start it with: ollama serve"
            )

    def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string."""
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode()

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from VLM response, handling markdown code blocks."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try extracting from markdown code block
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Try finding any JSON object
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    def _resize_for_api(self, image: Image.Image, max_dim: int = 1568) -> Image.Image:
        """Resize image if needed to stay within API limits."""
        w, h = image.size
        if max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        return image

    def _call_ollama(self, image: Image.Image, prompt: str) -> str:
        """Send image + prompt to Ollama and return text response."""
        image = self._resize_for_api(image, max_dim=1024)
        b64 = self._image_to_base64(image)

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "images": [b64],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 512,
            }
        }

        start = time.time()
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=120
        )
        elapsed = time.time() - start

        resp.raise_for_status()
        result = resp.json()

        self._last_usage = {
            "total_duration_ms": result.get("total_duration", 0) / 1e6,
            "eval_count": result.get("eval_count", 0),
            "elapsed_s": elapsed,
        }

        return result.get("response", "")

    def _call_ollama_multi(self, images: list, prompt: str) -> str:
        """Send multiple images + prompt to Ollama."""
        b64_images = []
        for img in images:
            img = self._resize_for_api(img, max_dim=1024)
            b64_images.append(self._image_to_base64(img))

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "images": b64_images,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 1024,
            }
        }

        start = time.time()
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=180
        )
        elapsed = time.time() - start

        resp.raise_for_status()
        result = resp.json()

        self._last_usage = {
            "total_duration_ms": result.get("total_duration", 0) / 1e6,
            "eval_count": result.get("eval_count", 0),
            "elapsed_s": elapsed,
        }

        return result.get("response", "")

    def _call_claude(self, image: Image.Image, prompt: str) -> str:
        """Send image + prompt to Claude API and return text response."""
        image = self._resize_for_api(image)
        b64 = self._image_to_base64(image)
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        self._last_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cost": (response.usage.input_tokens * 3.0 / 1_000_000 +
                     response.usage.output_tokens * 15.0 / 1_000_000),
        }
        return response.content[0].text

    def _call_claude_multi(self, images: list, prompt: str) -> str:
        """Send multiple images + prompt to Claude API."""
        content = []
        for img in images:
            img = self._resize_for_api(img)
            b64 = self._image_to_base64(img)
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64}
            })
        content.append({"type": "text", "text": prompt})

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": content}]
        )
        self._last_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cost": (response.usage.input_tokens * 3.0 / 1_000_000 +
                     response.usage.output_tokens * 15.0 / 1_000_000),
        }
        return response.content[0].text

    def _call_vlm(self, image: Image.Image, prompt: str) -> str:
        """Route to the appropriate VLM backend."""
        if self.backend == "ollama":
            return self._call_ollama(image, prompt)
        elif self.backend == "claude":
            return self._call_claude(image, prompt)

    def _call_vlm_multi(self, images: list, prompt: str) -> str:
        """Route multi-image call to the appropriate backend."""
        if self.backend == "ollama":
            return self._call_ollama_multi(images, prompt)
        elif self.backend == "claude":
            return self._call_claude_multi(images, prompt)

    def extract_engineer_stamp(self, stamp_image: Image.Image) -> VLMExtraction:
        """Extract engineer name from circular professional seal."""
        prompt = """Examine this image of a professional engineer's stamp/seal from an ADOT (Arizona Department of Transportation) engineering drawing.

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

        response_text = self._call_vlm(stamp_image, prompt)
        data = self._parse_json_response(response_text)

        name = data.get("engineer_name")
        conf = float(data.get("confidence", 0.5))

        return VLMExtraction(
            field_name="engineer_stamp_name",
            value=name.upper().strip() if name else None,
            confidence=conf,
            source=f"{self.backend}_vlm",
            reasoning=response_text[:300]
        )

    def extract_firm(self, firm_image: Image.Image) -> VLMExtraction:
        """Extract firm name from logo/text area."""
        prompt = """Examine this image from an ADOT engineering drawing title block.

Identify the engineering firm(s) shown. Known firms on ADOT I-10/SR 202L drawings:
- CONNECT 2.2 (joint venture)
- ethos
- NF Res Inc.
- Stantec Consulting
- Stanley Consultants
- SALT RIVER SEGMENT CI / C2 (segment partners)
- PAPAGO SEGMENT DI (segment partner)

List the primary firm and any partner/segment firms. Respond with JSON only:
{"firm": "PRIMARY FIRM / PARTNER", "confidence": 0.0-1.0}"""

        response_text = self._call_vlm(firm_image, prompt)
        data = self._parse_json_response(response_text)

        firm = data.get("firm")
        conf = float(data.get("confidence", 0.5))

        return VLMExtraction(
            field_name="firm",
            value=firm.strip() if firm else None,
            confidence=conf,
            source=f"{self.backend}_vlm",
            reasoning=response_text[:300]
        )

    def extract_structure_number(self, title_block_image: Image.Image) -> VLMExtraction:
        """Extract structure number from drawing content or title block."""
        prompt = """Examine this engineering drawing title block image.

Look for a structure identification number in the format XXX-XXXX-X (e.g., 202-3208-B).
This may appear as text within the drawing content or in the title block.

Respond with JSON only:
{"structure_number": "XXX-XXXX-X or null", "confidence": 0.0-1.0}"""

        response_text = self._call_vlm(title_block_image, prompt)
        data = self._parse_json_response(response_text)

        sn = data.get("structure_number")
        conf = float(data.get("confidence", 0.5))

        if sn and sn.lower() in ("null", "none", "n/a"):
            sn = None

        return VLMExtraction(
            field_name="structure_number",
            value=sn,
            confidence=conf,
            source=f"{self.backend}_vlm",
            reasoning=response_text[:300]
        )

    def extract_all_tier2(self, regions: dict) -> list:
        """Run VLM extraction on appropriate regions for Tier 2 fields.

        Args:
            regions: Dict of region_name -> PIL Image.

        Returns:
            List of VLMExtraction objects.
        """
        results = []

        if "stamp_area" in regions:
            results.append(self.extract_engineer_stamp(regions["stamp_area"]))

        if "firm_area" in regions:
            results.append(self.extract_firm(regions["firm_area"]))

        if "full_title_block" in regions:
            results.append(self.extract_structure_number(regions["full_title_block"]))

        return results

    # -- Full extraction (dual-pass mode) --

    FULL_EXTRACTION_PROMPT = """You are analyzing an ADOT (Arizona Department of Transportation) engineering drawing. I'm showing you the full page and a cropped title block region.

Extract ALL fields below. Provide the exact value as it appears, or NOT_FOUND if you cannot read it. Be precise with dates (MM/DD/YYYY), names, and numbers. If this is not an ADOT engineering drawing, set is_adot_drawing to false and leave all other fields as NOT_FOUND.

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
  "firm": "",
  "structure_number": "",
  "milepost": "",
  "division": "",
  "is_bridge_drawing": false,
  "is_blank_page": false,
  "is_adot_drawing": true
}"""

    def extract_all_fields(self, page_image: Image.Image,
                           title_block_image: Image.Image) -> tuple:
        """Full-field VLM extraction for dual-pass mode.

        Sends both the full page and title block crop for
        comprehensive extraction of ALL fields.

        Args:
            page_image: Full rendered page as PIL Image.
            title_block_image: Cropped title block as PIL Image.

        Returns:
            Tuple of (list of VLMExtraction, usage_dict, metadata_dict).
        """
        self._last_usage = None

        response_text = self._call_vlm_multi(
            [page_image, title_block_image],
            self.FULL_EXTRACTION_PROMPT
        )

        data = self._parse_json_response(response_text)
        source = f"{self.backend}_vlm"

        results = []
        field_names = [
            "drawing_title", "location", "route", "project_number",
            "sheet_number", "total_sheets", "initial_date", "initial_designer",
            "final_date", "final_drafter", "rfc_date", "rfc_checker",
            "rw_number", "tracs_number", "engineer_stamp_name", "firm",
            "structure_number", "milepost", "division",
        ]

        for field in field_names:
            value = data.get(field)
            if value is not None and str(value).upper() in ("NOT_FOUND", "N/A", "NONE", "NULL", ""):
                value = None
            if isinstance(value, bool):
                value = str(value)
            if value is not None:
                value = str(value).strip()

            results.append(VLMExtraction(
                field_name=field,
                value=value,
                confidence=0.80 if value else 0.0,
                source=source,
            ))

        # Boolean flags as metadata
        is_adot = data.get("is_adot_drawing", True)
        is_blank = data.get("is_blank_page", False)

        usage = self._last_usage or {}

        return results, usage, {"is_adot_drawing": is_adot, "is_blank_page": is_blank}
