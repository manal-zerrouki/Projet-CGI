#!/bin/zsh

echo "=== Lancement Backend (FastAPI:8000) ==="
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements-api.txt
echo "Backend deps OK"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Nouveau terminal pour frontend (manuel)
