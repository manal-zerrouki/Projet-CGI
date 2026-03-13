"""
=====================
Service de classification locale des factures via le modèle Random Forest.

Utilisé dans invoice.py AVANT l'appel Gemini Vision pour :
  1. Pré-classifier rapidement la facture
  2. Si confiance élevée → éviter l'appel visuel cachet (économie API)
  3. Signaler les anomalies (désaccord modèle vs règles métier)
"""

import os
import pickle
import logging
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger(__name__)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml", "models", "classifier.pkl")

_model_cache = None


def _load_model():
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    if not os.path.exists(MODEL_PATH):
        log.warning("Modèle classifier non trouvé — classification locale désactivée")
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            _model_cache = pickle.load(f)
        log.info("Modèle classifier chargé")
        return _model_cache
    except Exception as e:
        log.error(f"Erreur chargement modèle : {e}")
        return None


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and len(v.strip()) == 0:
        return True
    return False


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except Exception:
        return None


_DEVISES_ETRANGERES = {"eur", "usd", "gbp", "chf"}


def _est_marocaine(data: dict) -> int:
    """Même logique que validation_service._est_facture_marocaine()"""
    devise = str(data.get("devise") or "").upper().strip()
    return 0 if devise in _DEVISES_ETRANGERES else 1


def extraire_features(data: dict, nb_pages: int = 1, longueur_ocr: int = 0) -> list:
    ht   = _to_float(data.get("montant_ht"))
    tva  = _to_float(data.get("tva"))
    ttc  = _to_float(data.get("montant_ttc"))
    taux = _to_float(data.get("taux_tva"))
    retenue = _to_float(data.get("retenue_source"))
    net     = _to_float(data.get("net_a_payer"))

    ht_tva_ttc_coherent = 0
    if ht is not None and tva is not None and ttc is not None and ttc != 0:
        diff = abs((ht + tva) - ttc)
        ht_tva_ttc_coherent = 1 if diff <= abs(ttc) * 0.005 else 0

    taux_tva_coherent = 0
    if ht is not None and tva is not None and taux is not None and ht != 0:
        expected = ht * taux / 100.0
        diff = abs(expected - tva)
        tol  = max(abs(expected) * 0.01, 0.01)
        taux_tva_coherent = 1 if diff <= tol else 0

    net_coherent = 0
    if net is not None and ttc is not None:
        if retenue:
            net_coherent = 1 if abs((ttc - retenue) - net) <= ttc * 0.02 else 0
        else:
            net_coherent = 1 if abs(net - ttc) <= ttc * 0.02 else 0

    est_marocaine = _est_marocaine(data)
    ice_present   = 0 if _is_blank(data.get("ice")) else 1
    # a_ice = 1 si ICE présent OU si facture étrangère (ICE non applicable)
    a_ice = 1 if (ice_present or not est_marocaine) else 0

    return [
        # Champs obligatoires
        0 if _is_blank(data.get("prestataire"))    else 1,
        a_ice,                                              # conditionnel devise
        0 if _is_blank(data.get("date_facture"))   else 1,
        0 if _is_blank(data.get("numero_facture")) else 1,
        0 if _is_blank(data.get("montant_ht"))     else 1,
        0 if _is_blank(data.get("tva"))            else 1,
        0 if _is_blank(data.get("taux_tva"))       else 1,
        0 if _is_blank(data.get("montant_ttc"))    else 1,
        # a_cachet retiré — détection visuelle via Gemini Vision uniquement
        # Montants complémentaires
        0 if _is_blank(data.get("net_a_payer"))      else 1,
        0 if _is_blank(data.get("retenue_source"))   else 1,
        # Cohérence
        ht_tva_ttc_coherent,
        taux_tva_coherent,
        net_coherent,
        # Champs complémentaires
        0 if _is_blank(data.get("montant_ttc_lettres")) else 1,
        0 if _is_blank(data.get("numero_engagement"))   else 1,
        0 if _is_blank(data.get("date_echeance"))       else 1,
        # Contexte
        est_marocaine,
        ice_present,
        # Métadonnées
        nb_pages,
        longueur_ocr,
    ]


def classifier_facture(
    data: dict,
    nb_pages: int = 1,
    longueur_ocr: int = 0,
) -> Tuple[Optional[str], Optional[float]]:
    """
    Classifie une facture via le modèle local.

    Returns:
        (label_prédit, confiance) ou (None, None) si modèle non disponible
    """
    bundle = _load_model()
    if bundle is None:
        return None, None

    try:
        clf = bundle["model"]
        le  = bundle["label_encoder"]

        features = extraire_features(data, nb_pages, longueur_ocr)
        proba    = clf.predict_proba([features])[0]
        idx      = proba.argmax()
        label    = le.inverse_transform([idx])[0]
        confiance = float(proba[idx])

        return label, confiance

    except Exception as e:
        log.error(f"Erreur classification : {e}")
        return None, None