"""
Database models based on PRD schema
"""
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid

from core.database.connection import Base


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    api_key = Column(String(64), unique=True, nullable=True, index=True)
    role = Column(String(20), default="user", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Scraper(Base):
    """Scraper configuration model"""
    __tablename__ = "scrapers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    target_url = Column(Text, nullable=False)
    target_domain = Column(String(255), nullable=True, index=True)
    scraping_config = Column(JSONB, nullable=False)  # Stores generated code and config
    schedule_cron = Column(String(100), nullable=True)
    status = Column(String(20), default="active", nullable=False, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    page_hash = Column(String(64), nullable=True)  # SHA-256 for change detection
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ScrapingRun(Base):
    """Scraping execution history model"""
    __tablename__ = "scraping_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scraper_id = Column(UUID(as_uuid=True), ForeignKey("scrapers.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)  # queued, running, success, failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    records_scraped = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    output_url = Column(Text, nullable=True)  # S3/MinIO URL for results
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ScraperTemplate(Base):
    """Platform-specific scraping templates"""
    __tablename__ = "scraper_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform = Column(String(50), nullable=False, index=True)  # shopify, woocommerce, etc.
    selector_patterns = Column(JSONB, nullable=True)
    api_patterns = Column(JSONB, nullable=True)
    common_issues = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ScrapingKnowledge(Base):
    """Vector storage for RAG (future use)"""
    __tablename__ = "scraping_knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    embedding = Column(Vector(1536), nullable=False)  # OpenAI embedding dimension
    content = Column(Text, nullable=False)
    meta_data = Column(JSONB, nullable=True, name='metadata')  # {type, platform, etc.}
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Vector similarity index
    __table_args__ = (
        Index(
            'ix_scraping_knowledge_embedding',
            'embedding',
            postgresql_using='ivfflat',
            postgresql_with={'lists': 100},
            postgresql_ops={'embedding': 'vector_l2_ops'}
        ),
    )


class ChatSession(Base):
    """Chat sessions for scraper creation"""
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    scraper_id = Column(UUID(as_uuid=True), ForeignKey("scrapers.id", ondelete="SET NULL"), nullable=True, index=True)
    messages = Column(JSONB, nullable=False, default=list)  # Array of message objects
    status = Column(String(20), default="active", nullable=False)  # active, completed, abandoned
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
