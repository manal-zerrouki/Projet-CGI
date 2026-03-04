import os
import json
import re
import time
import random
from typing import Any, Dict, Optional

from google import genai
from dotenv import load_dotenv

load_dotenv()

# =========================
# Config modèles (primary + fallbacks)
# =========================
MODEL_PRIMARY = os.getenv("MODEL_NAME", "gemini-2.5-flash").strip()
MODEL_FALLBACK_1 = os.getenv("MODEL_FALLBACK_1", "").strip()
MODEL_FALLBACK_2 = os.getenv("MODEL_FALLBACK_2", "").strip()
MODELS_TO_TRY = [MODEL_PRIMARY] + [m for m in [MODEL_FALLBACK_1, MODEL_FALLBACK_2] if m]

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Limite OCR (réduit tokens => moins de 503/timeout)
MAX_OCR_CHARS = int(os.getenv("MAX_OCR_CHARS", "15000"))

# Si True: ajoute un warning si montant TTC en lettres n'est pas trouvé
REQUIRE_TTC_LETTERS = os.getenv("REQUIRE_TTC_LETTERS", "true").lower() in ("1", "true", "yes", "y")

# =========================
# Prompt
# =========================
PROMPT = """
RÔLE
Tu es un système d’extraction d’informations à partir de factures (texte OCR issu de PDF scannés).

OBJECTIF
À partir du TEXTE fourni, extrais les informations et retourne UNIQUEMENT un JSON valide.
Aucun texte, aucune explication, aucun markdown.

RÈGLES GÉNÉRALES
- Si une information est introuvable ou illisible : mets null.
- N’invente jamais une valeur.
- date_facture doit être au format DD-MM-YYYY.
- Les montants doivent être des nombres (ex: 1250.50) sans symbole monétaire.
- La devise doit être : "EUR", "MAD", "USD" ou null.
- taux_tva doit être un nombre représentant un pourcentage (ex: 20 pour 20%).
- montant_ttc_lettres doit contenir le texte exact du TTC en toutes lettres (si présent). Ne pas reformuler.

RÈGLES MÉTIER IMPORTANTES
- numero_facture correspond à : "Facture n°", "Invoice #", "N° facture". Ne pas utiliser "Référence client".
- date_facture = date d’émission de la facture. Ne pas prendre la date de commande/livraison.
- ICE = Identifiant Commun de l’Entreprise. Extraire uniquement si clairement indiqué.
- montant_ttc correspond à "TOTAL TTC", "NET À PAYER", "MONTANT DÛ" ou équivalent.
- montant_ttc_lettres correspond à la ligne contenant le montant en toutes lettres ("Arrêtée la présente facture...", "La somme de...", "Montant en lettres", etc.).

RÈGLES DE COHÉRENCE
- montant_ttc ≈ montant_ht + tva (tolérance 0.5%)
- Si taux_tva est présent, il doit être cohérent avec montant_ht et tva : tva ≈ montant_ht * taux_tva/100 (tolérance 1%)
- Si montant_ttc_lettres est présent, il doit être cohérent avec le montant TTC (si incohérence évidente => warning).
- Si incohérence détectée, ajouter un warning explicite.

SCHÉMA JSON (respect strict)
{
  "prestataire": null,
  "ice": null,
  "date_facture": null,
  "numero_facture": null,
  "numero_engagement": null,
  "montant_ht": null,
  "tva": null,
  "taux_tva": null,
  "montant_ttc": null,
  "montant_ttc_lettres": null,
  "devise": null,
  "confidence": 0.0,
  "warnings": []
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
    """
    Erreurs transitoires à retry: 429, 503, unavailable, timeouts...
    """
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
    # si string "1 234,56" ou "1234.56"
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


def _post_validate(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validation backend (sérieuse) :
    - HT + TVA ≈ TTC (0.5%)
    - taux_tva cohérent si possible (1%)
    - warning si TTC lettres manquant (option)
    """
    warnings = data.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []

    ht = _to_float(data.get("montant_ht"))
    tva = _to_float(data.get("tva"))
    ttc = _to_float(data.get("montant_ttc"))
    taux = _to_float(data.get("taux_tva"))

    # 1) Cohérence HT+TVA ≈ TTC
    try:
        if ht is not None and tva is not None and ttc is not None and ttc != 0:
            diff = abs((ht + tva) - ttc)
            if diff > abs(ttc) * 0.005:
                warnings.append("Incohérence numérique: HT + TVA ≠ TTC (tolérance 0.5%)")
    except Exception:
        pass

    # 2) Cohérence taux TVA (si HT et TVA présents)
    try:
        if ht is not None and tva is not None and ht != 0 and taux is not None:
            expected_tva = ht * (taux / 100.0)
            diff = abs(expected_tva - tva)
            # tolérance 1% du montant TVA attendu (minimum 0.01)
            tol = max(abs(expected_tva) * 0.01, 0.01)
            if diff > tol:
                warnings.append("Incohérence: taux_tva ne correspond pas à TVA/HT (tolérance 1%)")
    except Exception:
        pass

    # 3) Montant TTC en lettres
    ttc_letters = data.get("montant_ttc_lettres")
    if REQUIRE_TTC_LETTERS:
        if ttc_letters is None or (isinstance(ttc_letters, str) and len(ttc_letters.strip()) < 3):
            warnings.append("Montant TTC en lettres introuvable/illisible (requis pour contrôle)")

    data["warnings"] = warnings

    # Normaliser types numériques (optionnel)
    # On force à float si possible (sinon on laisse tel quel)
    if ht is not None:
        data["montant_ht"] = ht
    if tva is not None:
        data["tva"] = tva
    if ttc is not None:
        data["montant_ttc"] = ttc
    if taux is not None:
        data["taux_tva"] = taux

    return data


# =========================
# Main extraction
# =========================
def extract_invoice_json_from_text(ocr_text: str, *, max_retries: int = 3) -> Dict[str, Any]:
    api_key = GOOGLE_API_KEY
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY manquante")

    if not ocr_text or len(ocr_text.strip()) < 30:
        return {
            "prestataire": None,
            "ice": None,
            "date_facture": None,
            "numero_facture": None,
            "numero_engagement": None,
            "montant_ht": None,
            "montant_tva": None,
            "taux_tva": None,
            "montant_ttc": None,
            "montant_ttc_lettres": None,
            "devise": None,
            "confidence": 0.0,
            "warnings": ["texte OCR vide ou insuffisant"],
        }

    client = genai.Client(api_key=api_key)

    # Réduction tokens
    ocr_text = _shrink_ocr_text(ocr_text, MAX_OCR_CHARS)

    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        for model_name in MODELS_TO_TRY:
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=[
                        PROMPT,
                        "\n\n===== TEXTE OCR FACTURE =====\n\n",
                        ocr_text,
                    ],
                )
                parsed = _extract_json_loose((resp.text or "").strip())
                return _post_validate(parsed)

            except Exception as e:
                last_err = e
                msg = str(e).lower()

                # Transient -> try next model or next attempt
                if _is_transient_error(msg):
                    continue

                # Non-transient -> raise
                raise

        # tous les modèles ont échoué à cet attempt -> backoff + jitter
        sleep_s = (2 ** (attempt - 1)) + random.uniform(0.2, 0.8)
        time.sleep(sleep_s)

    raise RuntimeError(
        f"503 UNAVAILABLE / transient error: échec LLM après {max_retries} tentatives: {last_err}"
    )