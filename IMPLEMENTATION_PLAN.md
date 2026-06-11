# Implementation Plan — Beacon

## Goal

Build a **local-first, API-driven internal knowledge base** with semantic search (pgvector) and RAG-powered chat (Ollama). Everything runs locally — no data leaves the machine.

> **Project name: Beacon**
> Each step below is independently **runnable and testable**. We don't move to the next step until you've verified the current one. If a step fails, we fix only that step.

---

## Locked Design Decisions

| # | Decision |
|---|---|
| 1 | Tags → `TEXT[]` + GIN index |
| 2 | Embedding input → `title + problem_description + solution` concatenated |
| 3 | Contact info → `JSONB` column |
| 4 | `created_by` → optional (nullable FK) |
| 5 | Search → semantic + optional tag filter |
| 6 | Top-k → default 5, max 20 |
| 7 | Chat card selection → client-driven (pass card IDs) |
| 8 | Chat statefulness → client-managed history |
| 9 | Ollama model → configurable via `.env`, default `llama3.1:8b` |
| 10 | Chat with creator → separate `GET /cards/{id}/creator` endpoint |
| 11 | Auth → none (v1) |
| 12 | User management → open CRUD |
| 13 | Embedding on update → auto-regenerate on content change |
| 14 | Health check → DB + Ollama + embedding model |
| 15 | Runtime → Postgres in Docker, app + Ollama native |

---

## Project Structure (final state)

```
Beacon/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── card.py
│   │   └── user.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── card.py
│   │   └── user.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── cards.py
│   │   ├── users.py
│   │   ├── search.py
│   │   ├── chat.py
│   │   └── health.py
│   └── services/
│       ├── __init__.py
│       ├── embedding.py
│       ├── search.py
│       └── chat.py
├── tests/
│   ├── test_step_03_db.py
│   ├── test_step_04_user_model.py
│   ├── test_step_05_card_model.py
│   └── test_step_08_embedding.py
├── .env
├── .gitignore
├── requirements.txt
└── docker-compose.yml
```

> The `tests/` folder contains standalone test scripts (not pytest suites). Each one can be run directly with `python tests/test_step_XX_*.py` and prints clear PASS/FAIL output. They exist purely to verify each step independently.

---

## Step 1 — Infrastructure Setup

**Goal:** Get Postgres + pgvector running in Docker, install all Python dependencies.

### Files

#### [NEW] docker-compose.yml
- `pgvector/pgvector:pg16` image
- Port `5432` → localhost
- Named volume `beacon_pgdata` for persistence
- DB name: `beacon`, user: `beacon`, password: `beacon`

#### [NEW] .env
```env
DATABASE_URL=postgresql+asyncpg://beacon:beacon@localhost:5432/beacon
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

#### [NEW] .gitignore
- `__pycache__/`, `*.pyc`, `venv/`, `.env`, `*.egg-info`

#### [NEW] requirements.txt
```
fastapi[standard]
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
pgvector
pydantic-settings
sentence-transformers
httpx
python-dotenv
```

### How to test

```bash
# 1. Start Postgres
docker compose up -d

# 2. Verify it's running
docker compose ps
# → should show beacon container as "running"

# 3. Connect to it directly
docker exec -it beacon-db psql -U beacon -d beacon -c "SELECT 1;"
# → should return 1

# 4. Verify pgvector extension is available
docker exec -it beacon-db psql -U beacon -d beacon -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extname FROM pg_extension WHERE extname = 'vector';"
# → should show "vector"

# 5. Create venv and install deps
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

✅ **Pass criteria:** Postgres is running, pgvector extension loads, all pip packages install without errors.

---

## Step 2 — App Configuration

**Goal:** Centralized settings loaded from `.env` via Pydantic.

### Files

#### [NEW] app/__init__.py
- Empty init file.

