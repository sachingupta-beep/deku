#!/usr/bin/env bash
# Prove this machine can run BOTH phases before spending anything.
#
#   harness/preflight.sh <task-dir> [agent]
#
# Exit 0 = go. Exit 2 = a blocker, named, with the fix.
#
# WHY THIS EXISTS
#
# Every failure it checks for has already cost a run, and none of them announced
# itself: the agent phase started, spent 3-30 minutes, and died with an error
# that pointed somewhere other than its cause.
#
#   agent dialled api.anthropic.com directly   `invalid x-api-key`, nothing in the bridge log
#   bridge OAuth grant rotated out             `invalid_grant`, 401 identical to a missing key
#   seed script not executable                 database healthy, no app role, every login 28P01
#   network_mode unenforceable on this kernel  Harbor aborts before the agent starts
#   services declared, no compose              agent gets a hostname that resolves to nothing
#
# The rule this encodes: check the path the AGENT takes, not a path that merely
# resembles it. The host reaching the bridge proves nothing about a container
# reaching it, and that difference is exactly what cost the most recent run.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

TASK="${1:-}"
AGENT="${2:-openhands}"
FAIL=0

ok()   { printf "  \033[32mok\033[0m    %s\n" "$1"; }
bad()  { printf "  \033[31mFAIL\033[0m  %s\n" "$1"; FAIL=1; }
warn() { printf "  \033[33mwarn\033[0m  %s\n" "$1"; }
fix()  { printf "        -> %s\n" "$1"; }

echo "== host =="

command -v docker >/dev/null 2>&1 && ok "docker CLI" || { bad "docker CLI not found"; fix "install Docker"; }
if docker info >/dev/null 2>&1; then
  ok "docker daemon ($(docker info --format '{{.ServerVersion}}' 2>/dev/null))"
else
  bad "docker daemon is not responding"; fix "start Docker Desktop"
fi
command -v python3 >/dev/null 2>&1 && ok "python3" || bad "python3 not found"
command -v curl >/dev/null 2>&1 && ok "curl" || bad "curl not found"

# Free disk. An image build plus a fresh postgres needs a few GB; running out
# surfaces as an opaque build failure halfway through.
AVAIL=$(df -g . 2>/dev/null | awk 'NR==2{print $4}')
if [[ -n "${AVAIL:-}" && "$AVAIL" -lt 5 ]]; then
  warn "only ${AVAIL}GB free -- an image build plus a fresh database may not fit"
else
  ok "disk space (${AVAIL:-?}GB free)"
fi

echo
echo "== harness =="

# The grader is overlaid into the container from here at grading time, so a
# missing source is a grading failure, not a task problem.
MISSING_GRADER=""
for f in verifier/test.sh verifier/score.py verifier/appclient.py verifier/capabilities.py \
         verifier/_shapes.py verifier/pytest.ini eval/run_workflows.py eval/run_rubric.py; do
  [[ -f "harness/$f" ]] || MISSING_GRADER+=" $f"
done
if [[ -z "$MISSING_GRADER" ]]; then
  ok "grader sources present in harness/"
else
  bad "missing grader source:$MISSING_GRADER"
fi
[[ -f harness/prompt/deployment_contract.j2 ]] \
  && ok "deployment contract" \
  || warn "harness/prompt/deployment_contract.j2 missing -- briefs run unwrapped"

echo
echo "== LLM endpoint =="

if [[ "$AGENT" == "nop" || "$AGENT" == "oracle" ]]; then
  ok "skipped -- agent '$AGENT' makes no LLM calls"
