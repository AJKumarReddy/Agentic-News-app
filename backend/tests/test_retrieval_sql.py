"""Retrieval filters executed against a real PostgreSQL.

Every other test in this suite fakes `retrieve_rag`, so `_apply_filters` — the
code that actually enforces a date window or a section — was never executed at
all. Two defects lived there undetected because of it: filter bounds compared a
naive datetime against a `timestamptz` column, and the section predicate
compared our slug to the publisher's display name and therefore matched
nothing.

Neither is reachable without a database, so these run against the local
docker-compose Postgres and skip when it is not up. Everything happens inside a
transaction that is rolled back, so the developer's database is left untouched.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.database.models import Article, Base, Chunk
from app.rag.vector_store import RetrievalFilters, _apply_filters, keyword_search
from app.sources.sections import related_sections

pytestmark = pytest.mark.integration

DIMENSIONS = get_settings().embedding_dimensions
MARCH = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)

#: create_all is idempotent but not free; once per session is enough
_schema_ready = False


class Fixtures:
    """Rows scoped to one test.

    The developer's database holds real indexed reporting, so every query here
    is narrowed to this run's `source_id`. That isolates the assertions without
    weakening them — the date and section predicates under test still run over
    the same table, alongside the real rows.
    """

    def __init__(self, db):
        self.db = db
        self.run = f"test-{uuid.uuid4().hex[:8]}"

    def _id(self, name: str) -> str:
        return f"{self.run}/{name}"

    async def add(
        self,
        name: str,
        *,
        published_at: datetime | None = MARCH,
        section: str = "World news",
        text: str = "the inquiry published its findings on the spending bill",
    ) -> None:
        article_id = self._id(name)
        self.db.add(
            Article(
                article_id=article_id,
                headline="H",
                url=f"https://example.com/{article_id}",
                section=section,
                published_at=published_at,
                source_id=self.run,
            )
        )
        await self.db.flush()
        self.db.add(
            Chunk(
                article_id=article_id,
                chunk_index=0,
                text=text,
                embedding=[0.0] * DIMENSIONS,
                headline="H",
                published_at=published_at,
                section=section,
                source_id=self.run,
            )
        )
        await self.db.flush()

    def scoped(self, filters: RetrievalFilters) -> RetrievalFilters:
        filters.source_ids = [self.run]
        return filters

    async def matching(self, filters: RetrievalFilters) -> list[str]:
        rows = await self.db.execute(_apply_filters(select(Chunk), self.scoped(filters)))
        return sorted(chunk.article_id.split("/", 1)[1] for chunk in rows.scalars())


@pytest_asyncio.fixture
async def fixtures():
    """Rows written inside a transaction that is rolled back afterwards, so
    the developer's database is left exactly as it was found.

    Each test gets its own NullPool engine. The application's module-level
    engine binds its pool to whichever event loop created it, and pytest-asyncio
    gives every test a fresh loop — reusing it made connections fail on
    alternate tests, which the fixture then reported as "database unreachable".
    """
    global _schema_ready
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            if _schema_ready:
                await conn.execute(text("SELECT 1"))
            else:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
                _schema_ready = True
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL not reachable ({type(exc).__name__}) — start docker compose")

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        transaction = await db.begin()
        try:
            yield Fixtures(db)
        finally:
            await transaction.rollback()
    await engine.dispose()


# ── date bounds ───────────────────────────────────────────────────

async def test_window_is_inclusive_at_both_ends(fixtures):
    await fixtures.add("first", published_at=MARCH.replace(day=1))
    await fixtures.add("last", published_at=MARCH.replace(day=31))
    await fixtures.add("after", published_at=MARCH.replace(month=4, day=1))

    found = await fixtures.matching(RetrievalFilters.from_iso("2026-03-01", "2026-03-31"))
    assert found == ["first", "last"]


async def test_end_of_day_is_included(fixtures):
    """to_date is a calendar day, so an article published at 23:50 that day
    must survive the filter."""
    await fixtures.add("late", published_at=datetime(2026, 3, 31, 23, 50, tzinfo=timezone.utc))
    found = await fixtures.matching(RetrievalFilters.from_iso("2026-03-01", "2026-03-31"))
    assert found == ["late"]


async def test_bounds_are_not_shifted_by_the_session_timezone(fixtures):
    """A naive bound is read in the database session's timezone. These two
    articles sit either side of a UTC midnight — a shifted bound moves one of
    them across the boundary."""
    await fixtures.add("just-before", published_at=datetime(2026, 2, 28, 23, 59, tzinfo=timezone.utc))
    await fixtures.add("just-after", published_at=datetime(2026, 3, 1, 0, 1, tzinfo=timezone.utc))
    found = await fixtures.matching(RetrievalFilters.from_iso("2026-03-01", "2026-03-31"))
    assert found == ["just-after"]


async def test_an_open_ended_window_only_bounds_one_side(fixtures):
    await fixtures.add("old", published_at=MARCH - timedelta(days=90))
    await fixtures.add("new", published_at=MARCH)
    assert await fixtures.matching(RetrievalFilters.from_iso("2026-03-01", None)) == ["new"]
    assert await fixtures.matching(RetrievalFilters.from_iso(None, "2026-03-31")) == ["new", "old"]


# ── sections, as publishers actually store them ───────────────────

async def test_slug_matches_the_publishers_display_name(fixtures):
    """This is the defect behind "the index is too narrow": the filter asked
    for "us-news" and the column held "US news", so it matched nothing."""
    await fixtures.add("guardian", section="US news")
    await fixtures.add("nyt", section="U.S.")
    await fixtures.add("other", section="Technology")

    found = await fixtures.matching(RetrievalFilters(sections=["us-news"]))
    assert found == ["guardian", "nyt"]


async def test_section_group_reaches_every_desk_carrying_the_subject(fixtures):
    await fixtures.add("usnews", section="US news")
    await fixtures.add("politics", section="Politics")
    await fixtures.add("opinion", section="Opinion")
    await fixtures.add("sport", section="Sport")

    found = await fixtures.matching(RetrievalFilters(sections=related_sections("us-news")))
    assert found == ["opinion", "politics", "usnews"]


async def test_unrelated_sections_stay_out(fixtures):
    await fixtures.add("tech", section="Technology")
    await fixtures.add("sport", section="Sport")
    assert await fixtures.matching(RetrievalFilters(sections=["sport"])) == ["sport"]


# ── the filters reach the actual search path ──────────────────────

async def test_keyword_search_honours_the_window(fixtures):
    await fixtures.add("inside", published_at=MARCH)
    await fixtures.add("outside", published_at=MARCH.replace(month=6))
    results = await keyword_search(
        fixtures.db,
        "inquiry findings",
        filters=fixtures.scoped(RetrievalFilters.from_iso("2026-03-01", "2026-03-31")),
    )
    assert [scored.chunk.article_id.split("/", 1)[1] for scored in results] == ["inside"]


async def test_keyword_search_honours_the_section(fixtures):
    await fixtures.add("usnews", section="US news")
    await fixtures.add("tech", section="Technology")
    results = await keyword_search(
        fixtures.db,
        "inquiry findings",
        filters=fixtures.scoped(RetrievalFilters(sections=["us-news"])),
    )
    assert [scored.chunk.article_id.split("/", 1)[1] for scored in results] == ["usnews"]