#### [NEW] app/config.py
- `class Settings(BaseSettings)` with fields: `DATABASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM` (int), `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `model_config = SettingsConfigDict(env_file=".env")`
- `get_settings()` function with `@lru_cache`

### How to test

```bash
python -c "from app.config import get_settings; s = get_settings(); print(f'DB: {s.DATABASE_URL}'); print(f'Model: {s.EMBEDDING_MODEL}'); print(f'Dim: {s.EMBEDDING_DIM}'); print(f'Ollama: {s.OLLAMA_BASE_URL}')"
```

✅ **Pass criteria:** Prints all 4 values correctly from `.env`. Changing a value in `.env` and re-running reflects the change.

---

## Step 3 — Database Connection Layer

**Goal:** Async SQLAlchemy engine + session factory + a test script that proves connectivity.

### Files

#### [NEW] app/database.py
- `Base = declarative_base()` (shared base for all models)
- `engine = create_async_engine(settings.DATABASE_URL)`
- `AsyncSessionLocal = async_sessionmaker(engine)`
- `async def get_db()` — yields an `AsyncSession`, used as a FastAPI dependency
- `async def init_db()` — runs `CREATE EXTENSION IF NOT EXISTS vector`, then `create_all()` to sync tables

#### [NEW] tests/test_step_03_db.py
- Standalone async script that:
  1. Imports `engine` from `app.database`
  2. Runs `SELECT 1` using `engine.connect()`
  3. Prints `"✅ DB connection OK"` or `"❌ DB connection FAILED"` with the error

### How to test

```bash
python tests/test_step_03_db.py
```

✅ **Pass criteria:** Prints `✅ DB connection OK`. If Postgres isn't running, prints a clear error message.

---

## Step 4 — User Database Model

**Goal:** Create the `users` table in Postgres and verify CRUD at the ORM level (no API yet).

### Files

#### [NEW] app/models/__init__.py
- Imports `User` and `ProblemCard` (card imported later, guarded)

#### [NEW] app/models/user.py
- `class User(Base)` with columns: `id` (UUID, PK), `name`, `email` (unique), `department` (nullable), `contact_info` (JSONB, default `{}`), `created_at`
- Relationship to `ProblemCard` (added when card model exists)

#### [NEW] tests/test_step_04_user_model.py
- Standalone async script that:
  1. Calls `init_db()` to create tables
  2. Inserts a test user (`name="Alice"`, `email="alice@test.com"`, `department="Engineering"`, `contact_info={"slack": "@alice"}`)
  3. Reads it back by email
  4. Prints the user's fields
  5. Deletes it
  6. Confirms deletion

### How to test

```bash
python tests/test_step_04_user_model.py
```

✅ **Pass criteria:** Creates user, reads it back with correct fields, deletes it, confirms it's gone. Also: check `docker exec -it beacon-db psql -U beacon -d beacon -c "\d users"` to verify the table schema.

---

## Step 5 — ProblemCard Database Model (with pgvector)

**Goal:** Create the `problem_cards` table with a `vector(384)` column, GIN index on tags, HNSW index on embedding.

### Files

#### [NEW] app/models/card.py
- `class ProblemCard(Base)` with columns: `id` (UUID, PK), `title`, `problem_description` (Text), `solution` (Text), `outcome` (Text, nullable), `tags` (ARRAY(Text)), `embedding` (Vector(384), nullable), `created_by` (FK → users.id, nullable), `created_at`, `updated_at`
- GIN index on `tags`
- HNSW index on `embedding` with cosine distance ops

#### [MODIFY] app/models/__init__.py
- Now imports both `User` and `ProblemCard`
- Add relationship between User ↔ ProblemCard

#### [NEW] tests/test_step_05_card_model.py
- Standalone async script that:
  1. Calls `init_db()` to create/update tables
  2. Inserts a card with `tags=["networking", "dns"]`, `embedding=None`
  3. Reads it back, prints fields
  4. Inserts a card linked to a user via `created_by`
  5. Reads the card and accesses `card.creator.name`
  6. Cleans up

### How to test

```bash
python tests/test_step_05_card_model.py
```

✅ **Pass criteria:** Both cards created and read back correctly. Foreign key relationship works. Verify schema: `docker exec -it beacon-db psql -U beacon -d beacon -c "\d problem_cards"` — should show `vector(384)` column and indices.

---

## Step 6 — FastAPI App Skeleton + Basic Health Endpoint

**Goal:** A running FastAPI server with one endpoint (`GET /health`) that checks DB connectivity.

### Files

#### [NEW] app/main.py
- FastAPI app with `lifespan` context manager → calls `init_db()` on startup
- CORS middleware (allow all for dev)
- Includes the `health` router
- Title: "Beacon API"

#### [NEW] app/routers/__init__.py
- Empty init.

#### [NEW] app/routers/health.py
- `GET /health` → pings DB with `SELECT 1`, returns `{ "status": "healthy", "database": "connected", "card_count": N }`
- If DB is down → returns `503` with `{ "status": "unhealthy", "database": "disconnected", "error": "..." }`

### How to test

```bash
# Start the server
uvicorn app.main:app --reload --port 8000

