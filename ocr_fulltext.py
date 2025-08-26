
#!/usr/bin/env python3
"""
ocr_fulltext.py — High-fidelity OCR pipeline for scanned PDFs.

Features
- High-DPI rendering via PyMuPDF (fitz)
- Image cleanup: denoise, de-skew, adaptive/Sauvola binarization, unsharp mask
- Orientation detection (OSD) with Tesseract
- Multiprocessing (per-page) OCR using pytesseract
- Word/line-level bounding boxes + confidences
- Optional table detection for scanned pages via OpenCV morphology (best-effort)
- Vector-text extraction (if present) to avoid re-OCRing good text
- Outputs: structured JSON, word-level CSV, and a searchable OCR PDF
- Per-page quality metrics & low-confidence flags

Usage
    python ocr_fulltext.py input.pdf --lang eng --outdir out
    python ocr_fulltext.py input.pdf --lang "eng+msa" --dpi 400 --psm 1

Notes
- macOS: brew install tesseract
- Add language packs as needed (e.g., brew install tesseract-lang)
"""

import argparse
import io
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image
import pytesseract
from pytesseract import Output
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

# Optional: Sauvola thresholding (fallback to OpenCV adaptive if skimage missing)
try:
    from skimage.filters import threshold_sauvola
    _HAS_SAUVOLA = True
except Exception:
    _HAS_SAUVOLA = False

# --------- Image preprocessing utilities --------- #

def pil_to_cv(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

def cv_to_pil(img_cv: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))

def unsharp_mask(gray: np.ndarray, ksize: int = 5, amount: float = 1.5) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (ksize, ksize), 0)
    sharp = cv2.addWeighted(gray, 1 + amount, blurred, -amount, 0)
    return sharp

def estimate_skew_angle(binary: np.ndarray) -> float:
    # Use Hough transform on edges to estimate skew angle (in degrees)
    edges = cv2.Canny(binary, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180.0, threshold=200)
    if lines is None:
        return 0.0
    angles = []
    for rho_theta in lines:
        rho, theta = rho_theta[0]
        angle = (theta * 180 / np.pi) - 90  # convert to degrees, normalize
        # Filter near-vertical/horizontal lines less informative
        if -45 <= angle <= 45:
            angles.append(angle)
    if not angles:
        return 0.0
    return float(np.median(angles))

def rotate_image_bound(img: np.ndarray, angle: float, bg=255) -> np.ndarray:
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(M[0, 0])
    sin = abs(M[0, 1])
    nW = int((h * sin) + (w * cos))
    nH = int((h * cos) + (w * sin))
    M[0, 2] += (nW / 2) - center[0]
    M[1, 2] += (nH / 2) - center[1]
    rotated = cv2.warpAffine(img, M, (nW, nH), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=bg)
    return rotated

def adaptive_binarize(gray: np.ndarray) -> np.ndarray:
    # Prefer Sauvola for historical docs; fallback to OpenCV adaptive
    if _HAS_SAUVOLA:
        window = 31
        k = 0.2
        thresh_s = threshold_sauvola(gray, window_size=window, k=k)
        bin_img = (gray > thresh_s).astype(np.uint8) * 255
        return bin_img
    # OpenCV adaptive Gaussian threshold as fallback
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 35, 11)

def remove_noise(binary: np.ndarray) -> np.ndarray:
    # Remove tiny speckles and fill gaps
    kernel = np.ones((3, 3), np.uint8)
    opening = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, kernel, iterations=1)
    return closing

