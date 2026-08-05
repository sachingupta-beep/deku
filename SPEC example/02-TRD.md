# 02 — TRD: Ethara Seat Allocation & Project Mapping System

The stack. Locked-in decisions so the agent doesn't re-pick libraries every file.

## Platform

Web app: React SPA frontend + standalone FastAPI REST backend + SQL database. Deployed as two services (static frontend + API) plus a managed database.

## Frontend

- **Framework**: React 18 (Vite)
- **Language**: TypeScript (strict)
- **Styling**: Tailwind CSS v3 (+ a small design-token layer; no component library lock-in, headless primitives only where needed)
- **State / data fetching**: TanStack Query (React Query) for server state; React Context for auth/session
- **Routing**: React Router v6
- **Forms**: react-hook-form
- **Validation**: Zod (shared request/response shapes)
- **Charts**: Recharts (dashboard project/floor utilization)
- **HTTP**: typed `fetch` wrapper with JWT injection + 401 handling

## Backend

- **Runtime / framework**: Python 3.12 + FastAPI + Uvicorn (ASGI). Host Python is 3.9, so the **Docker image (`python:3.12-slim`) is the canonical runtime**; code is kept 3.9-safe via `from __future__ import annotations` regardless.
- **API style**: REST (JSON), auto OpenAPI/Swagger at `/docs` and ReDoc at `/redoc`
- **Validation**: Pydantic v2 (settings + request/response models)
- **Background jobs**: none in v1 (allocation is synchronous + transactional)

## Database

- **Engine**: SQLite (local demo) / PostgreSQL (deploy) — chosen via `DATABASE_URL`
- **Provider**: local file `./ethara.db` for dev; Render/Railway managed Postgres for prod
- **Client / ORM**: SQLAlchemy 2.0 (typed, `Mapped[...]`)
- **Migrations tool**: Alembic (forward-only)
- **Notes**: partial unique index enforces "one active allocation per seat" and "one active allocation per employee"; on SQLite this uses a filtered unique index, mirrored in Postgres.

## Auth

- **Provider**: custom (in-app), no third-party
- **Methods**: email + password (seeded accounts)
- **Session**: stateless JWT (HS256), 8h expiry; sent as `Authorization: Bearer <token>`
- **Password hashing**: passlib[bcrypt]
- **Roles**: `admin` (HR/Admin/Growth — full mutate), `employee` (read + AI query)

## Hosting & deploy

- **Frontend**: Vercel or Netlify (static build; `VITE_API_BASE_URL` points at the API)
- **Backend**: Render or Railway (Docker container from `backend/Dockerfile`)
- **Database**: Render/Railway managed Postgres (prod); SQLite file (local)
- **Static assets / CDN**: platform default (Vercel/Netlify edge)
- **Local**: `docker-compose up` runs Postgres + backend + frontend together for parity

## Third-party services

| Service | Purpose | Tier |
|---|---|---|
| OpenAI / Anthropic / Gemini API | Optional LLM adapter for the AI assistant | Pay-as-you-go (optional; off by default) |
| Render / Railway | Backend + Postgres hosting | Free/Hobby |
| Vercel / Netlify | Frontend hosting | Free |

## Key libraries

- Backend: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `alembic`, `pydantic>=2`, `pydantic-settings`, `passlib[bcrypt]`, `pyjwt`, `python-multipart` (CSV upload), `psycopg[binary]` (prod), `pytest`, `httpx` (test client)
- Frontend: `react`, `react-dom`, `react-router-dom`, `@tanstack/react-query`, `react-hook-form`, `zod`, `recharts`, `tailwindcss`, `clsx`

## Env vars

Variable NAMES only. Never paste values into source-controlled docs.

- **Vite / frontend** → public prefix `VITE_*` (baked into the client bundle)
- **Python / backend** → everything secret by default, load via `.env`, never commit

```
# Frontend — public (safe to expose in client bundle)
VITE_API_BASE_URL

# Backend — secret (server-only)
DATABASE_URL              # sqlite:///./ethara.db  OR  postgresql+psycopg://...
JWT_SECRET                # signing key for HS256
JWT_EXPIRE_MINUTES        # default 480
CORS_ORIGINS              # comma-separated allowed origins
AI_PROVIDER               # none | openai | anthropic | gemini  (default: none -> rule-based)
AI_API_KEY                # only if AI_PROVIDER != none
AI_MODEL                  # optional model override
SEED_ON_STARTUP           # true|false — auto-seed empty DB on boot (default false)
```

## Observability

- **Error reporting**: none-yet (structured stdout logging; Sentry-ready hook left as TODO)
- **Logs**: stdout (captured by Render/Railway/Vercel platform logs)
- **Uptime / health**: `GET /health` endpoint for platform health checks

## Constraints

- Free-tier friendly (SQLite local, Postgres free tier prod).
- Must handle the full seed volume (5,000 employees / 6,000 seats) with responsive dashboard queries — aggregations use indexed `GROUP BY`, seeding uses bulk inserts.
- AI assistant must work with **zero external dependencies** (rule-based default); LLM is strictly optional.

## Folder structure

```
ethara-seat-allocation/            # = repo root (this directory)
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app + router mounting + CORS + /health
│   │   ├── config.py              # Pydantic settings from env
│   │   ├── database.py            # engine, session, Base
│   │   ├── models/                # SQLAlchemy models (employee, project, seat, allocation, user)
│   │   ├── schemas/               # Pydantic request/response models
│   │   ├── routers/               # employees, projects, seats, dashboard, ai, auth
│   │   ├── services/              # allocation engine, dashboard aggregates, search
│   │   ├── auth/                  # jwt, password hashing, deps (require_admin)
│   │   └── ai/                    # intent parser + LLM adapter
│   ├── seeds/seed.py              # deterministic bulk seed (5k emp / 6k seats / 12 proj)
│   ├── tests/                     # pytest (business rules, endpoints, AI, concurrency)
│   ├── alembic/                   # migrations
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/                   # typed API client + hooks
│   │   ├── components/            # ui primitives, layout, tables, charts
│   │   ├── pages/                 # Login, Dashboard, Employees, Seats, Projects, Assistant
│   │   ├── hooks/                 # useAuth, useDebounce
│   │   ├── lib/                   # zod schemas, formatters
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── .env.example
├── docker-compose.yml             # postgres + backend + frontend
├── render.yaml / railway config   # backend deploy
├── vercel.json / netlify.toml     # frontend deploy
├── README.md
├── AI_PROMPTS.md
└── docs/vibecoding/               # these docs
```

## Coding conventions

- Python: snake_case, Ruff lint + format, type hints everywhere, services pure/testable.
- TypeScript: PascalCase components, camelCase functions, absolute imports via `@/` alias, ESLint + Prettier.
- Tests: backend in `backend/tests/` (pytest); frontend colocated `*.test.tsx` where useful.
- Every commit leaves build + tests green.

---
*If a library or service isn't in this doc, the agent must ask before adding it.*