# In another terminal:
curl http://localhost:8000/health
# → {"status":"healthy","database":"connected","card_count":0}

# Also open: http://localhost:8000/docs
# → Should show interactive Swagger UI with the /health endpoint
```

✅ **Pass criteria:** Server starts, `/health` returns 200 with DB status, `/docs` renders the Swagger UI. Stop Postgres → `/health` returns 503.

---

## Step 7 — Users CRUD (Schemas + Router)

**Goal:** Full REST API for managing users.

### Files

#### [NEW] app/schemas/__init__.py
- Empty init.

#### [NEW] app/schemas/user.py
- `UserCreate`: `name`, `email` (EmailStr), `department` (optional), `contact_info` (dict, default `{}`)
- `UserUpdate`: all fields optional
- `UserResponse`: all fields + `id`, `created_at`; `model_config = ConfigDict(from_attributes=True)`

#### [NEW] app/routers/users.py
| Endpoint | Description |
|---|---|
| `POST /users` | Create user; 409 if email already exists |
| `GET /users` | List users (paginated: `skip`, `limit`) |
| `GET /users/{id}` | Get by ID; 404 if not found |
| `PUT /users/{id}` | Partial update; 404 if not found |
| `DELETE /users/{id}` | Delete; 404 if not found |

#### [MODIFY] app/main.py
- Add `users` router

### How to test

```bash
# Create a user
curl -X POST http://localhost:8000/users -H "Content-Type: application/json" -d "{\"name\": \"Alice\", \"email\": \"alice@example.com\", \"department\": \"Engineering\", \"contact_info\": {\"slack\": \"@alice\"}}"
# → 201 with user object including UUID

# List users
curl http://localhost:8000/users

# Update
curl -X PUT http://localhost:8000/users/<uuid> -H "Content-Type: application/json" -d "{\"department\": \"Platform\"}"

# Duplicate email → 409 Conflict
curl -X POST http://localhost:8000/users -H "Content-Type: application/json" -d "{\"name\": \"Bob\", \"email\": \"alice@example.com\"}"