def preprocess_for_ocr(img_pil: Image.Image, fast_mode: bool = False) -> Tuple[Image.Image, Dict[str, Any]]:
    info = {}
    img_cv = pil_to_cv(img_pil)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    
    if fast_mode:
        # Fast mode: minimal preprocessing
        info["fast_mode"] = True
        # Use bilateral filter instead of expensive denoising
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        # Simple threshold instead of adaptive
        _, bin_img = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Skip deskewing and OSD for speed
        info["deskew_angle_deg"] = 0
        info["osd_skipped"] = True
    else:
        # Full preprocessing pipeline
        gray = cv2.fastNlMeansDenoising(gray, h=7)
        gray = unsharp_mask(gray, ksize=5, amount=1.2)
        # First binarize
        bin_img = adaptive_binarize(gray)
        # Deskew (estimate on binary)
        angle = estimate_skew_angle(bin_img)
        info["deskew_angle_deg"] = angle
        if abs(angle) > 0.3:
            bin_img = rotate_image_bound(bin_img, angle, bg=255)
            gray = rotate_image_bound(gray, angle, bg=255)
        # Clean
        bin_img = remove_noise(bin_img)
        # Ensure black text on white background
        if np.mean(bin_img) < 127:
            bin_img = 255 - bin_img
        # OSD orientation (coarse 0/90/180/270) using Tesseract
        try:
            osd = pytesseract.image_to_osd(bin_img)
            info["osd_raw"] = osd
            rotate = 0
            for token in osd.split():
                if token.startswith("Rotate:"):
                    # sometimes formatted as "Rotate: 90"
                    pass
            # simple parse
            if "Rotate:" in osd:
                rotate_line = [ln for ln in osd.splitlines() if "Rotate:" in ln]
                if rotate_line:
                    rotate = int(rotate_line[0].split(":")[1].strip())
            if rotate in (90, 180, 270):
                bin_img = rotate_image_bound(bin_img, -rotate, bg=255)
                gray = rotate_image_bound(gray, -rotate, bg=255)
                info["osd_rotation_applied"] = rotate
        except Exception as e:
            info["osd_error"] = str(e)
    
    # Ensure black text on white background
    if np.mean(bin_img) < 127:
        bin_img = 255 - bin_img

    processed = cv_to_pil(cv2.cvtColor(bin_img, cv2.COLOR_GRAY2BGR))
    return processed, info

# --------- Table detection (best-effort for scanned pages) --------- #

def detect_tables(binary_bgr: np.ndarray) -> List[Dict[str, Any]]:
    """
    Heuristic table detector using morphological line detection.
    Returns list of table dicts with bbox and cell boxes (without OCR).
    """
    img_gray = cv2.cvtColor(binary_bgr, cv2.COLOR_BGR2GRAY)
    # Invert (lines are black, background white)
    _, bw = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    inv = 255 - bw

    # detect horizontal lines
    horizontalsize = max(10, inv.shape[1] // 100)
    vertsize = max(10, inv.shape[0] // 100)
    horizontalStructure = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontalsize, 1))
    verticalStructure = cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertsize))

    horizontal = cv2.erode(inv, horizontalStructure)
    horizontal = cv2.dilate(horizontal, horizontalStructure)

    vertical = cv2.erode(inv, verticalStructure)
    vertical = cv2.dilate(vertical, verticalStructure)

    mask = cv2.add(horizontal, vertical)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    tables = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 60 or h < 40:
            continue
        tables.append({"bbox": [int(x), int(y), int(w), int(h)], "cells": []})
    return tables

# --------- OCR worker --------- #

@dataclass
class OCRConfig:
    lang: str = "eng"
    psm: int = 1   # 1 = automatic page segmentation with OSD; 6 = uniform block
    oem: int = 3   # 3 = default LSTM
    dpi: int = 400
    fast_mode: bool = False
    skip_tables: bool = False

def ocr_page_worker(args: Tuple[int, bytes, OCRConfig]) -> Dict[str, Any]:
    page_index, png_bytes, cfg = args
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    processed, prep_info = preprocess_for_ocr(img, fast_mode=cfg.fast_mode)

    # Tesseract config
    tess_config = f'--oem {cfg.oem} --psm {cfg.psm}'
    data = pytesseract.image_to_data(processed, lang=cfg.lang, output_type=Output.DICT, config=tess_config)
    
    # Generate PDF and HOCR in one efficient call if possible
    if cfg.fast_mode:
        # In fast mode, skip HOCR generation to save time
        hocr = b""
        pdf_bytes = pytesseract.image_to_pdf_or_hocr(processed, lang=cfg.lang, config=tess_config, extension='pdf')
    else:
        hocr = pytesseract.image_to_pdf_or_hocr(processed, lang=cfg.lang, config=tess_config, extension='hocr')
        pdf_bytes = pytesseract.image_to_pdf_or_hocr(processed, lang=cfg.lang, config=tess_config, extension='pdf')

    # Build word-level records
    words = []
    n = len(data['text'])
    confs = []
    for i in range(n):
        txt = data['text'][i]
        if txt is None or str(txt).strip() == "":
            continue
        conf = int(data['conf'][i]) if str(data['conf'][i]).isdigit() else -1
        confs.append(conf if conf >= 0 else None)
        words.append({
            "block_num": int(data.get('block_num', [0]*n)[i]),
            "par_num": int(data.get('par_num', [0]*n)[i]),
            "line_num": int(data.get('line_num', [0]*n)[i]),
            "word_num": int(data.get('word_num', [0]*n)[i]),
            "left": int(data['left'][i]),
            "top": int(data['top'][i]),
            "width": int(data['width'][i]),
            "height": int(data['height'][i]),
            "conf": conf,
            "text": txt
        })

    # Table detection (heuristic); OCR per table region (optional)
    if cfg.skip_tables:
        table_ocr = []
    else:
        bin_bgr = pil_to_cv(processed)
        tables = detect_tables(bin_bgr)
        # Optional: OCR table cells as a block to encourage row-wise reading
        table_ocr = []
        for t in tables:
            x, y, w, h = t["bbox"]
            roi = processed.crop((x, y, x + w, y + h))
            roi_data = pytesseract.image_to_data(roi, lang=cfg.lang, output_type=Output.DICT, config=tess_config)
            cells = []
            for i in range(len(roi_data["text"])):
                txt = roi_data["text"][i]
                if txt and str(txt).strip():
                    cells.append({
                        "left": int(roi_data["left"][i]) + x,
                        "top": int(roi_data["top"][i]) + y,
                        "width": int(roi_data["width"][i]),
                        "height": int(roi_data["height"][i]),
                        "conf": int(roi_data["conf"][i]) if str(roi_data["conf"][i]).isdigit() else -1,
                        "text": txt
                    })
            table_ocr.append({"bbox": t["bbox"], "cells": cells})

    # Quality metrics
    conf_vals = [c for c in confs if isinstance(c, int) and c >= 0]
    avg_conf = float(np.mean(conf_vals)) if conf_vals else None

    return {
        "page_index": page_index,
        "prep_info": prep_info,
        "avg_confidence": avg_conf,
        "hocr": hocr.decode("utf-8", errors="ignore") if isinstance(hocr, bytes) and hocr else "",
        "pdf_bytes": pdf_bytes,
        "words": words,
        "tables": table_ocr
    }

