"""
================================
Route FastAPI pour l'analyse et la validation des factures PDF.

Endpoint principal :
  POST /analyze
    - Reçoit un fichier PDF
    - Lance l'OCR
    - Extrait les données via LLM (+ détection visuelle cachet si pdf_path fourni)
    - Valide les règles métier
    - Retourne un résultat structuré complet
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import shutil

from app.services.ocr_service import extract_text_from_pdf, format_preview
from app.services.llm_service import extract_invoice_json_from_text
from app.services.validation_service import valider_facture

router = APIRouter()
UPLOAD_FOLDER = "uploads"


@router.post("/analyze")
async def analyze_invoice(file: UploadFile = File(...)):
    """
    Analyse complète d'une facture PDF.

    Retourne :
      - status       : "ok" | "error"
      - validation   : statut métier ("accepté" | "rejeté" | "accepté_avec_réserve")
      - motifs_rejet : liste des raisons de rejet (bloquantes)
      - exceptions   : champs complémentaires manquants (non bloquants)
      - warnings     : incohérences mineures ou informations
      - data         : JSON complet extrait par le LLM
      - ocr_preview_lines : aperçu du texte OCR (pour debug/affichage)
    """
    # --- Vérification du type de fichier ---
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un PDF")

    # --- Sauvegarde du PDF uploadé ---
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # --- Étape 1 : OCR / extraction texte ---
        ocr_text = extract_text_from_pdf(file_path)

        if not ocr_text or len(ocr_text.strip()) < 20:
            return {
                "status": "error",
                "step": "ocr",
                "message": (
                    "Texte OCR vide ou insuffisant. "
                    "La facture est peut-être illisible, protégée, ou Tesseract n'est pas installé."
                ),
                "validation": None,
                "motifs_rejet": [],
                "exceptions": [],
                "warnings": [],
                "data": None,
                "ocr_preview_lines": [],
            }

        # --- Étape 2 : Extraction des données via LLM ---
        # pdf_path est passé pour activer la détection visuelle du cachet via Gemini Vision
        data = extract_invoice_json_from_text(ocr_text, pdf_path=file_path)

        # --- Étape 3 : Validation métier ---
        result = valider_facture(data)

        # --- Réponse complète ---
        return {
            "status": "ok",
            "step": "completed",
            "validation": result.statut,
            "motifs_rejet": result.motifs_rejet,
            "exceptions": result.exceptions,
            "warnings": result.warnings,
            "data": data,
            "ocr_preview_lines": format_preview(ocr_text, max_chars=1500).split("\n"),
        }

    except Exception as e:
        msg = str(e).lower()

        if "503" in msg or "unavailable" in msg or "high demand" in msg:
            raise HTTPException(status_code=503, detail=str(e))

        raise HTTPException(status_code=500, detail=str(e))