# Delete → 200, then GET → 404
curl -X DELETE http://localhost:8000/users/<uuid>
curl http://localhost:8000/users/<uuid>
```

✅ **Pass criteria:** All 5 CRUD operations work. Duplicate email returns 409. Missing ID returns 404.

---

## Step 8 — Embedding Service

**Goal:** Load `sentence-transformers` model locally and embed text. No API dependency, no rate limits.

### Files

#### [NEW] app/services/__init__.py
- Empty init.

#### [NEW] app/services/embedding.py
- Loads `SentenceTransformer(settings.EMBEDDING_MODEL)` at module level (lazy singleton)
- `embed_text(text: str) → list[float]` — encodes a single string, returns vector
- `embed_card_content(title, problem_description, solution) → list[float]` — concatenates with `\n`, then embeds
- `is_model_loaded() → bool` — returns True if model object exists (for health check)

#### [NEW] tests/test_step_08_embedding.py
- Standalone script that:
  1. Calls `embed_text("How do I fix a DNS resolution failure?")`
  2. Prints vector length (should be 384)
  3. Calls `embed_card_content(title="DNS Issue", problem="Can't resolve hostnames", solution="Flush DNS cache")`
  4. Computes cosine similarity between two related sentences vs two unrelated ones
  5. Prints both scores (related should be higher)

### How to test

```bash
python tests/test_step_08_embedding.py
```

Expected output:
```
Vector length: 384
Card vector length: 384
Similarity (related):   0.82
Similarity (unrelated): 0.19
✅ Embedding service OK
```

✅ **Pass criteria:** Vector is 384-dim, related sentences have higher similarity than unrelated ones.

---

## Step 9 — Cards CRUD with Auto-Embedding

**Goal:** Full REST API for problem cards. Embedding is automatically generated on create, and regenerated when content fields change on update.

### Files

#### [NEW] app/schemas/card.py
- `CardCreate`: `title`, `problem_description`, `solution`, `outcome` (optional), `tags` (list, default `[]`), `created_by` (UUID, optional)
- `CardUpdate`: all fields optional
- `CardResponse`: all fields + `id`, `created_at`, `updated_at`, `has_embedding` (bool, computed)

#### [NEW] app/routers/cards.py
| Endpoint | Description |
|---|---|
| `POST /cards` | Create card → auto-embed → save; 400 if `created_by` doesn't exist |
| `GET /cards` | List cards (paginated); optional `?tag=` filter |
| `GET /cards/{id}` | Get by ID; 404 if not found |
| `GET /cards/{id}/creator` | Get creator info; 404 if card not found; returns `null` fields if no creator |
| `PUT /cards/{id}` | Update card; re-embed only if `title`, `problem_description`, or `solution` changed |
| `DELETE /cards/{id}` | Delete card |

#### [MODIFY] app/main.py
- Add `cards` router

### How to test

```bash
# Create card WITH creator → has_embedding: true
# Create card WITHOUT creator → created_by: null, has_embedding: true
# GET /cards/{id}/creator → returns user contact info
# GET /cards?tag=kubernetes → filtered results
# PUT with content change → embedding regenerated
# PUT with tags-only change → embedding unchanged
```

✅ **Pass criteria:** Cards CRUD works. `has_embedding` is `true` after creation. Creator endpoint returns correct user. Tag filtering works. Content updates regenerate embedding; tag-only updates don't.

---

## Step 10 — Search Service + Endpoint

**Goal:** Semantic similarity search over card embeddings using pgvector, with optional tag filtering.

### Files

#### [NEW] app/services/search.py
- `async def semantic_search(query, db, top_k=5, tags=None) → list[dict]`
  1. Embeds the query via `embed_text()`
  2. Builds SQLAlchemy query using cosine distance operator (`<=>`)
  3. If `tags` provided, adds overlap filter (`&&` operator)
  4. Filters out cards with `embedding IS NULL`
  5. Orders by distance ascending, limits to `top_k`
  6. Returns list of `{ card, similarity_score }` (score = `1 - distance`)

#### [NEW] app/routers/search.py
| Endpoint | Description |
|---|---|
| `POST /search` | Body: `{ query: str, top_k: int = 5, tags: list[str] = [] }` → ranked cards with scores |

- `top_k` clamped to `1..20`
- Response: list of `{ card: CardResponse, similarity_score: float }`

#### [MODIFY] app/main.py
- Add `search` router

### How to test

```bash
# Semantic search — relevant card should rank first
curl -X POST http://localhost:8000/search -H "Content-Type: application/json" -d "{\"query\": \"hostname resolution not working\"}"

# With tag filter
curl -X POST http://localhost:8000/search -H "Content-Type: application/json" -d "{\"query\": \"hostname resolution not working\", \"tags\": [\"kubernetes\"]}"

# Off-topic query → low scores
curl -X POST http://localhost:8000/search -H "Content-Type: application/json" -d "{\"query\": \"how to deploy a React app\"}"

# Custom top_k
curl -X POST http://localhost:8000/search -H "Content-Type: application/json" -d "{\"query\": \"server issues\", \"top_k\": 2}"
```

✅ **Pass criteria:** Relevant cards rank higher than irrelevant ones. Tag filtering narrows results. Scores between 0 and 1. Empty DB returns empty list.

---

## Step 11 — Ollama Chat Service

**Goal:** Connect to Ollama, send a prompt with card context, get a response. Non-streaming first — verify the RAG logic before adding SSE.

### Files

#### [NEW] app/services/chat.py
- `build_context(cards) → str` — formats cards into numbered context blocks
- `build_messages(context, query, history) → list[dict]` — system prompt + history + final user message
- `async def chat(query, card_ids, history, db) → dict` — non-streaming; calls Ollama with `stream=false`
- `async def chat_stream(query, card_ids, history, db) → AsyncGenerator` — streaming; yields tokens

#### [NEW] tests/test_step_11_chat.py
- Standalone async script that:
  1. Creates 2 test cards in DB (with embeddings)
  2. Calls `chat()` with their IDs and a related question → prints response
  3. Calls `chat()` with an off-topic question → verifies model refuses
  4. Cleans up test cards

### How to test

```bash
ollama pull llama3.1:8b
curl http://localhost:11434/api/tags  # verify Ollama is running

