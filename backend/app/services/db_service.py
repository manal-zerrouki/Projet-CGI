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