else
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    bad "ANTHROPIC_API_KEY is not set"
    fix 'export ANTHROPIC_API_KEY="$(cat .bridge_secret)"'
  else
    BODY='{"model":"claude-sonnet-4-5-20250929","max_tokens":8,'
    BODY+='"messages":[{"role":"user","content":"ok"}]}'

    # 1. From the HOST -- what the graders use.
    HOST_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
    HOST_URL="${HOST_URL/host.docker.internal/localhost}"
    OUT="$(curl -sS --max-time 30 -X POST "${HOST_URL%/}/v1/messages" \
        -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" \
        -H "content-type: application/json" -d "$BODY" 2>&1)"
    if [[ "$OUT" == *'"content"'* ]]; then
      ok "host -> ${HOST_URL%/} answered a real completion"
    else
      bad "host -> ${HOST_URL%/} did not answer a completion"
      fix "$(printf '%s' "$OUT" | head -c 200)"
      case "$OUT" in
        *invalid_grant*|*OAuth*) fix "the bridge grant was rotated -- restart it so it re-reads the keychain" ;;
        *exhausted*)             fix "the account is out of quota" ;;
      esac
    fi

    # 2. From a CONTAINER -- what the AGENT uses. This is the check that matters:
    #    the host reaching the bridge says nothing about a container reaching it.
    AGENT_URL="${LLM_BASE_URL:-${ANTHROPIC_API_BASE:-${ANTHROPIC_BASE_URL:-}}}"
    if [[ -z "$AGENT_URL" ]]; then
      warn "no LLM_BASE_URL/ANTHROPIC_API_BASE set -- the agent will use api.anthropic.com"
    elif docker info >/dev/null 2>&1; then
      COUT="$(docker run --rm --add-host host.docker.internal:host-gateway \
          curlimages/curl:latest -sS --max-time 30 -X POST "${AGENT_URL%/}/v1/messages" \
          -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" \
          -H "content-type: application/json" -d "$BODY" 2>&1)"
      if [[ "$COUT" == *'"content"'* ]]; then
        ok "container -> ${AGENT_URL%/} answered a real completion"
      else
        bad "container -> ${AGENT_URL%/} is unreachable from a container"
        fix "$(printf '%s' "$COUT" | head -c 200)"
        fix "the agent runs in a container: localhost there is NOT your machine"
      fi
    fi

    # openhands resolves LLM_BASE_URL FIRST and never consults the ANTHROPIC_*
    # names. Setting only those leaves it dialling api.anthropic.com with the
    # bridge secret -- 0 LLM calls, nothing in the bridge log, `invalid x-api-key`.
    if [[ "$AGENT" == "openhands" && -n "${ANTHROPIC_BASE_URL:-}" && -z "${LLM_BASE_URL:-}" ]]; then
      bad "LLM_BASE_URL is unset but ANTHROPIC_BASE_URL is set"
      fix "openhands reads LLM_BASE_URL, not ANTHROPIC_BASE_URL"
      fix "add LLM_BASE_URL=$ANTHROPIC_BASE_URL to .env"
    fi
  fi
fi

echo
echo "== task =="

if [[ -z "$TASK" || ! -d "$TASK" ]]; then
  bad "task directory not found: ${TASK:-<none>}"
else
  # Prefer the venv python: harbor is importable only there, and its own
  # is_valid_dir is the authority on whether this directory is a task at all.
  PY_BIN=python3
  [[ -x "$REPO/.venv/bin/python3" ]] && PY_BIN="$REPO/.venv/bin/python3"
  "$PY_BIN" - "$TASK" <<'PY'
import os, re, sys, tomllib
from pathlib import Path

T = Path(sys.argv[1]); fail = 0
def ok(m):   print(f"  \033[32mok\033[0m    {m}")
def bad(m, f=None):
    global fail; fail = 1
    print(f"  \033[31mFAIL\033[0m  {m}")
    if f: print(f"        -> {f}")
def warn(m): print(f"  \033[33mwarn\033[0m  {m}")

for rel in ("task.toml", "instruction.md", "environment", "tests"):
    (ok if (T/rel).exists() else bad)(f"{rel} present" if (T/rel).exists() else f"{rel} is missing")

try:
    cfg = tomllib.loads((T/"task.toml").read_text())
except Exception as e:
    bad(f"task.toml does not parse: {e}"); cfg = {}

