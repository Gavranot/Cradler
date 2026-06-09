"""
Admin API router
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/scrapers")
async def get_all_scrapers():
    """Get all scrapers (admin only)"""
    return {"message": "Get all scrapers - to be implemented"}


@router.get("/metrics")
async def get_metrics():
    """Get system metrics"""
    return {"message": "Get system metrics - to be implemented"}


@router.post("/maintenance")
async def trigger_maintenance():
    """Trigger maintenance checks"""
    return {"message": "Trigger maintenance - to be implemented"}
