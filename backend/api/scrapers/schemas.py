"""
Scraper API request/response schemas
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class ScraperCreate(BaseModel):
    """Schema for creating a new scraper"""
    name: str = Field(..., min_length=1, max_length=255)
    target_url: str = Field(..., description="Target URL to scrape")
    chat_session_id: Optional[UUID] = Field(None, description="Associated chat session ID")


class ScraperUpdate(BaseModel):
    """Schema for updating scraper configuration"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    schedule_cron: Optional[str] = Field(None, description="Cron expression for scheduling")
    status: Optional[str] = Field(None, description="active, paused, failed, maintenance")
    scraping_config: Optional[Dict[str, Any]] = Field(None, description="Scraper configuration")


class ScraperResponse(BaseModel):
    """Schema for scraper response"""
    id: UUID
    user_id: UUID
    name: str
    target_url: str
    target_domain: Optional[str]
    scraping_config: Dict[str, Any]
    schedule_cron: Optional[str]
    status: str
    last_run_at: Optional[datetime]
    last_success_at: Optional[datetime]
    page_hash: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScraperListResponse(BaseModel):
    """Schema for listing scrapers (simplified)"""
    id: UUID
    name: str
    target_url: str
    target_domain: Optional[str]
    status: str
    last_run_at: Optional[datetime]
    last_success_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class ScraperRunResponse(BaseModel):
    """Schema for scraping run response"""
    id: UUID
    scraper_id: UUID
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    records_scraped: int
    error_message: Optional[str]
    output_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ScraperTestRequest(BaseModel):
    """Schema for testing a scraper"""
    sample_size: Optional[int] = Field(5, description="Number of records to scrape in test")


class ScraperTestResponse(BaseModel):
    """Schema for scraper test response"""
    success: bool
    records_scraped: int
    sample_data: List[Dict[str, Any]]
    errors: List[str]
    execution_time: float
