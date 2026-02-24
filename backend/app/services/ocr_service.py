import os
import re
import io

import fitz  # PyMuPDF
from PIL import Image
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def format_preview(text: str, max_chars: int = 1500) -> str:
    if not text:
        return ""
    preview = text.strip()[:max_chars]
    # IMPORTANT: si le texte contient des "\n" littéraux, on les convertit en vrais retours ligne
    preview = preview.replace("\\r\\n", "\n").replace("\\n", "\n")
    # normaliser aussi les vrais retours Windows
    preview = preview.replace("\r\n", "\n")
    # enlever espaces en fin de ligne
    preview = "\n".join(line.rstrip() for line in preview.split("\n"))
    return preview

def extract_text_from_pdf(pdf_path: str, min_chars_text_pdf: int = 80) -> str:
    """
    - Essaie d'abord d'extraire le texte direct (si PDF texte)
    - Sinon: OCR page par page (PDF scanné)
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF introuvable: {pdf_path}")

    doc = fitz.open(pdf_path)

    # 1) Tentative texte direct
    direct_parts = []
    for page in doc:
        t = (page.get_text("text") or "").strip()
        if t:
            direct_parts.append(t)

    direct_text = _clean_text("\n\n".join(direct_parts))
    if len(direct_text) >= min_chars_text_pdf:
        return direct_text

    # 2) OCR (PDF scan)
    ocr_parts = []
    for i, page in enumerate(doc):
        zoom = 2.0  # augmente la qualité OCR
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        img_bytes = pix.tobytes("png")
        image = Image.open(io.BytesIO(img_bytes))

        page_text = pytesseract.image_to_string(image, lang="fra+eng").strip()
        if page_text:
            ocr_parts.append(f"--- PAGE {i+1} ---\n{page_text}")

    return _clean_text("\n\n".join(ocr_parts))