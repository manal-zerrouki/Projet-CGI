from fastapi import FastAPI
from app.routes.invoice import router as invoice_router
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Projet Factures API")

app.include_router(invoice_router)