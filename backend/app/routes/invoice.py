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
import json
import uuid
import time
from datetime import datetime

from app.services.db_service import get_db_connection
from app.services.ocr_service import extract_text_from_pdf, format_preview
from app.services.llm_service import extract_invoice_json_from_text
from app.services.validation_service import valider_facture
from app.services.db_service import get_all_factures


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
    file_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}.pdf")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        t_start = time.time()

        # OCR
        ocr_text = extract_text_from_pdf(file_path)
        t_after_ocr = time.time()
        t_ocr_ms = round((t_after_ocr - t_start) * 1000)

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

        # Qualité texte OCR
        ocr_chars = len(ocr_text)
        ocr_mots  = len(ocr_text.split())

        # LLM extraction
        data = extract_invoice_json_from_text(ocr_text, pdf_path=file_path)
        t_after_llm = time.time()
        t_llm_ms   = round((t_after_llm - t_after_ocr) * 1000)
        t_total_ms = round((t_after_llm - t_start)     * 1000)

        # Score confiance LLM : calculé dans llm_service.py sur l'extraction
        # brute (avant _post_validate) → valeur déjà dans data["confidence"]
        confidence_llm = int(data.get("confidence") or 0)

        # Validation
        result = valider_facture(data)

        # INSERT DB
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Si numero_facture non extrait → générer un ID unique pour éviter l'échec INSERT
            if not data.get("numero_facture"):
                data["numero_facture"] = f"UNKNOWN-{uuid.uuid4().hex[:8].upper()}"

            date_facture = safe_date(data.get("date_facture"))

            full_result = {
                "validation"       : result.statut,
                "motifs_rejet"     : result.motifs_rejet,
                "exceptions"       : result.exceptions,
                "warnings"         : result.warnings,
                "data"             : data,
                "ocr_preview_lines": format_preview(ocr_text, max_chars=1500).split("\n"),
                "perf": {
                    "t_ocr_ms"      : t_ocr_ms,
                    "t_llm_ms"      : t_llm_ms,
                    "t_total_ms"    : t_total_ms,
                    "t_response_ms" : round((time.time() - t_start) * 1000),
                    "ocr_chars"     : ocr_chars,
                    "ocr_mots"      : ocr_mots,
                    "confidence_llm": confidence_llm,
                },
            }

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
                    statut_validation,
                    exception,
                    motifs_rejet,
                    result_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    prestataire       = VALUES(prestataire),
                    ice               = VALUES(ice),
                    date_facture      = VALUES(date_facture),
                    numero_engagement = VALUES(numero_engagement),
                    montant_ht        = VALUES(montant_ht),
                    tva               = VALUES(tva),
                    montant_ttc       = VALUES(montant_ttc),
                    devise            = VALUES(devise),
                    statut_validation = VALUES(statut_validation),
                    exception         = VALUES(exception),
                    motifs_rejet      = VALUES(motifs_rejet),
                    result_json       = VALUES(result_json),
                    date_creation     = CURRENT_TIMESTAMP
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
                result.statut,
                json.dumps(result.exceptions,  ensure_ascii=False),
                json.dumps(result.motifs_rejet, ensure_ascii=False),
                json.dumps(full_result,         ensure_ascii=False),
            ))

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as db_error:
            print("DB ERROR:", db_error)

        t_response_ms = round((time.time() - t_start) * 1000)

        return {
            "status": "ok",
            "step": "completed",
            "validation": result.statut,
            "motifs_rejet": result.motifs_rejet,
            "exceptions": result.exceptions,
            "warnings": result.warnings,
            "data": data,
            "ocr_preview_lines": format_preview(ocr_text, max_chars=1500).split("\n"),
            "perf": {
                "t_ocr_ms"      : t_ocr_ms,
                "t_llm_ms"      : t_llm_ms,
                "t_total_ms"    : t_total_ms,
                "t_response_ms" : t_response_ms,
                "ocr_chars"     : ocr_chars,
                "ocr_mots"      : ocr_mots,
                "confidence_llm": confidence_llm,
            },
        }

    except Exception as e:
        msg = str(e).lower()

        if "503" in msg or "unavailable" in msg or "high demand" in msg:
            raise HTTPException(status_code=503, detail=str(e))

        raise HTTPException(status_code=500, detail=str(e))
    
    
@router.get("/factures")
def get_factures():
    try:
        return get_all_factures()
    except Exception as e:
        return {"error": str(e)}