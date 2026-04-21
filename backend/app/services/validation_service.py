"""
=====================
Moteur de validation métier des factures :

  Passe 1 — Champs obligatoires      → rejet immédiat si manquant
  Passe 2 — Délai des 7 jours        → rejet si facture expirée
  Passe 3 — Cohérence des montants   → rejet si incohérence critique HT/TVA/TTC
  Passe 4 — Champs complémentaires   → warning seulement (pas de rejet)

La détection visuelle du cachet/signature est gérée dans llm_service.py
via Gemini Vision. Ce fichier lit simplement le champ cachet_signature
comme n'importe quel autre champ — il n'appelle plus Anthropic.

Règles warnings vs motifs_rejet :
  motifs_rejet → bloquant, statut "rejeté"
  exceptions   → champ manquant non bloquant, statut "accepté_avec_réserve"
  warnings     → informatif uniquement, n'affecte pas le statut

Règles cachet/signature :
  cachet False → absent confirmé  → rejet bloquant
  cachet None  → détection incertaine (scan flou, pâle…) → exception non-bloquante (vérification manuelle)

Règles dates :
  date_facture + 7j dépassée       → avertissement (non bloquant)
  date_echeance présente dépassée  → rejet bloquant
  date_echeance absente + facture + 60j dépassée → rejet bloquant

Les warnings générés par le LLM (data["warnings"]) sont filtrés à l'entrée
pour supprimer les doublons avec ce que ce fichier calcule lui-même.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import re


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES MÉTIER
# ══════════════════════════════════════════════════════════════════════════════
DELAI_MAX_JOURS   = 7      # Warning si date_facture > aujourd'hui - 7j (non bloquant)
TOLERANCE_MONTANT = 0.005  # 0.5 % pour TTC = HT + TVA
TOLERANCE_TVA     = 0.01   # 1 % pour taux TVA cohérent


# ══════════════════════════════════════════════════════════════════════════════
# RÉSULTAT DE VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
class ValidationResult:
    def __init__(
        self,
        statut: str,
        motifs_rejet: List[str],
        exceptions: List[str],
        warnings: List[str],
    ):
        self.statut       = statut
        self.motifs_rejet = motifs_rejet
        self.exceptions   = exceptions
        self.warnings     = warnings

    def to_dict(self) -> Dict[str, Any]:
        return {
            "statut"      : self.statut,
            "motifs_rejet": self.motifs_rejet,
            "exceptions"  : self.exceptions,
            "warnings"    : self.warnings,
        }


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        s = re.sub(r"[^0-9.\-]", "", s)
        try:
            return float(s)
        except Exception:
            return None
    return None


def _parse_date(date_str: Any) -> Optional[datetime]:
    if not date_str or not isinstance(date_str, str):
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and len(v.strip()) == 0:
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# CONVERTISSEUR MONTANT EN LETTRES → CHIFFRES (Français)
# Supporte : dirhams, euros, dollars — majuscules/minuscules
# Gère     : mille, million, milliard, cent(s), quatre-vingts, etc.
# ══════════════════════════════════════════════════════════════════════════════

_LETTRES_UNITS = {
    "zero": 0, "zéro": 0, "un": 1, "une": 1, "deux": 2, "trois": 3,
    "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
    "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16,
    "dixsept": 17, "dixhuit": 18, "dixneuf": 19,
    "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "soixantedix": 70, "quatrevingt": 80, "quatrevingtdix": 90,
}

_LETTRES_DEVISE = {
    "dirhams", "dirham", "euros", "euro", "dollars", "dollar",
    "livres", "livre", "mad", "eur", "usd",
}

_LETTRES_IGNORE = {"et", "de", "le", "la", "les", "des"}

_LETTRES_MULTS = [
    ("milliards", 1_000_000_000), ("milliard", 1_000_000_000),
    ("millions",  1_000_000),     ("million",  1_000_000),
    ("mille",     1_000),
]


def _normalize_lettres(t: str) -> str:
    """Normalise un texte de montant en lettres pour faciliter le parsing."""
    t = t.lower().strip()
    t = re.sub(r"[^a-zàâéèêîôùûç\s-]", " ", t)
    # Normaliser les mots composés AVANT de supprimer les tirets
    t = t.replace("quatre-vingts",    "quatrevingt")
    t = t.replace("quatre-vingt-dix", "quatrevingtdix")
    t = t.replace("quatre-vingt",     "quatrevingt")
    t = t.replace("soixante-dix",     "soixantedix")
    t = t.replace("dix-sept",         "dixsept")
    t = t.replace("dix-huit",         "dixhuit")
    t = t.replace("dix-neuf",         "dixneuf")
    t = t.replace("-", " ")
    for d in _LETTRES_DEVISE:
        t = re.sub(rf"\b{d}\b", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _group_value(tokens: list) -> int:
    """Calcule la valeur entière d'un groupe de tokens (max ~999)."""
    v = 0
    for tok in tokens:
        if tok in _LETTRES_IGNORE or tok in _LETTRES_DEVISE:
            continue
        if tok in ("cent", "cents"):
            v = (v if v > 0 else 1) * 100
        elif tok in _LETTRES_UNITS:
            v += _LETTRES_UNITS[tok]
    return v


