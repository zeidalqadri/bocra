# High‑Fidelity OCR for Scanned PDFs

This pipeline aims for “nothing‑left‑behind” OCR on noisy, historical scans.

## Install (macOS)
```bash
brew install tesseract
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

> Add language packs if needed (e.g., Malay): `brew install tesseract-lang` then use `--lang "eng+msa"`.

## Run
```bash
python ocr_fulltext.py input.pdf --lang "eng" --dpi 400 --psm 1 --outdir out
```

### Outputs
- `structured.json` — metadata, per‑page words (bboxes, confidences), vector text if present, table regions
- `words.csv` — word‑level flat table for quick QA/grep
- `ocr_searchable.pdf` — original pages with a selectable/searchable text layer
- `quality_report.json` — overall average confidence and low‑confidence page list

### Tips
- Try `--psm 6` for dense single‑column text; `--psm 4` for multi‑column.
- Bump `--dpi` to 500–600 for tiny type or microfilm scans.
- For multilingual pages, chain languages: `--lang "eng+msa"` or add Chinese/Jawi packs if installed.
- Use `--keep_page_pngs` to inspect preprocessed images for QC.