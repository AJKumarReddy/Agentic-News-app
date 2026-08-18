from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Article, Chunk, Conversation, Message
from app.guardian.models import NormalizedArticle
from app.sources.sections import related_sections, section_match_values


def _section_column():
    """`Article.section` canonicalised the same way the slug is."""
    return func.lower(func.regexp_replace(Article.section, r"[^a-zA-Z0-9]", "", "g"))


def to_normalized(row: Article) -> NormalizedArticle:
    """Stored row -> the canonical shape the rest of the app speaks."""
    return NormalizedArticle(
        article_id=row.article_id,
        headline=row.headline,
        section=row.section,
        author=row.author,
        published_at=row.published_at,
        url=row.url,
        thumbnail=row.thumbnail,
        trail_text=row.trail_text,
        body_text=row.body_text,
        tags=row.tags or [],
        source=row.source,
        source_id=row.source_id,
        production_office=row.production_office,
        retrieved_at=row.retrieved_at,
        content_hash=row.content_hash,
    )


class ArticleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, article_id: str) -> Article | None:
        return await self.session.get(Article, article_id)

    async def get_many(self, article_ids: list[str]) -> list[Article]:
        if not article_ids:
            return []
        result = await self.session.execute(select(Article).where(Article.article_id.in_(article_ids)))
        return list(result.scalars())

    async def upsert(self, normalized: NormalizedArticle) -> Article:
        article = await self.get(normalized.article_id)
        if article is None:
            article = Article(article_id=normalized.article_id)
            self.session.add(article)
        article.headline = normalized.headline
        article.section = normalized.section
        article.author = normalized.author
        article.published_at = normalized.published_at
        article.url = normalized.url
        article.thumbnail = normalized.thumbnail
        article.trail_text = normalized.trail_text
        article.body_text = normalized.body_text
        article.tags = normalized.tags
        article.production_office = normalized.production_office
        article.source = normalized.source
        article.source_id = normalized.source_id
        article.retrieved_at = normalized.retrieved_at
        return article

    async def search_stored(
        self,
        *,
        source_id: str,
        query: str = "",
        section: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        order_by: str = "newest",
        page: int = 1,
        page_size: int = 12,
    ) -> tuple[list[Article], int]:
        """Previously fetched articles for one publisher.

        This is what the site falls back to when a publisher cannot be reached.
        It is deliberately a plain relational query — the vector index answers
        "what is this about", but a section browse only needs "what do we have".
        """
        filters = [Article.source_id == source_id]
        if section:
            # widened to the section's subject neighbours, like RAG retrieval
            wanted: list[str] = []
            for related in related_sections(section):
                wanted.extend(section_match_values(related))
            if wanted:
                filters.append(_section_column().in_(list(dict.fromkeys(wanted))))
        if from_date:
            filters.append(Article.published_at >= from_date)
        if to_date:
            filters.append(Article.published_at <= to_date)
        if query:
            like = f"%{query}%"
            filters.append(
                or_(
                    Article.headline.ilike(like),
                    Article.trail_text.ilike(like),
                )
            )

        total = await self.session.scalar(
            select(func.count()).select_from(Article).where(*filters)
        )
        # undated rows sort last either way, matching the live merge
        ordering = (
            Article.published_at.asc().nullslast()
            if order_by == "oldest"
            else Article.published_at.desc().nullslast()
        )
        rows = await self.session.execute(
            select(Article)
            .where(*filters)
            .order_by(ordering)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars()), int(total or 0)

    async def mark_indexed(self, article: Article, content_hash: str, embedding_model: str, chunk_count: int) -> None:
        now = datetime.now(timezone.utc)
        if article.first_indexed_at is None:
            article.first_indexed_at = now
        article.last_checked_at = now
        article.content_hash = content_hash
        article.embedding_model = embedding_model
        article.chunk_count = chunk_count

    async def touch_checked(self, article: Article) -> None:
        article.last_checked_at = datetime.now(timezone.utc)


class ChunkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def delete_for_article(self, article_id: str) -> None:
        await self.session.execute(delete(Chunk).where(Chunk.article_id == article_id))

    async def add_all(self, chunks: list[Chunk]) -> None:
        self.session.add_all(chunks)


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, title: str = "New chat", user_id: str = "") -> Conversation:
        conversation = Conversation(title=title[:256], user_id=user_id[:64])
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get(self, conversation_id: str, user_id: str = "") -> Conversation | None:
        """Fetch a conversation, but only for the client that owns it."""
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is not None and conversation.user_id != user_id:
            return None
        return conversation

    async def list_recent(self, user_id: str = "", limit: int = 20) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def delete(self, conversation_id: str, user_id: str = "") -> bool:
        """Delete one conversation (and its messages, via cascade).
        Returns False when it doesn't exist or belongs to another client."""
        conversation = await self.get(conversation_id, user_id=user_id)
        if conversation is None:
            return False
        await self.session.delete(conversation)
        return True

    async def delete_all(self, user_id: str) -> int:
        """Delete every conversation owned by this client. Returns the count."""
        result = await self.session.execute(
            delete(Conversation).where(Conversation.user_id == user_id)
        )
        return result.rowcount or 0

    async def add_message(self, conversation: Conversation, role: str, content: str, sources: list | None = None) -> Message:
        message = Message(
            conversation_id=conversation.id, role=role, content=content, sources=sources or []
        )
        self.session.add(message)
        conversation.updated_at = datetime.now(timezone.utc)
        return message

    async def get_messages(self, conversation_id: str, limit: int = 50) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def get_message(self, conversation_id: str, message_id: int) -> Message | None:
        """One message, scoped to the conversation it belongs to.

        Message ids are sequential integers, so scoping by conversation is what
        stops a caller reading somebody else's message by guessing one — the
        conversation itself is ownership-checked by `get` before this runs.
        """
        result = await self.session.execute(
            select(Message).where(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
            )
        )
        return result.scalars().first()

    async def get_recent_messages(self, conversation_id: str, n: int = 8) -> list[Message]:
        """Last n messages in chronological order, without loading the full history."""
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(n)
        )
        return list(reversed(list(result.scalars())))