# Harbor's own opinion, on the path deku-run uses.
try:
    from harbor.models.task.task import Task
    if Task.is_valid_dir(str(T), disable_verification=True):
        ok("harbor accepts the task directory")
    else:
        bad("harbor rejects this task directory",
            "check task.toml parses and instruction.md exists")
except Exception:
    warn("could not ask harbor (not importable from this python)")

env = cfg.get("environment") or {}
mode = env.get("network_mode")
if mode is None:
    warn("network_mode unset -- harbor defaults to public")
elif mode != "public" and sys.platform == "darwin":
    bad(f'network_mode = "{mode}" cannot be enforced on Docker Desktop',
        'set network_mode = "public" and comment out allowed_hosts TOGETHER')
else:
    ok(f'network_mode = "{mode}"')
if mode == "public" and env.get("allowed_hosts"):
    bad("allowed_hosts is set alongside network_mode = public",
        "harbor rejects the pair, and reports it as 'Either datasets or tasks must be provided'")

# Services declared but nothing to start them.
services = (cfg.get("metadata") or {}).get("services") or {}
compose = (T/"environment"/"docker-compose.yaml")
if services and not compose.exists():
    bad(f"declares {sorted(services)} but has no environment/docker-compose.yaml",
        f"python3 environment/compose.py --write --task {T.name}")
elif services:
    ok(f"services {sorted(services)} + compose present")

# The silent one: postgres EXECUTES *-init.sh and does NOT stop if it cannot.
for p in sorted((T/"environment").glob("*-init.sh")) if (T/"environment").is_dir() else []:
    if os.access(p, os.X_OK):
        ok(f"{p.name} is executable")
    else:
        bad(f"{p.name} is not executable",
            f"chmod +x {p}  (else the DB comes up healthy with no app role)")

# The graders run INSIDE this image (verifier.environment_mode = "shared"), so
# every module they import must be installed by the task's own Dockerfile. A task
# can build, deploy and serve perfectly and still score 0.0 because the GRADER
# could not start: on 2026-08-14 top-poster-dashboard died at
# `ModuleNotFoundError: No module named 'httpx'` after a full agent phase, $6.65
# spent, app up and healthy. Nothing before this point looked at the image.
dockerfile = T / "environment" / "Dockerfile"
if dockerfile.is_file():
    body = dockerfile.read_text()
    needed = {
        "pytest": "pytest",                 # test.sh invokes it directly
        "pytest-json-ctrf": "pytest-json-ctrf",  # score.py reads its ctrf.json
        "httpx": "httpx",                   # appclient.py + both graders
        "pyyaml": "pyyaml",                 # score.py parses workflows.yaml
        "playwright": "playwright",         # run_workflows.py + run_rubric.py
    }
    missing = sorted(name for name, token in needed.items() if token not in body)
    if missing:
        bad(f"environment/Dockerfile installs no {', '.join(missing)}",
            "the graders run in THIS image; without these, grading dies after the "
            "agent phase has already been paid for")
    elif not re.search(r"playwright install(\s+--\S+)*\s+chromium", body):
        # `--with-deps` is a legitimate form and was being reported as missing
        # chromium. Both are accepted; the flag matters only on distributions
        # where playwright resolves an Ubuntu package list, and a task that
        # builds is the proof that its own base is fine.
        bad("playwright is installed but chromium is not",
            "add: RUN playwright install chromium")
    else:
        ok("environment/Dockerfile carries the grader runtime")

if not cfg.get("artifacts"):
    bad("no [[artifacts]] block -- /app is never collected, so nothing can be graded",
        'add [[artifacts]] with source = "/app"')
else:
    ok("collects /app")

# The graded contract itself. score.py reads workflows.yaml and resolves each
# pytest substep by exact `file.py::test_name`; a name that does not resolve is
# scored FALSE, not flagged, so a typo is indistinguishable from a broken app.
# Same for an unknown `kind`. Both are silent, and both bill a full agent phase.
wf = T / "tests" / "workflows.yaml"
if not wf.is_file():
    bad("tests/workflows.yaml is missing -- score.py has nothing to grade against")
