# Deku — Measuring Whether AI Can Build Real, Working Software

**One line:** Deku is a benchmark that gives an AI agent a written product spec, lets it build the entire application from scratch, then **deploys that app and tests it like a real user** to score how much of it actually works.

---

## 1. Why this matters

Today's AI coding tools are measured on *toy* tasks: "fix this bug," "make this unit test pass." But the thing customers actually want is **zero-to-one**: *"Here's what I need — build me the app."* No benchmark measured that, because measuring it is hard — you have to actually run the software and check whether it *works*, not just whether the code looks right.

Deku measures exactly that. It answers the question every buyer of AI coding tools is really asking:

> **"If I hand an AI a spec, how much of a working product do I get back?"**

Whoever can answer that credibly owns the conversation on AI software engineering.

---

## 2. What Deku is, in one paragraph

Deku is an **evaluation platform**. Each *task* is a realistic product brief (e.g. "a habit tracker with login, streaks, and a dashboard"). An AI agent reads the brief and **builds the complete app** — frontend, backend, database wiring — inside an isolated sandbox with real backing services: a real database, a real authentication server, a real email server, object storage, and an in-house payments service. Deku then **deploys the app and grades its behavior**: it drives the live UI like a human, and independently checks the data behind the scenes. The output is a single score from 0 to 1 — *the fraction of the product's user journeys that genuinely work.*

---

## 3. The big picture

```
   INPUT: a task                AGENT BUILDS               EVALUATION
 ┌───────────────────┐    ┌────────────────────┐    ┌──────────────────────────┐
 │ • product spec     │    │  AI agent, in a     │    │  1. Is it deployed?      │
 │ • real services    │──► │  sandbox, writes    │──► │  2. Drive the UI (browser)│──► SCORE
 │ • hidden test plan │    │  the whole app +    │    │  3. Check the data (API) │    0.0 – 1.0
 │ • reference answer │    │  deploys it live    │    │  4. Aggregate → reward   │
 └───────────────────┘    └────────────────────┘    └──────────────────────────┘
        (authored          (produces a full app +          (grades behavior,
         by our team)        a recorded "trajectory")        not source code)
```

Three actors, cleanly separated:
- **The task** — authored by our team (the spec + the grading plan + a reference solution).
- **The agent** — the AI under test (any model / any coding agent can be plugged in).
- **The evaluator** — Deku's automated grader.

---

## 4. Anatomy of a task (the input)

Every task is a self-contained package:

| Piece | What it is |
|---|---|
| **The spec** (`instruction.md`) | The product brief the agent reads — features, screens, data model, API contract, deployment rules. |
| **The environment** (`environment/`) | The real backing services the app needs — database, authentication, storage, email, payments — started automatically. |
| **The hidden test plan** (`workflows.yaml`) | A checklist of real user journeys ("sign in → add an item → see it appear"). The agent never sees this. |
| **The graders** (`tests/`) | The code that drives the browser and checks the data. |
| **The reference solution** (`solution/`) | A known-good implementation, used to prove the task is fair and solvable before any AI is tested on it. |

**Difficulty is a dial, not luck.** The same product can be made harder by swapping in a less-common technology (e.g. a familiar database vs. an obscure one), so we can build a smooth ladder from easy to expert across thousands of tasks.

---

## 5. How it works — the pipeline, stage by stage

### Stage 1 — Set up a realistic world
Deku spins up an isolated sandbox and starts the app's backing services (a real Postgres database, a real auth server, etc.). This is a **production-like environment**, not mocks — so passing means the app works for real, not just in theory.

### Stage 2 — The agent builds the app
The AI agent reads the spec and works like an engineer: it writes files, runs commands, installs dependencies, and stands up a running application — all inside the sandbox. Every step it takes is recorded as a **trajectory** (a complete transcript of how it built the app). When it's done, a full working application exists: frontend, backend, and data.

### Stage 3 — Evaluation (the heart of Deku)
Here's what makes Deku trustworthy: **it grades behavior, not code.** A separate grader:

1. **Deploy gate** — Is the app actually up and reachable? If not, it scores zero. No running app, no credit.
2. **Browser test** — An automated tester **drives the real UI like a person**: signs in, clicks buttons, fills forms, and checks what appears on screen.
3. **Data test** — Independently checks the database and API to confirm the actions had the *right effect* (the item was really saved, the streak really updated, another user's data is really protected).
4. **Quality review** — An automated reviewer rates design, usability, and polish (advisory only — see §6).

Because Deku deploys the app and uses it, it can't be fooled by code that *looks* correct but doesn't run. **The only way to score is to actually work.**

---

## 6. How the score works

The app is graded on **user journeys** ("workflows"), each made of small verifiable steps ("substeps"):

```
A journey passes  ⇄  ≥90% of its steps pass  AND  every critical step passes
Final score       =  (journeys that fully passed) ÷ (total journeys)
```

So a score of **0.82** means *"82% of the product's user journeys genuinely work."* Simple, honest, and directly meaningful to a non-technical stakeholder.

Two design principles keep the number trustworthy:
- **The quality reviewer never moves the score.** Design polish is reported, but the reward is driven only by *did it actually work* — because a "looks nice" score is easy to game.
- **"We couldn't measure it" ≠ "it failed."** If grading is interrupted (e.g. an infrastructure hiccup), the run is flagged as **invalid and set aside**, never counted as an AI failure. This keeps the data clean.

---

## 7. What makes it credible (and hard to fake)

This is the moat. Anyone can write a quiz; a *trustworthy* benchmark requires engineering rigor:

- **Behavior-based grading** — we run the app and use it; we don't read the source. Working software is the only thing that scores.
- **Anti-gaming by design** — the agent never sees the test plan; graders check real side effects, not superficial output; security rules (one user can't touch another's data) are enforced and tested.
- **Built for reproducibility** — a fixed grader model and version-pinned environments, so results hold up over time.
- **Full audit trail** — runs capture the built app, a screen-by-screen record of grading, and complete logs, so any score can be independently reviewed.
- **Realistic surface area** — real databases, authentication, email, and storage, plus an in-house payments service, so the benchmark reflects the messiness of production, not a sandbox toy.

---

## 8. Why it's valuable (three business uses)

1. **Measure & compare** — a credible, apples-to-apples score for any AI model or coding agent on real product-building. The scoreboard everyone wants to be on.
2. **Improve the models** — successful build trajectories become **training data** to make AI coding agents better (the benchmark doubles as a data engine).
3. **Optimize the product** — systematically test which prompts, tools, and agent designs produce more working software.

In short: it's both the **ruler** the industry measures itself with **and** the **factory** that produces the data to get better.

---

## 9. Status & roadmap (honest)

**Implemented — the platform end to end:** realistic environments, the agent build loop, behavior-based grading (browser + data), the scoring engine, and a complete audit/debug trail for every run. The architecture is built and the individual pieces run.

**Being validated & hardened — the current focus:** the platform is implemented but **not yet demonstrated end-to-end on an admitted task**, because two things are in progress:
1. **Reference solutions.** Each task is admitted only after a known-good implementation scores a perfect run (the fairness gate). Authoring those reference solutions is underway; until a task has one, its grading pipeline is not yet proven on that task.
2. **Grading throughput.** The browser grader is LLM-driven and, under load, competes for the same API rate limit as the agent that just ran — so grading is being hardened (dedicated capacity / pacing) before large batches.

This is the normal "content + scale" phase after a platform is built — but we are honest that a fully-validated, passing end-to-end run is the immediate next milestone, not a shipped result.

**Next milestones (in order):**
1. Author a reference solution for one task and pass its fairness gate (first proven end-to-end run).
2. Resolve grader rate-limiting so browser grading runs reliably at scale.
3. Admit a first batch of validated tasks, then publish a head-to-head model comparison.

---

*Deku turns a subjective question — "is this AI good at building software?" — into a number a CEO, a customer, and an engineer can all trust.*
