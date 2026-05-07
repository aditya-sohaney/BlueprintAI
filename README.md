# BlueprintAI

Automated metadata extraction from scanned engineering drawing PDFs using ensemble OCR and vision-language models.

Reads title blocks from ADOT construction drawings, extracts 18 structured fields per page, and presents results in an interactive Streamlit dashboard. All models run locally via Ollama — no cloud APIs needed for the core pipeline.

**Results:** 90%+ field fill rate across 1,332 pages from 37 PDFs.

## How It Works

```
PDF → PyMuPDF (render at 200 DPI)
  → Title block cropping (7 zones)
  → Ensemble OCR (PaddleOCR + Tesseract)
  → Regex extraction (18 fields)
  → VLM extraction (stamps, firms, structure numbers)
  → Multi-source merge (embedded > OCR > VLM)
  → Validation + derived fields
  → SQLite → Streamlit dashboard
```

The pipeline has two tiers:
- **Tier 1** — OCR + regex. Fast, handles most fields.
- **Tier 2** — VLM (Qwen2.5-VL 7B) fills in what OCR misses: engineer stamps, firm logos, degraded text.

Results are merged by confidence: embedded PDF text (1.0) > OCR regex (0.9) > VLM (0.8).

## Tech Stack

- Python 3.12, Streamlit, Plotly
- PaddleOCR + Tesseract for OCR
- Qwen2.5-VL 7B (via Ollama) for vision extraction
- Mistral 7B / Qwen2.5 7B (via Ollama) for AI chat
- PyMuPDF + pdfplumber for PDF handling
- SQLite, pandas

## Dashboard Pages

1. **Dashboard** — stats, fill rates, division breakdown, top engineers, design velocity
2. **Search & Browse** — filter by division/route/engineer/etc, export CSV
3. **Engineer Profiles** — per-engineer stats, drawing history, specialization
4. **Upload & Extract** — upload PDFs, see extracted fields with confidence scores
5. **AI Chat** — ask questions in natural language, get SQL-backed answers + charts
6. **Data Quality** — health grades, missing data analysis, review queue
7. **Project Timeline** — design duration analysis by engineer and division
8. **Bridge Tracker** — bridge drawing detection and tracking
9. **Reports** — downloadable summary reports

## Setup

```bash
git clone https://github.com/aditya-sohaney/BlueprintAI.git
cd BlueprintAI
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install paddlepaddle paddleocr

# pull models
ollama pull qwen2.5vl
ollama pull mistral
```

## Usage

```bash
# run dashboard
streamlit run app.py

# extract from PDFs
python main.py data/raw/yourfile.pdf --mode dual

# batch VLM extraction
python run_vlm_parallel.py
```

## Project Structure

```
├── app.py                  # Streamlit dashboard
├── main.py                 # CLI extraction
├── core/                   # Extraction pipeline modules
│   ├── pdf_loader.py
│   ├── title_block.py
│   ├── ocr_engine.py       # PaddleOCR + Tesseract
│   ├── regex_extractor.py
│   ├── vlm_engine.py       # Qwen2.5-VL integration
│   ├── merger.py           # Multi-source merging
│   ├── validator.py
│   └── database.py
├── config/                 # Coordinates, field defs, lookups
├── analytics/              # Chat agent, dashboards, reports
├── eval/                   # Benchmarking + ground truth
└── data/                   # PDFs, DB, exports (gitignored)
```

## License

MIT