else:
    try:
        import yaml
        flows = yaml.safe_load(wf.read_text()) or []
    except Exception as e:
        bad(f"tests/workflows.yaml does not parse: {e}"); flows = []

    if flows:
        known = set()
        for f in (T / "tests").glob("test_*.py"):
            known |= {f"{f.name}::{m}"
                      for m in re.findall(r"^def (test_\w+)", f.read_text(), re.M)}
        refs, kinds, ids = [], set(), []
        for w in flows:
            ids.append(w.get("id"))
            for s in w.get("substeps") or []:
                kinds.add(s.get("kind"))
                if s.get("kind") == "pytest":
                    refs.append(s.get("test"))
        unknown_kinds = sorted(k for k in kinds if k not in ("pytest", "browser"))
        missing_tests = sorted({r for r in refs if r not in known})
        dupe_ids = sorted({i for i in ids if ids.count(i) > 1})

        if unknown_kinds:
            bad(f"workflows.yaml uses unknown substep kind(s): {unknown_kinds}",
                'score.py accepts only "pytest" and "browser"; anything else fails the substep')
        elif missing_tests:
            bad(f"{len(missing_tests)} pytest substep(s) name a test that does not exist: "
                f"{missing_tests[:3]}",
                "score.py scores an unresolvable name as FAILED, so this reads as a broken app")
        elif dupe_ids:
            bad(f"duplicate workflow id(s): {dupe_ids}",
                "ids must be unique; results are keyed by them")
        elif not refs and "browser" not in kinds:
            bad("workflows.yaml declares no substeps at all")
        else:
            ok(f"{len(flows)} workflow(s), {len(refs)} pytest ref(s) all resolve")

# Harbor runs [environment.healthcheck].command inside the AGENT container, not
# inside the service it is checking. A command whose binary the agent image does
# not install therefore fails all 60 retries and harbor aborts with
# HealthcheckError -- ten minutes, before the agent starts. Measured 2026-08-14
# on seasonal-offer-publisher: `pg_isready` against a node:22-slim image with no
# postgresql-client. Postgres itself was healthy in 25 seconds.
hc = ((cfg.get("environment") or {}).get("healthcheck") or {}).get("command", "")
if hc and dockerfile.is_file():
    body = dockerfile.read_text()
    # binary -> the apt package that provides it
    provides = {"pg_isready": "postgresql-client", "psql": "postgresql-client",
                "curl": "curl", "wget": "wget", "nc": "netcat",
                "redis-cli": "redis-tools", "mysqladmin": "default-mysql-client"}
    tool = hc.split()[0] if hc.split() else ""
    pkg = provides.get(tool)
    if pkg and pkg not in body and tool not in body:
        bad(f"healthcheck runs `{tool}` but the agent image installs no {pkg}",
            "harbor runs the healthcheck INSIDE the agent container; without the "
            "binary it fails every retry and aborts before the agent starts")
    elif tool:
        ok(f"healthcheck `{tool}` is available in the agent image")

# eval_fresh.py probes the deployed app by running curl INSIDE this same image:
#     docker exec <grader-container> sh -c "curl ... $APP_PUBLIC_URL/api/health"
# With no curl the exec yields an empty string, the probe reads it as
# "no response" for the whole 180s window, and the run reports `deployed 0.0`
# on an app that was serving 200s the entire time. Measured 2026-08-14 on
# seasonal-offer-publisher: the image ran, seeded, bound 0.0.0.0:4173 and
# answered /api/health with 200 when probed from a container that had curl.
# Match an INSTALL, not a mention. `"curl" not in body` passed a Dockerfile whose
# only occurrence was a comment claiming the base image ships it -- it does not,
# and the built image had no curl (tessellate-market, 2026-08-17). Strip comments
# and require the word inside an install command.
_body = "\n".join(l for l in dockerfile.read_text().splitlines()
                  if not l.lstrip().startswith("#")) if dockerfile.is_file() else ""
