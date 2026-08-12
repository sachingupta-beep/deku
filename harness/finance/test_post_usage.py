#!/usr/bin/env python3
"""Tests for the finance POST transport, against a real local HTTP server.

    .venv/bin/pytest harness/finance/test_post_usage.py

These run a stdlib HTTPServer rather than mocking urllib, because the failures
worth catching here are wire-level: which header the credential actually goes
in, whether an Odoo-style HTTP-200-with-error-body is detected, and whether a
retry loop double-sends. A mock asserts what we already believe; a socket
asserts what actually happens.

The highest-value case is `test_http_200_with_error_body_is_a_failure`. Odoo's
JSON-RPC layer answers 200 and puts the failure in the body, so "2xx means
created" would write a success receipt for a record that does not exist -- and
the receipt then suppresses every future retry.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import post_usage as pu  # noqa: E402

PAYLOAD = {"project_id": "PRJ-512", "trajectory_id": "t__abc", "judge_lines": []}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep pytest output clean
        pass

    def do_POST(self):
        state = self.server.state
        state["hits"] += 1
        length = int(self.headers.get("Content-Length", 0))
        state["last_body"] = json.loads(self.rfile.read(length) or b"{}")
        state["last_headers"] = {k.lower(): v for k, v in self.headers.items()}
        state["last_path"] = self.path

        mode = state["mode"]
        if mode == "ok":
            code, body = 200, {"id": 4242, "success": True}
        elif mode == "jsonrpc_error":
            code, body = 200, {"error": {"code": 200, "message": "Odoo Server Error"}}
        elif mode == "success_false":
            code, body = 200, {"success": False, "message": "unknown project_id"}
        elif mode == "500":
            code, body = 500, {"error": "boom"}
        elif mode == "400":
            code, body = 400, {"error": "missing field"}
        elif mode == "flaky":
            code, body = ((503, {"error": "unavailable"}) if state["hits"] < 3
                          else (200, {"id": 7, "success": True}))
        else:
            code, body = 200, {}
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    srv.state = {"mode": "ok", "hits": 0}
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.base = "http://127.0.0.1:{}/api/v1".format(srv.server_port)
    yield srv
    srv.shutdown()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("DEKU_FINANCE_AUTH", raising=False)


# ------------------------------------------------------------------- wire
def test_url_and_body_reach_the_endpoint_intact(server):
    result = pu.post(PAYLOAD, server.base, "tok123")
    assert result["status"] == 200 and result["response"]["id"] == 4242
    assert server.state["last_path"] == "/api/v1/ethara_project/trajectory_usage/create"
    assert server.state["last_body"] == PAYLOAD
    assert server.state["last_headers"]["content-type"] == "application/json"


@pytest.mark.parametrize("scheme,header,value", [
    (None, "authorization", "Bearer tok"),
    ("bearer", "authorization", "Bearer tok"),
    ("api-key", "api-key", "tok"),
    ("x-api-key", "x-api-key", "tok"),
    ("header:X-Odoo-Token", "x-odoo-token", "tok"),
])
def test_auth_scheme_is_configurable(server, monkeypatch, scheme, header, value):
    """The finance doc never states the scheme; hardcoding one guarantees a 401."""
    if scheme is not None:
        monkeypatch.setenv("DEKU_FINANCE_AUTH", scheme)
    pu.post(PAYLOAD, server.base, "tok")
    assert server.state["last_headers"].get(header) == value


def test_unknown_auth_scheme_fails_loudly(server, monkeypatch):
    monkeypatch.setenv("DEKU_FINANCE_AUTH", "nonsense")
    with pytest.raises(pu.PostFailed, match="not a known scheme"):
        pu.post(PAYLOAD, server.base, "tok")


# --------------------------------------------------------- body-level errors
def test_http_200_with_error_body_is_a_failure(server):
    """Odoo answers 200 and puts the error in the body. 2xx != created."""
    server.state["mode"] = "jsonrpc_error"
    with pytest.raises(pu.PostFailed) as exc:
        pu.post(PAYLOAD, server.base, "tok")
    assert exc.value.retryable is False
    assert server.state["hits"] == 1, "a body-level error must not be retried"


def test_http_200_with_success_false_is_a_failure(server):
    server.state["mode"] = "success_false"
    with pytest.raises(pu.PostFailed, match="success=false"):
        pu.post(PAYLOAD, server.base, "tok")


def test_unrecognised_success_body_is_accepted(server):
    """We cannot enumerate every Odoo module's envelope; don't block a good one."""
    server.state["mode"] = "empty"
    assert pu.post(PAYLOAD, server.base, "tok")["status"] == 200


# ----------------------------------------------------------------- retries
def test_5xx_is_retried_and_4xx_is_not(server):
    server.state["mode"] = "500"
    with pytest.raises(pu.PostFailed) as exc:
        pu.post(PAYLOAD, server.base, "tok", attempts=3)
    assert exc.value.retryable is True
    assert server.state["hits"] == 3

    server.state.update(mode="400", hits=0)
    with pytest.raises(pu.PostFailed) as exc:
        pu.post(PAYLOAD, server.base, "tok", attempts=3)
    assert exc.value.retryable is False
    assert server.state["hits"] == 1, "a 400 fails identically every time"


def test_recovers_after_transient_failures(server):
    server.state["mode"] = "flaky"
    assert pu.post(PAYLOAD, server.base, "tok", attempts=3)["response"]["id"] == 7


def test_connection_error_is_a_retryable_postfailed():
    with pytest.raises(pu.PostFailed) as exc:
        pu.post(PAYLOAD, "http://127.0.0.1:1/api/v1", "tok", attempts=2)
    assert exc.value.retryable is True


# ------------------------------------------------------------- idempotency
def _run(root: Path, name: str = "run_1", trial="streak-habit-tracker__jZiMs3R") -> Path:
    run = root / "streak-habit-tracker" / "claude-opus-4-8" / name
    (run / "trajectory").mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({
        "task": "streak-habit-tracker", "model": "claude-opus-4-8",
        "trial_id": trial, "reward": 0.9, "deployed": 1.0, "invalid": [],
        "finished_at": "2026-08-04T11:28:00Z", "graded_by": "verifier"}))
    (run / "trajectory" / "trajectory.json").write_text(json.dumps({"final_metrics": {
        "total_prompt_tokens": 100, "total_completion_tokens": 10,
        "total_cached_tokens": 5, "total_cost_usd": 1.23}}))
    (run / "workflows.json").write_text(json.dumps({"summary": {"grader_usage": {
        "browser": {"model_name": "claude-sonnet-4-6", "calls": 2,
                    "input_tokens": 1000, "output_tokens": 100,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0}}}}))
    return run


@pytest.fixture
def posting_env(server, tmp_path, monkeypatch):
    monkeypatch.setattr(pu, "OUT", tmp_path)
    monkeypatch.setenv("DEKU_FINANCE_URL", server.base)
    monkeypatch.setenv("DEKU_FINANCE_TOKEN", "tok")
    monkeypatch.setenv("DEKU_SUBSCRIPTION_ID", "SUB-1")
    monkeypatch.setenv("DEKU_PROJECT_ID", "PRJ-512")
    monkeypatch.setenv("DEKU_BUDGET_TYPE", "RFP")
    monkeypatch.setenv("DEKU_RFP_SUB_TYPE", "Testing")
    for name in ("DEKU_PRODUCTION_MODE", "DEKU_MODEL_PRICES", "DEKU_TASK_ID"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_successful_post_writes_a_receipt_and_clears_pending(server, posting_env):
    run = _run(posting_env)
    assert pu.main(["post_usage.py", str(run), "--post"]) == 0
    assert server.state["hits"] == 1
    assert (run / pu.RECEIPT).exists()
    assert not (run / pu.PENDING).exists()


def test_reposting_the_same_run_is_skipped(server, posting_env):
    run = _run(posting_env)
    pu.main(["post_usage.py", str(run), "--post"])
    pu.main(["post_usage.py", str(run), "--post"])
    assert server.state["hits"] == 1, "a second post would double-bill"
    pu.main(["post_usage.py", str(run), "--post", "--force"])
    assert server.state["hits"] == 2, "--force is the deliberate override"


def test_same_trajectory_under_a_second_run_dir_is_not_rebilled(
        server, posting_env, capsys):
    """repackage.py publishes a re-run as run_2 with the SAME trial_id.

    The per-directory receipt does not cover this -- run_2 is a fresh directory
    with no receipt -- so without a trajectory-level check the agent phase gets
    billed once per publication.

    Exit code stays 0: re-publishing a trial is routine, so a duplicate skip is
    the guard working, not a fault. Only blocked records, POST failures, and
    unresolved crash markers set a non-zero exit -- if a normal `--all --post`
    exited non-zero whenever some trial had been republished, the exit code
    would stop meaning anything. The skip is surfaced on stderr and counted in
    the summary instead.
    """
    first = _run(posting_env, "run_1")
    second = _run(posting_env, "run_2")           # identical trial_id
    pu.main(["post_usage.py", str(first), "--post"])
    capsys.readouterr()
    rc = pu.main(["post_usage.py", str(second), "--post"])
    captured = capsys.readouterr()

    assert server.state["hits"] == 1, "one trajectory, one invoice line"
    assert not (second / pu.RECEIPT).exists()
    assert rc == 0, "a duplicate skip is expected behaviour, not a failure"
    assert "already billed from" in captured.err, "the skip must not be silent"
    assert "duplicate-skipped 1" in captured.out


def test_distinct_trajectories_both_post(server, posting_env):
    a = _run(posting_env, "run_1", trial="streak-habit-tracker__aaaaaaa")
    b = _run(posting_env, "run_2", trial="streak-habit-tracker__bbbbbbb")
    pu.main(["post_usage.py", str(a), str(b), "--post"])
    assert server.state["hits"] == 2, "the guard must not suppress real spend"


def test_failed_post_leaves_no_receipt_and_clears_pending(server, posting_env):
    server.state["mode"] = "jsonrpc_error"
    run = _run(posting_env)
    assert pu.main(["post_usage.py", str(run), "--post"]) == 1
    assert not (run / pu.RECEIPT).exists()
    assert not (run / pu.PENDING).exists(), "a proven failure is safe to retry"


def test_stale_pending_marker_halts_instead_of_double_billing(server, posting_env):
    """A crash between POST and receipt leaves an UNKNOWN, not a free retry."""
    run = _run(posting_env)
    (run / pu.PENDING).write_text(json.dumps({"trajectory_id": "x"}))
    assert pu.main(["post_usage.py", str(run), "--post"]) == 1
    assert server.state["hits"] == 0, "must not re-send an unconfirmed record"


def test_dry_run_sends_nothing(server, posting_env):
    run = _run(posting_env)
    pu.main(["post_usage.py", str(run)])
    assert server.state["hits"] == 0
    assert not (run / pu.RECEIPT).exists()


def test_post_refuses_without_a_configured_url(posting_env, monkeypatch):
    monkeypatch.delenv("DEKU_FINANCE_URL")
    run = _run(posting_env)
    assert pu.main(["post_usage.py", str(run), "--post"]) == 2