python tests/test_step_11_chat.py
```

✅ **Pass criteria:** Ollama responds with a grounded answer. Off-topic question gets a refusal. Response includes model name.

---

## Step 12 — Chat Streaming Endpoint (SSE)

**Goal:** Expose RAG chat as a streaming SSE endpoint.

### Files

#### [NEW] app/routers/chat.py
| Endpoint | Description |
|---|---|
| `POST /chat` | Body: `{ query: str, card_ids: list[UUID], history: list[{role, content}] = [] }` → `StreamingResponse` (SSE) |

- Validates all `card_ids` exist → 400 if any missing
- Validates `card_ids` is not empty → 400
- Streams tokens as `data: {"token": "..."}\n\n`
- Final event: `data: {"done": true, "model": "...", "cards_used": N}\n\n`
- Ollama unreachable → 503

#### [MODIFY] app/main.py
- Add `chat` router

### How to test

```bash
# Streaming — tokens arrive one by one
curl -N -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d "{\"query\": \"How was the DNS issue resolved?\", \"card_ids\": [\"<card-uuid>\"]}"

# Invalid card ID → 400
# Empty card_ids → 400
# Multi-turn with history → coherent follow-up
```

✅ **Pass criteria:** Tokens stream in real-time. Invalid/empty card IDs return 400. Ollama down returns 503. Multi-turn history works.

---

## Step 13 — Full System Health Check

**Goal:** Upgrade `/health` to check all three system dependencies.

### Files

#### [MODIFY] app/routers/health.py
- Checks: DB (`SELECT 1`), Ollama (`GET /api/tags`), Embedding model (`is_model_loaded()`)
- Returns `200` only if all three healthy, `503` with per-component detail if any is down

### How to test

```bash
curl http://localhost:8000/health
# → 200, all components green

# Kill Ollama → 503, ollama.status = "disconnected"
# Stop Postgres → 503, database.status = "disconnected"
```

✅ **Pass criteria:** Accurate per-component status. 200 when all up, 503 with details when anything is down.

---

## Step 14 — README + Final Wiring

**Goal:** Documentation and final end-to-end verification.

### Files

#### [NEW] README.md
- Project overview
- Prerequisites (Docker, Python 3.11+, Ollama)
- Quick start (5 commands)
- API reference (all endpoints with examples)
- Architecture diagram (text-based)

#### Final Verification
- Cold start: `docker compose up -d` → `pip install -r requirements.txt` → `uvicorn app.main:app` → `GET /health` → all green
- Full workflow: create user → create cards → search → chat → get creator info

---

## Build Order Summary

| Step | What | Key Test |
|---|---|---|
| 1 | Infrastructure | Postgres running, pgvector loads, pip installs |
| 2 | Config | Print settings from `.env` |
| 3 | Database layer | `SELECT 1` succeeds |
| 4 | User model | Insert + read + delete user via ORM |
| 5 | Card model | Insert card with tags + FK, vector column exists |
| 6 | FastAPI + basic health | `GET /health` → 200, `/docs` renders |
| 7 | Users CRUD | Full CRUD, 409 on dupe email, 404 on missing |
| 8 | Embedding service | 384-dim vectors, semantic similarity correct |
| 9 | Cards CRUD | Auto-embed, tag filter, creator endpoint |
| 10 | Search | Semantic ranking correct, tag filter works |
| 11 | Chat service | Grounded answer, off-topic refusal |
| 12 | Chat endpoint | SSE streaming, error handling |
| 13 | Full health | All 3 components checked |
| 14 | README + polish | Cold start works end-to-end |

> We move to step N+1 **only** after you've tested and approved step N. If any step fails, we fix that step in isolation.
