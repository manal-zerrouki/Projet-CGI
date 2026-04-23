from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.invoice import router as invoice_router
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Projet Factures API")

app.include_router(invoice_router)

# React (CRA) : souvent localhost:3000, parfois 3001+ si le port est pris — 127.0.0.1 aussi utilisé.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
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