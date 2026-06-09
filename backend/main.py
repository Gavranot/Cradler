"""
Cradler - AI-Powered Web Scraping SaaS Platform
Main FastAPI application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
import logging

from core.config import settings
from core.database.connection import init_db, close_db
from api.auth import router as auth_router
from api.scrapers import router as scrapers_router
from api.chat import router as chat_router
from api.data import router as data_router
from api.admin import router as admin_router

# Configure logging with environment variable support
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Set specific loggers to DEBUG for detailed information
logging.getLogger('agents.secondary.agent').setLevel(logging.DEBUG)
logging.getLogger('agents.mcp').setLevel(logging.DEBUG)
logging.getLogger('api.scrapers').setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)
logger.info(f"Logging configured with level: {settings.LOG_LEVEL.upper()}")


# Initialize Sentry if DSN is provided
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        environment=settings.ENVIRONMENT,
        traces_sample_rate=1.0 if settings.ENVIRONMENT == "development" else 0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


# Create FastAPI application
app = FastAPI(
    title="Cradler API",
    description="AI-powered web scraping SaaS platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "0.1.0"
    }


# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(scrapers_router, prefix="/api/scrapers", tags=["Scrapers"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(data_router, prefix="/api/data", tags=["Data"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Welcome to Cradler API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health"
    }