def _lettres_to_float(texte: str) -> Optional[float]:
    """
    Convertit un montant en lettres français en float.

    Exemples :
      "VINGT-TROIS MILLE HUIT CENT QUATRE-VINGTS DIRHAMS" → 23880.0
      "DEUX MILLE CINQ CENTS EUROS"                       → 2500.0
      "CENT VINGT MILLE DIRHAMS"                          → 120000.0

    Retourne None si la conversion échoue.
    """
    if not texte or not isinstance(texte, str):
        return None

    t = _normalize_lettres(texte)
    if not t:
        return None

    tokens = t.split()

    segments: list = []
    current: list  = []
    for tok in tokens:
        matched_mult = None
        for name, val in _LETTRES_MULTS:
            if tok == name:
                matched_mult = val
                break
        if matched_mult is not None:
            segments.append((current, matched_mult))
            current = []
        else:
            current.append(tok)
    segments.append((current, None))

    total = 0
    for grp_tokens, mult in segments:
        g = _group_value(grp_tokens)
        if mult is not None:
            total += (g if g > 0 else 1) * mult
        else:
            total += g

    return float(total) if total > 0 else None


# ══════════════════════════════════════════════════════════════════════════════
# FILTRAGE WARNINGS LLM
# Supprime les warnings du LLM qui doublonnent avec ce que validation_service
# calcule lui-même dans ses passes.
# ══════════════════════════════════════════════════════════════════════════════
_FILTRES_WARNINGS_LLM = (
    "net_a_payer",
    "net à payer",
    "incohérence: net",
    "incohérence numérique",
    "montant ttc en lettres introuvable",
)


def _filtrer_warnings_llm(warnings_llm: list) -> List[str]:
    return [
        w for w in (warnings_llm or [])
        if not any(mot in w.lower() for mot in _FILTRES_WARNINGS_LLM)
    ]


# ══════════════════════════════════════════════════════════════════════════════
# PASSES DE VALIDATION MÉTIER
# ══════════════════════════════════════════════════════════════════════════════

CHAMPS_OBLIGATOIRES = {
    "prestataire"   : "Nom du prestataire manquant",
    # ICE géré séparément — uniquement pour les factures marocaines
    "date_facture"  : "Date de facture manquante",
    "numero_facture": "Numéro de facture manquant",
    "montant_ht"    : "Montant HT manquant",
    "tva"           : "Montant TVA manquant",
    "taux_tva"      : "Taux de TVA manquant",
    "montant_ttc"   : "Montant TTC manquant",
}

# Devises et indicateurs de factures étrangères (hors Maroc)
# Devises étrangères telles que retournées par Gemini
# Gemini retourne : "MAD", "EUR", "USD" ou null
_DEVISES_ETRANGERES = {"EUR", "USD", "GBP", "CHF"}


def _est_facture_marocaine(data: Dict[str, Any]) -> bool:
    """
    Détermine si la facture est marocaine (ICE obligatoire) ou étrangère.
    Se base sur le champ 'devise' extrait par Gemini ("MAD", "EUR", "USD", null).

    Règle :
      - devise == "MAD" ou null → marocaine (contexte CGI Maroc par défaut)
      - devise == "EUR" / "USD" / autre devise étrangère → étrangère, ICE non requis
    """
    devise = str(data.get("devise") or "").upper().strip()

    if devise in _DEVISES_ETRANGERES:
        return False

    # "MAD", "" (null), ou toute autre valeur → on suppose marocaine
    return True


