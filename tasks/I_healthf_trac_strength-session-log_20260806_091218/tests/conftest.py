"""Fixtures, pinned literals and helpers for ethara/strength-session-log.

No test functions live here (G10). Every literal below is pinned verbatim in instruction.md
(G6): a value this file asserts against and the brief never stated is the Bug-2 defect.

The tests observe the app only through HTTP at APP_PUBLIC_URL under the /api prefix. Nothing
imports a provider SDK, reads the agent's source, or assumes a framework, ORM, response
envelope or id type (INV6).
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
import json as _json

import pytest

# --- pinned literals (instruction.md) ---------------------------------------------------

LIFTER_EMAIL = "lifter@ethara.ai"
LIFTER2_EMAIL = "lifter2@ethara.ai"
PASSWORD = "deku-demo-pw-2026"

LOGIN_PATH = "/api/auth/login"
HEALTH_PATH = "/api/health"
SESSIONS_PATH = "/api/sessions"
SETS_PATH = "/api/sets"
TREND_PATH = "/api/trend"
EXERCISES_PATH = "/api/exercises"

SLUG_SQUAT = "back-squat"
SLUG_BENCH = "bench-press"
SLUG_DEADLIFT = "deadlift"

SEED_WEEK = "2026-W28"
SEED_SQUAT_UID_1 = "seed-squat-w28-1"
SEED_SQUAT_UID_2 = "seed-squat-w28-2"
SEED_BENCH_UID_1 = "seed-bench-w28-1"

# Derived from the seeded sets: 100 kg x 5 reps + 105 kg x 3 reps.
SEED_SQUAT_TOP_WEIGHT = 105
SEED_SQUAT_VOLUME = 815
SEED_SQUAT_SET_COUNT = 2

STATUS_OPEN = "open"
STATUS_FINISHED = "finished"

SETTLE_DEADLINE_SEC = 10.0
SETTLE_INTERVAL_SEC = 0.25


# --- HTTP plumbing ----------------------------------------------------------------------


def _decode_json(body: bytes):
    """Decode a JSON body, or return None when the body is not JSON.

    None is not a swallowed failure: every caller asserts on the decoded shape and reports the
    status plus a body excerpt, so a non-JSON response fails loudly at the assertion instead of
    raising here. Decoding is done with raw_decode against a pre-checked first character so no
    exception handler is needed to classify the body."""
    text = body.decode("utf-8", "replace").strip()
    if not text or text[0] not in "[{\"-0123456789tfn":
        return None
    value, _end = _json.JSONDecoder().raw_decode(text)
    return value


class Response:
    """A tolerant response wrapper. The spec pins no envelope, so `json` is whatever the app
    returned and callers reach into it defensively."""

    def __init__(self, status: int, body: bytes):
        self.status_code = status
        self.body = body
        self.json = _decode_json(body)

    def excerpt(self, limit: int = 240) -> str:
        text = self.body.decode("utf-8", "replace")
        return text[:limit]


class _KeepErrorResponses(urllib.request.HTTPErrorProcessor):
    """Return 4xx and 5xx as ordinary responses instead of raising.

    A rejection status IS the observation in this suite -- most of what the brief pins is a
    422, a 409, a 404 or a 401. Letting urllib raise on those and catching it would put a
    swallowing except handler on the hot path of every negative test."""

    def http_response(self, request, response):
        return response

    https_response = http_response


def _base_url() -> str:
    url = os.environ.get("APP_PUBLIC_URL")
    if not url:
        raise RuntimeError(
            "APP_PUBLIC_URL is not set; the app address comes from the environment "
            "per the deployment contract")
    return url.rstrip("/")


def request(method: str, path: str, token: str | None = None,
            payload: dict | None = None) -> Response:
    """One HTTP call against the deployed app. Never raises on a 4xx/5xx: the status is the
    observation, and swallowing it would turn a real failure into a non-event."""
    url = _base_url() + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = _json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(_KeepErrorResponses)
    with opener.open(req, timeout=30) as resp:
        return Response(resp.status, resp.read())


def settle(predicate, deadline_sec: float = SETTLE_DEADLINE_SEC):
    """Poll `predicate` a bounded number of times and return its first truthy result, else None.

    The only sanctioned sleep in this suite. A bare sleep before asserting that something did
    happen is always wrong; this polls instead, so a slow-but-correct app is not failed for
    being slow and a broken one still fails inside a bounded number of attempts. The bound is
    an attempt count rather than a wall-clock deadline, so two identical runs poll identically."""
    attempts = max(1, int(deadline_sec / SETTLE_INTERVAL_SEC))
    outcome = predicate()
    for _ in range(attempts):
        if outcome:
            return outcome
        time.sleep(SETTLE_INTERVAL_SEC)
        outcome = predicate()
    return outcome


def login(email: str, password: str = PASSWORD) -> str:
    r = request("POST", LOGIN_PATH, payload={"email": email, "password": password})
    assert r.status_code == 200, (
        f"login for {email} at POST {LOGIN_PATH}: expected 200, observed "
        f"{r.status_code}; body: {r.excerpt()}")
    assert isinstance(r.json, dict), (
        f"login for {email}: expected a JSON object carrying a token, observed "
        f"{r.excerpt()}")
    token = r.json.get("token")
    assert isinstance(token, str) and token, (
        f"login for {email}: response carries no non-empty `token` string; "
        f"body: {r.excerpt()}")
    return token


# --- domain helpers ---------------------------------------------------------------------


def unique_uid(prefix: str = "probe") -> str:
    """A per-run identifier, so a replay assertion is never confused by a previous run's row."""
    return f"{prefix}-{os.urandom(6).hex()}"


