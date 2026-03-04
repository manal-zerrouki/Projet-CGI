from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import shutil

from app.services.ocr_service import extract_text_from_pdf, format_preview
from app.services.llm_service import extract_invoice_json_from_text

router = APIRouter()
UPLOAD_FOLDER = "uploads"


@router.post("/analyze")
async def analyze_invoice(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un PDF")

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)

    # 1) Sauvegarde du PDF
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2) OCR / extraction texte (PDF texte ou scan)
    try:
        ocr_text = extract_text_from_pdf(file_path)

        # Si OCR vide => on le signale
        if not ocr_text or len(ocr_text.strip()) < 20:
            return {
                "status": "error",
                "step": "ocr",
                "message": "Texte OCR vide ou insuffisant (facture illisible ou OCR non installé).",
            }

        # 3) Appel LLM avec texte OCR
        data = extract_invoice_json_from_text(ocr_text)

        return {
            "status": "ok",
            "step": "llm",
            "data": data,
            "ocr_preview_lines": format_preview(ocr_text, max_chars=1500).split("\n"),
        }

    except Exception as e:
        # Si c'est un problème de dispo LLM (503), on renvoie 503 au lieu de 500
        msg = str(e).lower()
        if "503" in msg or "unavailable" in msg or "high demand" in msg:
            raise HTTPException(status_code=503, detail=str(e))

        raise HTTPException(status_code=500, detail=str(e))