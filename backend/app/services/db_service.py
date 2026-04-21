import mysql.connector
import os

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST") or "host.docker.internal",
        port=int(os.getenv("DB_PORT") or 3306), 
        user=os.getenv("DB_USER") or "root",
        password=os.getenv("DB_PASSWORD") or "",
        database=os.getenv("DB_NAME") or "factures_db"
    )

def get_all_factures():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            numero_facture,
            prestataire,
            ice,
            date_facture,
            numero_engagement,
            montant_ht,
            tva,
            montant_ttc,
            devise,
            statut_validation,
            exception,
            motifs_rejet,
            result_json,
            commentaire,
            date_creation
        FROM factures_cgi
        ORDER BY date_creation DESC
    """)

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    from datetime import date, datetime
    from decimal import Decimal

    result = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, (date, datetime)):
                clean[k] = v.isoformat()
            elif isinstance(v, Decimal):
                clean[k] = float(v)
            else:
                clean[k] = v
        result.append(clean)
    return result