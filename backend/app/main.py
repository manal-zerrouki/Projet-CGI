from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.invoice import router as invoice_router
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Projet Factures API")

app.include_router(invoice_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return RedirectResponse(url="/docs")