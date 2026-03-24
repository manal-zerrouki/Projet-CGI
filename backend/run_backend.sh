#!/bin/zsh
cd /Users/mac/Projet-CGI/backend
source venv/bin/activate
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/local/opt/tesseract/bin:$PATH"
export TESSERACT_CMD="/opt/local/bin/tesseract"

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

export TESSERACT_CMD=$(which tesseract || echo "tesseract")
