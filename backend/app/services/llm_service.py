import os
import json
import re
import time
import random
import base64
from io import BytesIO
from typing import Any, Dict, Optional

from google import genai
from dotenv import load_dotenv

load_dotenv()

# =========================
# Config modèles (primary + fallbacks)
# =========================
MODEL_PRIMARY    = os.getenv("MODEL_NAME",      "gemini-2.5-flash").strip()
MODEL_FALLBACK_1 = os.getenv("MODEL_FALLBACK_1", "").strip()
MODEL_FALLBACK_2 = os.getenv("MODEL_FALLBACK_2", "").strip()
MODELS_TO_TRY    = [MODEL_PRIMARY] + [m for m in [MODEL_FALLBACK_1, MODEL_FALLBACK_2] if m]

GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

# Limite OCR (réduit tokens => moins de 503/timeout)
MAX_OCR_CHARS = int(os.getenv("MAX_OCR_CHARS", "15000"))

# Si True: ajoute un warning si montant TTC en lettres n'est pas trouvé
REQUIRE_TTC_LETTERS = os.getenv("REQUIRE_TTC_LETTERS", "true").lower() in ("1", "true", "yes", "y")

# Seuil de confiance pour valider une détection visuelle de cachet
_CACHET_CONFIDENCE_THRESHOLD = 0.35
_CACHET_PDF_DPI               = 200

# Imports optionnels pour la détection visuelle du cachet
try:
    import fitz as _fitz
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False

try:
    from PIL import Image as _Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


