#!/bin/bash
# Verifier entrypoint. Orchestrates both graders and writes the reward.
#
# NO `set -e`. A failing pytest is a SCORE, not a harness error -- aborting here
# would strand the reward file at 0.0 and hide the browser result. A verifier that
# exits without a reward file raises RewardFileNotFoundError and the trial is LOST,
# not scored zero (PLAN.md 2.4, 4.5).

mkdir -p /logs/verifier

# 1. Zero reward FIRST. Every exit path from here on already has a reward file.
#    Single key only: Harbor registers every top-level key here as its own reward
#    stream, so diagnostics belong in workflows.json, never in this file.
cat > /logs/verifier/reward.json <<'EOF'
{"reward": 0.0}
EOF

: "${APP_PUBLIC_URL:?APP_PUBLIC_URL is not set}"
APP_PUBLIC_URL="${APP_PUBLIC_URL%/}"
export APP_PUBLIC_URL

# 2. Deploy gate. A deploy failure is a hard zero with no partial credit.
DEPLOYED=0.0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 10 "${APP_PUBLIC_URL}/api/health" > /dev/null 2>&1 \
     || curl -fsS --max-time 10 "${APP_PUBLIC_URL}/" > /dev/null 2>&1; then
    DEPLOYED=1.0
    break
  fi
  sleep 5
done

if [ "$DEPLOYED" != "1.0" ]; then
  echo "app never became reachable at ${APP_PUBLIC_URL} - scoring 0" >&2
  # Route through score.py so reward.json + workflows.json carry the deploy
  # failure marker; a bare stub is indistinguishable from a legitimate agent 0.
  /tests/score.py \
    --workflows /tests/workflows.yaml \
    --pytest /nonexistent-ctrf.json \
    --browser /nonexistent-browser.json \
    --deployed 0.0 \
    --out /logs/verifier/reward.json || {
      echo '{"reward": 0.0}' > /logs/verifier/reward.json
      printf '{"summary": {"reward": 0.0, "invalid": ["deploy_failed", "scorer_crashed"]}}\n' \
        > /logs/verifier/workflows.json
    }
  exit 0
fi

# 3. Browser pass -- drives the UI through real user actions. Runs FIRST so the
#    pytest pass only ever sees state a user actually created (PLAN.md 4.5).
# /logs/verifier is COLLECTED; /tmp is not. This file carries the only record of
# WHY grading failed -- meta.grader_model / meta.grader_provider, and the
# per-substep `note` holding the actual exception text. Parking it in /tmp meant
# every grader fault reduced to a bare `invalid` reason code with the diagnosis
# thrown away, so a 401, a bad request and a transport timeout were
# indistinguishable after the run (2026-08-05: `grader_llm_error` on all 7
# substeps, cause unrecoverable).
BROWSER_RESULTS=/logs/verifier/browser_results.json
if [ -x /tests/run_workflows.py ]; then
  /tests/run_workflows.py \
    --workflows /tests/workflows.yaml \
    --url "$APP_PUBLIC_URL" \
    --out "$BROWSER_RESULTS"
else
  echo "no browser executor in this image - pytest substeps only" >&2
fi

# 4. pytest pass -- asserts the side effects those actions should have produced.
pytest /tests -rA --ctrf /logs/verifier/ctrf.json || true

# A collection-time error (bad import, missing driver, broken conftest) exits
# before any report is written. score.py would then read an empty result map, fail
# every pytest substep, and emit a reward:0.0 indistinguishable from an app that
# genuinely passed nothing. Surface it instead.
if [ ! -s /logs/verifier/ctrf.json ]; then
  echo "PYTEST WROTE NO CTRF REPORT - collection failed before running any test." >&2
  echo "The reward below is a harness fault, not an agent score." >&2
  printf '{"error": "ctrf_missing"}\n' > /logs/verifier/ctrf-error.json
fi

# 5. Rubric judge -- UI/UX, motion, accessibility, instruction-following.
#    ADVISORY ONLY (PLAN.md 1.4): it writes its own judge.json and its score is
#    copied into reward.json as a diagnostic. It never moves the reward, because
#    a judge-only reward is trivially gamed.
JUDGE_RESULTS=/logs/verifier/judge.json
# The judge is advisory only (PLAN.md 1.4) but is ~64% of the LLM call surface,
# so on a capacity-constrained run it can starve the browser grader, whose result
# DOES set the reward. DEKU_SKIP_RUBRIC lets a smoke/CI task spend its inference
# budget on the signal that actually scores.
if [ "${DEKU_SKIP_RUBRIC:-0}" = "1" ]; then
  echo "DEKU_SKIP_RUBRIC=1 - skipping the advisory rubric judge" >&2
  printf '{"judge_score": null, "dimensions": {}, "meta": {"skipped": "DEKU_SKIP_RUBRIC"}}\n' > "$JUDGE_RESULTS"
elif [ -x /tests/run_rubric.py ] && [ -f /tests/instruction.md ]; then
  /tests/run_rubric.py \
    --instruction /tests/instruction.md \
    --url "$APP_PUBLIC_URL" \
    --screenshot-dir /logs/verifier/shots \
    --out "$JUDGE_RESULTS" || true
else
  echo "no rubric judge in this image (or no instruction.md) - skipping" >&2
fi

# 6. Aggregate, applying the 90% + critical rule.
# If score.py itself crashes, the zero-preamble reward.json is left in place with
# no invalid marker -- indistinguishable from an honest agent 0. Mark it.
if ! /tests/score.py \
    --workflows /tests/workflows.yaml \
    --pytest /logs/verifier/ctrf.json \
    --browser "$BROWSER_RESULTS" \
    --judge "$JUDGE_RESULTS" \
    --deployed "$DEPLOYED" \
    --out /logs/verifier/reward.json; then
  echo "score.py crashed - emitting invalid marker so this run is not read as an agent score" >&2
  echo '{"reward": 0.0}' > /logs/verifier/reward.json
  printf '{"summary": {"reward": 0.0, "invalid": ["scorer_crashed"]}}\n' \
    > /logs/verifier/workflows.json
fi

exit 0
