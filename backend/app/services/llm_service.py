import os
import json
import re
import time
from typing import Any, Dict, Optional
from google import genai

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-flash-latest")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

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
- Si plusieurs montants existent, montant_ttc correspond au "TOTAL TTC", "NET À PAYER", "MONTANT DÛ" ou équivalent.
- Si HT/TVA/TTC sont ambigus, remplis uniquement ce qui est certain et ajoute un warning.

RÈGLES MÉTIER IMPORTANTES
- numero_facture correspond à : "Facture n°", "Invoice #", "N° facture". Ne pas utiliser "Référence client".
- date_facture = date d’émission de la facture. Ne pas prendre la date de commande/livraison.
- ICE = Identifiant Commun de l’Entreprise. Extraire uniquement si clairement indiqué.

RÈGLES DE COHÉRENCE MATHÉMATIQUE
- montant_ttc ≈ montant_ht + tva
- Si incohérence (tolérance 0.5%), ajouter "incohérence montants HT/TVA/TTC".
- Ne pas recalculer ni inventer des montants manquants.

SCHÉMA JSON (respect strict)
{
  "prestataire": null,
  "ice": null,
  "date_facture": null,
  "numero_facture": null,
  "numero_engagement": null,
  "montant_ht": null,
  "tva": null,
  "montant_ttc": null,
  "devise": null,
  "confidence": 0.0,
  "warnings": []
}
""".strip()


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
            "tva": None,
            "montant_ttc": None,
            "devise": None,
            "confidence": 0.0,
            "warnings": ["texte OCR vide ou insuffisant"]
        }

    client = genai.Client(api_key=api_key)

    # Petite astuce: réduire un peu le bruit
    ocr_text = ocr_text.strip()

    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=[
                    PROMPT,
                    "\n\n===== TEXTE OCR FACTURE =====\n\n",
                    ocr_text
                ],
            )
            return _extract_json_loose((resp.text or "").strip())

        except Exception as e:
            last_err = e
            msg = str(e).lower()

            # Retry simple si rate limit / 429
            if "429" in msg or "rate" in msg or "quota" in msg:
                # backoff progressif: 1s, 2s, 4s...
                time.sleep(2 ** (attempt - 1))
                continue

            # Sinon: pas un problème de quota → on remonte
            raise

    # Après retries
    raise RuntimeError(f"Échec LLM après {max_retries} tentatives: {last_err}")