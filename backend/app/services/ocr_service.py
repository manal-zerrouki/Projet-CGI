"""
ocr_service.py
==============
Extraction de texte à partir de fichiers PDF.

Deux stratégies :
  1. Extraction directe si le PDF contient du texte natif (PDF texte)
  2. OCR via Tesseract si le PDF est scanné (image)

La commande Tesseract est configurable via la variable d'environnement
TESSERACT_CMD (évite le chemin Windows hardcodé).
"""

import os
import re
import io

import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from dotenv import load_dotenv

load_dotenv()

# =========================
# Config Tesseract
# Configurable via .env : TESSERACT_CMD=/usr/bin/tesseract  (Linux/Mac)
#                         TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe  (Windows)
# =========================
tesseract_cmd = os.getenv("TESSERACT_CMD", "/opt/local/bin/tesseract").strip()
pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def _clean_text(text: str) -> str:
    """Nettoie le texte brut extrait (caractères nuls, espaces multiples, lignes vides)."""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_preview(text: str, max_chars: int = 1500) -> str:
    """
    Retourne un aperçu propre du texte OCR pour l'affichage frontend.
    Convertit les séquences \\n littérales en vrais retours ligne.
    """
    if not text:
        return ""
    preview = text.strip()[:max_chars]
    preview = preview.replace("\\r\\n", "\n").replace("\\n", "\n")
    preview = preview.replace("\r\n", "\n")
    preview = "\n".join(line.rstrip() for line in preview.split("\n"))
    return preview


def extract_text_from_pdf(pdf_path: str, min_chars_text_pdf: int = 80) -> str:
    """
    Extrait le texte d'un PDF (texte natif ou scanné).

    Args:
        pdf_path: chemin vers le fichier PDF
        min_chars_text_pdf: seuil minimum de caractères pour considérer
                            qu'un PDF contient du texte natif exploitable.
                            En dessous, on bascule sur l'OCR.

    Returns:
        Texte extrait (nettoyé), ou chaîne vide si échec total.

    Raises:
        FileNotFoundError: si le fichier PDF n'existe pas.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF introuvable : {pdf_path}")

    doc = fitz.open(pdf_path)

    # --- Stratégie 1 : extraction texte natif ---
    direct_parts = []
    for page in doc:
        t = (page.get_text("text") or "").strip()
        if t:
            direct_parts.append(t)

    direct_text = _clean_text("\n\n".join(direct_parts))
    if len(direct_text) >= min_chars_text_pdf:
        return direct_text

    # --- Stratégie 2 : OCR page par page ---
    ocr_parts = []
    for i, page in enumerate(doc):
        # zoom=2.0 améliore la résolution pour un meilleur OCR
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)

        image = Image.open(io.BytesIO(pix.tobytes("png")))
        page_text = pytesseract.image_to_string(image, lang="fra+eng").strip()

        if page_text:
            ocr_parts.append(f"--- PAGE {i + 1} ---\n{page_text}")

    return _clean_text("\n\n".join(ocr_parts))