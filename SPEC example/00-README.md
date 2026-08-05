# Vibecoding docs — Ethara Seat Allocation & Project Mapping System

The 6 briefing documents an AI coding agent needs to build the Ethara Seat Allocation & Project Mapping System. Each doc owns one concern. Together they're the contract.

| # | Doc | Owns |
|---|---|---|
| 01 | [PRD](01-PRD.md) | Product scope, users, features, success |
| 02 | [TRD](02-TRD.md) | Stack, libraries, env vars, hosting |
| 03 | [App Flow](03-app-flow.md) | Pages, navigation, user journeys, states |
| 04 | [UI/UX Brief](04-uiux-brief.md) | Visual language, color, type, motion |
| 05 | [Backend Schema](05-backend-schema.md) | Tables, relationships, auth, indexes |
| 06 | [Implementation Plan](06-implementation-plan.md) | Build order, phases, done criteria |

## Source of truth

This project implements the **Vibe Coding Assessment: Ethara Seat Allocation & Project Mapping System** brief (`../../Vibe Coding Assessment- Ethara Seat Allocation & Project Mapping System.pdf`). Where these docs and the PDF disagree, the PDF's functional requirements win; these docs resolve everything the PDF left open.

## How to use these with an agent

1. Open `kickoff-prompt.md`
2. Copy the entire contents into a fresh AI agent session
3. Tell the agent to start with **Phase 1** of the Implementation Plan
4. Keep these docs updated when scope changes — they are living source of truth

## Conflict resolution

If any two docs disagree, authority order is:

**01 PRD → 02 TRD → 05 Backend Schema → 06 Implementation Plan → 03 App Flow → 04 UI/UX Brief**

The PRD wins over everything else. Visual decisions never override product or data decisions.

## Open decisions

Search this folder for `TODO:` to find unresolved choices. Resolve before starting the relevant phase. As of generation there are none — all decisions are locked below.

## Locked decisions (from intake)

- **Frontend**: Vite + React 18 + TypeScript + Tailwind CSS (SPA against a standalone REST API)
- **Backend**: Python 3.12 + FastAPI (run in Docker; host Python is 3.9, so Docker is the canonical runtime)
- **Database**: SQLite for local demo, PostgreSQL for deploy — one `DATABASE_URL` switch, SQLAlchemy 2.0 + Alembic
- **Auth**: custom JWT, role-based (`admin` = HR/Admin, `employee`), seeded logins
- **AI assistant**: deterministic rule-based intent parser as primary; optional LLM adapter (OpenAI/Claude/Gemini) auto-activates if an API key is set
- **Deployment**: build + verify locally via docker-compose now; ship all deploy artifacts; go live together at the end

## Status

- Generated: 2026-07-10
- Last updated: 2026-07-10
