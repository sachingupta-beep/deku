#!/usr/bin/env python3
"""Repackage a raw Harbor trial (jobs/<ts>/<task>__<id>/) into a clean,
debuggable output tree: output/<task>/<model>/run_<N>/.

Pure stdlib -- runs with the system python3, no venv required.

    python3 harness/repackage.py jobs/2026-08-03__13-16-53/streak-habit-tracker__jZiMs3R
    python3 harness/repackage.py --all          # repackage every trial under jobs/

What it does (all additive -- never touches jobs/ or tasks/):
  - copies the built app (/app artifact)      -> app/
  - copies the trajectory + raw CLI log       -> trajectory/
  - copies every browser screenshot           -> screenshots/
  - copies every verifier/agent log           -> logs/
  - writes services.json from the task's declared slots + compose  -> services/
  - writes manifest.json (provenance: model, digests, timings, reward)
  - writes harness-debug.log: ONE start->end timeline for fast debugging
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

REPO = Path(__file__).resolve().parent.parent
JOBS = REPO / "jobs"
OUT = REPO / "output"


# ----------------------------------------------------------------- helpers
def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "-" for c in text).strip("-") or "unknown"


def _copytree(src: Path, dst: Path) -> int:
    """Copy a directory if it exists and is non-empty. Returns file count."""
    if not src.exists() or not src.is_dir():
        return 0
    n = sum(1 for p in src.rglob("*") if p.is_file())
    if n:
        shutil.copytree(src, dst, dirs_exist_ok=True)
    return n


def _iso(t: str | None) -> str:
    return t or "?"


def _dur(stage: dict | None) -> float | None:
    if not isinstance(stage, dict):
        return None
    a, b = stage.get("started_at"), stage.get("finished_at")
    if not (a and b):
        return None
    try:
        pa = datetime.fromisoformat(a.replace("Z", "+00:00"))
        pb = datetime.fromisoformat(b.replace("Z", "+00:00"))
        return round((pb - pa).total_seconds(), 1)
    except Exception:
        return None


# ------------------------------------------------------------- task services
def _task_services(task_name: str) -> dict:
    """Read the task's declared slots + parse service images from its compose."""
    tdir = REPO / "tasks" / task_name
    services: dict = {"declared": {}, "images": {}, "seed_files": []}
    toml_path = tdir / "task.toml"
    if tomllib and toml_path.exists():
        try:
            meta = tomllib.loads(toml_path.read_text())
            services["declared"] = (meta.get("metadata") or {}).get("services") or {}
        except Exception:
            pass
    compose = tdir / "environment" / "docker-compose.yaml"
    if compose.exists():
        # lightweight parse: pull `<name>:` blocks and their `image:` lines
        name = None
        for line in compose.read_text().splitlines():
            s = line.strip()
            if line[:4].strip() and s.endswith(":") and not s.startswith("#") and "  " in line[:4] + "x":
                pass
            if s.startswith("image:"):
                if name:
                    services["images"][name] = s.split("image:", 1)[1].strip()
            elif s and s.endswith(":") and not s.startswith("#") and line.startswith("  ") and not line.startswith("    "):
                name = s[:-1]
    env_dir = tdir / "environment"
    if env_dir.exists():
        services["seed_files"] = sorted(
            p.name for p in env_dir.iterdir()
            if p.is_file() and p.name not in {"Dockerfile", "docker-compose.yaml"}
        )
    return services


