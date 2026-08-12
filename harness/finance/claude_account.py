#!/usr/bin/env python3
"""Identify the Claude subscription that generated a trajectory.

    python3 harness/finance/claude_account.py        # prints the resolved account

The finance record needs a `subscription_id` naming WHICH paid account produced
a trajectory. The harness authenticates by reusing Claude Code's OAuth login
(claude_code/bridge.py swaps a stub key for the stored token), so there is no
API key to read the account off -- the identity lives in the credential store
Claude Code writes at login:

    macOS:  Keychain generic password, service "Claude Code-credentials"
    Linux:  ~/.claude/.credentials.json

Both hold the same JSON:
    {"claudeAiOauth": {"accessToken": ..., "refreshToken": ..., "expiresAt": ...,
                       "scopes": [...], "subscriptionType": "max", ...}}

That access token is accepted by an internal profile endpoint:

    GET https://api.anthropic.com/api/oauth/profile
    Authorization: Bearer <access_token>

CAVEAT, and it is a real one: that endpoint is NOT public API. It is what
Claude Code's own `/status` calls. It works today against a subscription OAuth
token, but it carries no compatibility promise and can change without notice.
The documented alternative -- the Admin API's GET /v1/organizations/users --
needs an API-key-based Console admin org, which is a different auth model to
the subscription this harness actually runs on, so it does not fit.

Consequences for how this module is written:
  - Everything is best-effort. No exception escapes `get_claude_account_info()`;
    a failure returns {"error": ...} and the caller falls back to
    DEKU_SUBSCRIPTION_ID. Finance reporting must never take a trial down.
  - DEKU_SUBSCRIPTION_ID short-circuits the whole path, so a CI box with no
    Claude Code login (or a future where the endpoint is gone) still produces a
    complete, postable record.
  - The token is never cached to disk and never logged. It is read at call
    time, sent once, and dropped -- Claude Code refreshes it in the background
    on its own use, so re-reading the store beats holding a stale copy.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
KEYCHAIN_SERVICE = "Claude Code-credentials"
TIMEOUT_SEC = 15

_CACHE = {}


def _read_credentials() -> dict:
    """The OAuth blob `claude login` stored on this machine."""
    if platform.system() == "Darwin":
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=True,
        ).stdout
        return json.loads(out)
    return json.loads((Path.home() / ".claude" / ".credentials.json").read_text())


def _fetch_profile(access_token: str) -> dict:
    req = urllib.request.Request(
        PROFILE_URL,
        headers={"Authorization": "Bearer " + access_token,
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_claude_account_info(refresh: bool = False) -> dict:
    """Account/org identity for the subscription Claude Code is logged into.

    Returns a dict with account_uuid / name / email / organization_uuid /
    subscription_status / rate_limit_tier / subscription_type, or a dict with
    an `error` key. Never raises.

    Cached per process: the harness repackages many trials in one `--all` run
    and the answer cannot change between them, so this is one call per run
    rather than one per trial.
    """
    if not refresh and "info" in _CACHE:
        return _CACHE["info"]

    info: dict
    try:
        oauth = (_read_credentials() or {}).get("claudeAiOauth") or {}
        token = oauth.get("accessToken")
        if not token:
            info = {"error": "no accessToken in the Claude Code credential store"}
        else:
            data = _fetch_profile(token)
            account = data.get("account") or {}
            org = data.get("organization") or {}
            info = {
                "account_uuid": account.get("uuid"),
                "name": account.get("full_name") or account.get("display_name"),
                "email": account.get("email"),
                "organization_uuid": org.get("uuid"),
                "organization_name": org.get("name"),
                "subscription_status": org.get("subscription_status"),
                "rate_limit_tier": org.get("rate_limit_tier"),
                # From the local store, not the endpoint: it is the plan the
                # trajectory was actually billed against ("max"/"pro").
                "subscription_type": oauth.get("subscriptionType"),
            }
    except subprocess.CalledProcessError:
        info = {"error": "no Claude Code credentials in the macOS keychain "
                         "(run `claude login`)"}
    except FileNotFoundError:
        info = {"error": "no ~/.claude/.credentials.json (run `claude login`)"}
    except urllib.error.HTTPError as exc:
        # 401 is the expected, actionable one: the stored token expired and
        # Claude Code has not refreshed it yet.
        info = {"error": "profile endpoint returned HTTP {} ({})".format(
            exc.code, "token expired -- run `claude login`" if exc.code == 401
            else "unexpected")}
    except Exception as exc:
        info = {"error": "{}: {}".format(exc.__class__.__name__, exc)}

    _CACHE["info"] = info
    return info


def subscription_id() -> str:
    """The value to put in the finance record's `subscription_id` field.

    DEKU_SUBSCRIPTION_ID wins when set -- finance may key billing on their own
    identifier (the doc's example is "SUB-98765"), and it is also the only way
    to produce a complete record on a machine with no Claude Code login.
    Otherwise the account UUID, which is stable and uniquely identifies the
    paying account. Empty string when neither is available; post_usage.py
    treats that as a hard error rather than posting an unattributable record.
    """
    override = os.environ.get("DEKU_SUBSCRIPTION_ID", "").strip()
    if override:
        return override
    return (get_claude_account_info().get("account_uuid") or "")


if __name__ == "__main__":
    print(json.dumps(get_claude_account_info(), indent=2))
