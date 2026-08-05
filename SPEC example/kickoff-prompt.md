# Kickoff prompt

Copy everything below this line into a fresh AI agent session.

---

I'm building **Ethara Seat Allocation & Project Mapping System** — find any employee's seat, project, and floor in seconds, for ~5,000 people across 5 floors.

Below this folder are the 6 source-of-truth docs. Treat them as authoritative. If you need to deviate, ask first.

**Authority order (highest to lowest)**: PRD → TRD → Backend Schema → Implementation Plan → App Flow → UI/UX Brief.

## Your job

1. Read all 6 docs in `docs/vibecoding/` before writing code.
2. Start with **Phase 1** of `docs/vibecoding/06-implementation-plan.md`.
3. After completing each phase, stop and confirm done criteria are met before starting the next.
4. If you hit ambiguity, ask one clarifying question rather than guessing.
5. Update the relevant doc whenever scope changes — don't let docs and code drift.

## Docs

- `docs/vibecoding/01-PRD.md` — product
- `docs/vibecoding/02-TRD.md` — stack
- `docs/vibecoding/03-app-flow.md` — screens and journeys
- `docs/vibecoding/04-uiux-brief.md` — visual language
- `docs/vibecoding/05-backend-schema.md` — data + auth
- `docs/vibecoding/06-implementation-plan.md` — build order

## House rules

- Don't add libraries not listed in TRD § Key libraries without asking.
- Don't suppress compiler or lint errors. No silencing the type system to make red turn green.
  - TypeScript: no `any`, `@ts-ignore`, or `@ts-expect-error` to silence the compiler.
  - Python: no `# type: ignore` without a justifying comment on the same line.
- Each commit leaves the build green.
- Match existing patterns once the codebase has any — don't re-pick conventions per file.
- Don't invent product or visual decisions. If it's not in a doc, ask.
- Test-first for every business rule and endpoint (RED → GREEN → real-surface proof).

## Project-specific must-nots

- Never allocate a Reserved/Maintenance/Occupied seat.
- Never allow two active allocations for one seat or one employee (enforced by partial-unique indexes — don't remove them).
- Never hard-delete an employee — `DELETE /employees/{id}` deactivates and releases their seat.
- Keep the AI assistant answerable with zero external API (`AI_PROVIDER=none`); the LLM is optional.

## Start here

Before writing any code: read the 6 docs, then post your **Phase 1 plan** back to me as a numbered todo list. Wait for my `go` before implementing.
