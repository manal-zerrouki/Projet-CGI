"""
===================
Entraîne un classificateur Random Forest sur le dataset de factures.

Usage :
    python train_classifier.py

Entrée  : backend/app/ml/dataset/dataset.csv
Sortie  : backend/app/ml/models/classifier.pkl
          backend/app/ml/models/classifier_meta.json
"""

import os
import sys
import json
import pickle
import logging
import numpy as np
import pandas as pd

from collections import Counter
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── Chemins ──────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(__file__)
ML_DIR      = os.path.abspath(os.path.join(BASE_DIR, ".."))
DATASET_CSV = os.path.join(ML_DIR, "dataset", "dataset.csv")
MODELS_DIR  = os.path.join(ML_DIR, "models")
MODEL_PATH  = os.path.join(MODELS_DIR, "classifier.pkl")
META_PATH   = os.path.join(MODELS_DIR, "classifier_meta.json")

# ── Features utilisées pour l'entraînement ───────────────────────────────────
FEATURE_COLS = [
    "a_prestataire", "a_ice", "a_date_facture", "a_numero_facture",
    "a_montant_ht", "a_tva", "a_taux_tva", "a_montant_ttc",
    # a_cachet retiré : le cachet est visuel, détecté par Gemini Vision uniquement
    "a_net_a_payer", "a_retenue_source",
    "ht_tva_ttc_coherent", "taux_tva_coherent", "net_coherent",
    "a_ttc_lettres", "a_numero_engagement", "a_date_echeance",
    "est_marocaine", "a_ice_present",  # permet au modèle de comprendre le contexte ICE
    "nb_pages", "longueur_ocr",
]


def main():
    # ── Chargement dataset ────────────────────────────────────────────────────
    if not os.path.exists(DATASET_CSV):
        log.error(f"Dataset introuvable : {DATASET_CSV}")
        log.error("Lancez d'abord build_dataset.py")
        sys.exit(1)

    df = pd.read_csv(DATASET_CSV)
    log.info(f"Dataset chargé : {len(df)} factures")
    log.info(f"Distribution labels :\n{df['label'].value_counts().to_string()}")

    # ── Vérification colonnes ─────────────────────────────────────────────────
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        log.error(f"Colonnes manquantes dans le dataset : {missing}")
        sys.exit(1)

    X = df[FEATURE_COLS].fillna(0).values
    y = df["label"].values

    # ── Encodage labels ───────────────────────────────────────────────────────
    le = LabelEncoder()
    y_enc = le.fit_transform(y)
    log.info(f"Classes : {list(le.classes_)}")

    # ── Entraînement ─────────────────────────────────────────────────────────
    # LeaveOneOut : idéal pour peu de données (70 factures)
    # Entraîne sur N-1 factures, teste sur 1, répète N fois
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_leaf=1,
        class_weight="balanced",   # compense les classes déséquilibrées
        random_state=42,
    )

    log.info("Cross-validation LeaveOneOut en cours...")
    loo = LeaveOneOut()
    y_pred_enc = cross_val_predict(clf, X, y_enc, cv=loo)
    y_pred = le.inverse_transform(y_pred_enc)

    # ── Évaluation ────────────────────────────────────────────────────────────
    log.info("\n── Rapport de classification (Leave-One-Out) ──")
    print(classification_report(y, y_pred, zero_division=0))

    log.info("── Matrice de confusion ──")
    cm = confusion_matrix(y, y_pred, labels=le.classes_)
    cm_df = pd.DataFrame(cm, index=le.classes_, columns=le.classes_)
    print(cm_df.to_string())

    # Accuracy globale
    accuracy = (y == y_pred).mean()
    log.info(f"\nAccuracy LOO : {accuracy:.1%}")

    # ── Entraînement final sur tout le dataset ────────────────────────────────
    log.info("\nEntraînement final sur tout le dataset...")
    clf.fit(X, y_enc)

    # ── Feature importance ────────────────────────────────────────────────────
    importances = clf.feature_importances_
    feat_imp = sorted(
        zip(FEATURE_COLS, importances),
        key=lambda x: x[1],
        reverse=True
    )
    log.info("\n── Feature importance ──")
    for feat, imp in feat_imp:
        bar = "█" * int(imp * 50)
        log.info(f"  {feat:<25} {imp:.3f} {bar}")

    # ── Sauvegarde ────────────────────────────────────────────────────────────
    os.makedirs(MODELS_DIR, exist_ok=True)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": clf, "label_encoder": le, "features": FEATURE_COLS}, f)

    meta = {
        "n_samples"      : int(len(df)),
        "classes"        : list(le.classes_),
        "features"       : FEATURE_COLS,
        "accuracy_loo"   : round(float(accuracy), 4),
        "label_counts"   : {k: int(v) for k, v in Counter(y).items()},
        "feature_importance": {f: round(float(i), 4) for f, i in feat_imp},
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    log.info(f"\n Modèle sauvegardé : {MODEL_PATH}")
    log.info(f" Métadonnées       : {META_PATH}")
    log.info(f"   Accuracy LOO      : {accuracy:.1%}")


if __name__ == "__main__":
    main()