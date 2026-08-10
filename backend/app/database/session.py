import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.database.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(
    get_settings().database_url,
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create the pgvector extension, tables, and search indexes."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # Full-text index for the keyword leg of hybrid search
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_chunks_text_tsv ON chunks "
                "USING gin (to_tsvector('english', text))"
            )
        )
        # HNSW index for vector similarity (pgvector >= 0.5)
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw ON chunks "
                "USING hnsw (embedding vector_cosine_ops)"
            )
        )
        # migrations for tables created before these columns existed
        await conn.execute(
            text("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS user_id VARCHAR(64) DEFAULT ''")
        )
        for table in ("articles", "chunks"):
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS production_office VARCHAR(8) DEFAULT ''")
            )
    logger.info("Database initialized")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        yield session


async def check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_vector_extension() -> bool:
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            return result.first() is not None
    except Exception:
        return False
