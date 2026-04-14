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
            date_creation
        FROM factures_cgi
        ORDER BY date_creation DESC
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows