from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])
Database = Annotated[AsyncSession, Depends(get_db)]


@router.get("/summary")
async def analytics_summary(db: Database) -> dict:
    return await AnalyticsService(db).summary()


@router.get("/trends")
async def analytics_trends(db: Database, days: Annotated[int, Query(ge=7, le=90)] = 30) -> dict:
    return await AnalyticsService(db).trends(days)
