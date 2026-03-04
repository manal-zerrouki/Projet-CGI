import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError("GOOGLE_API_KEY manquante dans .env")

client = genai.Client(api_key=api_key)

# Selon versions du SDK, la méthode peut varier
try:
    models = client.models.list()
    for m in models:
        print(getattr(m, "name", m))
except Exception as e:
    print("❌ Impossible de lister les modèles avec client.models.list()")
    print("Erreur:", e)