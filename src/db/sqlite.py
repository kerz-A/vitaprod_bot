"""
SQLite database connection and session management.
Uses async SQLAlchemy for non-blocking operations.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, Tuple, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.db.models import Base


class Database:
    """Async database manager."""

    def __init__(self, url: Optional[str] = None):
        self.url = url or settings.db_url
        self._engine = None
        self._session_factory = None

    async def init(self) -> None:
        """Initialize database engine and create tables."""
        # Ensure data directory exists
        if "sqlite" in self.url:
            # Extract path from URL: sqlite+aiosqlite:///C:/path/to/db.db or sqlite+aiosqlite:///path/to/db.db
            path_part = self.url.split("///", 1)[-1]
            db_path = Path(path_part)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self._engine = create_async_engine(
            self.url,
            echo=settings.debug,
            future=True,
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        # Create all tables
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Close database connections."""
        if self._engine:
            await self._engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session."""
        if not self._session_factory:
            await self.init()

        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Global database instance
db = Database()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes."""
    async with db.session() as session:
        yield session