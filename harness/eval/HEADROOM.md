# Headroom prompt compression

Shrinks grader prompts before they go upstream. **Off by default.** Read this
before enabling it — the default is deliberate, not an oversight.

## TL;DR

```bash
bash harness/eval/check_headroom.sh              # is it installed correctly?
harness/eval/enable_headroom.sh <task>           # turn it on for one task
# rebuild the task image, run the task, then:
grep grader_compress logs/*.log                  # did it actually do anything?
harness/eval/enable_headroom.sh <task> --disable # turn it back off
```

## Where it applies, and why only there

It is wired into the **grader** path only — `run_workflows.Anthropic.message`,
`run_workflows.OpenAI.message`, and the `run_rubric` judge that subclasses them.

It is deliberately **not** on the agent path (`claude_code/bridge.py`). Measured
over the 230 recorded completions in `jobs/*/agent/completions/`:

```
requests carrying cache_control:  230 / 230
cache_read_input_tokens:       16,299,305   (98.5% of prompt tokens)
recorded cost:                      $13.40
billed token-equivalents:        1,935,980   (an 88.3% discount from caching)
```

Prompt caching is an exact-prefix match. Compression rewrites the prefix, so
every cache breakpoint downstream misses — and because compression re-decides
what to crush on every turn, the cache never re-stabilises. The same traffic
would cost **$104–$130** instead of $13.40, roughly **8x more**, for a ~9%
reduction in raw tokens. To merely break even, compression would have to delete
**88.3%** of every prompt.

There is also a correctness argument: `jobs/*/agent/` is the experimental
record. Deleting parts of the agent's context means the score no longer measures
the model, and since compression varies with how the conversation grew, the same
task stops being reproducible.

The grader path has neither problem — no `cache_control` anywhere, and it is not
the thing being measured.

`grader_compress._has_cache_control()` enforces this permanently: if anyone adds
prompt caching to the grader path, compression stands down automatically instead
of silently costing 8x.

## Enabling

Two edits are required and **both must land or it silently does nothing**:

1. `tasks/<task>/environment/Dockerfile` — add `headroom-ai>=0.24,<0.25` to the
   grader runtime pip block. That block appears **twice** (a
   `--break-system-packages` attempt plus a plain-pip fallback); both copies
   need it.
2. `tasks/<task>/task.toml` — set `DEKU_GRADER_HEADROOM_ENABLED = "true"` inside
   `[verifier].env`. That block is the only passthrough into the grader
   container. **This repo has no `.env` file and nothing loads one** — don't
   create one expecting it to be read.

`enable_headroom.sh` does both, is idempotent, and `--disable` reverts them
byte-identically. Rebuild the task image afterwards.

Skip `smoke-tip-calculator` and `calculator` — they set `DEKU_SKIP_RUBRIC`, so
the judge never runs and you would see nothing. `--all` already excludes them.

## Confirming it works

```bash
grep grader_compress logs/*.log
```

| Output | Meaning |
|---|---|
| `[grader_compress] 24310 -> 18422 tokens (saved 5888, 24.2%)` | working |
| `[grader_compress] headroom not importable ...` | Dockerfile step failed |
| `[grader_compress] messages carry cache_control ...` | interlock tripped (expected if caching was added) |
| nothing at all | not running — the `task.toml` step failed |

**"No errors" does not mean it worked.** Every failure path returns the messages
unchanged, so a broken install and a disabled one behave identically. The log
line is the only positive signal.

## Tuning

| Env var | Default | Notes |
|---|---|---|
| `DEKU_GRADER_HEADROOM_ENABLED` | `false` | master switch |
| `DEKU_GRADER_HEADROOM_MIN_TOKENS` | `500` | per-message gate; lower first if nothing compresses |
| `DEKU_GRADER_HEADROOM_TARGET_RATIO` | `0.4` | |
| `DEKU_GRADER_HEADROOM_PROTECT_RECENT` | `2` | messages left verbatim at the tail |

`MIN_TOKENS` is the knob that matters. In a sibling repo the library default of
2000 meant no message ever qualified, and the integration saved nothing for
weeks while appearing healthy.

## Expect a modest win, and measure before rolling out

Much of a grader prompt cannot be compressed:

| Content | Compressible |
|---|---|
| Judge text evidence (DOM, computed styles, console errors) | **yes** — the only real target |
| Screenshots (`image` blocks) | no |
| Substep tool results (`run_workflows.py` sends `"ok"`) | no — far below the gate |
| System prompt | no — carries the JSON verdict contract |

Grader token usage is also **not yet recorded** — `finance/usage.py` reads
`logs/judge.json -> meta.usage` and no run has populated it. So the payoff is
unmeasured, and `headroom-ai` is a 16 MB compiled wheel that pins
`litellm==1.82.3`.

Enable it on **one** task, read the log line, and decide from a real number.

## Files

| Path | Role |
|---|---|
| `grader_compress.py` | the integration; fail-open, never raises |
| `test_grader_compress.py` | 29 tests |
| `check_headroom.sh` | verifies the integration is correctly installed |
| `enable_headroom.sh` | enables/disables it per task |

`grader_compress.py` is synced into every `tasks/*/tests/` by
`harness/sync_verifier.py` — edit the copy in `harness/eval/`, never a task copy.