if dockerfile.is_file() and not re.search(
        r"(apt-get|apk add|yum|dnf)[^\n]*(\\\n[^\n]*)*\bcurl\b", _body):
    bad("environment/Dockerfile installs no curl",
        "eval_fresh probes the app with curl from INSIDE this image; without it "
        "every probe returns nothing and a working app scores deployed 0.0")

# Probe addresses on a special-use domain. RFC 6761 reserves .test, .invalid,
# .localhost and .example, and `email-validator` -- which every Pydantic
# `EmailStr` field goes through -- refuses them outright. A fixture that signs up
# with `probe@something.test` therefore fails every app that validates its input
# properly and passes the ones that do not. Measured 2026-08-14 on
# marketplace-order-split: 15 of 16 signups returned 422 and the failure cascaded
# into 16 of 31 tests, on an app whose signup was correct.
bad_domains = set()
for f in list((T / "tests").glob("*.py")) if (T / "tests").is_dir() else []:
    for m in re.findall(r"@[a-z0-9.-]+\.(test|invalid|localhost|example)\b", f.read_text()):
        bad_domains.add(m)
if bad_domains:
    bad(f"test fixtures build email addresses on reserved domain(s): "
        f"{sorted('.' + d for d in bad_domains)}",
        "email-validator rejects RFC 6761 special-use names; use example.com")

# A task rubric that does not parse silently falls back to the GENERIC rubric,
# so the run is graded against questions written for a different product.
rubric = T / "tests" / "rubric.json"
if rubric.is_file():
    try:
        import json as _json
        crits = _json.loads(rubric.read_text())
        n = len(crits.get("criteria", crits) if isinstance(crits, dict) else crits)
        ok(f"tests/rubric.json parses ({n} criteria)")
    except Exception as e:
        bad(f"tests/rubric.json does not parse: {e}",
            "an unparseable task rubric silently falls back to the generic one")

# Harbor kills the agent at this budget. Unset means whatever harbor defaults to,
# which is not the 5h the corpus assumes.
if not (cfg.get("agent") or {}).get("timeout_sec") and "timeout_sec" not in (T / "task.toml").read_text():
    warn("no timeout_sec in task.toml -- the agent gets harbor's default, not the corpus 5h")

# Endpoints the tests call must be pinned in the brief, or a correct app fails.
tests = T/"tests"
if tests.is_dir():
    spec = (T/"instruction.md").read_text()
    # Paths that appear ONLY inside a negative test are routes the app must
    # REFUSE, not routes it must build. camping-site-catalog probes four candidate
    # signup paths and asserts >= 400 on each because its brief offers no signup;
    # reporting those as "not named in the brief" is backwards, and a warning that
    # fires on correct authoring is a warning people learn to skip.
    negative = re.compile(r"^def (test_(no|never)_\w+|test_\w+_(refused|denied|"
                          r"rejected|forbidden|not_\w+))\(", re.M)

    def _paths(src: str) -> set:
        return {m for m in re.findall(r'"(/[a-z][a-z0-9/_-]*)"', src)
                if not m.startswith(("/app", "/tests", "/logs", "/v1/", "/api/v1/"))}

    def _split(src: str):
        """(paths in negative tests, paths anywhere else)."""
        blocks = re.split(r"(?=^def )", src, flags=re.M)
        neg, pos = set(), set()
        for b in blocks:
            (neg if negative.match(b) else pos).update(_paths(b))
        return neg, pos

    called = set()
    negative_only = set()
    for f in list(tests.glob("test_*.py")) + list(tests.glob("conftest.py")):
        # Only the APP's own surface. The App Contract mounts it under /api, so
        # a path the fixtures call on a SIDECAR -- the payments provider's /v1/*,
        # mailpit's /api/v1/search -- is not something the agent implements and
        # must not be reported as unpinned. Left in, every well-authored
        # multi-service task warns about endpoints its brief is right to omit,
        # which teaches people to ignore the check.
        neg, pos = _split(f.read_text())
        called |= pos
        negative_only |= (neg - pos)
    called -= negative_only
    # A path whose last segment is a bare number is a PROBE -- `/assets/999999999`
    # exists to assert a 404 for an unknown id, so it can never appear in the
    # brief and reporting it trains people to ignore this check. Compare the
    # parent path instead, which is what the brief does pin (`GET /api/assets/:id`).
    def _pinned(path: str) -> bool:
        for cand in (path, f"/api{path}"):
            if cand in spec:
                return True
        # A brief pins a TEMPLATE -- `/media/{slug}`, `/assets/:id` -- while a test
        # calls it with a value filled in. Literal matching therefore reports a
        # correctly-pinned route as missing, which is how `/assets/999999999` and
        # `/media/materials` both surfaced. Accept the path when its parent is
        # pinned and the brief shows a placeholder in that position.
        head, _, last = path.rpartition("/")
        if head and last:
            for cand in (head, f"/api{head}"):
                if re.search(re.escape(cand) + r"/[{:<]", spec):
                    return True
            if last.isdigit():
                return any(c in spec for c in (head, f"/api{head}"))
        return False

    missing = sorted(e for e in called if not _pinned(e))
    if missing:
        warn(f"{len(missing)} endpoint(s) the tests call are not named in the brief: "
             f"{missing[:4]}")
        print("        -> the agent cannot guess these; a working app will fail")
    elif called:
        ok(f"all {len(called)} endpoints the tests call are pinned in the brief")

