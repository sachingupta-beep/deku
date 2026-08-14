#!/usr/bin/env python3
"""Copy the shared grader into every task's tests/ directory.

    python harness/sync_verifier.py tasks/*/          # write
    python harness/sync_verifier.py tasks/*/ --check  # verify, exit 1 on drift

Why this exists: `verifier.environment_mode = "separate"` cannot grade a running
app -- Harbor stops the agent environment before starting the separate verifier,
so there is a zero-second window in which a live app and a running grader coexist.
Shared mode runs the graders inside the agent environment, where the app is still
the process the agent just started.

The consequence is that the grader can no longer live in a verifier base image.
Harbor uploads the task's `tests/` directory at verification time, so the shared
files have to be physically present there. This keeps `harness/verifier/` as the
single source of truth and makes the copies a build artifact, with `--check`
guarding against drift -- a grader change is a corpus-wide event (PLAN.md 4.5) and
must not silently apply to only some tasks.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "verifier"
SHARED = ("score.py", "test.sh", "capabilities.py", "appclient.py",
          "_shapes.py", "pytest.ini", "motion.py")
# grader_compress.py is imported by run_workflows.py, so it has to ride along
# into every tests/ dir -- the graders import it at /tests inside the container.
# run_workflows falls back to an identity function if it is ever missing, so a
# stale task that predates this entry still grades correctly, just uncompressed.
OPTIONAL = ("run_workflows.py", "run_rubric.py", "grader_compress.py")
EVAL = Path(__file__).resolve().parent / "eval"


def files_to_sync() -> list[Path]:
    out = [SOURCE / name for name in SHARED]
    out += [EVAL / name for name in OPTIONAL if (EVAL / name).exists()]
    return out


def sync(tests_dir: Path, *, check: bool) -> list[str]:
    problems: list[str] = []
    # The rubric judge grades against the spec, but Harbor only ever passes
    # instruction.md to the agent as a prompt -- it is never uploaded, so
    # /app/instruction.md does not exist inside the container. tests/ IS uploaded,
    # so the spec rides along with the graders. No leak: the agent already has it.
    sources = files_to_sync() + [tests_dir.parent / "instruction.md"]
    for src in sources:
        if not src.exists():
            continue
        dst = tests_dir / src.name
        # ABSENT is a decision, not drift.
        #
        # eval_fresh.py assembles /tests itself and overlays the shared grader --
        # and instruction.md -- straight from harness/ after copying tests/, so a
        # task does not need its own copy for grading. A task pruned to just its
        # own data (conftest.py, test_*.py, workflows.yaml, rubric.json) is a
        # deliberate state: 3,863 lines of duplicated grader against 1,853 lines
        # of actual task in payroll-journal-approval before pruning.
        #
        # So: keep an EXISTING copy current, never resurrect a removed one. Tasks
        # that still carry copies stay correct and keep working with Harbor's own
        # verifier; pruned tasks stay pruned instead of being refilled by the next
        # `scripts/deku-run`.
        if not dst.exists():
            continue
        if check:
            if not filecmp.cmp(src, dst, shallow=False):
                problems.append(f"{tests_dir.parent.name}: {src.name} differs from "
                                f"harness/verifier (run harness/sync_verifier.py)")
        else:
            shutil.copy2(src, dst)
            dst.chmod(0o755 if dst.suffix in (".sh", ".py") else 0o644)
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tasks", nargs="+", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv[1:])

    problems: list[str] = []
    for task in args.tasks:
        tests_dir = task / "tests"
        if not tests_dir.is_dir():
            problems.append(f"{task}: no tests/ directory")
            continue
        found = sync(tests_dir, check=args.check)
        problems += found
        if not args.check and not found:
            print(f"synced: {task.name}")

    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if args.check:
        print(f"grader in sync across {len(args.tasks)} tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
