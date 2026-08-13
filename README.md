# News AI

A production-ready AI news research assistant. It searches live reporting from **The Guardian** and **The New York Times**, indexes it into a vector store, and answers natural-language questions with **grounded, citation-backed answers** — summaries, comparisons, timelines and follow-ups — falling back to the open web only when the newsrooms can't answer.

**Repository:** https://github.com/AJKumarReddy/Agentic-News-app

```
React + TypeScript + Vite + Tailwind  →  FastAPI + LangGraph + pgvector  →  Guardian · NYT · Tavily · OpenAI
```

---

## Contents

- [Architecture](#architecture) · [Design decisions](#key-design-decisions)
- [Quick start](#quick-start-local) · [Configuration](#configuration)
- [How it works](#how-it-works): [routing](#1-routing--the-understand-step) · [RAG](#2-the-rag-pipeline) · [citations](#3-citation-integrity)
- [News sources](#news-sources) · [Scheduled ingestion](#scheduled-ingestion)
- [Interface](#interface) · [API](#backend-api) · [Testing](#testing)
- [Deployment](#deployment): [production on ECS Fargate](#production-codepipeline--ecr--ecs-fargate) · [local Docker Compose](#local-docker-compose)
- [Security checklist](#security-checklist-production) · [Troubleshooting](#troubleshooting)

---

## Architecture

```mermaid
flowchart TB
    U[User Browser] --> F[React Frontend<br/>Vite · Tailwind · light/dark]
    F -- HTTPS REST + SSE --> N[Load balancer<br/>ALB in prod · Vite proxy in dev]
    N --> B[FastAPI<br/>Gunicorn + Uvicorn · Docker]

    B --> AG[LangGraph Agent]
    B --> PG[(PostgreSQL 16 + pgvector<br/>articles · chunks · chats)]
    B --> R[(Redis — cache + locks)]
    B --> SCH[Ingestion<br/>in-process in dev · scheduled task in prod]

    AG --> UN[understand<br/>resolve · route · build queries]
    UN --> SRC[Sources]
    SRC --> G[Guardian Content API]
    SRC --> NY[NY Times API]
    UN --> WEB[Tavily web search<br/>gated · cited separately]

    SRC --> RAG[RAG Engine]
    RAG --> CH[Chunk 600–1000 tok]
    RAG --> EM[OpenAI embeddings]
    RAG --> HY[Hybrid retrieval<br/>vector + keyword + recency + edition]
    HY --> PG
    HY --> RR[Rerank + source diversity]
    RR --> LLM[OpenAI chat model]
    WEB --> LLM
    LLM --> C[Cited answer<br/>real publisher URLs]
```

## Key design decisions

| Decision | Choice | Why |
|---|---|---|
| Vector DB | **PostgreSQL + pgvector** | One database serves relational data *and* vectors — simplest, cheapest and transactional on a single instance. `rag/vector_store.py` is small enough to swap for Qdrant if scale demands it. |
| Agent | **LangGraph, four modes** | `understand` resolves the message, then routes to ARTICLE / NEWS / WEB / BOTH. Each mode does only its own work, so an article question never touches the search machinery. Bounded and debuggable — no runaway autonomy. |
| Query resolution | **Resolve before searching** | Follow-ups ("search youtube for related news", "now do a google search") are rewritten against the conversation *first*. Searching the raw words was the single largest source of wrong answers. |
| Multi-source | **Adapter per publisher** | Every source returns the same `NormalizedArticle`, so retrieval, chunking, citations and the UI are source-agnostic. Adding a newsroom is one adapter. |
| Fair ranking | **Per-source retrieval** | Publishers expose wildly different text lengths (NYT gives abstracts only). A shared candidate pool silently excluded NYT entirely, so retrieval runs per source and merges. |
| Web fallback | **Tavily, gated** | Results exclude our own publishers' domains, must pass relevance/recency/low-signal-domain gates, and are cited separately. Disabled entirely without `TAVILY_API_KEY`. |
| Edition | **US desk preferred** | Guardian `productionOffice` is stored per article and nudges ranking. A nudge, not a filter — a better UK/AUS match still wins. |
| Freshness | **API-first for "latest/today"** | Recency questions are answered from *current* API results indexed on the fly, never from stale vectors with high semantic scores. |
| Dedup | **Article ID + SHA-256 content hash** | An article is embedded once; re-embedding only when content or the embedding model changes. |
| Streaming | **Server-Sent Events** | Route decision, pipeline status and answer tokens stream into the UI. |

## Repository layout

```
├── frontend/               React + TS + Vite + Tailwind
│   └── src/
│       ├── components/     Sidebar, chat, cards, citations, theme toggle
│       ├── pages/          Chat · Search · Article intelligence
│       ├── hooks/          useChat (SSE), useTheme
│       ├── services/       API client
│       └── constants/      section taxonomy
├── backend/
│   ├── app/
│   │   ├── api/            chat · news · rag · health routers
│   │   ├── agents/         graph, understand (resolve+route), dateparse, tools
│   │   ├── sources/        NewsSource abstraction · Guardian · NYT · registry
│   │   ├── guardian/       Guardian client, normalizer, shared models
│   │   ├── websearch/      Tavily client + quality gates
│   │   ├── rag/            chunker · embeddings · vector store · retrieval · reranker · ingestion
│   │   ├── database/       SQLAlchemy models, session, repositories
│   │   ├── llm/            chat model factory, prompts (grounding rules)
│   │   ├── services/       chat orchestration/SSE, search, article intelligence, cache
│   │   ├── tasks/          scheduler, ingest_recent, edition backfill
│   │   └── core/           config, JSON logging, security middleware
│   ├── tests/              110 tests
│   └── evaluation/         20-question RAG evaluation harness
├── aws/                    ECS Fargate task definitions + production deployment guide
├── scripts/                health-check.sh · guardian_api_smoke.py
├── .github/workflows/      test.yml  (tests only — deployment is CodePipeline)
├── buildspec.yml           AWS CodeBuild spec (builds + pushes both images)
├── docker-compose.yml      local dev: postgres · redis · backend · frontend
└── .env.example
```

## Quick start (local)

Prerequisites: Docker Desktop, plus API keys — [Guardian](https://open-platform.theguardian.com/access/) (free), [OpenAI](https://platform.openai.com/), optionally [NYT](https://developer.nytimes.com/) and [Tavily](https://tavily.com) (both free tiers).

```bash
git clone https://github.com/AJKumarReddy/Agentic-News-app.git
cd Agentic-News-app
cp .env.example .env        # fill in the keys
docker compose up -d --build
```

- Frontend: http://localhost:3000
- API health: http://localhost:8000/api/health
- API docs (dev only): http://localhost:8000/docs

**Without Docker** — run Postgres and Redis in containers, everything else on the host:

```bash
docker compose up -d postgres redis          # DATABASE_URL/REDIS_URL → localhost
cd backend && python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
.venv/Scripts/uvicorn app.main:app --reload  # :8000
cd ../frontend && npm install && npm run dev # :5173, proxies /api
```

> Changing `tailwind.config.js` requires a **dev-server restart** — Vite hot-reloads CSS but not that config, and a stale config shows up as "class does not exist" or a blank page.

## Configuration

Full list in [.env.example](.env.example). The ones that matter:

| Variable | Purpose |
|---|---|
| `GUARDIAN_API_KEY` · `NYT_API_KEY` | publishers; a source with no key is skipped, so the app runs on whichever keys exist |
| `ENABLED_SOURCES` | active publishers in priority order (`guardian,nyt`) |
| `OPENAI_API_KEY` · `CHAT_MODEL` · `EMBEDDING_MODEL` | generation and embeddings |
| `TAVILY_API_KEY` | optional web fallback; empty = newsroom-only, no web request ever made |
| `WEB_SEARCH_THRESHOLD` | newsroom sources at or below this count trigger a web top-up |
| `DATABASE_URL` · `REDIS_URL` | infrastructure |
| `INGEST_ENABLED` · `INGEST_INTERVAL_MINUTES` · `INGEST_SECTIONS_PER_TICK` | scheduled pulls (default: on, one section every 5 min — 288 requests/day, under the 500 cap) |
| `PREFERRED_PRODUCTION_OFFICE` · `EDITION_BOOST` | Guardian desk to favour (default `US`) |
| `RAG_INITIAL_TOP_K` · `RAG_FINAL_TOP_K` | retrieval funnel (20 → 6) |
| `RERANKER` | `llm` (default) · `cohere` · `none` |
| `FRONTEND_URL` · `EXTRA_CORS_ORIGINS` | CORS allowlist — never `*` in production |
| `API_KEY` · `VITE_API_KEY` | optional `X-API-Key` gate for private deployments |
| `RATE_LIMIT_PER_MINUTE` · `CHAT_RATE_LIMIT_PER_MINUTE` | per-IP budgets (30 / 10) |

**Never commit** `.env`, API keys, database passwords, AWS credentials or SSH keys — all covered by [.gitignore](.gitignore).

---

## How it works

### 1. Routing — the `understand` step

One LLM call resolves the message *and* routes it. Inspect its decision without spending a chat turn:

```bash
curl -X POST http://localhost:8000/api/intent -H "Content-Type: application/json" \
  -d '{"message":"what do other outlets say about the merger"}'
```

| Route | When | Path |
|---|---|---|
| `ARTICLE` | About the article you're viewing | Reads that article — no search, no filters |
| `NEWS` | News and current events (default) | Publisher fetch → retrieve → rerank |
| `WEB` | Not news (how-to, definitions, docs), or "search the web" | Web search only |
| `BOTH` | Needs reporting plus outside context | Newsroom retrieval, then web |

Resolution is the important half. `"search for related news on youtube"` becomes *"related news about UK manufacturers facing cyber-attacks"* — the subject comes from the conversation, and the instruction is handled separately. Naming a site always reaches the web and bypasses the low-signal domain filter: ask for YouTube, get YouTube.

The route, intent and resolved question appear as a badge above every answer.

### 2. The RAG pipeline

```
publisher APIs → normalize → dedup (id + content hash) → chunk (~800 tok, 15% overlap)
              → embed (batched) → pgvector
              → hybrid retrieve (cosine + Postgres FTS, fused with RRF)
              → recency + edition boost → rerank → source diversity → top ~6
```

- **Date handling** is deterministic ("this week", "last 3 months" → exact ranges), not left to the model.
- **Narrow windows widen rather than fail.** A "today" query early in the publishing day matches nothing; retrieval relaxes to 14 days, then to everything, and the UI shows a *"Results from Last 14 days"* badge — the answer itself never editorialises about the search window.
- **Incremental only.** The whole index is never rebuilt; an article is embedded once and re-embedded only if its content hash or the embedding model changes.

### 3. Citation integrity

This is the part most likely to mislead a reader, so it's enforced end to end:

- Web results **exclude our publishers' own domains**, so they can never duplicate or impersonate indexed journalism.
- Every source carries a `type` (`publisher` / `web`), its publisher name and machine id, sharing **one citation numbering scheme**.
- Newsroom and web evidence get **separate context budgets** — long full-text chunks were otherwise starving web sources out of the prompt entirely, which caused the model to invent attributions.
- **Attribution must match the citation.** If a Guardian article reports what Reuters found, the answer must say "The Guardian reports that Reuters found… [1]" — never "Reuters reported… [1]", which implies Reuters is the cited source.
- **Citation density scales with the answer.** A single-article reply cites once; a multi-source synthesis cites per claim.
- NYT entries are **abstracts, not full articles**, and the prompt says so, so the model never implies it read the whole piece.
- The UI renders web citations in amber with a `Web · domain` label, distinct from newsroom citations.

---

## News sources

| Source | Coverage | Notes |
|---|---|---|
| **The Guardian** | Full article bodies, all sections, deep archive | The richest evidence; `productionOffice` enables US-desk preference |
| **The New York Times** | Headlines, abstracts and lead paragraphs | The API exposes **no article bodies** — evidence is short by design |
| **Tavily (web)** | Everything else | Supplementary only, gated and cited separately |

**NYT specifics worth knowing:**

- NYT enables each API **per key**. A key valid for Top Stories may be rejected by Article Search. The adapter detects a 401 once, remembers it, and falls back to Top Stories rather than dropping NYT entirely — enable "Article Search API" for your app at [developer.nytimes.com](https://developer.nytimes.com/) to unlock keyword search of the archive.
- A keyword-less section browse uses **Top Stories** directly, since Article Search would otherwise be asked for the literal word "news".
- Rate limits are tight (~5 req/min, 500/day); requests are throttled and responses cached.
- Its `multimedia` field has shipped as a list of objects, a list of strings and a dict — all three are handled.

Because NYT chunks are an order of magnitude shorter than full-text ones, **retrieval runs per source and merges**, and a diversity pass guarantees each publisher a foothold. Without it, answers silently became single-source.

## Scheduled ingestion

Locally the backend pulls fresh articles **every 5 minutes** while it runs — no cron required.

```bash
# manual run — sweeps every section, for a cold index or an external scheduler
docker compose exec backend python -m app.tasks.ingest_recent
```

**In production the in-process loop is off** (`INGEST_ENABLED=false` on the ECS services): every
Fargate replica would otherwise run its own copy, and cron work tied to long-running replicas
stops whenever the service scales down or redeploys. An **EventBridge Scheduler** runs the same
module as a one-shot Fargate task every 30 minutes, reusing the backend task definition with
only the command overridden. Same code, same request budget — see
[aws/ECS_PIPELINE.md](aws/ECS_PIPELINE.md).

A tick refreshes **one section** and cycles through the six, because the request budget is the binding constraint: each section costs one request per publisher and developer keys cap at **500 requests/day**. One section every 5 minutes is 288/day — in budget, with every section current within 30 minutes. Sweeping all six on that interval would be 1,728/day, and the overage fails quietly (a rejected fetch is logged and returns empty, so the index just stops moving). Keep `(1440 / INGEST_INTERVAL_MINUTES) × INGEST_SECTIONS_PER_TICK` under 500 when tuning, or set `INGEST_ENABLED=false` to drive ingestion externally.

Under multiple Gunicorn workers a short-lived **Redis lock** ensures exactly one worker performs each run, so publisher API usage isn't multiplied by the worker count. The rotation is derived from the clock rather than in-process state, so every worker resolves the same slice for a tick and a restart resumes the cycle in place. The lock fails open: a Redis outage still ingests rather than silently freezing the index. A failed run is logged and retried on the next tick.

## Interface

**Three pages**, all responsive, in **light or dark theme** (follows your OS until you choose, then persists per browser):

- **Chat** — streaming answers with a route badge, inline citation chips and a grouped source list
- **Search** — 18 sections across three groups, date range, sort, per-publisher filter chips, real pagination (`Page 1 of 50 · 131,819 results`)
- **Article intelligence** — AI summary, key points, entities, topics, important dates, related coverage, and "Ask AI about this article"

Chats are scoped to an anonymous per-browser id (`X-Client-Id`), so one visitor never sees another's history; individual chats and the whole history can be deleted from the sidebar.

## Backend API

| Endpoint | Description |
|---|---|
| `POST /api/chat` | agentic chat; `{"message", "conversation_id?", "article_id?", "stream": true}` → SSE (`state`, `route`, `status`, `token`, `sources`, `notice`, `done`, `error`) or JSON with `stream:false` |
| `POST /api/intent` | routing decision only — no search, no answer, nothing written |
| `GET /api/news/search` | multi-source search: `q, from_date, to_date, section, order_by, page, page_size, sources` |
| `GET /api/news/sources` | active publishers, for the UI's filter |
| `GET /api/news/article/{id}` | normalized article (index first, then publisher API) |
| `GET /api/news/article/{id}/intelligence` | AI analysis + related coverage |
| `POST /api/rag/retrieve` | hybrid retrieval with metadata filters |
| `POST /api/rag/ingest` | index by article ids and/or a search query |
| `GET /api/conversations` · `GET /api/conversations/{id}` | chat history, scoped to `X-Client-Id` |
| `DELETE /api/conversations/{id}` · `DELETE /api/conversations` | delete one chat / clear history |
| `GET /api/health` | database, vector extension, cache and each publisher |

## Testing

```bash
cd backend && pytest -q     # 110 tests
cd frontend && npm test     # 17 tests
```

Covers the Guardian and NYT adapters (mocked HTTP), chunking, dedup, RRF fusion, edition boost, source diversity, reranking, routing and resolution, the scheduler's lock, security middleware, API contracts, the SSE parser and citation components.

**RAG evaluation** — 20 questions against a running stack with real keys:

```bash
cd backend && python evaluation/run_eval.py --base-url http://localhost:8000
```

Checks citation presence, real publisher URLs, honest refusals on unanswerable questions (anti-hallucination), routing accuracy and follow-up context retention.

---

## Deployment

Production runs on **AWS ECS Fargate**, deployed by CodePipeline. Docker Compose is the local
development stack and is not used in production.

### Production: CodePipeline → ECR → ECS Fargate

```
Developer ──► git push main ──► GitHub ──► CodePipeline ──► CodeBuild
                                                                │
                                            Docker images ──► Amazon ECR
                                                                │
                                                        Amazon ECS Fargate
                                                                │
                                                  Application Load Balancer (HTTPS)
                                                     ├── /api/*  ──► backend  :8000
                                                     └── /*      ──► frontend :80
```

Behind the backend service:

```
Backend
 ├── Amazon RDS PostgreSQL + pgvector      DATABASE_URL
 ├── Amazon ElastiCache Redis              REDIS_URL
 ├── SSM Parameter Store / Secrets Manager all API keys, injected at task start
 ├── Amazon CloudWatch Logs                /ecs/guardian-backend · /ecs/guardian-frontend
 └── Guardian · NYT · Tavily · OpenAI
```

| Piece | Where |
|---|---|
| Build spec (ECR login, both images, commit-SHA tags, `imagedefinitions-*.json`) | [`buildspec.yml`](buildspec.yml) |
| Fargate task definitions (`awsvpc`, backend :8000, frontend :80, `awslogs`, SSM secrets) | [`aws/taskdef-backend.json`](aws/taskdef-backend.json) · [`aws/taskdef-frontend.json`](aws/taskdef-frontend.json) |
| Full setup: VPC, security groups, RDS, ElastiCache, IAM, ALB, services, scheduler, pipeline | **[aws/ECS_PIPELINE.md](aws/ECS_PIPELINE.md)** |

Notes that matter in production:

- **Secrets never live in the repo, images or task definitions** — the task definitions carry
  SSM parameter ARNs and ECS injects the values at task start.
- **Postgres and Redis are managed services**, not containers in the task. The application is
  unchanged: it still reads `DATABASE_URL` and `REDIS_URL`.
- **ALB idle timeout must be ~300 s** — `/api/chat` streams over SSE and the 60 s default cuts
  long answers off mid-stream.
- **`INGEST_ENABLED=false` on the services**; ingestion is an EventBridge-scheduled Fargate task.
- **RDS and ElastiCache are never publicly accessible** — private data subnets, security groups
  that only accept traffic from the ECS tasks.

Rough cost: ALB + 2 Fargate services + RDS + ElastiCache ≈ **$80–120/month** at the smallest
sensible sizes.

### Local: Docker Compose

```bash
docker compose up -d --build
```

Services: `postgres` (pgvector), `redis`, `backend`, `frontend`. Postgres and Redis bind to
loopback only.

**Where your data lives:** the Docker volume `project_postgres-data` (`/var/lib/docker/volumes/project_postgres-data/_data`, inside the Docker VM). It survives `docker compose down`; only `down -v` destroys it. Back up with:

```bash
docker exec project-postgres-1 pg_dump -U guardian guardian_news > backup.sql
```

Article text and embeddings are rebuildable from the APIs — conversations are the only irreplaceable data.

### CI/CD

Two systems, cleanly split — **GitHub Actions tests, CodePipeline deploys**:

- **GitHub Actions ([`test.yml`](.github/workflows/test.yml))** — every push and pull request:
  backend pytest + import validation, frontend vitest + production build, both Docker image
  builds. No AWS credentials, no deployment secrets in GitHub at all.
- **AWS CodePipeline** — every push to `main`: CodeBuild runs [`buildspec.yml`](buildspec.yml),
  pushes both images to ECR tagged with the commit SHA, and two ECS deploy actions roll the
  backend and frontend services. New tasks must pass the target-group health check
  (`/api/health` for the backend) before the old ones drain.

The only GitHub-side configuration is a **CodeConnections/CodeStar connection** authorizing AWS
to read the repository — created once and approved in the console.

### Scaling further

| Concern | Next step |
|---|---|
| Traffic | Raise `desired-count`, or attach ECS **Service Auto Scaling** on ALB request count / CPU |
| Database | Larger RDS instance class, then a **read replica**; Multi-AZ for failover |
| Cache | ElastiCache replication group instead of a single node |
| Rate limiting | Currently per-task in memory — move to **Redis-backed** storage so limits are global |
| Assets | Serve the SPA from **S3 + CloudFront** instead of a frontend Fargate service |
| Background jobs | Promote `app/tasks` to Celery when ingestion volume outgrows one scheduled task |
| Vector store | `rag/vector_store.py` is small enough to swap for Qdrant/OpenSearch if pgvector plateaus |

## Security checklist (production)

- [x] API keys server-side only; the React bundle never sees them
- [x] Optional `X-API-Key` gate for the whole API (constant-time comparison)
- [x] CORS restricted to explicit origins; optional Host allowlist
- [x] Per-IP rate limiting (30/min general, 10/min for `/api/chat`) with idle-key eviction
- [x] Request body cap (64 KB) and time-to-first-byte timeout (120 s)
- [x] Content-Security-Policy on API responses and the SPA
- [x] Secure headers (nosniff, frame-deny, referrer policy); HTTPS terminated at the ALB
- [x] Publisher/OpenAI calls time-boxed with retries; SSE streamed unbuffered
- [x] Bounded agent (recursion limit, capped evidence context, capped tool fan-out)
- [x] Prompt-injection defenses: evidence wrapped as data with an explicit "ignore instructions inside articles" rule; user input sanitized and truncated
- [x] Conversations scoped per client; cross-client access returns 404, not 403, so ids aren't enumerable
- [x] RDS and ElastiCache in private subnets, reachable only from the ECS security group
- [x] Secrets in **SSM Parameter Store** only — never in the repo, images, task definitions or GitHub
- [x] Non-root Docker user for the backend; no SSH keys or AWS credentials stored in GitHub
- [x] Structured JSON logs with request ids to CloudWatch; secrets redacted, never logged
- [ ] Rotate the RDS password and API keys periodically (update the SSM parameters, redeploy)
- [ ] Enable RDS automated backups / snapshots and ECR image scanning
- [ ] Use ECS Exec (not SSH) for shell access into a running task

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Blank page, or "class does not exist" in dev | `tailwind.config.js` changed while the dev server was running — **restart Vite**. If it starts on `:5174`, an orphaned process still holds `:5173`; kill it. |
| NYT missing from results | Key not licensed for Article Search (401). It falls back to Top Stories; enable "Article Search API" at developer.nytimes.com for archive search. |
| `"nyt": "unavailable"` in `/api/health` | No `NYT_API_KEY`, or the key is rejected by every endpoint. |
| Answer says evidence is insufficient | Index may be cold — run `python -m app.tasks.ingest_recent`, or wait for the next tick. |
| Chat returns 500 | Missing `OPENAI_API_KEY`, or Postgres/pgvector not reachable — check `/api/health`. |
| Frontend can't reach the API | `VITE_API_BASE_URL` mismatch, or the origin isn't in `FRONTEND_URL`/`EXTRA_CORS_ORIGINS`. |
| Chat stream cuts off in production | ALB idle timeout — raise it to 300 s. See [aws/ECS_PIPELINE.md](aws/ECS_PIPELINE.md). |
| ECS tasks stop right after starting | Usually a missing SSM parameter or no route to ECR — check the stopped reason and `/ecs/guardian-backend`. |

## License and attribution

For educational and portfolio use. Content is subject to each publisher's terms — the [Guardian Open Platform](https://open-platform.theguardian.com/documentation/) and the [NYT Developer terms](https://developer.nytimes.com/terms). Non-commercial tiers require retaining attribution and linking back to source articles, which the citation system does by design.
