"""
build_dataset.py — 100% local, zéro appel API

Génère deux fichiers CSV :
  - dataset.csv      : factures synthétiques pour l'entraînement
  - dataset_test.csv : vraies factures CGI pour l'évaluation uniquement
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
TEST_CSV   = os.path.join(os.path.dirname(__file__), "..", "dataset", "dataset_test.csv")

# Vraies factures CGI validées par l'entreprise.
# Exclues de l'entraînement car l'OCR ne les lit pas bien (features incohérentes).
# Utilisées uniquement comme jeu de test pour évaluer le modèle sur de vraies factures.
FACTURES_TEST = {
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
    if re.match(r"^\d{1,3}([.,]\d{3})+[.,]\d{2}$", s):
        s = re.sub(r"[.,](?=\d{3})", "", s)
    s = s.replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except Exception:
        return None


def _extract_montant_apres(pattern: str, text: str) -> float | None:
    m = re.search(
        pattern + r"[^\d\n]{0,30}([\d\s]{1,10}[.,]\d{2})",
        text, re.IGNORECASE
    )
    if m:
        return _parse_nombre(m.group(1))
    m = re.search(
        pattern + r"[^\d\n]{0,30}(\d[\d\s]{2,12})\b",
        text, re.IGNORECASE
    )
    if m:
        return _parse_nombre(m.group(1))
    return None


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION MONTANTS
# ══════════════════════════════════════════════════════════════════════════════

def extraire_montants(text: str) -> dict:
    ht = (
        _extract_montant_apres(r"montant\s+(?:net\s+)?h\.?t\.?(?:\s+apr[eè]s\s+remise)?", text)
        or _extract_montant_apres(r"sous[-\s]?total\s+h\.?t\.?", text)
        or _extract_montant_apres(r"total\s+h\.?t\.?", text)
        or _extract_montant_apres(r"total\s+h\.?t\.?\s*\(?\w*\)?", text)
    )

    tva = (
        _extract_montant_apres(r"montant\s+t\.?v\.?a\.?\s*(?:\d+\s*%)?", text)
        or _extract_montant_apres(r"t\.?v\.?a\.?\s*\(\s*\d+\s*%\s*\)", text)
        or _extract_montant_apres(r"t\.?v\.?a\.?\s*\d+\s*%", text)
    )

    taux_m = re.search(r"\b(20|14|10|7)\s*%", text)
    taux = float(taux_m.group(1)) if taux_m else None

    ttc = (
        _extract_montant_apres(r"montant\s+t\.?t\.?c\.?", text)
        or _extract_montant_apres(r"total\s+t\.?t\.?c\.?", text)
        or _extract_montant_apres(r"montant\s+ne[tl]\s+[ct]", text)
    )

    net = (
        _extract_montant_apres(r"net\s+[àa]\s+payer", text)
        or _extract_montant_apres(r"montant\s+net\s+[àa]\s+payer", text)
        or _extract_montant_apres(r"net\s+payable", text)
        or _extract_montant_apres(r"solde\s+[àa]\s+payer", text)
    )

    retenue = (
        _extract_montant_apres(r"retenue\s+[àa]\s+la\s+source\s*\(\s*\d+\s*%\s*\)", text)
        or _extract_montant_apres(r"retenue\s+[àa]\s+la\s+source", text)
        or _extract_montant_apres(r"\bRAS\b", text)
    )

    return {"ht": ht, "tva": tva, "taux": taux, "ttc": ttc, "net": net, "retenue": retenue}


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION FEATURES
# ══════════════════════════════════════════════════════════════════════════════

def extraire_features_ocr(text: str, nb_pages: int) -> dict:
    t = text or ""
    m = extraire_montants(t)

    a_prestataire = _found(
        r"(s\.a\.s?\.?|s\.a\.|sarl|soci[eé]t[eé]\s+\w|company|ltd|inc\.?|"
        r"group|entreprise|consulting|technology|services|solutions)", t
    )

    devise_etrangere = _found(r"\b(EUR|USD|GBP|CHF|euro[s]?|dollar[s]?|pound[s]?)\b", t)
    devise_mad = _found(r"\b(MAD|dirham[s]?|DH\b)", t)
    facture_marocaine = bool(devise_mad or not devise_etrangere)

    a_ice_present = _found(r"\bICE\s*:?\s*\d{10,15}\b", t)
    a_ice = 1 if (a_ice_present or not facture_marocaine) else 0

    a_date_facture = _found(
        r"\b(0?[1-9]|[12]\d|3[01])[\/\-\.](0?[1-9]|1[0-2])[\/\-\.](20\d{2})\b", t
    )
    a_numero_facture = _found(
        r"(n[°o\.]\s*(?:de\s*)?facture|facture\s*n[°o\.]|invoice\s*(?:n[°o\.]|#)|"
        r"FA[-\s]?\d|LOC\d{4,}|FAC[-\s]?\d|N°\s*FA)", t
    )

    a_montant_ht  = 1 if m["ht"]  is not None else 0
    a_tva         = 1 if m["tva"] is not None else 0
    a_taux_tva    = 1 if m["taux"] is not None else 0
    a_montant_ttc = 1 if m["ttc"] is not None else 0
    a_net_a_payer = 1 if m["net"] is not None else 0
    a_retenue     = 1 if m["retenue"] is not None else 0

    ht_tva_ttc_coherent = 0
    if m["ht"] and m["tva"] and m["ttc"] and m["ttc"] != 0:
        diff = abs((m["ht"] + m["tva"]) - m["ttc"])
        ht_tva_ttc_coherent = 1 if diff <= abs(m["ttc"]) * 0.05 else 0

    taux_tva_coherent = 0
    if m["taux"] and m["ht"] and m["tva"] and m["ht"] != 0:
        expected = m["ht"] * m["taux"] / 100.0
        diff = abs(expected - m["tva"])
        tol  = max(abs(expected) * 0.05, 1.0)
        taux_tva_coherent = 1 if diff <= tol else 0

    net_coherent = 0
    if m["net"] and m["ttc"]:
        if m["retenue"]:
            expected_net = m["ttc"] - m["retenue"]
            net_coherent = 1 if abs(expected_net - m["net"]) <= m["ttc"] * 0.02 else 0
        else:
            net_coherent = 1 if abs(m["net"] - m["ttc"]) <= m["ttc"] * 0.02 else 0

    a_ttc_lettres = _found(
        r"(arr[eê]t[eé]e?\s+la\s+présente|la\s+somme\s+de\s*:|montant\s+en\s+lettres|"
        r"(vingt|trente|quarante|cinquante|soixante|cent|mille)\s+\w+\s+\w+)", t
    )
    a_numero_engagement = _found(
        r"(n[°o\.]\s*(?:d['\s])?engagement|bon\s*de\s*commande|"
        r"CGI[-\s][A-Z]{2}[-\s]\d{4}|BC\s*n[°o\.]|PO\s*n[°o\.]|"
        r"r[eé]f\.?\s*(?:engagement|commande)|AT\d{9,})", t
    )
    a_date_echeance = _found(
        r"([eé]ch[eé]ance\s*(?:le|au|:|\d)|date\s+(?:d['\s])?[eé]ch[eé]ance|"
        r"due\s+date|date\s+limite\s+(?:de\s+)?paiement|"
        r"[àa]\s+r[eé]gler\s+(?:avant|le|au))", t
    )

    return {
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
        "ht_tva_ttc_coherent": ht_tva_ttc_coherent,
        "taux_tva_coherent"  : taux_tva_coherent,
        "net_coherent"       : net_coherent,
        "a_ttc_lettres"      : a_ttc_lettres,
        "a_numero_engagement": a_numero_engagement,
        "a_date_echeance"    : a_date_echeance,
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

def traiter_pdf(pdf_path: str, label_force: str = None) -> dict | None:
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

        if label_force is not None:
            label, source = label_force, "test"
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

    train_results = []
    test_results  = []

    for i, pdf_path in enumerate(pdfs, 1):
        nom = os.path.basename(pdf_path)
        log.info(f"[{i}/{len(pdfs)}]")

        if nom in FACTURES_TEST:
            # Vraie facture CGI → jeu de test uniquement
            r = traiter_pdf(pdf_path, label_force=FACTURES_TEST[nom])
            if r:
                test_results.append(r)
        else:
            # Facture synthétique → entraînement
            r = traiter_pdf(pdf_path)
            if r:
                train_results.append(r)

    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_CSV)), exist_ok=True)

    # Sauvegarde dataset entraînement
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(train_results[0].keys()))
        writer.writeheader()
        writer.writerows(train_results)

    # Sauvegarde dataset test
    with open(TEST_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(test_results[0].keys()))
        writer.writeheader()
        writer.writerows(test_results)

    log.info(f"\n✅ Entraînement : {len(train_results)} factures → {os.path.abspath(OUTPUT_CSV)}")
    log.info(f"✅ Test         : {len(test_results)} factures  → {os.path.abspath(TEST_CSV)}")

    log.info("\n── Distribution labels (entraînement) ──")
    for label, count in sorted(Counter(r["label"] for r in train_results).items()):
        log.info(f"   {label:<25} : {count:>3} ({count/len(train_results)*100:.0f}%)")

    log.info("\n── Vraies factures CGI (test) ──")
    for r in test_results:
        log.info(
            f"   {r['fichier']:<30} → {r['label']} | "
            f"ht={r['a_montant_ht']} tva={r['a_tva']} ttc={r['a_montant_ttc']} "
            f"net={r['a_net_a_payer']} ret={r['a_retenue_source']}"
        )


if __name__ == "__main__":
    main()