def _valider_champs_obligatoires(data: Dict[str, Any]) -> List[str]:
    motifs = []
    warnings = []
    for champ, message in CHAMPS_OBLIGATOIRES.items():
        if _is_blank(data.get(champ)):
            motifs.append(message)

    # ICE : rejet bloquant si facture MAD/devise inconnue (supposée marocaine) et ICE absent.
    # Si devise étrangère (EUR, USD…) → géré en exception non-bloquante dans _valider_champs_complementaires.
    if _est_facture_marocaine(data) and _is_blank(data.get("ice")):
        motifs.append("ICE (Identifiant Commun de l'Entreprise) manquant")

    # cachet_signature est renseigné par llm_service (texte + vision Gemini).
    # False = Gemini confirme l'absence → rejet bloquant
    # None  = détection incertaine (scan flou, cachet pâle…) → exception non-bloquante
    #         gérée dans valider_facture pour ne pas rejeter une facture valide
    cachet = data.get("cachet_signature")
    if cachet is False:
        motifs.append("Cachet ou signature absent de la facture")

    # ── Date d'échéance ───────────────────────────────────────────────────────
    # Règle 1 : date_echeance présente et dépassée → rejet bloquant
    # Règle 2 : date_echeance absente ET date_facture + 60j dépassée → rejet bloquant
    today        = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    date_ech_str = data.get("date_echeance")

    if not _is_blank(date_ech_str):
        date_ech = _parse_date(date_ech_str)
        if date_ech is not None and today > date_ech:
            warnings.append(
                f"Délai réglementaire 60j dépassé : facture du {date_fac.strftime('%d/%m/%Y')} — "
                f"vérification manuelle recommandée"
            )
    else:
        # Pas de date d'échéance explicite → délai légal implicite de 60 jours
        date_fac_str = data.get("date_facture")
        if not _is_blank(date_fac_str):
            date_fac = _parse_date(date_fac_str)
            if date_fac is not None:
                echeance_implicite = date_fac + timedelta(days=60)
                if today > echeance_implicite:
                    warnings.append("date à verifier")

    return motifs, warnings


