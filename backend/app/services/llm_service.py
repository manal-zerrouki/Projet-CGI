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

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

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
- pays_prestataire : pays du prestataire émetteur. Mettre "Maroc" si l'adresse est marocaine.
  Si le pays n'est pas explicitement mentionné, l'inférer depuis :
  • Indicatif téléphonique : +212 ou 05/06/07 → Maroc | +33 → France | +34 → Espagne | +1 → USA/Canada
  • Code postal : 5 chiffres commençant par 7x/8x/9x/1x/2x/3x/4x/5x/6x → Maroc (ex: 20000, 10000)
    vs 75xxx/69xxx/13xxx → France | 28xxx/08xxx → Espagne
  • IBAN : MA → Maroc | FR → France | ES → Espagne | etc.
  • Numéros d'identification : RC/IF/ICE/CNSS/Patente → Maroc | SIRET/SIREN/TVA FR → France | VAT ES → Espagne
  • Ville connue : Casablanca, Rabat, Marrakech, Fès… → Maroc | Paris, Lyon… → France
  Si aucun indice disponible → mettre null.
- numero_engagement : chercher "Réf. engagement", "N° engagement", "Bon de commande", "BC n°", "PO number".
- montant_ttc : chercher "TOTAL TTC", "NET À PAYER", "MONTANT DÛ" ou équivalent.
- montant_ttc_lettres : chercher "Arrêtée la présente facture...", "La somme de...", "Montant en lettres".
- retenue_source : chercher "RAS", "Retenue à la source", "Retenue de garantie", "RS". Mettre null si absent.
- net_a_payer : montant final après déduction de la retenue à la source (TTC - RAS).
  Si pas de retenue, net_a_payer = montant_ttc.
- a_cachet : mettre true si le texte contient des indices qu'un tampon/cachet a été APPOSÉ sur le document.
  Indices positifs : mots "cachet", "tampon", "sceau" apparaissant dans une zone de validation
  (bas de page, section signature/approbation) — PAS dans le tableau des désignations/produits.
  IMPORTANT : si "cachet" ou "tampon" apparaît uniquement dans la liste des articles facturés
  (ex: "Cachet automatique 4911", "Cachet rond"), c'est un nom de produit vendu, PAS un indice
  de tampon apposé — mettre false dans ce cas.
  Mettre false uniquement si AUCUN indice de cachet apposé n'est présent.
- a_signature : mettre true si le texte contient des indices de présence d'une signature manuscrite.
  Indices positifs : mots "signature", "signé", "lu et approuvé", "certifié", "visa", "paraphé",
  "bon pour accord", "docusign", "docusigned", "signed by", "electronic signature",
  "signé électroniquement". Mettre false uniquement si AUCUN indice de signature n'est présent.
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
  "a_cachet": null,
  "a_signature": null,
  "autres_montants": {},
  "devise": null,
  "pays_prestataire": null,
  "confidence": 0.0,
  "warnings": []
}
""".strip()


# =========================
# Prompt détection visuelle cachet (Gemini Vision)
# =========================
_CACHET_VISION_PROMPT = """
Analyze this region of an invoice image and detect TWO things independently:

A) COMPANY STAMP / SEAL (cachet):
   A real stamp is a mark PHYSICALLY APPLIED to the document — it is NOT part of the printed template.
   Valid stamps:
   - Circular or oval ink stamp (company name arranged in a ring/arc, typical Moroccan/French seal)
   - Rectangular ink stamp with company name and registration numbers, visually distinct from body text
   - Embossed or watermark-style seal
   - Partial or faint ink impression of any of the above

   NOT a stamp — do NOT set cachet_trouve=true for:
   - A preprinted company footer line at the very bottom margin (address, phone, email, ICE/RC/CNSS/Patente
     formatted as a text line or horizontal band — this is part of the invoice template, always present,
     NOT manually applied)
   - The company logo or branding at the top of the page
   - A plain text block that is clearly part of the invoice layout/template

   Key distinction: a real stamp looks physically applied — slightly tilted, ink bleed, imperfect edges,
   circular or oval border, color that stands out (blue, purple, red ink circle). A footer is perfectly
   aligned, same font as the rest of the document, spans the full width.

B) HANDWRITTEN SIGNATURE (signature):
   - Handwritten signature, initials, or paraph (ink strokes, cursive, irregular lines)
   - Electronic signature mark (DocuSign, Adobe Sign, etc.)
   - Any personal ink mark representing individual authorization
   - Ink strokes, crossing lines, or any handwritten mark INSIDE or ON TOP of a company stamp
     → these are very common in Moroccan/French invoices and count as a signature

IMPORTANT rules:
- A signature written ON TOP of or INSIDE a stamp → set BOTH cachet_trouve=true AND signature_trouvee=true
- If you detect a stamp with ANY ink marks, strokes, or lines inside it beyond just printed text → set signature_trouvee=true
- When in doubt about a stamp vs printed footer, prefer cachet_trouve=false
- Do NOT flag: pure date/reception stamp applied by the RECIPIENT ("ACCUSE DE RECEPTION", "REÇU LE")

