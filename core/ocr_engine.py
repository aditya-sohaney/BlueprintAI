"""Ensemble OCR engine: PaddleOCR (primary) vs Tesseract (secondary)."""

import logging
import os
import warnings

import pytesseract
from PIL import Image
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OCRWord:
    """A single word detected by OCR with position and confidence."""
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float


@dataclass
class OCRResult:
    """OCR output for a single image region."""
    raw_text: str
    words: list = field(default_factory=list)
    region_name: str = ""
    avg_confidence: float = 0.0
    engine: str = ""


# Map region types to optimal Tesseract PSM modes
REGION_PSM_MODES = {
    "full_title_block": "--psm 11 --oem 3",    # Sparse text, find as much as possible
    "top_right_grid": "--psm 6 --oem 3",       # Uniform block of text
    "revision_table": "--psm 6 --oem 3",       # Uniform block (table)
    "division_title": "--psm 6 --oem 3",       # Block of text
    "stamp_area": "--psm 11 --oem 3",          # Sparse (circular text)
    "firm_area": "--psm 6 --oem 3",            # Block with logo text
    "bottom_info_bar": "--psm 6 --oem 3",      # Bottom bar: route, TRACS, project no
    "rw_number_area": "--psm 6 --oem 3",       # RW number + sheet count
}

# Regions where Tesseract is the PRIMARY engine (large images where PaddleOCR is too slow)
TESSERACT_PRIMARY_REGIONS = {"full_title_block", "division_title"}

# Regions where PaddleOCR is the PRIMARY engine (dense/tabular data where Tesseract fails)
PADDLE_PRIMARY_REGIONS = {"revision_table", "top_right_grid", "bottom_info_bar",
                          "rw_number_area", "firm_area"}


def _init_paddle():
    """Lazily initialize PaddleOCR (heavy import)."""
    old_level = logging.root.level
    logging.disable(logging.WARNING)
    warnings.filterwarnings("ignore")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang="en")
    finally:
        logging.disable(logging.NOTSET)
        logging.root.setLevel(old_level)
    return ocr


class OCREngine:
    """Ensemble OCR: PaddleOCR primary, Tesseract secondary."""

    def __init__(self, lang: str = "eng", engine: str = "ensemble"):
        """
        Args:
            lang: Tesseract language code.
            engine: 'ensemble' (default), 'paddleocr', or 'tesseract'.
        """
        self.lang = lang
        self.engine = engine
        self._paddle = None

    def _get_paddle(self):
        if self._paddle is None:
            self._paddle = _init_paddle()
        return self._paddle

    def _ocr_tesseract(self, image: Image.Image, region_name: str) -> OCRResult:
        """Run Tesseract OCR on a region."""
        config = REGION_PSM_MODES.get(region_name, "--psm 6 --oem 3")

        raw_text = pytesseract.image_to_string(image, lang=self.lang, config=config)

        data = pytesseract.image_to_data(
            image, lang=self.lang, config=config,
            output_type=pytesseract.Output.DICT
        )

        words = []
        confidences = []
        for i in range(len(data["text"])):
            word_text = data["text"][i].strip()
            conf = float(data["conf"][i])
            if word_text and conf > 0:
                words.append(OCRWord(
                    text=word_text,
                    x=data["left"][i],
                    y=data["top"][i],
                    width=data["width"][i],
                    height=data["height"][i],
                    confidence=conf
                ))
                confidences.append(conf)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        return OCRResult(
            raw_text=raw_text.strip(),
            words=words,
            region_name=region_name,
            avg_confidence=avg_conf,
            engine="tesseract"
        )

    def _ocr_paddle(self, image: Image.Image, region_name: str) -> OCRResult:
        """Run PaddleOCR on a region."""
        import numpy as np

        paddle = self._get_paddle()

        # PaddleOCR expects numpy array or file path
        img_array = np.array(image.convert("RGB"))
        result = paddle.ocr(img_array)

        if not result or not result[0]:
            return OCRResult(
                raw_text="",
                words=[],
                region_name=region_name,
                avg_confidence=0.0,
                engine="paddleocr"
            )

        r = result[0]
        texts = r["rec_texts"]
        scores = r["rec_scores"]
        polys = r["dt_polys"]

        words = []
        confidences = []
        text_lines = []

        for text, score, poly in zip(texts, scores, polys):
            text = text.strip()
            if not text:
                continue
            # poly is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            x_min, x_max = int(min(xs)), int(max(xs))
            y_min, y_max = int(min(ys)), int(max(ys))

            words.append(OCRWord(
                text=text,
                x=x_min,
                y=y_min,
                width=x_max - x_min,
                height=y_max - y_min,
                confidence=float(score) * 100  # normalize to 0-100 like Tesseract
            ))
            confidences.append(float(score) * 100)
            text_lines.append((y_min, x_min, text))

        # Sort by y then x to reconstruct reading order
        text_lines.sort(key=lambda t: (t[0], t[1]))

        # Group into lines (items within 15px y-distance = same line)
        lines = []
        current_line = []
        current_y = -999
        for y, x, text in text_lines:
            if abs(y - current_y) > 15:
                if current_line:
                    current_line.sort(key=lambda t: t[1])
                    lines.append(" ".join(t[2] for t in current_line))
                current_line = [(y, x, text)]
                current_y = y
            else:
                current_line.append((y, x, text))
        if current_line:
            current_line.sort(key=lambda t: t[1])
            lines.append(" ".join(t[2] for t in current_line))

        raw_text = "\n".join(lines)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        return OCRResult(
            raw_text=raw_text,
            words=words,
            region_name=region_name,
            avg_confidence=avg_conf,
            engine="paddleocr"
        )

    def _ensemble_region(self, image: Image.Image, region_name: str) -> OCRResult:
        """Route each region to the best engine.

        Strategy:
        - full_title_block, division_title: Use Tesseract (fast on large sparse images,
          PaddleOCR takes 176s on full_title_block vs 2s for Tesseract).
        - revision_table, top_right_grid, etc.: Use PaddleOCR (Tesseract garbles dates
          and dense text, PaddleOCR reads them perfectly).
        """
        if region_name in TESSERACT_PRIMARY_REGIONS:
            return self._ocr_tesseract(image, region_name)
        else:
            return self._ocr_paddle(image, region_name)

    def ocr_region(self, image: Image.Image, region_name: str = "",
                   custom_config: str = None) -> OCRResult:
        """Run OCR on a single image region.

        Args:
            image: PIL Image to OCR.
            region_name: Name of the region (determines PSM mode).
            custom_config: Override config (Tesseract only).

        Returns:
            OCRResult with raw text and word-level data.
        """
        if self.engine == "tesseract":
            return self._ocr_tesseract(image, region_name)
        elif self.engine == "paddleocr":
            return self._ocr_paddle(image, region_name)
        else:
            return self._ensemble_region(image, region_name)

    def ocr_all_regions(self, regions: dict) -> dict:
        """Run OCR on all title block sub-regions.

        Args:
            regions: Dict of region_name -> PIL Image (preprocessed).

        Returns:
            Dict of region_name -> OCRResult.
        """
        results = {}
        for name, image in regions.items():
            if name == "stamp_area":
                continue
            results[name] = self.ocr_region(image, region_name=name)
        return results
