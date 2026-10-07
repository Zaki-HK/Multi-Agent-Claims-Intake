from fastapi import APIRouter

from app.api.claims import router as claims_router
from app.api.reviews import router as reviews_router
from app.api.policies import router as policies_router
from app.api.analytics import router as analytics_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(claims_router)
api_router.include_router(reviews_router)
api_router.include_router(policies_router)
api_router.include_router(analytics_router)
