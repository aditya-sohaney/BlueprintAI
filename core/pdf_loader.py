"""PDF loading and page rendering using PyMuPDF."""

import fitz  # PyMuPDF
from dataclasses import dataclass, field
from pathlib import Path
from PIL import Image


@dataclass
class PageInfo:
    """Metadata and embedded text for a single PDF page."""
    page_number: int        # 1-indexed
    width_pts: float
    height_pts: float
    embedded_text: str      # Sparse text from embedded text layer
    embedded_words: list    # List of (x0, y0, x1, y1, word) tuples with positions


@dataclass
class PDFDocument:
    """Represents a loaded PDF with metadata and page info."""
    filepath: Path
    num_pages: int
    metadata: dict
    pages: list = field(default_factory=list)


def load_pdf(filepath: str | Path) -> PDFDocument:
    """Open PDF with PyMuPDF, extract metadata and embedded text per page.

    Note: ADOT engineering drawings have very sparse embedded text layers.
    Most content is vector/path graphics and requires OCR on rendered images.
    """
    filepath = Path(filepath)
    doc = fitz.open(str(filepath))

    pages = []
    for i in range(doc.page_count):
        page = doc[i]
        text = page.get_text("text")
        words_raw = page.get_text("words")
        # words_raw format: (x0, y0, x1, y1, word, block_no, line_no, word_no)
        words = [(w[0], w[1], w[2], w[3], w[4]) for w in words_raw]

        pages.append(PageInfo(
            page_number=i + 1,
            width_pts=page.rect.width,
            height_pts=page.rect.height,
            embedded_text=text,
            embedded_words=words
        ))

    pdf_doc = PDFDocument(
        filepath=filepath,
        num_pages=doc.page_count,
        metadata=dict(doc.metadata) if doc.metadata else {},
        pages=pages
    )

    doc.close()
    return pdf_doc


def render_page_to_image(filepath: str | Path, page_num: int, dpi: int = 300) -> Image.Image:
    """Render a single PDF page to a PIL Image at specified DPI.

    Args:
        filepath: Path to the PDF file.
        page_num: 1-indexed page number.
        dpi: Resolution for rendering (default 300).

    Returns:
        PIL Image of the rendered page.
    """
    doc = fitz.open(str(filepath))
    page = doc[page_num - 1]  # Convert to 0-indexed

    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    doc.close()
    return img


def get_page_dimensions(filepath: str | Path, page_num: int = 1) -> tuple:
    """Get page dimensions in points and at 300 DPI.

    Returns:
        Tuple of (width_pts, height_pts, width_px_300dpi, height_px_300dpi)
    """
    doc = fitz.open(str(filepath))
    page = doc[page_num - 1]
    w_pts = page.rect.width
    h_pts = page.rect.height
    doc.close()

    scale = 300 / 72
    return (w_pts, h_pts, int(w_pts * scale), int(h_pts * scale))
