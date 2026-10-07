from fastapi import FastAPI
from app.config import settings
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.celery_app import celery_app

app = FastAPI(
    title="AI Claims Intake API",
    description="Multi-agent system for First Notice of Loss (FNOL) processing",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "AI Claims Intake API"}

app.include_router(api_router)
