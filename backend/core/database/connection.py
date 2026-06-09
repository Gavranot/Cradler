"""
Database connection and session management
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from core.config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.ENVIRONMENT == "development",
    future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Base class for models
Base = declarative_base()


async def init_db():
    """
    Initialize database connection
    """
    async with engine.begin() as conn:
        # Import all models to ensure they're registered
        from core.database import models  # noqa
        # Create tables (in production, use Alembic migrations)
        # await conn.run_sync(Base.metadata.create_all)
    print("Database initialized")


async def close_db():
    """
    Close database connections
    """
    await engine.dispose()
    print("Database connections closed")


async def get_db() -> AsyncSession:
    """
    Dependency for getting database sessions
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
