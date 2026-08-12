#!/usr/bin/env python3
"""Build and (optionally) POST finance trajectory-usage records.

    python3 harness/finance/post_usage.py output/streak-habit-tracker/*/run_*
    python3 harness/finance/post_usage.py --all                  # every run
    python3 harness/finance/post_usage.py --all --post           # actually send

DRY RUN BY DEFAULT. Nothing leaves the machine without `--post`. This writes
finance rows into an external accounting system, so the default has to be the
one you can run by accident: it prints exactly what would be sent, plus every
warning, and exits non-zero if any record is incomplete.

Idempotency, keyed on the TRAJECTORY. The endpoint creates a new record per
call and offers no server-side dedupe, so preventing a duplicate invoice line
is entirely this tool's job, at two levels:

  - a successful POST writes `finance_posted.json` into the run directory, and
  - before posting, every other run directory's receipt is checked for the
    same trajectory_id (see posted_trajectories) -- because repackage.py
    publishes the same trial under a fresh run_N each time it is invoked, so
    "this directory has no receipt" does NOT mean "this trajectory is unbilled".

`finance_pending.json` is written before the request and removed after, so a
crash mid-flight leaves a marker rather than an invisible unknown.

Environment (see harness/finance/usage.py for the full list):
    DEKU_FINANCE_URL     base URL, e.g. https://odoo.example.com/api/v1
    DEKU_FINANCE_TOKEN   credential for that endpoint
    DEKU_FINANCE_AUTH    header scheme: bearer (default) | api-key |
                         x-api-key | header:<Name>  -- CONFIRM WITH THE
                         ENDPOINT OWNER; the doc does not specify one
    DEKU_PROJECT_ID / DEKU_BUDGET_TYPE / ...   classification fields
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from usage import build_payload, wire_payload  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "output"


def _load_dotenv() -> None:
    """Fill unset config from the repo's .env (gitignored; see .env.example).

    Without this the caller has to `set -a; source .env; set +a` in every
    terminal, and the failure when they forget is opaque: the config file
    plainly sets DEKU_PROJECT_ID, yet this script reports it unset, because a
    bare shell assignment is not exported and so never reaches os.environ.

    A variable already present in the environment WINS, so an explicit
    `DEKU_BUDGET_TYPE=Production python3 post_usage.py ...` still overrides the
    file for a one-off. Deliberately no python-dotenv dependency: this repo's
    host requirements are four packages and this parser is a dozen lines.
    """
    path = REPO / ".env"
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key.isidentifier() or key in os.environ:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ[key] = value
    except OSError:
        pass  # unreadable .env must not stop a post


_load_dotenv()

ENDPOINT_PATH = "ethara_project/trajectory_usage/create"
RECEIPT = "finance_posted.json"
PENDING = "finance_pending.json"
TIMEOUT_SEC = 30


def discover() -> list:
    return sorted(p for p in OUT.glob("*/*/run_*") if p.is_dir())


def posted_trajectories(exclude: Path = None) -> dict:
    """trajectory_id -> the run dir whose receipt already billed it.

    The receipt file alone does NOT make this idempotent, because the unit it
    protects is a DIRECTORY and the unit finance bills is a TRAJECTORY, and
    those are not one-to-one. repackage.py allocates a fresh run_N on every
    invocation:

        run_n = 1 + sum(1 for p in dest_root.glob("run_*") if p.is_dir())

    so repackaging the same trial twice -- or publishing Harbor's grading and
    an eval_fresh regrade of it, which is a documented workflow -- yields
    run_1 and run_2 carrying the SAME trial_id. Each is a new directory with
    no receipt, so a per-directory check waves both through and the trajectory
    is billed once per copy. Verified on this repo: oracle-streak__DYAyEJm is
    currently published under three run directories.

    The agent phase ran once and cost money once, so the id is the correct
    idempotency key. Scanning receipts is O(runs) against a local glob, which
    is nothing next to a duplicated invoice line.
    """
    index = {}
    for receipt in sorted(OUT.glob("*/*/run_*/" + RECEIPT)):
        run = receipt.parent
        if exclude is not None and run == exclude:
            continue
        try:
            tid = json.loads(receipt.read_text()).get("trajectory_id")
        except (json.JSONDecodeError, OSError):
            continue
        if tid:
            index.setdefault(tid, run)
    return index


class PostFailed(Exception):
    """A POST that did not demonstrably create a record. Retryable or not."""

    def __init__(self, message: str, retryable: bool = False, detail=None):
        super().__init__(message)
        self.retryable = retryable
        self.detail = detail


def auth_headers(token: str) -> dict:
    """Authentication headers, configurable because the doc does not specify one.

    The Finance API doc says only "ensure proper authentication headers are
    included" -- it never states the scheme. Odoo deployments differ: a custom
    /api/v1 controller may want a bearer token, an `api-key` header, or an
    Odoo session cookie. Hardcoding one guarantees a 401 against the other two,
    so the scheme is configuration:

        DEKU_FINANCE_AUTH=bearer   (default)  ->  Authorization: Bearer <token>
        DEKU_FINANCE_AUTH=api-key             ->  api-key: <token>
        DEKU_FINANCE_AUTH=x-api-key           ->  X-API-Key: <token>
        DEKU_FINANCE_AUTH=header:<Name>       ->  <Name>: <token>

    CONFIRM THE SCHEME WITH WHOEVER OWNS THE ODOO ENDPOINT before the first
    real post. A 401 is the good outcome here -- it fails loudly. The bad
    outcome is an endpoint that accepts unauthenticated writes and files the
    record against nobody.
    """
    if not token:
        return {}
    scheme = os.environ.get("DEKU_FINANCE_AUTH", "bearer").strip().lower()
    if scheme.startswith("header:"):
        return {scheme.split(":", 1)[1].strip(): token}
    if scheme == "api-key":
        return {"api-key": token}
    if scheme == "x-api-key":
        return {"X-API-Key": token}
    if scheme == "bearer":
        return {"Authorization": "Bearer " + token}
    raise PostFailed("DEKU_FINANCE_AUTH={!r} is not a known scheme "
                     "(bearer | api-key | x-api-key | header:<Name>)".format(scheme))


def check_body(status: int, parsed):
    """Reject a 2xx whose BODY reports failure.

    This is the defect that matters most against Odoo. Odoo's JSON-RPC layer
    answers HTTP 200 and puts the failure in the body -- {"error": {...}} --
    and hand-written /api/v1 REST controllers commonly return
    {"success": false, ...} the same way. Treating any 2xx as success would
    write a "posted" receipt for a record that was never created, and the
    receipt then suppresses every future retry: the trajectory is dropped from
    the ledger permanently, with a local file claiming it was billed.

    So a 2xx is only a success if the body does not say otherwise. An
    unrecognised body shape is accepted -- we cannot enumerate every Odoo
    module's success envelope, and rejecting on unknown shapes would block a
    correctly-working endpoint.
    """
    if not isinstance(parsed, dict):
        return
    if parsed.get("error") not in (None, "", {}, []):
        raise PostFailed("endpoint returned HTTP {} but the body carries an "
                         "error".format(status), retryable=False, detail=parsed)
    for key in ("success", "ok", "result"):
        if key in parsed and parsed[key] is False:
            raise PostFailed("endpoint returned HTTP {} but the body reports "
                             "{}=false".format(status, key),
                             retryable=False, detail=parsed)


def post_once(payload: dict, base_url: str, token: str) -> dict:
    url = base_url.rstrip("/") + "/" + ENDPOINT_PATH
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    headers.update(auth_headers(token))
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        # 429/5xx are transient; 4xx is a bad request that will fail identically
        # on every retry, so retrying only delays the person who must fix it.
        raise PostFailed("HTTP {}: {}".format(exc.code, detail),
                         retryable=exc.code == 429 or exc.code >= 500)
    except Exception as exc:
        raise PostFailed("{}: {}".format(exc.__class__.__name__, exc),
                         retryable=True)

    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = {"raw": raw[:2000]}
    check_body(status, parsed)
    return {"status": status, "response": parsed}


def post(payload: dict, base_url: str, token: str, attempts: int = 3) -> dict:
    """POST with backoff on transient failures only.

    Retrying is safe ONLY because a retry happens after a failure we can prove
    -- a connection error, a 5xx, or a body that reported an error. A response
    we never saw (a timeout mid-flight) is the ambiguous case: the record may
    or may not exist. Those are retried too, which risks a duplicate rather
    than a silent gap; a duplicate is visible in the ledger and can be voided,
    a missing record is not. That tradeoff is deliberate -- see `--force` and
    the pending marker for the audit trail it leaves behind.
    """
    last = None
    for attempt in range(attempts):
        try:
            return post_once(payload, base_url, token)
        except PostFailed as exc:
            last = exc
            if not exc.retryable or attempt == attempts - 1:
                raise
            delay = 2 ** attempt
            print("    transient failure ({}); retrying in {}s "
                  "({}/{})".format(exc, delay, attempt + 1, attempts),
                  file=sys.stderr)
            time.sleep(delay)
    raise last


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="*", type=Path,
                    help="run dirs (output/<task>/<model>/run_N)")
    ap.add_argument("--all", action="store_true", help="every run under output/")
    ap.add_argument("--post", action="store_true",
                    help="actually POST (default is a dry run)")
    ap.add_argument("--force", action="store_true",
                    help="re-post runs that already have a receipt")
    ap.add_argument("--json", action="store_true", help="print payloads as JSON")
    args = ap.parse_args(argv[1:])

    runs = discover() if args.all else [p.resolve() for p in args.runs]
    if not runs:
        print("no runs given (pass run dirs or --all)", file=sys.stderr)
        return 2

    base_url = os.environ.get("DEKU_FINANCE_URL", "").strip()
    token = os.environ.get("DEKU_FINANCE_TOKEN", "").strip()
    if args.post and not base_url:
        print("DEKU_FINANCE_URL is not set -- refusing to post", file=sys.stderr)
        return 2

    incomplete = 0
    posted = 0
    failed = 0
    unresolved = 0
    duplicates = 0

    for run in runs:
        payload = build_payload(run)
        diag = payload["_diagnostics"]
        label = "/".join(run.parts[-3:])

        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("{}  traj={}  model={}  cost=${}  judge_lines={}".format(
                label, payload["trajectory_id"], payload["model_name"],
                payload["trajectory_cost_usd"], len(payload["judge_lines"])))
        for b in diag.get("blockers", []):
            print("    BLOCKER: {}".format(b), file=sys.stderr)
        for w in diag.get("warnings", []):
            print("    warn: {}".format(w), file=sys.stderr)
        if not diag.get("postable"):
            incomplete += 1

        if not args.post:
            continue

        receipt = run / RECEIPT
        pending = run / PENDING
        if receipt.exists() and not args.force:
            print("    skip: already posted (see {}); --force to re-post"
                  .format(RECEIPT), file=sys.stderr)
            continue

        # Idempotency is keyed on the TRAJECTORY, not this directory -- the same
        # trial can be published under several run_N dirs (see
        # posted_trajectories). Without this, a re-publish bills it again.
        already = posted_trajectories(exclude=run).get(payload["trajectory_id"])
        if already is not None and not args.force:
            print("    skip: trajectory {} was already billed from {} -- this "
                  "is another publication of the same trial, not new spend"
                  .format(payload["trajectory_id"],
                          "/".join(already.parts[-3:])), file=sys.stderr)
            duplicates += 1
            continue

        # A leftover pending marker means a previous run sent this payload and
        # died before it could record the outcome. The record may or may not
        # exist in Odoo. Re-posting blind would double-bill, so stop and make a
        # human check -- this is the one case the tool must not decide alone.
        if pending.exists() and not args.force:
            print("    SKIP -- UNRESOLVED: {} exists, so a previous post was "
                  "sent but never confirmed. Check Odoo for trajectory_id {} "
                  "before continuing: if the record is absent, delete {} and "
                  "re-run; if it is present, move it to {}."
                  .format(PENDING, payload["trajectory_id"], PENDING, RECEIPT),
                  file=sys.stderr)
            unresolved += 1
            continue
        if not diag.get("postable"):
            # A wrong record is worse than a missing one: it lands in the ledger
            # looking authoritative and nobody re-checks it. Warnings alone do
            # not stop a post -- only blockers do.
            print("    skip: record would be wrong -- fix the blockers above",
                  file=sys.stderr)
            continue

        # Written BEFORE the request, so a crash mid-flight is detectable. The
        # window this closes: post succeeds, the process dies before the
        # receipt lands, the next --all --post sees no receipt and bills the
        # same trajectory twice. Now it leaves a marker instead.
        pending.write_text(json.dumps({
            "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "endpoint": base_url.rstrip("/") + "/" + ENDPOINT_PATH,
            "trajectory_id": payload["trajectory_id"],
            "note": "in flight; if this file survives, the outcome is UNKNOWN "
                    "-- check Odoo before re-posting",
        }, indent=2) + "\n")

        try:
            result = post(wire_payload(payload), base_url, token)
        except PostFailed as exc:
            failed += 1
            # A failure we can prove means nothing was created, so clear the
            # marker and let a later run retry cleanly.
            pending.unlink(missing_ok=True)
            print("    POST failed: {}".format(exc), file=sys.stderr)
            if exc.detail:
                print("      body: {}".format(
                    json.dumps(exc.detail)[:500]), file=sys.stderr)
            continue
        except Exception as exc:
            failed += 1
            pending.unlink(missing_ok=True)
            print("    POST failed: {}: {}".format(exc.__class__.__name__, exc),
                  file=sys.stderr)
            continue

        posted += 1
        pending.unlink(missing_ok=True)
        receipt.write_text(json.dumps({
            "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "endpoint": base_url.rstrip("/") + "/" + ENDPOINT_PATH,
            "trajectory_id": payload["trajectory_id"],
            "status": result["status"],
            "response": result["response"],
        }, indent=2) + "\n")
        print("    posted (HTTP {})".format(result["status"]))

    print("\nruns {} · incomplete {} · posted {} · duplicate-skipped {} · "
          "failed {} · unresolved {}{}"
          .format(len(runs), incomplete, posted, duplicates, failed, unresolved,
                  "" if args.post else "  (dry run -- pass --post to send)"))
    return 1 if (incomplete or failed or unresolved) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