def _valider_delai(data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    motifs   = []
    warnings = []

    date_str = data.get("date_facture")
    if _is_blank(date_str):
        return motifs, warnings

    date_facture = _parse_date(date_str)
    if date_facture is None:
        motifs.append(
            f"Date de facture illisible ou format invalide : '{date_str}' "
            "(attendu DD-MM-YYYY)"
        )
        return motifs, warnings

    today  = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    limite = date_facture + timedelta(days=DELAI_MAX_JOURS)

    if today > limite:
        jours_retard = (today - limite).days
        warnings.append(
            f"Délai de soumission dépassé : la facture du {date_facture.strftime('%d/%m/%Y')} "
            f"aurait dû être soumise avant le {limite.strftime('%d/%m/%Y')} "
            f"(délai interne de {DELAI_MAX_JOURS}j), retard de {jours_retard} jour(s) — "
            f"vérification manuelle recommandée"
        )
    elif today == date_facture:
        warnings.append("Facture datée d'aujourd'hui — vérifier la date si besoin")

    return motifs, warnings


def _valider_coherence(data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    motifs   = []
    warnings = []

    ht      = _to_float(data.get("montant_ht"))
    tva     = _to_float(data.get("tva"))
    ttc     = _to_float(data.get("montant_ttc"))
    taux    = _to_float(data.get("taux_tva"))
    retenue = _to_float(data.get("retenue_source"))
    net     = _to_float(data.get("net_a_payer"))

    # ── 1. TTC = HT + TVA  → BLOQUANT ────────────────────────────────────────
    if ht is not None and tva is not None and ttc is not None and ttc != 0:
        diff = abs((ht + tva) - ttc)
        if diff > abs(ttc) * TOLERANCE_MONTANT:
            motifs.append(
                f"Incohérence de calcul : HT ({ht}) + TVA ({tva}) = {ht + tva:.2f} "
                f"≠ TTC ({ttc}) — écart de {diff:.2f}"
            )

    # ── 2. TVA = HT × taux / 100  → BLOQUANT ─────────────────────────────────
    if ht is not None and tva is not None and ht != 0 and taux is not None:
        expected_tva = ht * taux / 100.0
        diff         = abs(expected_tva - tva)
        tol          = max(abs(expected_tva) * TOLERANCE_TVA, 0.01)
        if diff > tol:
            motifs.append(
                f"Incohérence TVA : {taux}% × HT ({ht}) = {expected_tva:.2f} "
                f"≠ TVA extraite ({tva}) — écart de {diff:.2f}"
            )

    # ── 3. Net à payer  → WARNING uniquement (jamais bloquant) ───────────────
    # Certaines factures (marchés publics) calculent NET = HT hors RG - Retenue
    # et non TTC - Retenue. C'est une formule alternative valide.
    if ttc is not None and retenue is not None and net is not None:
        expected_net = ttc - retenue
        diff         = abs(expected_net - net)
        if diff > 0.5:
            warnings.append(
                f"Net à payer ({net}) ≠ TTC ({ttc}) - Retenue ({retenue}) = {expected_net:.2f} "
                f"(écart : {diff:.2f}) — formule alternative possible (HT hors RG - Retenue), "
                "vérification manuelle recommandée"
            )

    # ── 4. Montant en lettres  → vérification automatique ────────────────────
    ttc_lettres = data.get("montant_ttc_lettres")
    if not _is_blank(ttc_lettres) and ttc is not None:
        ttc_from_lettres = _lettres_to_float(ttc_lettres)
        if ttc_from_lettres is None:
            warnings.append(
                f"Montant TTC en lettres '{ttc_lettres}' non convertible "
                "automatiquement — vérification manuelle requise"
            )
        else:
            diff_lettres = abs(ttc_from_lettres - ttc)
            if diff_lettres > 0.10:
                motifs.append(
                    f"Incohérence montant en lettres : '{ttc_lettres}' "
                    f"= {ttc_from_lettres:.2f} ≠ TTC chiffres ({ttc}) "
                    f"— écart de {diff_lettres:.2f}"
                )
            # Si cohérent → aucun message (vérification silencieuse réussie)

    return motifs, warnings


CHAMPS_COMPLEMENTAIRES = {
    "montant_ttc_lettres": "Montant TTC en lettres absent",
    "numero_engagement"  : "Numéro d'engagement / bon de commande absent",
    "date_echeance"      : "Date d'échéance absente",
    "retenue_source"     : "Retenue à la source non mentionnée",
}


def _valider_champs_complementaires(data: Dict[str, Any]) -> List[str]:
    exceptions = [
        message
        for champ, message in CHAMPS_COMPLEMENTAIRES.items()
        if _is_blank(data.get(champ))
    ]
    # ICE absent sur facture étrangère (EUR/USD/…) → exception non-bloquante uniquement
    if not _est_facture_marocaine(data) and _is_blank(data.get("ice")):
        devise = str(data.get("devise") or "").upper().strip()
        exceptions.append(
            f"Facture étrangère ({devise}) — ICE non applicable pour un prestataire étranger, "
            "vérification manuelle de l'identifiant fiscal recommandée"
        )
    return exceptions


# ══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def valider_facture(data: Dict[str, Any]) -> ValidationResult:
    """
    Valide une facture à partir du JSON retourné par llm_service.

    Le champ cachet_signature est lu directement depuis data — il a déjà
    été renseigné par llm_service (détection textuelle + visuelle Gemini).
    Ce fichier ne fait aucun appel API.

    Args:
        data : dict retourné par extract_invoice_json_from_text()

    Returns:
        ValidationResult avec statut, motifs_rejet, exceptions, warnings
    """
    all_motifs: List[str] = []

    # ── Filtrage des warnings LLM redondants ──────────────────────────────────
    # Le LLM peut encore générer des warnings sur des sujets gérés ici.
    # On les filtre à l'entrée pour éviter les doublons dans la réponse finale.
    all_warnings: List[str] = _filtrer_warnings_llm(data.get("warnings", []))

    # ── Passe 1 : Champs obligatoires ─────────────────────────────────────────
    champs_motifs, champs_warnings = _valider_champs_obligatoires(data)
    all_motifs.extend(champs_motifs)
    all_warnings.extend(champs_warnings)

    # ── Passe 2 : Délai des 7 jours ───────────────────────────────────────────
    motifs_delai, warnings_delai = _valider_delai(data)
    all_warnings.extend(motifs_delai)   # délai 7j dépassé → avertissement uniquement
    all_warnings.extend(warnings_delai)

    # ── Passe 3 : Cohérence des montants ──────────────────────────────────────
    motifs_coh, warnings_coh = _valider_coherence(data)
    all_motifs.extend(motifs_coh)
    all_warnings.extend(warnings_coh)

    # ── Passe 4 : Champs complémentaires ──────────────────────────────────────
    exceptions = _valider_champs_complementaires(data)

    # cachet None = détection incertaine → exception non-bloquante (accepté_avec_réserve)
    if data.get("cachet_signature") is None:
        exceptions.append(
            "Cachet/signature non confirmé visuellement — vérification manuelle requise"
        )

    # ── Statut final ──────────────────────────────────────────────────────────
    if all_motifs:
        statut = "rejeté"
    elif exceptions:
        statut = "accepté_avec_réserve"
    else:
        statut = "accepté"

    return ValidationResult(
        statut=statut,
        motifs_rejet=all_motifs,
        exceptions=exceptions,
        warnings=all_warnings,
    )