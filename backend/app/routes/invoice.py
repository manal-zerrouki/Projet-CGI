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
from datetime import datetime

from app.services.db_service import get_db_connection
from app.services.ocr_service import extract_text_from_pdf, format_preview
from app.services.llm_service import extract_invoice_json_from_text
from app.services.validation_service import valider_facture

router = APIRouter()
UPLOAD_FOLDER = "uploads"


def safe_float(value):
    try:
        return float(value)
    except:
        return None


def safe_date(date_str):
    try:
        return datetime.strptime(date_str, "%d-%m-%Y").date()
    except:
        return None


@router.post("/analyze")
async def analyze_invoice(file: UploadFile = File(...)):

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un PDF")

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # OCR
        ocr_text = extract_text_from_pdf(file_path)

        if not ocr_text or len(ocr_text.strip()) < 20:
            return {
                "status": "error",
                "step": "ocr",
                "message": "Texte OCR insuffisant",
                "validation": None,
                "motifs_rejet": [],
                "exceptions": [],
                "warnings": [],
                "data": None,
                "ocr_preview_lines": [],
            }

        # LLM extraction
        data = extract_invoice_json_from_text(ocr_text, pdf_path=file_path)

        # Validation
        result = valider_facture(data)

        # INSERT DB
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            date_facture = safe_date(data.get("date_facture"))

            cursor.execute("""
                INSERT INTO factures_cgi (
                    numero_facture,
                    prestataire,
                    ice,
                    date_facture,
                    numero_engagement,
                    montant_ht,
                    tva,
                    montant_ttc,
                    devise,
                    exception
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data.get("numero_facture"),
                data.get("prestataire"),
                data.get("ice"),
                date_facture,
                data.get("numero_engagement"),
                safe_float(data.get("montant_ht")),
                safe_float(data.get("tva")),
                safe_float(data.get("montant_ttc")),
                data.get("devise"),
                str(result.exceptions)
            ))

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as db_error:
            print("DB ERROR:", db_error)

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