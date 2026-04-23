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
import time
from datetime import datetime

from app.services.db_service import get_db_connection
from app.services.ocr_service import extract_text_from_pdf, format_preview
from app.services.llm_service import extract_invoice_json_from_text
from app.services.validation_service import valider_facture
from app.services.db_service import get_all_factures

# Référence ICE de CGI
ICE_CGI_REFERENCE = "001592148000076"

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


def ocr_indicates_cgi_name(ocr_text: str) -> bool:
    """Vérifie si le texte OCR contient 'CGI' ou 'c g i' (insensible à la casse)."""
    if not ocr_text:
        return False
    text_lower = ocr_text.lower()
    if "cgi" in text_lower:
        return True
    if "c g i" in text_lower:
        return True
    if "c.g.i" in text_lower:
        return True
    return False


@router.post("/analyze")
async def analyze_invoice(file: UploadFile = File(...)):
    start_time = time.time()  # KPI : début du chrono

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un PDF")

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # OCR
        ocr_text = extract_text_from_pdf(file_path)
        cgi_nom_present = ocr_indicates_cgi_name(ocr_text)
        ocr_success = bool(ocr_text and len(ocr_text.strip()) >= 20)

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
                "ice_cgi_reference": ICE_CGI_REFERENCE,
                "cgi_nom_present_ocr": False,
                "retenue_garantie": None
            }

        # LLM extraction
        data = extract_invoice_json_from_text(ocr_text, pdf_path=file_path)

        # Validation métier
        result = valider_facture(data)

        # Vérification CGI : si le nom CGI est présent mais l'ICE extrait est différent de la référence
        if cgi_nom_present:
            ice_extrait = data.get("ice")
            if ice_extrait != ICE_CGI_REFERENCE:
                warning_msg = f"L'ICE extrait ({ice_extrait}) ne correspond pas à la référence CGI ({ICE_CGI_REFERENCE}) - facture suspecte"
                if warning_msg not in result.warnings:
                    result.warnings.append(warning_msg)

        # Retenue de garantie (10% du TTC)
        retenue_garantie = None
        if data.get("montant_ttc") is not None:
            try:
                retenue_garantie = round(float(data["montant_ttc"]) * 0.10, 2)
            except:
                pass

        statut_validation = result.statut
        cachet_detecte = data.get("cachet_signature")
        end_time = time.time()
        duration = end_time - start_time

        # Insertion dans la base de données
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            date_facture = safe_date(data.get("date_facture"))

            cursor.execute("""
                INSERT INTO factures_cgi (
                    numero_facture, prestataire, ice, date_facture, numero_engagement,
                    montant_ht, tva, montant_ttc, devise, exception,
                    date_analyse, duree_secondes, ocr_succes, statut_validation, cachet_detecte
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    prestataire = VALUES(prestataire),
                    ice = VALUES(ice),
                    date_facture = VALUES(date_facture),
                    numero_engagement = VALUES(numero_engagement),
                    montant_ht = VALUES(montant_ht),
                    tva = VALUES(tva),
                    montant_ttc = VALUES(montant_ttc),
                    devise = VALUES(devise),
                    exception = VALUES(exception),
                    date_analyse = VALUES(date_analyse),
                    duree_secondes = VALUES(duree_secondes),
                    ocr_succes = VALUES(ocr_succes),
                    statut_validation = VALUES(statut_validation),
                    cachet_detecte = VALUES(cachet_detecte)
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
                str(result.exceptions),
                duration,
                ocr_success,
                statut_validation,
                cachet_detecte
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
            "ice_cgi_reference": ICE_CGI_REFERENCE,
            "cgi_nom_present_ocr": cgi_nom_present,
            "retenue_garantie": retenue_garantie
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