sys.exit(1 if fail else 0)
PY
  [[ $? -ne 0 ]] && FAIL=1
fi

# ---------------------------------------------------------------- environment
# The gates above READ files. Everything below STARTS them, because the two
# failures that have actually aborted agent phases were both invisible to a
# reader: a Dockerfile that mentions every right package but does not parse, and
# a compose whose one-shot init container exits 0 -- which `up --wait` counts as
# a failure. Both cost a launch each, and both are free to catch here.
#
# Skip with DEKU_SKIP_ENV_BOOT=1 when iterating on a task whose image is known good.
if [[ -z "${DEKU_SKIP_ENV_BOOT:-}" && -f "$TASK/environment/Dockerfile" ]]; then
  echo
  echo "== environment boots =="
  if ! build_out="$(docker build -q -t "deku-preflight:$(basename "$TASK")" "$TASK/environment" 2>&1)"; then
    echo "  FAIL  environment/Dockerfile does not build"
    echo "$build_out" | grep -iE "error|failed to solve|parse error" | head -3 | sed 's/^/        /'
    FAIL=1
  else
    echo "  ok    environment/Dockerfile builds"
    COMPOSE="$TASK/environment/docker-compose.yaml"
    if [[ -f "$COMPOSE" ]]; then
      PROJ="dekupreflight$(basename "$TASK" | tr -cd '[:alnum:]' | tr 'A-Z' 'a-z' | tail -c 30)"
      # --wait is the same call harbor makes, so this reproduces its verdict.
      if up_out="$(docker compose -p "$PROJ" -f "$COMPOSE" up --wait --wait-timeout 180 -d 2>&1)"; then
        echo "  ok    docker compose up --wait brings every service up"
      else
        echo "  FAIL  docker compose up --wait does not come up -- harbor aborts here"
        echo "$up_out" | grep -iE "exited|error|unhealthy|dependency" | head -4 | sed 's/^/        /'
        echo "        -> a one-shot init container must STAY running (append: && tail -f /dev/null);"
        echo "           --wait requires every service to be running or healthy"
        FAIL=1
      fi
      docker compose -p "$PROJ" -f "$COMPOSE" down -v --remove-orphans >/dev/null 2>&1 || true
    fi
  fi
fi

echo
if [[ $FAIL -ne 0 ]]; then
  echo "PREFLIGHT FAILED -- fix the items above, or DEKU_SKIP_PREFLIGHT=1 to bypass." >&2
  exit 2
fi
echo "preflight passed"
