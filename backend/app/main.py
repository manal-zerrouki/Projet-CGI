from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.invoice import router as invoice_router
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Projet Factures API")

app.include_router(invoice_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)