# =========================
# Prompt extraction (inchangé)
# =========================
PROMPT = """
RÔLE
Tu es un système d'extraction d'informations à partir de factures (texte OCR issu de PDF scannés).

OBJECTIF
À partir du TEXTE fourni, extrais les informations et retourne UNIQUEMENT un JSON valide.
Aucun texte, aucune explication, aucun markdown.

RÈGLES GÉNÉRALES
- Si une information est introuvable ou illisible : mets null.
- N'invente jamais une valeur.
- Toutes les dates doivent être au format DD-MM-YYYY.
- Les montants doivent être des nombres (ex: 1250.50) sans symbole monétaire.
- La devise doit être : "EUR", "MAD", "USD" ou null.
- taux_tva doit être un nombre représentant un pourcentage (ex: 20 pour 20%).
- montant_ttc_lettres doit contenir le texte exact du TTC en toutes lettres (si présent). Ne pas reformuler.

IDENTIFICATION DU PRESTATAIRE (RÈGLE CRITIQUE)
- Le prestataire est l'entité qui ÉMET la facture : son nom/raison sociale apparaît EN HAUT du document,
  souvent avec son ICE, son adresse, son logo.
- Ne pas confondre avec : le client (destinataire), les partenaires, les sous-traitants,
  les slogans commerciaux, ou d'autres entités mentionnées dans le corps de la facture.
- Si plusieurs entités sont présentes, prendre UNIQUEMENT celle associée à l'ICE émetteur.
- FORMULATION INDIRECTE : si le nom du prestataire apparaît après "Affaires suivies par :",
  "Suivi par :", "Référent :", "Cabinet :", "Société :", "Émetteur :" → c'est le nom du prestataire.
- LOGO ILLISIBLE / STYLISÉ : si le logo en haut est une image ou un texte stylisé difficile à lire,
  chercher le nom dans les champs RC:, IF:, ICE: de l'en-tête — ils appartiennent à l'émetteur.
- CACHET DE RÉCEPTION : un cachet apposé par le destinataire ("REÇU LE", "ACCUSÉ DE RÉCEPTION",
  cachet CGI) N'EST PAS le prestataire — c'est le client qui a tamponné le document reçu.
- CGI, Groupe CGI, CGI Maroc = TOUJOURS le client/destinataire dans ce système, JAMAIS le prestataire.
  Si "CGI" ressort comme prestataire, c'est une erreur — chercher le vrai émetteur ailleurs.
- L'ICE 001592148000076 appartient à CGI (le client). S'il apparaît, l'ignorer pour le prestataire.

RÈGLES MÉTIER
- numero_facture : chercher "Facture n°", "Invoice #", "N° facture". Ne PAS utiliser "Référence client".
- date_facture : date d'ÉMISSION de la facture uniquement. Ne pas prendre la date de commande/livraison.
- date_echeance : chercher "Date d'échéance", "Échéance", "Due date", "Date limite de paiement".
  S'il est absent du document, mettre null. NE PAS calculer cette date.
- ICE : Identifiant Commun de l'Entreprise (Maroc). Extraire uniquement si clairement indiqué comme "ICE".
- numero_engagement : chercher "Réf. engagement", "N° engagement", "Bon de commande", "BC n°", "PO number".
- montant_ttc : chercher "TOTAL TTC", "NET À PAYER", "MONTANT DÛ" ou équivalent.
- montant_ttc_lettres : chercher "Arrêtée la présente facture...", "La somme de...", "Montant en lettres".
- retenue_source : chercher "RAS", "Retenue à la source", "Retenue de garantie", "RS". Mettre null si absent.
- net_a_payer : montant final après déduction de la retenue à la source (TTC - RAS).
  Si pas de retenue, net_a_payer = montant_ttc.
- cachet_signature : mettre true si le texte contient des indices de présence d'un cachet ou d'une signature.
  Indices positifs : mots "cachet", "signature", "lu et approuvé", "certifié", "signé", "visa",
  "bon pour accord", "docusign", "docusigned", "signed by", "electronic signature",
  "signé électroniquement", "paraphé", ou présence d'un bloc circulaire (RC, IF, ICE, CNSS groupés
  en bas de page hors section coordonnées principale — typique des cachets d'entreprise marocains),
  ou présence d'un pied de page entreprise avec logo + adresse en bas du document.
  Mettre false uniquement si AUCUN indice n'est présent.
- autres_montants : dictionnaire clé/valeur pour tout montant présent dans la facture qui ne rentre pas
  dans les champs ci-dessus (ex: "timbre_fiscal": 20.0, "remise": 150.0, "frais_port": 50.0).
  Mettre {} si aucun montant supplémentaire.

RÈGLES DE COHÉRENCE (à évaluer — ne pas bloquer l'extraction)
- montant_ttc ≈ montant_ht + tva (tolérance 0.5%)
- tva ≈ montant_ht × taux_tva / 100 (tolérance 1%)
- Si incohérence détectée sur HT/TVA/TTC, ajouter un warning dans le tableau warnings.
- Ne PAS ajouter de warning sur net_a_payer : ce calcul est géré par le moteur de validation.

SCHÉMA JSON (respect strict — tous les champs doivent être présents)
{
  "prestataire": null,
  "ice": null,
  "date_facture": null,
  "date_echeance": null,
  "numero_facture": null,
  "numero_engagement": null,
  "montant_ht": null,
  "tva": null,
  "taux_tva": null,
  "montant_ttc": null,
  "montant_ttc_lettres": null,
  "retenue_source": null,
  "net_a_payer": null,
  "cachet_signature": null,
  "autres_montants": {},
  "devise": null,
  "confidence": 0.0,
  "warnings": []
}
""".strip()


# =========================
# Prompt détection visuelle cachet (Gemini Vision)
# =========================
_CACHET_VISION_PROMPT = """
Analyze this region of an invoice image.

Detect any of the following:
1. Company stamp or seal — circular, oval, rectangular, even if partially overlapping text or faint
2. Circular text arranged in a ring/arc around a center (typical Moroccan/French company seal)
3. Handwritten signature, initials, or paraph
4. Company logo block at the BOTTOM of the page with name and address — standard authorization
   footer on French and Moroccan invoices, valid official mark even without a physical stamp border
5. Any ink mark, colored overlay, or graphic element suggesting authorization or validation
6. Embossed or watermark-style seals

IMPORTANT — Be INCLUSIVE, not restrictive:
- A circular arrangement of text (company name, city, registration number) IS a company seal
  → set cachet_trouve = true, type = company_stamp
- A company logo/name+address block at the BOTTOM is a valid authorization mark
  → set cachet_trouve = true, type = logo_stamp
- When in doubt between "stamp present" and "no stamp", prefer cachet_trouve = true with lower confidence
- Do NOT require the stamp to be perfectly clear or ink-colored

Do NOT flag ONLY these specific cases:
- The header branding logo at the very TOP of the invoice (top 20% of page)
- A pure date/reception stamp applied by the RECIPIENT (e.g. "received on...", "ACCUSE DE RECEPTION")

Return ONLY valid JSON, no markdown, no backticks:
{
  "cachet_trouve": false,
  "type": "company_stamp | handwritten_signature | partial_stamp | logo_stamp | none",
  "description": "precise description of what you observed",
  "confidence": 0.0
}
""".strip()