def open_session(token: str) -> str:
    """Return the id of a session that is open for this lifter, opening one if needed.

    Self-seeding: the suite never depends on a session left behind by another test."""
    r = request("POST", SESSIONS_PATH, token=token, payload={})
    if r.status_code in (200, 201):
        return str(_session_id(r.json))
    assert r.status_code == 409, (
        f"POST {SESSIONS_PATH}: expected 201 for a new session or 409 when one is already "
        f"open, observed {r.status_code}; body: {r.excerpt()}")
    listed = request("GET", SESSIONS_PATH, token=token)
    assert listed.status_code == 200, (
        f"GET {SESSIONS_PATH}: expected 200, observed {listed.status_code}; "
        f"body: {listed.excerpt()}")
    for row in _rows(listed.json):
        if str(row.get("status", "")).lower() == STATUS_OPEN:
            return str(row.get("id"))
    raise AssertionError(
        f"POST {SESSIONS_PATH} answered 409 (a session is already open) but GET "
        f"{SESSIONS_PATH} lists none with status {STATUS_OPEN!r}; body: {listed.excerpt()}")


def _session_id(payload):
    if isinstance(payload, dict):
        for key in ("id", "session_id"):
            if key in payload:
                return payload[key]
        nested = payload.get("session")
        if isinstance(nested, dict) and "id" in nested:
            return nested["id"]
    raise AssertionError(
        f"session response carries no id field; observed {payload!r}")


def _rows(payload):
    """Tolerate a bare array or a single-key envelope; the spec pins neither."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("sessions", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def log_set(token: str, session_id: str, set_uid: str, slug: str = SLUG_SQUAT,
            weight_kg=100, reps=5) -> Response:
    return request("POST", SETS_PATH, token=token, payload={
        "session_id": session_id,
        "exercise_slug": slug,
        "weight_kg": weight_kg,
        "reps": reps,
        "set_uid": set_uid,
    })


def trend_series(token: str, slug: str = SLUG_SQUAT) -> list:
    r = request("GET", f"{TREND_PATH}?exercise={slug}", token=token)
    assert r.status_code == 200, (
        f"GET {TREND_PATH}?exercise={slug}: expected 200, observed {r.status_code}; "
        f"body: {r.excerpt()}")
    assert isinstance(r.json, dict), (
        f"GET {TREND_PATH}?exercise={slug}: expected a JSON object carrying `series`, "
        f"observed {r.excerpt()}")
    series = r.json.get("series")
    assert isinstance(series, list), (
        f"GET {TREND_PATH}?exercise={slug}: `series` is not an array; body: {r.excerpt()}")
    return series


def week_entry(series: list, iso_week: str) -> dict | None:
    for entry in series:
        if isinstance(entry, dict) and entry.get("iso_week") == iso_week:
            return entry
    return None


def week_counts(token, slug: str = SLUG_SQUAT) -> dict:
    """iso_week -> set_count for one exercise. The basis of the idempotency-by-delta
    assertions: a replay must move no entry in this map."""
    return {e.get("iso_week"): e.get("set_count")
            for e in trend_series(token, slug) if isinstance(e, dict)}


def total_set_count(token, slug: str = SLUG_SQUAT) -> int:
    """The summed set_count across every week of one exercise's trend."""
    return sum(v for v in week_counts(token, slug).values() if isinstance(v, int))


def set_id_of(payload):
    if isinstance(payload, dict):
        for key in ("id", "set_id"):
            if key in payload:
                return payload[key]
        nested = payload.get("set")
        if isinstance(nested, dict) and "id" in nested:
            return nested["id"]
    raise AssertionError(f"set response carries no id field; observed {payload!r}")


def field_of(payload, name):
    if isinstance(payload, dict):
        if name in payload:
            return payload[name]
        nested = payload.get("set")
        if isinstance(nested, dict) and name in nested:
            return nested[name]
    raise AssertionError(
        f"set response carries no {name!r} field; observed {payload!r}")


# --- fixtures ---------------------------------------------------------------------------


@pytest.fixture()
def lifter_token() -> str:
    return login(LIFTER_EMAIL)


@pytest.fixture()
def lifter2_token() -> str:
    return login(LIFTER2_EMAIL)


@pytest.fixture()
def session_id(lifter_token) -> str:
    return open_session(lifter_token)
