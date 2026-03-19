"""
OCR Mock - utilise texte natif PDF + fallback vide
LLM extrait données réelles facture
"""

import fitz

def extract_text_from_pdf(pdf_path: str):
    try:
        doc = fitz.open(pdf_path)
        text = ''
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.strip()
    except:
        return "Texte PDF natif introuvable"

def format_preview(text: str, max_chars: int = 1500):
    return text[:max_chars]
