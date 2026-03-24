"""
build_dataset.py — 100% local, zéro appel API
"""

import os, sys, re, csv, logging
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
from app.services.ocr_service import extract_text_from_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PDFS_DIR   = os.path.join(os.path.dirname(__file__), "..", "dataset", "pdfs")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "..", "dataset", "dataset.csv")

LABELS_MANUELS = {
    "ARKEOS.pdf"           : "accepté",
    "Atlas Geo Conseil.pdf": "accepté",
    "DXC.pdf"              : "accepté",
    "Globetudes.pdf"       : "accepté",
    "jaggear.pdf"          : "accepté",
    "Lacivac.pdf"          : "accepté",
    "OPEN.pdf"             : "accepté",
    "Skatys.pdf"           : "accepté",
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _found(pattern, text, flags=re.IGNORECASE):
    return 1 if re.search(pattern, text, flags) else 0


def _parse_nombre(s: str) -> float | None:
    """Convertit une chaîne OCR en float. Ex: '23 880,00' → 23880.0"""
    if not s:
        return None
    s = s.strip().replace("\u00a0", "").replace(" ", "")
    # Format européen : 23.880,00 ou 23 880,00
    if re.match(r"^\d{1,3}([.,]\d{3})+[.,]\d{2}$", s):
        s = re.sub(r"[.,](?=\d{3})", "", s)   # suppr séparateur milliers
    s = s.replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except Exception:
        return None


def _extract_montant_apres(pattern: str, text: str) -> float | None:
    """
    Cherche le pattern, puis capture le premier nombre sur la même ligne.
    Supporte les formats : 19 900,00  /  19900.00  /  19 900.00 DH
    """
    m = re.search(
        pattern + r"[^\d\n]{0,30}([\d\s]{1,10}[.,]\d{2})",
        text, re.IGNORECASE
    )
    if m:
        return _parse_nombre(m.group(1))
    # Fallback : nombre entier sans décimales
    m = re.search(
        pattern + r"[^\d\n]{0,30}(\d[\d\s]{2,12})\b",
        text, re.IGNORECASE
    )
    if m:
        return _parse_nombre(m.group(1))
    return None


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION MONTANTS — patterns adaptés aux 3 formats observés
# ══════════════════════════════════════════════════════════════════════════════

def extraire_montants(text: str) -> dict:
    """
    Extrait HT, TVA (montant), taux TVA, TTC, Net à payer depuis le texte OCR.

    Formats couverts :
      ARKEOS    → "Montant Net HT"  / "Montant TVA 20%"  / "Montant Net[C|T]"
      DXC       → "Montant HT"      / "Montant TVA"      / "Montant TTC"
      facture_* → "Montant HT après remise" / "TVA (20%)" / "Montant TTC" / "NET À PAYER"
    """

    # ── HT ────────────────────────────────────────────────────────────────────
    # Ordre : du plus spécifique au plus général pour éviter les faux positifs
    ht = (
        _extract_montant_apres(r"montant\s+(?:net\s+)?h\.?t\.?(?:\s+apr[eè]s\s+remise)?", text)
        or _extract_montant_apres(r"sous[-\s]?total\s+h\.?t\.?", text)
        or _extract_montant_apres(r"total\s+h\.?t\.?", text)
        # Ligne tableau : "Total HT (MAD)" suivi du montant
        or _extract_montant_apres(r"total\s+h\.?t\.?\s*\(?\w*\)?", text)
    )

    # ── TVA (montant, pas le taux) ────────────────────────────────────────────
    # "Montant TVA 20%  140,43"  ou  "TVA (20%)  6 175,00"  ou  "Montant TVA  3980,00"
    tva = (
        _extract_montant_apres(r"montant\s+t\.?v\.?a\.?\s*(?:\d+\s*%)?", text)
        or _extract_montant_apres(r"t\.?v\.?a\.?\s*\(\s*\d+\s*%\s*\)", text)
        or _extract_montant_apres(r"t\.?v\.?a\.?\s*\d+\s*%", text)
    )

    # ── Taux TVA ─────────────────────────────────────────────────────────────
    taux_m = re.search(r"\b(20|14|10|7)\s*%", text)
    taux = float(taux_m.group(1)) if taux_m else None

    # ── TTC ───────────────────────────────────────────────────────────────────
    # "Montant TTC"  ou  "Montant Net[C]" (ARKEOS tronqué OCR) ou "Total TTC"
    ttc = (
        _extract_montant_apres(r"montant\s+t\.?t\.?c\.?", text)
        or _extract_montant_apres(r"total\s+t\.?t\.?c\.?", text)
        # ARKEOS : "Montant Net C 84;" — OCR tronqué, on lit quand même
        or _extract_montant_apres(r"montant\s+ne[tl]\s+[ct]", text)
    )

    # ── Net à payer (après retenue, si présent) ────────────────────────────────
    # "NET À PAYER : 33 962,50"  ou  "Net à payer  33962.50"
    net = (
        _extract_montant_apres(r"net\s+[àa]\s+payer", text)
        or _extract_montant_apres(r"montant\s+net\s+[àa]\s+payer", text)
        or _extract_montant_apres(r"net\s+payable", text)
        or _extract_montant_apres(r"solde\s+[àa]\s+payer", text)
    )

    # ── Retenue à la source ───────────────────────────────────────────────────
    retenue = (
        _extract_montant_apres(r"retenue\s+[àa]\s+la\s+source\s*\(\s*\d+\s*%\s*\)", text)
        or _extract_montant_apres(r"retenue\s+[àa]\s+la\s+source", text)
        or _extract_montant_apres(r"\bRAS\b", text)
    )

    return {
        "ht"      : ht,
        "tva"     : tva,
        "taux"    : taux,
        "ttc"     : ttc,
        "net"     : net,
        "retenue" : retenue,
    }


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION FEATURES COMPLÈTE
# ══════════════════════════════════════════════════════════════════════════════

def extraire_features_ocr(text: str, nb_pages: int) -> dict:
    t = text or ""
    m = extraire_montants(t)

    # ── Champs obligatoires ───────────────────────────────────────────────────
    a_prestataire = _found(
        r"(s\.a\.s?\.?|s\.a\.|sarl|soci[eé]t[eé]\s+\w|company|ltd|inc\.?|"
        r"group|entreprise|consulting|technology|services|solutions)",
        t
    )
    # ── Origine : marocaine ou étrangère ─────────────────────────────────────
    # Même logique que validation_service.py :
    #   devise étrangère (EUR, USD, GBP...) → ICE non requis
    #   devise MAD, ou aucune devise détectée → marocaine par défaut (contexte CGI Maroc)
    #
    # On cherche les devises telles qu elles apparaissent dans le texte OCR,
    # cohérentes avec ce que Gemini retourne ("MAD", "EUR", "USD").
    devise_etrangere = _found(
        r"\b(EUR|USD|GBP|CHF|euro[s]?|dollar[s]?|pound[s]?)\b",
        t
    )
    devise_mad = _found(
        r"\b(MAD|dirham[s]?|DH\b)",
        t
    )

    # MAD explicite → marocaine / devise étrangère → étrangère
    # Aucune devise détectée → marocaine par défaut (contexte CGI Maroc)
    facture_marocaine = bool(devise_mad or not devise_etrangere)

    a_ice_present = _found(r"\bICE\s*:?\s*\d{10,15}\b", t)
    # ICE = 1 si présent, OU si facture étrangère (ICE non applicable)
    a_ice = 1 if (a_ice_present or not facture_marocaine) else 0
    a_date_facture = _found(
        r"\b(0?[1-9]|[12]\d|3[01])[\/\-\.](0?[1-9]|1[0-2])[\/\-\.](20\d{2})\b", t
    )
    a_numero_facture = _found(
        r"(n[°o\.]\s*(?:de\s*)?facture|facture\s*n[°o\.]|invoice\s*(?:n[°o\.]|#)|"
        r"FA[-\s]?\d|LOC\d{4,}|FAC[-\s]?\d|N°\s*FA)",
        t
    )
    a_montant_ht  = 1 if m["ht"]  is not None else 0
    a_tva         = 1 if m["tva"] is not None else 0
    a_taux_tva    = 1 if m["taux"] is not None else 0
    a_montant_ttc = 1 if m["ttc"] is not None else 0
    a_net_a_payer = 1 if m["net"] is not None else 0
    a_retenue     = 1 if m["retenue"] is not None else 0

    # NOTE : a_cachet retiré intentionnellement.
    # Le cachet est un élément VISUEL (tampon, signature manuscrite) que l'OCR
    # ne peut pas détecter fiablement. La détection est faite par Gemini Vision
    # en production, après la classification ML.

    # ── Cohérence HT + TVA = TTC ─────────────────────────────────────────────
    ht_tva_ttc_coherent = 0
    if m["ht"] and m["tva"] and m["ttc"] and m["ttc"] != 0:
        diff = abs((m["ht"] + m["tva"]) - m["ttc"])
        ht_tva_ttc_coherent = 1 if diff <= abs(m["ttc"]) * 0.05 else 0

    # ── Cohérence taux TVA : HT × taux = TVA ─────────────────────────────────
    taux_tva_coherent = 0
    if m["taux"] and m["ht"] and m["tva"] and m["ht"] != 0:
        expected = m["ht"] * m["taux"] / 100.0
        diff = abs(expected - m["tva"])
        tol  = max(abs(expected) * 0.05, 1.0)
        taux_tva_coherent = 1 if diff <= tol else 0

    # ── Cohérence Net = TTC - Retenue ────────────────────────────────────────
    net_coherent = 0
    if m["net"] and m["ttc"]:
        if m["retenue"]:
            expected_net = m["ttc"] - m["retenue"]
            net_coherent = 1 if abs(expected_net - m["net"]) <= m["ttc"] * 0.02 else 0
        else:
            # Pas de retenue → Net ≈ TTC
            net_coherent = 1 if abs(m["net"] - m["ttc"]) <= m["ttc"] * 0.02 else 0

    # ── Champs complémentaires ────────────────────────────────────────────────
    a_ttc_lettres = _found(
        r"(arr[eê]t[eé]e?\s+la\s+présente|la\s+somme\s+de\s*:|montant\s+en\s+lettres|"
        r"(vingt|trente|quarante|cinquante|soixante|cent|mille)\s+\w+\s+\w+)",
        t
    )
    a_numero_engagement = _found(
        r"(n[°o\.]\s*(?:d['\s])?engagement|bon\s*de\s*commande|"
        r"CGI[-\s][A-Z]{2}[-\s]\d{4}|BC\s*n[°o\.]|PO\s*n[°o\.]|"
        r"r[eé]f\.?\s*(?:engagement|commande)|AT\d{9,})",
        t
    )
    a_date_echeance = _found(
        r"([eé]ch[eé]ance\s*(?:le|au|:|\d)|date\s+(?:d['\s])?[eé]ch[eé]ance|"
        r"due\s+date|date\s+limite\s+(?:de\s+)?paiement|"
        r"[àa]\s+r[eé]gler\s+(?:avant|le|au))",
        t
    )

    return {
        # Présence champs
        "a_prestataire"      : a_prestataire,
        "a_ice"              : a_ice,
        "a_date_facture"     : a_date_facture,
        "a_numero_facture"   : a_numero_facture,
        "a_montant_ht"       : a_montant_ht,
        "a_tva"              : a_tva,
        "a_taux_tva"         : a_taux_tva,
        "a_montant_ttc"      : a_montant_ttc,
        "a_net_a_payer"      : a_net_a_payer,
        "a_retenue_source"   : a_retenue,
        "est_marocaine"      : int(facture_marocaine),
        "a_ice_present"      : a_ice_present,
        # a_cachet : détecté par Gemini Vision uniquement, pas ici
        # Cohérence
        "ht_tva_ttc_coherent": ht_tva_ttc_coherent,
        "taux_tva_coherent"  : taux_tva_coherent,
        "net_coherent"       : net_coherent,
        # Complémentaires
        "a_ttc_lettres"      : a_ttc_lettres,
        "a_numero_engagement": a_numero_engagement,
        "a_date_echeance"    : a_date_echeance,
        # Métadonnées
        "nb_pages"           : nb_pages,
        "longueur_ocr"       : len(t),
    }


# ══════════════════════════════════════════════════════════════════════════════
# LABEL AUTOMATIQUE
# ══════════════════════════════════════════════════════════════════════════════

def determiner_label_auto(features: dict) -> str:
    motifs = []
    for champ in [
        "a_prestataire", "a_ice", "a_date_facture", "a_numero_facture",
        "a_montant_ht", "a_tva", "a_taux_tva", "a_montant_ttc",
    ]:
        if features.get(champ, 0) == 0:
            motifs.append(champ)

    # a_cachet : non inclus — détection visuelle via Gemini uniquement

    if (features.get("a_montant_ht") and features.get("a_montant_ttc")
            and features.get("ht_tva_ttc_coherent", 0) == 0):
        motifs.append("montants_incoherents")

    if motifs:
        return "rejeté"

    manquants = [c for c in ["a_ttc_lettres", "a_numero_engagement", "a_date_echeance"]
                 if features.get(c, 0) == 0]
    return "accepté_avec_réserve" if manquants else "accepté"


# ══════════════════════════════════════════════════════════════════════════════
# TRAITEMENT PDF
# ══════════════════════════════════════════════════════════════════════════════

def traiter_pdf(pdf_path: str) -> dict | None:
    nom = os.path.basename(pdf_path)
    log.info(f"Traitement : {nom}")
    try:
        ocr_text = extract_text_from_pdf(pdf_path)
        if not ocr_text or len(ocr_text.strip()) < 20:
            log.warning(f"  ⚠ OCR vide")
            return None

        try:
            import fitz
            doc = fitz.open(pdf_path)
            nb_pages = len(doc)
            doc.close()
        except Exception:
            nb_pages = 1

        features = extraire_features_ocr(ocr_text, nb_pages)

        if nom in LABELS_MANUELS:
            label, source = LABELS_MANUELS[nom], "manuel"
        else:
            label, source = determiner_label_auto(features), "auto"

        log.info(
            f"  ✓ [{source}] {label} | "
            f"ht={features['a_montant_ht']} tva={features['a_tva']} "
            f"ttc={features['a_montant_ttc']} net={features['a_net_a_payer']} "
            f"ret={features['a_retenue_source']} coh={features['ht_tva_ttc_coherent']}"
        )
        return {"fichier": nom, "label": label, "source_label": source, **features}

    except Exception as e:
        log.error(f"  ✗ {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    pdfs_dir = os.path.abspath(PDFS_DIR)
    if not os.path.isdir(pdfs_dir):
        log.error(f"Dossier PDFs introuvable : {pdfs_dir}")
        sys.exit(1)

    pdfs = sorted([
        os.path.join(pdfs_dir, f)
        for f in os.listdir(pdfs_dir) if f.lower().endswith(".pdf")
    ])
    if not pdfs:
        log.error("Aucun PDF trouvé.")
        sys.exit(1)

    log.info(f"{len(pdfs)} PDFs trouvés. Traitement 100% local (sans API)...")

    resultats = [r for r in (traiter_pdf(p) for p in (
        (log.info(f"[{i}/{len(pdfs)}]") or p)
        for i, p in enumerate(pdfs, 1)
    )) if r]

    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_CSV)), exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(resultats[0].keys()))
        writer.writeheader()
        writer.writerows(resultats)

    log.info(f"\n✅ {len(resultats)}/{len(pdfs)} factures → {os.path.abspath(OUTPUT_CSV)}")

    log.info("\n── Distribution labels ──")
    for label, count in sorted(Counter(r["label"] for r in resultats).items()):
        log.info(f"   {label:<25} : {count:>3} ({count/len(resultats)*100:.0f}%)")

    log.info("\n── Vraies factures ──")
    for r in resultats:
        if r["source_label"] == "manuel":
            log.info(
                f"   {r['fichier']:<30} → {r['label']} | "
                f"ht={r['a_montant_ht']} tva={r['a_tva']} ttc={r['a_montant_ttc']} "
                f"net={r['a_net_a_payer']} ret={r['a_retenue_source']}"
            )


if __name__ == "__main__":
    main()