# --------------------------------------------------------------- the writer
def repackage(trial: Path, verifier_dir: str = "verifier") -> Path:
    """Repackage a trial. `verifier_dir` selects WHICH grading run to publish.

    "verifier"       -- Harbor's in-place (shared-container) grading
    "verifier_fresh" -- harness/eval_fresh.py's clean-container regrade

    Both live side by side under the same trial, so the same trial can be
    published twice and the two scores compared directly.
    """
    if not trial.exists():
        sys.exit(f"trial not found: {trial}")
    vdir = trial / verifier_dir
    if not vdir.is_dir():
        sys.exit(f"no {verifier_dir}/ in {trial} -- has that grading run happened?")

    config = _load_json(trial / "config.json")
    result = _load_json(trial / "result.json")
    lock = _load_json(trial / "lock.json")

    # Prefer the TRIAL DIRECTORY name over result.json's `task_name`.
    #
    # `task_name` is the [task].name declared inside task.toml, which several
    # tasks share: tasks/oracle-streak declares "ethara/streak-habit-tracker"
    # because it is a variant of it. Trusting that filed oracle-streak's run under
    # output/streak-habit-tracker/ next to genuine streak runs -- and worse, made
    # _task_services() read tasks/streak-habit-tracker/, reporting the wrong
    # task's service slots as this run's provenance.
    #
    # The directory name comes from the task path that was actually run, so it is
    # the identity that matches tasks/<name>/ on disk. Fall back to the declared
    # name only when the trial directory has no `__` suffix to split on.
    task_name = _slug(
        trial.name.split("__")[0]
        or result.get("task_name", "").split("/")[-1]
    )
    agent_info = result.get("agent_info") or {}
    model = _slug(
        (config.get("agent") or {}).get("model_name")
        or (agent_info.get("model_info") or {}).get("name")
        or "unknown-model"
    )

    dest_root = OUT / task_name / model
    dest_root.mkdir(parents=True, exist_ok=True)
    run_n = 1 + sum(1 for p in dest_root.glob("run_*") if p.is_dir())
    dest = dest_root / f"run_{run_n}"
    dest.mkdir(parents=True, exist_ok=True)

    # --- reward + workflows (the score) ---
    for fn in ("reward.json", "workflows.json"):
        src = vdir / fn
        if src.exists():
            shutil.copy2(src, dest / fn)

    # --- app (the built frontend/backend) ---
    app_files = 0
    for cand in (trial / "artifacts" / "app", trial / "artifacts" / "logs" / "app"):
        app_files += _copytree(cand, dest / "app")
    if app_files == 0:
        (dest / "app").mkdir(exist_ok=True)
        (dest / "app" / "MISSING.txt").write_text(
            "No /app artifact was captured for this trial. On a deploy-failed run the\n"
            "app is often not collected. On a successful run this holds the built app.\n"
        )

    # --- trajectory ---
    traj = dest / "trajectory"
    traj.mkdir(exist_ok=True)
    for fn in ("trajectory.json", "claude-code.txt"):
        src = trial / "agent" / fn
        if src.exists():
            shutil.copy2(src, traj / fn)
    _copytree(trial / "agent" / "sessions", traj / "sessions")

    # --- screenshots ---
    shots = 0
    for cand in (vdir / "shots", vdir / "screenshots"):
        shots += _copytree(cand, dest / "screenshots")

    # --- services evidence ---
    (dest / "services").mkdir(exist_ok=True)
    (dest / "services" / "services.json").write_text(
        json.dumps(_task_services(task_name), indent=2) + "\n"
    )

    # --- every raw log ---
    logs = dest / "logs"
    logs.mkdir(exist_ok=True)
    log_map = {
        trial / "trial.log": "orchestration.log",
        vdir / "test-stdout.txt": "verifier_stdout.txt",
        vdir / "ctrf.json": "pytest_ctrf.json",
        vdir / "judge.json": "judge.json",
        vdir / "ctrf-error.json": "pytest_collection_error.json",
        trial / "artifacts" / "manifest.json": "artifacts_manifest.json",
    }
    for src, name in log_map.items():
        if src.exists():
            shutil.copy2(src, logs / name)

    # --- manifest (provenance) ---
    #
    # result.json only ever records HARBOR's grading, so it is the wrong source
    # when publishing a regrade: a fresh-container run that scored 0.0 would be
    # published carrying the shared-container 0.9 beside its own
    # invalid:["no_start_script"] -- a manifest that contradicts itself.
    # Prefer the reward file of the grading run actually being published.
    rewards = (result.get("verifier_result") or {}).get("rewards") or {}
    published = _load_json(vdir / "reward.json")
    if "reward" in published:
        rewards = {**rewards, "reward": published["reward"]}
    manifest = {
        "task": task_name,
        "model": model,
        "trial_id": trial.name,
        "source_job": str(trial.relative_to(REPO)) if str(trial).startswith(str(REPO)) else str(trial),
        "task_checksum": lock.get("task_checksum") or result.get("task_checksum"),
        "reward": rewards.get("reward"),
        "deployed": rewards.get("deployed"),
        "invalid": (_load_json(dest / "workflows.json").get("summary") or {}).get("invalid") or [],
        "exception": result.get("exception_info"),
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
        "stage_seconds": {
            s: _dur(result.get(s))
            for s in ("environment_setup", "agent_setup", "agent_execution", "verifier")
        },
        "agent": {
            "version": (result.get("agent_info") or {}).get("version"),
            "cost_usd": (result.get("agent_result") or {}).get("cost_usd"),
        },
        "repackaged_from": "harness/repackage.py",
        "graded_by": verifier_dir,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    _write_debug_log(dest / "harness-debug.log", manifest, trial, result, vdir)
    return dest


def _write_debug_log(path: Path, m: dict, trial: Path, result: dict, vdir: Path) -> None:
    """One human-readable start->end timeline of the whole trial."""
    L: list[str] = []
    add = L.append
    add("=" * 72)
    add(f"HARNESS DEBUG TIMELINE  --  {m['task']}  /  {m['model']}  /  {m['trial_id']}")
    add("=" * 72)
    add(f"started : {_iso(m['started_at'])}")
    add(f"finished: {_iso(m['finished_at'])}")
    add(f"REWARD  : {m['reward']}   deployed={m['deployed']}   invalid={m['invalid']}")
    if m["exception"]:
        add(f"EXCEPTION: {m['exception']}")
    add("")
    add("--- stage durations (seconds) ---")
    for s, sec in m["stage_seconds"].items():
        add(f"  {s:20s}: {sec}")
    add("")
    add("--- 1. ENVIRONMENT + AGENT SETUP (orchestration.log) ---")
    tl = (trial / "trial.log")
    add(tl.read_text()[-4000:] if tl.exists() else "  (no trial.log)")
    add("")
    add("--- 2. AGENT EXECUTION ---")
    # `or {}` not `.get(k, {})`: Harbor writes an explicit null for agent_result
    # whenever the agent phase produced no usable result, and the {} default only
    # covers a MISSING key. Every such trial -- exactly the failed runs a debug
    # log is most wanted for -- was skipped whole with a bare AttributeError.
    ar = result.get("agent_result") or {}
    add(f"  cost_usd={ar.get('cost_usd')}  stop_reason={ar.get('stop_reason')}")
    add(f"  trajectory: trajectory/trajectory.json  (raw: trajectory/claude-code.txt)")
    add("")
    add("--- 3. VERIFIER (deploy gate -> browser -> pytest -> judge -> score) ---")
    vs = (vdir / "test-stdout.txt")
    add(vs.read_text() if vs.exists() else "  (no verifier stdout)")
    ctrf = _load_json(vdir / "ctrf.json")
    if ctrf:
        summ = (ctrf.get("results") or {}).get("summary") or {}
        add(f"  pytest: {summ}")
    add("")
    add("--- 4. SCORE ---")
    wf = _load_json(vdir / "workflows.json")
    if wf:
        add(f"  {json.dumps(wf.get('summary', {}), indent=2)}")
        for w in wf.get("workflows", []):
            add(f"    [{'PASS' if w.get('passed') else 'FAIL'}] {w.get('id')}  "
                f"({w.get('substeps_passed')}/{w.get('substeps_graded')})")
    else:
        add("  (no workflows.json -- grading did not complete; see verifier stdout above)")

    # --- 5. RUBRIC -------------------------------------------------------
    # judge.json holds a per-criterion breakdown, but nothing surfaced it: the
    # timeline showed only the single composite `judge_score`, so seeing WHICH
    # criteria failed meant hand-parsing a nested JSON file. For a task rubric
    # that breakdown is the useful part -- it names the specific product
    # qualities the app missed, and it corroborates (or contradicts) the browser
    # substeps from an independent grader.
    judge = _load_json(vdir / "judge.json")
    dims = judge.get("dimensions") or {}
    if dims:
        add("")
        jmeta = judge.get("meta") or {}
        n = jmeta.get("rubric_criteria")
        kind = f"task rubric, {n} criteria" if n else "generic dimensions"
        add(f"--- 5. RUBRIC ({kind}) ---")
        add(f"  judge_score = {judge.get('judge_score')}   ADVISORY ONLY -- "
            f"never enters reward (PLAN.md 1.4)")
        add("")
        # Worst first: the failures are what a reviewer is looking for.
        for _key, v in sorted(dims.items(), key=lambda kv: (kv[1].get("score", 0.0),
                                                            str(kv[1].get("number", "")))):
            score = float(v.get("score", 0.0) or 0.0)
            mark = "PASS" if score >= 0.8 else ("PART" if score > 0 else "FAIL")
            # A negative criterion is an anti-pattern: 1.0 means the defect is
            # ABSENT. Flag it so the row is not read backwards.
            neg = "" if v.get("is_positive", True) else " [NEG: 1.0 = defect absent]"
            label = v.get("number") or _key
            add(f"  [{mark}] {label:5} {score:.2f}  w={v.get('weight', 0):.3f}  "
                f"{v.get('dimension', '')}{neg}")
            crit = str(v.get("criterion", "")).strip()
            if crit:
                add(f"          {crit[:100]}")
            if mark != "PASS":
                why = str(v.get("rationale", "")).replace("\n", " ").strip()
                if why:
                    add(f"          why: {why[:220]}")

    add("")
    add("=" * 72)
    add("END")
    path.write_text("\n".join(L) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trial", nargs="?", help="path to a jobs/<ts>/<task>__<id> trial dir")
    ap.add_argument("--all", action="store_true", help="repackage every trial under jobs/")
    ap.add_argument(
        "--verifier-dir",
        default="verifier",
        help="which grading run to publish: 'verifier' (Harbor, shared "
             "container) or 'verifier_fresh' (harness/eval_fresh.py, clean "
             "container). Both can be published from the same trial.",
    )
    args = ap.parse_args()

    trials: list[Path] = []
    if args.all:
        trials = [p for p in JOBS.glob("*/*__*") if p.is_dir()]
        # With --verifier-dir verifier_fresh, most trials have never been
        # regraded. Filter rather than emit a SKIP line for each.
        if args.verifier_dir != "verifier":
            trials = [p for p in trials if (p / args.verifier_dir).is_dir()]
    elif args.trial:
        trials = [Path(args.trial).resolve()]
    else:
        ap.error("give a trial path or --all")

    failed = 0
    for t in trials:
        try:
            dest = repackage(t, verifier_dir=args.verifier_dir)
            print(f"repackaged {t.name}  ->  {dest.relative_to(REPO)}")
        except Exception as exc:  # one bad trial must not abort the batch
            failed += 1
            print(f"SKIP {t.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"\n{failed}/{len(trials)} trial(s) skipped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