Return ONLY valid JSON, no markdown, no backticks:
{
  "cachet_trouve": false,
  "signature_trouvee": false,
  "type": "company_stamp | handwritten_signature | both | partial_stamp | none",
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


def _detect_cachet_signature_gemini(pdf_path: str) -> tuple:
    """
    Détecte visuellement cachet ET signature séparément dans un PDF via Gemini Vision.

    Stratégie multi-zones : découpe chaque page en 6 zones. S'arrête dès que les deux
    sont trouvés avec certitude, sinon analyse toutes les zones.

    Returns:
        (a_cachet: Optional[bool], a_signature: Optional[bool], details: str)
          True  → élément détecté avec certitude
          False → analysé complètement, absent
          None  → erreur technique → traité comme incertain en validation
    """
    if not _FITZ_AVAILABLE or not _PIL_AVAILABLE:
        msg = "PyMuPDF ou Pillow non disponible pour la détection visuelle"
        return None, None, msg

    api_key = GOOGLE_API_KEY
    if not api_key:
        return None, None, "GOOGLE_API_KEY manquante"

    cachet_found    = False
    signature_found = False
    zones_analysed  = 0
    descriptions    = []

    try:
        client = genai.Client(api_key=api_key)
        doc    = _fitz.open(pdf_path)
        mat    = _fitz.Matrix(_CACHET_PDF_DPI / 72, _CACHET_PDF_DPI / 72)

        # Dernière page en premier : cachet/signature presque toujours sur la dernière page
        page_order = list(range(len(doc) - 1, -1, -1)) if len(doc) > 1 else [0]
        for page_num in page_order:
            page = doc[page_num]
            pix      = page.get_pixmap(matrix=mat, colorspace=_fitz.csRGB)
            full_img = _Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            zones    = _extract_cachet_zones(full_img)

            for zone_name, zone_img in zones.items():
                # Dès que les deux sont confirmés, inutile d'analyser plus
                if cachet_found and signature_found:
                    break
                try:
                    image_part = {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data"     : _img_to_b64(zone_img),
                        }
                    }
                    raw = None
                    for model_name in MODELS_TO_TRY:
                        try:
                            resp = client.models.generate_content(
                                model   =model_name,
                                contents=[_CACHET_VISION_PROMPT, image_part],
                            )
                            raw = (resp.text or "").strip()
                            break
                        except Exception as _model_err:
                            if "429" in str(_model_err) or "quota" in str(_model_err).lower():
                                continue  # essayer le modèle suivant
                            raise
                    if not raw:
                        continue
                    raw    = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
                    m      = re.search(r"\{.*\}", raw, re.DOTALL)
                    if not m:
                        continue
                    result = json.loads(m.group(0))
                    conf   = float(result.get("confidence", 0.0))
                    zones_analysed += 1

                    if conf >= _CACHET_CONFIDENCE_THRESHOLD:
                        if result.get("cachet_trouve", False) and not cachet_found:
                            cachet_found = True
                            descriptions.append(
                                f"[cachet p{page_num+1}/{zone_name}] "
                                f"{result.get('type','')} — {result.get('description','')}"
                            )
                        if result.get("signature_trouvee", False) and not signature_found:
                            signature_found = True
                            descriptions.append(
                                f"[signature p{page_num+1}/{zone_name}] "
                                f"{result.get('type','')} — {result.get('description','')}"
                            )

                except Exception as _zone_err:
                    descriptions.append(f"[err/{zone_name}] {_zone_err}")
                    continue

            if cachet_found and signature_found:
                break

        doc.close()

    except Exception as e:
        return None, None, f"Erreur détection visuelle : {e}"

    if zones_analysed == 0:
        err_info = " | ".join(descriptions) if descriptions else "raison inconnue"
        return None, None, f"Aucune zone n'a pu être analysée — {err_info}"

    details = " | ".join(d for d in descriptions if not d.startswith("[err/"))
    if not details:
        details = "Aucun cachet ni signature détecté"
    return cachet_found, signature_found, details


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

    # Normaliser numero_facture : supprimer les espaces parasites autour de / et -
    # ex: "006249 /2020" → "006249/2020"
    num = data.get("numero_facture")
    if isinstance(num, str):
        data["numero_facture"] = re.sub(r"\s*([/\-])\s*", r"\1", num.strip())

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
                      Si fourni, une détection visuelle via Gemini Vision
                      complète les champs a_cachet et a_signature non confirmés
                      par l'extraction texte.

    Returns:
        dict avec tous les champs de la facture + a_cachet / a_signature fiables
    """
    api_key = GOOGLE_API_KEY
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY manquante")

    if not ocr_text or len(ocr_text.strip()) < 30:
        return {
            "prestataire": None, "ice": None, "date_facture": None,
            "date_echeance": None, "numero_facture": None, "numero_engagement": None,
            "montant_ht": None, "tva": None, "taux_tva": None,
            "montant_ttc": None, "montant_ttc_lettres": None,
            "retenue_source": None, "net_a_payer": None,
            "a_cachet": None, "a_signature": None, "autres_montants": {},
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

                # ── Détection visuelle cachet + signature ─────────────────────
                # Lancée seulement si le LLM texte n'a pas confirmé les deux.
                # Économise les appels API quand le texte suffit.
                needs_vision = pdf_path and (
                    not validated.get("a_cachet") or not validated.get("a_signature")
                )
                if needs_vision:
                    vis_cachet, vis_sig, vis_desc = _detect_cachet_signature_gemini(pdf_path)
                    # Vision prime sur LLM si elle confirme explicitement (True ou False).
                    # None = erreur technique → on conserve le résultat LLM.
                    if vis_cachet is not None:
                        validated["a_cachet"] = vis_cachet
                    if vis_sig is not None:
                        validated["a_signature"] = vis_sig
                    validated["cachet_details"] = vis_desc

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