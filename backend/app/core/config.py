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

    # TheNewsAPI (api.thenewsapi.com) — an aggregator over thousands of
    # outlets rather than one masthead. Empty key disables the source.
    thenewsapi_api_key: str = ""
    #: Articles per request. The free plan hard-caps this at 3 and rejects
    #: anything larger, so the adapter clamps to whatever is set here.
    thenewsapi_page_size: int = 3
    #: Requests per UTC day. The free plan allows 100, and the scheduled
    #: ingestion would spend that by mid-morning on its own (288 ticks/day),
    #: leaving nothing for anyone actually using the site.
    thenewsapi_daily_budget: int = 100
    #: Of that budget, how much is held back for requests a person is waiting
    #: on. Background ingestion stops at budget - reserve; interactive search
    #: keeps going to the full budget.
    thenewsapi_interactive_reserve: int = 40

    # Active publishers, in priority order
    enabled_sources: str = "guardian,nyt,thenewsapi"

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
    # Most chunks any single article may contribute to one answer. A live blog
    # or a daily round-up is one article covering a dozen unrelated stories, so
    # a broad question ("top US news today") matches its chunks over and over
    # and every claim ends up citing that one piece. Capping the contribution
    # is what makes a multi-story answer cite multiple articles.
    rag_max_chunks_per_article: int = 2
    # How much wider than the candidate pool to read from the database before
    # the cap is applied. The cap discards chunks, so without headroom a
    # dominant article shrinks the pool instead of sharing it. Costs one wider
    # SQL read — no extra embedding or LLM call, since the pool is trimmed
    # before reranking.
    rag_candidate_overfetch: int = 3
    # Round-up questions ("top US news today") are answered from many articles
    # rather than many passages: one chunk each, so every story listed carries
    # its own citation pointing at the article that reported it. Depth is the
    # wrong shape here — a reader wants seven stories and seven links, not
    # seven paragraphs of one live blog.
    rag_roundup_top_k: int = 10
    # Round-up evidence is trimmed to each article's opening, so that many
    # articles fit the evidence budget instead of four full-text chunks.
    rag_roundup_chunk_chars: int = 1200
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

    # Text-to-speech for answer playback. Two independent gates govern this:
    # `tts_enabled` decides whether the feature exists at all, and the reader's
    # own preference (held in the browser, off by default) decides whether it
    # ever speaks. Enabled here costs nothing until somebody opts in.
    tts_enabled: bool = True
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "alloy"
    tts_format: str = "mp3"
    # Delivery steering. Only the gpt-4o speech models accept this; it is
    # dropped for the tts-1 family, which rejects the parameter.
    tts_instructions: str = "Read as a news presenter: measured, neutral, unhurried."
    tts_max_chars: int = 8000  # ceiling on one answer's audio spend
    tts_chunk_chars: int = 3800  # under the API's per-request input cap
    # Audio is three orders of magnitude larger than the JSON this cache
    # otherwise holds, and Redis runs allkeys-lru — a long TTL would evict the
    # article and search entries that keep the site up when a publisher is
    # unreachable. The browser cache carries the long tail instead.
    tts_cache_ttl_seconds: int = 3600

    # Speech-to-text for asking questions out loud. The mirror of the block
    # above, and gated the same way: `stt_enabled` decides whether the feature
    # exists, and nothing is ever recorded until the reader presses the button.
    stt_enabled: bool = True
    stt_model: str = "gpt-4o-mini-transcribe"
    # Empty means auto-detect. Naming the language is both cheaper and more
    # accurate when a deployment knows its audience speaks one.
    stt_language: str = ""
    # The recording is held in memory while it uploads, so this is the real
    # ceiling on the endpoint, not the duration below. Roughly ten minutes of
    # Opus; the browser stops well before it.
    stt_max_bytes: int = 8_388_608
    # The browser stops recording here. A forgotten open microphone would
    # otherwise run until it hit the byte cap and came back as a 413.
    stt_max_seconds: int = 60

    # Scheduled ingestion: keeps the index current without an external cron
    ingest_enabled: bool = True
    ingest_interval_minutes: int = 5
    ingest_start_delay_seconds: int = 60
    # sections refreshed per tick; interval × this must stay under the
    # publishers' 500 requests/day developer cap (see rotating_sections)
    ingest_sections_per_tick: int = 1

    # Security layer
    rate_limit_per_minute: int = 30
    chat_rate_limit_per_minute: int = 10
    # Answer playback gets its own budget rather than sharing the chat one.
    # With autoplay on, every turn is a chat request *and* an audio request —
    # on a shared bucket that halves usable chat throughput, and the 429 reads
    # to the user as the chat being broken rather than as voice being throttled.
    audio_rate_limit_per_minute: int = 20
    api_key: str = ""  # optional X-API-Key gate; empty = disabled
    # Proxies between the client and this process, counted from the right of
    # X-Forwarded-For. 1 = a single ALB/nginx (the default deployment), 2 =
    # CDN in front of it, 0 = reached directly, trust no forwarding header.
    # Anything left of these hops is written by the caller and cannot be
    # trusted — reading the wrong end makes the rate limiter bypassable.
    trusted_proxy_hops: int = 1
    # Gate for operator-only endpoints (/api/rag/*, /api/intent). These spend
    # publisher quota and OpenAI credit, and no part of the UI calls them.
    # Empty in production closes them entirely; empty in development leaves
    # them open so the tooling still works locally.
    admin_api_key: str = ""
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
