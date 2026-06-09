"""
Data API router
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/runs/{run_id}")
async def get_run_data(run_id: str):
    """Get scraped data from specific run"""
    return {"message": f"Get data for run {run_id} - to be implemented"}


@router.get("/export/{run_id}")
async def export_data(run_id: str, format: str = "json"):
    """Export data (JSON/CSV)"""
    return {"message": f"Export data for run {run_id} as {format} - to be implemented"}
