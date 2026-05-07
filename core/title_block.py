"""Title block detection and cropping from rendered page images."""

import json
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from pathlib import Path


class TitleBlockExtractor:
    """Crop title block sub-regions from rendered page images."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "title_block_coords.json"
        with open(config_path) as f:
            self.config = json.load(f)
        self.regions = self.config["regions"]

    def crop_region(self, page_image: Image.Image, region_name: str) -> Image.Image:
        """Crop a named region from the full page image.

        Args:
            page_image: Full rendered page as PIL Image.
            region_name: Key from title_block_coords.json regions.

        Returns:
            Cropped PIL Image of the region.
        """
        region = self.regions[region_name]
        w, h = page_image.size
        box = (
            int(w * region["x_start_ratio"]),
            int(h * region["y_start_ratio"]),
            int(w * region["x_end_ratio"]),
            int(h * region["y_end_ratio"])
        )
        return page_image.crop(box)

    def preprocess_for_ocr(self, image: Image.Image, method: str = "adaptive") -> Image.Image:
        """Enhance image for better OCR results.

        Args:
            image: Input image (can be color or grayscale).
            method: Preprocessing method - 'adaptive', 'simple', or 'enhanced'.

        Returns:
            Preprocessed grayscale/binary PIL Image.
        """
        # Convert to grayscale
        gray = image.convert("L")

        if method == "simple":
            # Just contrast enhancement + sharpen
            enhanced = ImageEnhance.Contrast(gray).enhance(2.0)
            return enhanced.filter(ImageFilter.SHARPEN)

        elif method == "enhanced":
            # More aggressive enhancement for faint text
            enhanced = ImageEnhance.Contrast(gray).enhance(2.5)
            enhanced = ImageEnhance.Sharpness(enhanced).enhance(2.0)
            enhanced = ImageEnhance.Brightness(enhanced).enhance(1.1)
            return enhanced

        else:  # adaptive (default) - best for engineering drawings
            arr = np.array(gray)
            # Adaptive thresholding handles varying lighting/background
            binary = cv2.adaptiveThreshold(
                arr, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=15,
                C=4
            )
            return Image.fromarray(binary)

    def extract_all_regions(
        self,
        page_image: Image.Image,
        page_num: int,
        output_dir: str = None,
        save: bool = True
    ) -> dict:
        """Crop all defined regions from a page image.

        Args:
            page_image: Full rendered page as PIL Image.
            page_num: Page number (for filename prefixing).
            output_dir: Directory to save cropped images (default: data/title_blocks).
            save: Whether to save cropped images to disk.

        Returns:
            Dict of region_name -> PIL Image.
        """
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "data" / "title_blocks"
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        results = {}
        for region_name in self.regions:
            cropped = self.crop_region(page_image, region_name)
            if save:
                cropped.save(out / f"page{page_num:02d}_{region_name}.png")
            results[region_name] = cropped

        return results

    def get_preprocessed_regions(
        self,
        page_image: Image.Image,
        page_num: int,
        save: bool = True
    ) -> dict:
        """Crop all regions and preprocess them for OCR.

        Uses 'simple' preprocessing (contrast+sharpen) which works much better
        than adaptive thresholding on CAD-generated engineering drawings where
        text is rendered as vector graphics.

        Returns:
            Dict of region_name -> preprocessed PIL Image.
        """
        raw_regions = self.extract_all_regions(page_image, page_num, save=save)

        preprocessed = {}
        for name, img in raw_regions.items():
            if name == "stamp_area":
                # Keep stamp in color for VLM
                preprocessed[name] = img
            elif name == "top_right_grid":
                # Top-right grid has high contrast text in a structured table
                preprocessed[name] = self.preprocess_for_ocr(img, method="adaptive")
            else:
                # Simple preprocessing works much better for CAD-rendered text
                preprocessed[name] = self.preprocess_for_ocr(img, method="simple")

        return preprocessed