# =========================
# Helpers JSON parsing
# =========================
def _extract_json_loose(text: str) -> Dict[str, Any]:
    """
    Accepte:
    - JSON pur
    - JSON entouré de texte
    - JSON dans ```json ... ```
    """
    if not text:
        raise ValueError("Réponse vide du modèle")

    t = text.strip()

    # 1) JSON direct
    try:
        return json.loads(t)
    except Exception:
        pass

    # 2) Dans un bloc ```json
    m = re.search(r"```json\s*(\{.*?\})\s*```", t, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return json.loads(m.group(1))

    # 3) Premier bloc {...}
    m = re.search(r"(\{.*\})", t, flags=re.DOTALL)
    if not m:
        raise ValueError(f"Réponse non-JSON (début): {t[:250]}")
    return json.loads(m.group(1))


def _shrink_ocr_text(text: str, max_chars: int) -> str:
    """
    Réduit la taille du texte envoyé au LLM.
    Stratégie: garder début + fin (en-tête + totaux sont souvent là).
    """
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t

    head_len = int(max_chars * 0.6)
    tail_len = max_chars - head_len
    head = t[:head_len]
    tail = t[-tail_len:]
    return head + "\n\n... [TRONQUÉ POUR LIMITER LES TOKENS] ...\n\n" + tail


def _is_transient_error(msg_lower: str) -> bool:
    return (
        "429" in msg_lower or "rate" in msg_lower or "quota" in msg_lower
        or "503" in msg_lower or "unavailable" in msg_lower or "high demand" in msg_lower
        or "timeout" in msg_lower or "temporar" in msg_lower or "try again later" in msg_lower
    )


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        s = s.replace(" ", "").replace("\u00a0", "")
        s = s.replace(",", ".")
        s = re.sub(r"[^0-9.\-]", "", s)
        try:
            return float(s)
        except Exception:
            return None
    return None


# =========================
# Détection visuelle cachet via Gemini Vision
# =========================
def _img_to_b64(img: "_Image.Image") -> str:
    """Encode une image PIL en base64 PNG."""
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def _extract_cachet_zones(img: "_Image.Image") -> dict:
    """
    Découpe la page en 6 zones couvrant tous les emplacements possibles d'un cachet.
    Ordre = priorité de traitement (zones les plus probables en premier).
    """
    w, h = img.size
    return {
        "bottom_right"      : img.crop((int(w * 0.55), int(h * 0.60), w,             h)),
        "bottom_left"       : img.crop((0,              int(h * 0.60), int(w * 0.45), h)),
        "bottom_right_zoom" : img.crop((int(w * 0.60), int(h * 0.70), w,             h)),
        "bottom_center"     : img.crop((int(w * 0.20), int(h * 0.65), int(w * 0.80), h)),
        "bottom_full"       : img.crop((0,              int(h * 0.55), w,             h)),
        "full_page"         : img,
    }


def _detect_cachet_gemini(pdf_path: str) -> tuple:
    """
    Détecte visuellement un cachet/signature dans un PDF via Gemini Vision.

    Stratégie multi-zones : découpe chaque page en 6 zones et les envoie
    une par une à Gemini. S'arrête dès qu'une détection fiable est trouvée
    (confidence >= _CACHET_CONFIDENCE_THRESHOLD).

    Args:
        pdf_path : chemin vers le fichier PDF

    Returns:
        (found: Optional[bool], details: str)
          True  → cachet détecté avec certitude
          False → toutes les zones analysées, aucun cachet trouvé
          None  → erreur technique (bibliothèque manquante, API KO, etc.)
                  → l'appelant doit traiter ça comme "incertain", pas "absent"
    """
    if not _FITZ_AVAILABLE or not _PIL_AVAILABLE:
        return None, "PyMuPDF ou Pillow non disponible pour la détection visuelle"

    api_key = GOOGLE_API_KEY
    if not api_key:
        print("Warning: GOOGLE_API_KEY manquante → mode dégradé (OCR + règles locales)")
        return None, "Gemini API manquante (OCR OK)"

    zones_analysed = 0

    try:
        client = genai.Client(api_key=api_key)
        doc    = _fitz.open(pdf_path)
        mat    = _fitz.Matrix(_CACHET_PDF_DPI / 72, _CACHET_PDF_DPI / 72)

        for page_num, page in enumerate(doc):
            pix      = page.get_pixmap(matrix=mat, colorspace=_fitz.csRGB)
            full_img = _Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            zones    = _extract_cachet_zones(full_img)

            for zone_name, zone_img in zones.items():
                try:
                    image_part = {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data"     : _img_to_b64(zone_img),
                        }
                    }
                    resp   = client.models.generate_content(
                        model   =MODEL_PRIMARY,
                        contents=[_CACHET_VISION_PROMPT, image_part],
                    )
                    raw    = (resp.text or "").strip()
                    raw    = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
                    m      = re.search(r"\{.*\}", raw, re.DOTALL)
                    if not m:
                        continue
                    result = json.loads(m.group(0))
                    conf   = float(result.get("confidence", 0.0))
                    found  = bool(result.get("cachet_trouve", False))
                    zones_analysed += 1

                    if found and conf >= _CACHET_CONFIDENCE_THRESHOLD:
                        desc = (
                            f"[page {page_num + 1}/{zone_name}] "
                            f"{result.get('type', '')} — {result.get('description', '')}"
                        )
                        doc.close()
                        return True, desc

                except Exception:
                    # Zone ignorée silencieusement, on continue les autres zones
                    continue

        doc.close()

    except Exception as e:
        # Erreur technique globale (ouverture PDF, API Gemini KO…)
        # → incertain, pas absent : on ne rejette pas sur une erreur technique
        return None, f"Erreur détection cachet : {e}"

    # Toutes les zones ont été analysées sans résultat positif
    if zones_analysed == 0:
        # Aucune zone n'a pu être analysée (toutes en erreur) → incertain
        return None, "Aucune zone n'a pu être analysée (erreurs API)"

    return False, "Aucun cachet ou signature détecté après analyse complète"


