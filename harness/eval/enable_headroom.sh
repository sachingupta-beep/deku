#!/usr/bin/env bash
# Enable (or disable) Headroom grader compression for a task.
#
#   harness/eval/enable_headroom.sh <task>            # turn it on
#   harness/eval/enable_headroom.sh <task> --disable  # turn it off
#   harness/eval/enable_headroom.sh --all             # every task that runs a rubric
#
# Two edits are needed and BOTH must happen or it silently does nothing:
#   1. environment/Dockerfile -- add headroom-ai to the grader runtime pip block.
#      That block is written TWICE (a --break-system-packages attempt with a
#      plain-pip fallback); miss the second copy and it half-works.
#   2. task.toml -- set DEKU_GRADER_HEADROOM_ENABLED in [verifier].env, which is
#      how DEKU_* vars reach the grader container. This repo has no .env file
#      and nothing loads one; task.toml is the only passthrough.
#
# Idempotent: re-running is a no-op. Rebuild the task image afterwards.
set -euo pipefail
cd "$(dirname "$0")/../.."

PIN='headroom-ai>=0.24,<0.25'

usage() { sed -n '2,12p' "$0" | sed 's/^# \?//'; exit 1; }
[ $# -ge 1 ] || usage

MODE=enable
TASKS=()
for arg in "$@"; do
  case "$arg" in
    --disable) MODE=disable ;;
    --all)
      for t in tasks/*/task.toml; do
        grep -q DEKU_SKIP_RUBRIC "$t" || TASKS+=("$(basename "$(dirname "$t")")")
      done ;;
    -h|--help) usage ;;
    *) TASKS+=("$arg") ;;
  esac
done
[ ${#TASKS[@]} -gt 0 ] || usage

for task in "${TASKS[@]}"; do
  dir="tasks/$task"
  [ -d "$dir" ] || { echo "❌ no such task: $task"; exit 1; }
  MODE="$MODE" PIN="$PIN" python3 - "$dir" <<'PY'
import os, re, sys
d, mode, pin = sys.argv[1], os.environ["MODE"], os.environ["PIN"]
task = os.path.basename(d)
dockerfile, toml = f"{d}/environment/Dockerfile", f"{d}/task.toml"

# --- 1a. tests/Dockerfile: the image the GRADER actually runs in -------------
# This is the one that matters. eval_fresh.py grades in a clean container built
# "from tests/ rather than environment/", so the grader imports headroom from
# THIS image on the default path. Patching only environment/Dockerfile (as an
# earlier version of this script did) installs the package somewhere the grader
# never looks, and headroom silently no-ops with the flag switched on.
#
# Not sync-managed -- sync_verifier's SHARED/OPTIONAL lists do not include
# Dockerfile -- so a per-task edit here is safe and will not be overwritten.
tests_df = f"{d}/tests/Dockerfile"
run_line = f'RUN pip install --no-cache-dir "{pin}"\n'
if os.path.exists(tests_df):
    src = open(tests_df).read()
    if mode == "enable":
        if pin not in src:
            # after the FROM, before the COPY, so a changed COPY list cannot
            # strand the install.
            src = re.sub(r'^(FROM [^\n]*\n)', r'\1\n' + run_line, src, count=1, flags=re.M)
    else:
        src = re.sub(r'\n*' + re.escape(run_line), '\n', src)
    open(tests_df, "w").write(src)

# --- 1b. environment/Dockerfile: only used by --in-place (shared) grading ----
# Best effort. Layouts differ across the corpus -- some tasks carry the grader
# deps in a doubled pip block (a --break-system-packages attempt plus a plain
# fallback), some a single block, and some none at all because they grade only
# in the verifier image. A task with no matching anchor is not an error here;
# 1a already covers the path that runs by default.
src = open(dockerfile).read()
line = f'      "{pin}" \\\n'
if mode == "enable":
    if pin not in src:
        # anchor on pytest-json-ctrf: present in every half of every block
        src = re.sub(r'( *)(pytest-json-ctrf==[^\s\\]+ \\\n)',
                     lambda m: m.group(0) + line, src)
else:
    src = re.sub(r' *"?' + re.escape(pin) + r'"? \\?\n', '', src)
open(dockerfile, "w").write(src)

# --- 2. task.toml: the [verifier].env passthrough ----------------------------
# Tasks use TWO shapes for this and they are mutually exclusive -- emitting the
# wrong one produces a duplicate-key TOML file that will not parse:
#   [verifier.env]            <- section style
#   KEY = "value"
# versus
#   [verifier]
#   env = { KEY = "value" }   <- inline table style
# Check for the section first; it is the one an inline-table regex silently
# misses, which is exactly how this went wrong the first time.
t = open(toml).read()
key = "DEKU_GRADER_HEADROOM_ENABLED"
# Interpolated, NOT a hardcoded "true": [verifier].env resolves ${VAR} from the
# host environment (it is how ANTHROPIC_API_KEY reaches the container), so this
# makes .env the single on/off switch. Install the plumbing once per task, then
# toggle DEKU_GRADER_HEADROOM_ENABLED in .env -- no re-edit, no image rebuild.
# Defaults to false, so a task carrying this line is still OFF unless asked.
val = '"${' + key + ':-false}"'
if mode == "enable":
    if key not in t:
        sec = re.search(r'^\[verifier\.env\]\s*$', t, re.M)
        if sec:
            t = t[:sec.end()] + f'\n{key} = {val}' + t[sec.end():]
        else:
            # The inline `env = {` MUST be the one inside [verifier]. Most
            # task.toml files also carry an [environment] env block, and that
            # one usually comes FIRST -- a whole-file search lands on the app
            # container's environment instead of the grader's, which sets the
            # flag somewhere nothing reads it and looks like it worked.
            # So: bound the search to the [verifier] section only.
            head = re.search(r'^\[verifier\]\s*$', t, re.M)
            if not head:
                raise SystemExit(f"{toml}: no [verifier] section")
            nxt = re.search(r'^\[', t[head.end():], re.M)
            end = head.end() + (nxt.start() if nxt else len(t) - head.end())
            inline = re.search(r'^\s*env\s*=\s*\{', t[head.end():end], re.M)
            if inline:
                at = head.end() + inline.end()
                t = t[:at] + f' {key} = {val},' + t[at:]
            else:
                t = t[:head.end()] + f'\nenv = {{ {key} = {val} }}' + t[head.end():]
else:
    # strip the key in either shape, leaving no empty scaffolding behind
    t = re.sub(r'^' + key + r'\s*=\s*"[^"]*"\n', '', t, flags=re.M)
    t = re.sub(r'\s*' + key + r'\s*=\s*"[^"]*",?', '', t)
open(toml, "w").write(t)

ok_d = (pin in open(dockerfile).read())
ok_t = (key in open(toml).read())
want = (mode == "enable")
mark = "✅" if (ok_d == want and ok_t == want) else "❌"
print(f"{mark} {task}: dockerfile={'yes' if ok_d else 'no'} task.toml={'yes' if ok_t else 'no'}")
PY
done

echo
if [ "$MODE" = enable ]; then
  echo "Next: rebuild the task image, run the task, then confirm with"
  echo "  grep grader_compress logs/*.log"
  echo "A line like '[grader_compress] 24310 -> 18422 tokens' means it worked."
  echo "No line at all means it is NOT running -- every failure path here is silent."
else
  echo "Disabled. Rebuild the task image to drop the dependency."
fi