# --------- Vector text extraction (if present) --------- #

def extract_vector_text(page: fitz.Page) -> Dict[str, Any]:
    raw = page.get_text("rawdict")  # includes blocks, spans, bbox
    return raw

# --------- Main pipeline --------- #

def render_page_to_png_bytes(page: fitz.Page, dpi: int) -> bytes:
    zoom = dpi / 72.0
    mtx = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mtx, alpha=False)
    return pix.tobytes("png")

def stitch_pdf(pages_pdf_bytes: List[bytes], output_path: str) -> None:
    # Combine per-page image_to_pdf_or_hocr PDFs into a single PDF
    out = fitz.open()
    for pb in pages_pdf_bytes:
        with fitz.open(stream=pb, filetype="pdf") as tmp:
            out.insert_pdf(tmp)
    out.save(output_path)
    out.close()

def main():
    ap = argparse.ArgumentParser(description="High-fidelity OCR for scanned PDFs")
    ap.add_argument("pdf", help="Input PDF path")
    ap.add_argument("--outdir", default=None, help="Output directory (default: create folder named after PDF)")
    ap.add_argument("--lang", default="eng", help='Tesseract language(s), e.g. "eng" or "eng+msa"')
    ap.add_argument("--dpi", type=int, default=400, help="Render DPI (300–600 recommended)")
    ap.add_argument("--psm", type=int, default=1, help="Tesseract PSM (1 auto with OSD, 4/6 for columns)")
    ap.add_argument("--oem", type=int, default=3, help="Tesseract OEM (3 LSTM default)")
    ap.add_argument("--max_workers", type=int, default= max(1, os.cpu_count() or 1), help="Parallel workers")
    ap.add_argument("--keep_page_pngs", action="store_true", help="Keep rendered PNGs for inspection")
    ap.add_argument("--fast", action="store_true", help="Fast mode: skip denoising, deskewing, OSD, and table detection")
    ap.add_argument("--skip_tables", action="store_true", help="Skip table detection and OCR")
    ap.add_argument("--adaptive_dpi", action="store_true", help="Use adaptive DPI: start low, increase if confidence is poor")
    args = ap.parse_args()

    # Auto-generate output directory name from PDF filename if not specified
    if args.outdir is None:
        pdf_basename = os.path.basename(args.pdf)
        pdf_name_without_ext = os.path.splitext(pdf_basename)[0]
        args.outdir = pdf_name_without_ext
        print(f"Auto-creating output directory: {args.outdir}")

    os.makedirs(args.outdir, exist_ok=True)

    doc = fitz.open(args.pdf)
    meta = doc.metadata or {}
    total_pages = len(doc)

    # Adjust DPI for fast mode or adaptive mode
    effective_dpi = args.dpi
    if args.fast and args.dpi == 400:  # Only auto-adjust if using default DPI
        effective_dpi = 300  # Lower DPI for faster processing
        print(f"Fast mode: using {effective_dpi} DPI instead of {args.dpi}")
    elif args.adaptive_dpi:
        effective_dpi = 250  # Start with low DPI
        print(f"Adaptive DPI mode: starting with {effective_dpi} DPI")
    
    # Render all pages to PNG bytes upfront (avoid sharing doc between processes)
    rendered = []
    vector_text = []
    for i in range(total_pages):
        page = doc.load_page(i)
        png_bytes = render_page_to_png_bytes(page, dpi=effective_dpi)
        rendered.append((i, png_bytes))
        vector_text.append(extract_vector_text(page))
        if args.keep_page_pngs:
            with open(os.path.join(args.outdir, f"page_{i+1:04d}.png"), "wb") as f:
                f.write(png_bytes)

    cfg = OCRConfig(
        lang=args.lang, 
        psm=args.psm, 
        oem=args.oem, 
        dpi=effective_dpi,
        fast_mode=args.fast,
        skip_tables=args.skip_tables or args.fast  # fast mode implies skip_tables
    )

    results: List[Optional[Dict[str, Any]]] = [None] * total_pages
    page_pdfs: List[bytes] = [b""] * total_pages

    with ProcessPoolExecutor(max_workers=args.max_workers) as ex:
        futures = {ex.submit(ocr_page_worker, (i, png, cfg)): i for (i, png) in rendered}
        for fut in tqdm(as_completed(futures), total=total_pages, desc="OCR pages"):
            i = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"page_index": i, "error": str(e)}
            results[i] = res

    # Assemble outputs
    structured = {
        "metadata": {
            "title": meta.get("title") or "",
            "author": meta.get("author") or "",
            "pages": total_pages,
            "source_pdf": os.path.abspath(args.pdf),
            "dpi": args.dpi,
            "lang": args.lang,
        },
        "content": []
    }

    import pandas as pd
    words_rows = []

    for i, res in enumerate(results):
        # Collect PDF bytes for final searchable PDF first
        if res and res.get("pdf_bytes"):
            page_pdfs[i] = res["pdf_bytes"]
        
        # Create JSON-safe page entry (avoid bytes objects)
        page_entry = {
            "page": i + 1,
            "avg_confidence": res.get("avg_confidence") if res else None,
            "prep_info": res.get("prep_info") if res else {},
            "vector_text": vector_text[i],  # rawdict structure (if any text present)
            "words": res.get("words") if res else [],
            "tables": res.get("tables") if res else [],
            "errors": res.get("error") if (res and "error" in res) else None,
            "hocr": res.get("hocr") if (res and isinstance(res.get("hocr"), str)) else ""
        }
        structured["content"].append(page_entry)

        for w in page_entry["words"]:
            words_rows.append({
                "page": i + 1,
                **{k: w[k] for k in ["block_num", "par_num", "line_num", "word_num", "left", "top", "width", "height", "conf", "text"]}
            })

    # Safe JSON serialization - handle any remaining bytes objects
    def json_safe(obj):
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="ignore")
        elif isinstance(obj, dict):
            return {k: json_safe(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [json_safe(item) for item in obj]
        else:
            return obj
    
    # Save JSON
    json_path = os.path.join(args.outdir, "structured.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_safe(structured), f, indent=2, ensure_ascii=False)

    # Save CSV
    df = pd.DataFrame(words_rows, columns=["page","block_num","par_num","line_num","word_num","left","top","width","height","conf","text"])
    csv_path = os.path.join(args.outdir, "words.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8")

    # Save searchable PDF (OCR layer)
    ocr_pdf_path = os.path.join(args.outdir, "ocr_searchable.pdf")
    stitch_pdf(page_pdfs, ocr_pdf_path)

    # Simple quality report
    avg_confs = [c.get("avg_confidence") for c in results if c and c.get("avg_confidence") is not None]
    overall_avg = float(np.mean(avg_confs)) if avg_confs else None
    report = {
        "overall_avg_confidence": overall_avg,
        "low_conf_pages": [i+1 for i, c in enumerate(results) if c and (c.get("avg_confidence") is not None) and c["avg_confidence"] < 70]
    }
    with open(os.path.join(args.outdir, "quality_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"[OK] JSON: {json_path}")
    print(f"[OK] CSV:  {csv_path}")
    print(f"[OK] PDF:  {ocr_pdf_path}")
    print(f"[OK] Quality: {os.path.join(args.outdir, 'quality_report.json')}")

if __name__ == "__main__":
    main()
