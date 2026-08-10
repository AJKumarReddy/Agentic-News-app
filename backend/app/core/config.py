from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    guardian_api_key: str = ""
    guardian_page_size: int = 20

    # New York Times (Article Search API). Empty key disables the source.
    nyt_api_key: str = ""
    # Active publishers, in priority order
    enabled_sources: str = "guardian,nyt"

    # Tavily web search — supplementary sources when Guardian evidence is thin.
    # Empty key disables web search entirely (Guardian-only mode).
    tavily_api_key: str = ""
    web_search_max_results: int = 5
    # Guardian evidence at or below this count triggers a web-search top-up
    web_search_threshold: int = 2

    openai_api_key: str = ""
    chat_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    database_url: str = "postgresql+asyncpg://guardian:guardian@localhost:5432/guardian_news"
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300

    frontend_url: str = "http://localhost:3000"
    extra_cors_origins: str = ""

    rag_initial_top_k: int = 20
    rag_final_top_k: int = 6
    # Guardian editorial desk to favour in ranking: US | UK | AUS | "" (none).
    # This is a ranking preference, not a filter — other editions still surface
    # when they are the better match.
    preferred_production_office: str = "US"
    edition_boost: float = 0.02
    chunk_target_tokens: int = 800
    chunk_overlap_tokens: int = 120
    reranker: str = "llm"  # llm | cohere | none
    cohere_api_key: str = ""

    max_agent_iterations: int = 6

    # Security layer
    rate_limit_per_minute: int = 30
    chat_rate_limit_per_minute: int = 10
    api_key: str = ""  # optional X-API-Key gate; empty = disabled
    allowed_hosts: str = ""  # comma-separated Host allowlist; empty = any
    max_body_bytes: int = 65536
    request_timeout_seconds: int = 120

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def cors_origins(self) -> list[str]:
        origins = [self.frontend_url.rstrip("/")]
        origins += [o.strip().rstrip("/") for o in self.extra_cors_origins.split(",") if o.strip()]
        return sorted(set(origins))

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
