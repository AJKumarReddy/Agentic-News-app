from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Article, Chunk, Conversation, Message
from app.guardian.models import NormalizedArticle


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
        article.source = normalized.source
        article.retrieved_at = normalized.retrieved_at
        return article

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

    async def get_recent_messages(self, conversation_id: str, n: int = 8) -> list[Message]:
        """Last n messages in chronological order, without loading the full history."""
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(n)
        )
        return list(reversed(list(result.scalars())))