# =========================
# Validation numérique post-extraction
# =========================
def _post_validate(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-traitement après extraction LLM :
      - Normalise les types numériques (str → float)
      - Warning si montant TTC en lettres manquant
      - S'assure que autres_montants est un dict

    Les vérifications de cohérence (HT+TVA=TTC, taux TVA, net_a_payer)
    sont entièrement déléguées à validation_service pour éviter les doublons.
    validation_service les traite de façon bloquante (motifs_rejet), ce qui
    est plus approprié que de simples warnings ici.
    """
    warnings = data.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []

    # Normaliser les types numériques (le LLM peut retourner des strings)
    ht      = _to_float(data.get("montant_ht"))
    tva     = _to_float(data.get("tva"))
    ttc     = _to_float(data.get("montant_ttc"))
    taux    = _to_float(data.get("taux_tva"))
    retenue = _to_float(data.get("retenue_source"))
    net     = _to_float(data.get("net_a_payer"))

    for field, val in [
        ("montant_ht", ht), ("tva", tva), ("montant_ttc", ttc),
        ("taux_tva", taux), ("retenue_source", retenue), ("net_a_payer", net),
    ]:
        if val is not None:
            data[field] = val

    # Warning TTC en lettres manquant — non géré par validation_service
    if REQUIRE_TTC_LETTERS:
        ttc_letters = data.get("montant_ttc_lettres")
        if ttc_letters is None or (isinstance(ttc_letters, str) and len(ttc_letters.strip()) < 3):
            warnings.append("Montant TTC en lettres introuvable/illisible (requis pour contrôle)")

    data["warnings"] = warnings

    # S'assurer que autres_montants est bien un dict
    if not isinstance(data.get("autres_montants"), dict):
        data["autres_montants"] = {}

    # Filet de sécurité : CGI = toujours client, jamais prestataire
    p = data.get("prestataire")
    if isinstance(p, str) and "cgi" in p.lower():
        data["prestataire"] = None

    # Filet de sécurité : ICE de CGI → forcer null
    if data.get("ice") == "001592148000076":
        data["ice"] = None

    return data


# =========================
# Main extraction
# =========================
def extract_invoice_json_from_text(
    ocr_text: str,
    *,
    max_retries: int = 3,
    pdf_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extrait les données structurées d'une facture depuis le texte OCR.

    Args:
        ocr_text    : texte brut extrait du PDF par ocr_service
        max_retries : nombre de tentatives en cas d'erreur transitoire
        pdf_path    : chemin vers le PDF source (optionnel).
                      Si fourni ET cachet_signature est False/None après
                      l'extraction texte, une détection visuelle via
                      Gemini Vision est lancée automatiquement.

    Returns:
        dict avec tous les champs de la facture + cachet_signature fiable
    """
    api_key = GOOGLE_API_KEY
    if not api_key:
        print("Warning: Gemini API manquante → extraction OCR basique")
        return {
            "prestataire": None, "ice": None, "date_facture": None,
            "date_echeance": None, "numero_facture": None, "numero_engagement": None,
            "montant_ht": None, "tva": None, "taux_tva": None,
            "montant_ttc": None, "montant_ttc_lettres": None,
            "retenue_source": None, "net_a_payer": None,
            "cachet_signature": None, "autres_montants": {},
            "devise": None, "confidence": 0.0,
            "warnings": ["Mode dégradé sans Gemini API (ajoutez GOOGLE_API_KEY)"],
        }

    if not ocr_text or len(ocr_text.strip()) < 30:
        return {
            "prestataire": None, "ice": None, "date_facture": None,
            "date_echeance": None, "numero_facture": None, "numero_engagement": None,
            "montant_ht": None, "tva": None, "taux_tva": None,
            "montant_ttc": None, "montant_ttc_lettres": None,
            "retenue_source": None, "net_a_payer": None,
            "cachet_signature": None, "autres_montants": {},
            "devise": None, "confidence": 0.0,
            "warnings": ["Texte OCR vide ou insuffisant"],
        }

    client   = genai.Client(api_key=api_key)
    ocr_text = _shrink_ocr_text(ocr_text, MAX_OCR_CHARS)
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        for model_name in MODELS_TO_TRY:
            try:
                resp = client.models.generate_content(
                    model   =model_name,
                    contents=[
                        PROMPT,
                        "\n\n===== TEXTE OCR FACTURE =====\n\n",
                        ocr_text,
                    ],
                )
                parsed = _extract_json_loose((resp.text or "").strip())

                # Score de complétude calculé sur l'extraction BRUTE de Gemini,
                # avant _post_validate (qui peut nullifier ICE/prestataire pour
                # des raisons métier non liées à la qualité d'extraction).
                _CORE_FIELDS = [
                    "prestataire", "date_facture", "numero_facture",
                    "montant_ht", "tva", "montant_ttc", "ice",
                    "numero_engagement", "devise",
                ]
                _filled = sum(
                    1 for k in _CORE_FIELDS
                    if parsed.get(k) not in (None, "", 0)
                )
                parsed["confidence"] = round(_filled / len(_CORE_FIELDS) * 100)

                validated = _post_validate(parsed)

                # ── Détection visuelle cachet ─────────────────────────────────
                # Déclenchée si le LLM n'a pas confirmé de cachet (False ou None).
                # Résultats possibles de _detect_cachet_gemini :
                #   True  → cachet trouvé visuellement
                #   False → analysé complètement, rien trouvé (cachet absent)
                #   None  → erreur technique → traité comme incertain en validation
                #           (accepté_avec_réserve, pas rejeté)
                if pdf_path and not validated.get("cachet_signature"):
                    cachet_found, cachet_desc = _detect_cachet_gemini(pdf_path)
                    validated["cachet_signature"] = cachet_found
                    validated["cachet_details"]   = cachet_desc

                return validated

            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if _is_transient_error(msg):
                    continue
                raise

        # Backoff exponentiel : 3s → 5s → 9s (max ~10s) avant chaque retry
        sleep_s = min(2 ** attempt, 10) + random.uniform(0.5, 1.5)
        time.sleep(sleep_s)

    raise RuntimeError(
        f"503 UNAVAILABLE / transient error: échec LLM après {max_retries} tentatives: {last_err}"
    )