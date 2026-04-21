-- Initial DB schema + migration commentaire
CREATE DATABASE IF NOT EXISTS factures_db;
USE factures_db;

CREATE TABLE IF NOT EXISTS factures_cgi (
  numero_facture VARCHAR(100) PRIMARY KEY,
  prestataire VARCHAR(255),
  ice VARCHAR(50),
  date_facture DATE,
  numero_engagement VARCHAR(100),
  montant_ht DECIMAL(12,2),
  tva DECIMAL(12,2),
  montant_ttc DECIMAL(12,2),
  devise VARCHAR(10),
  statut_validation ENUM('accepté', 'accepté_avec_réserve', 'rejeté'),
  exception TEXT,
  motifs_rejet TEXT,
  result_json LONGTEXT,
  commentaire VARCHAR(500),
  date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_date_creation (date_creation),
  INDEX idx_prestataire (prestataire)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Migration si colonne absente
ALTER TABLE factures_cgi ADD COLUMN IF NOT EXISTS commentaire VARCHAR(500);

