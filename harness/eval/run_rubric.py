#!/usr/bin/env python3
"""Qualitative rubric judge for Deku (PLAN.md 4.5 grader determinism).

DIAGNOSTIC ONLY. PLAN.md 1.4 and 4.7: `judge_score` is recorded but NEVER
drives training -- a judge-only reward is trivially gamed. This tool:

  * writes its own artifact (``judge.json``), never ``reward.json``;
  * never imports, calls, or influences ``harness/verifier/score.py``;
  * states advisory-only status in ``--help`` and in the emitted JSON.

The binary substep grader (``run_workflows.py``) owns the RL reward. This
file owns the human-facing quality read. The two must not be blurred.

Drives a real Chromium browser through the deployed app, gathers objective
evidence (screenshots, computed styles, real motion, console errors, a11y
snapshots) across desktop / tablet / mobile viewports, and scores against
the rubric in the spec:

    instruction_following  0.30
    functionality          0.25
    ux_flow                0.15
    ui_visual              0.15
    motion                 0.05
    accessibility          0.05
    responsiveness         0.05
                           -----
                           1.00

Each dimension is graded by a separate LLM call, so a failure in one does
not corrupt the others. The grader is pinned in-source (PLAN.md 4.5) and
recorded in ``meta.grader_model``.

Reuses ``Browser`` and ``Anthropic`` from ``run_workflows``; extends the
tool set with page_screenshot (base64 image), page_styles, page_motion,
page_console, page_a11y, set_viewport.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

# Reuse the browser layer + HTTP client. run_workflows.py sits next to this
# file locally and at /tests in the verifier image.
try:
    from run_workflows import Anthropic, Browser, read_credentials  # type: ignore
except ImportError:  # verifier image path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_workflows import Anthropic, Browser, read_credentials  # type: ignore

# --------------------------------------------------------------------------
# Constants -- pinned per PLAN.md 4.5 for cross-run comparability.

# claude-sonnet-4-6, not 4-5: harness/finance/pricing.py deliberately carries no
# rate for claude-sonnet-4-5 ("a number here would be invention"), so a run at
# the old default produced judge_cost_usd = null and finance refused to post the
# WHOLE record -- agent cost included. That surfaced ~30 minutes into a paid run
# (2026-08-12, reward 0.3043, never billed). 4-6 is priced, so the default now
# produces a postable record.
DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_VIEWPORTS = "1920x1200,768x1024,390x844"
DEFAULT_MAX_STEPS = 40         # per dimension
DEFAULT_CREDENTIALS_PATH = "/app/USER_README.md"
# Must exceed the bridge's worst-case absorb time. The bridge swallows upstream
# 429s by sleeping (ladder 2,4,8,16,32,64,90,90 = 306s with the current
# KAIJU_CC_MAX_INLINE_* settings). A client timeout below that converts every
# absorbed throttle into a ReadTimeout -- the same zero, just a different error.
LLM_TIMEOUT_SEC = 420
ACTION_TIMEOUT_MS = 15000
JUDGE_MAX_TOKENS = 4096         # rationales don't fit in the 1024 of run_workflows

# Rubric -- weights MUST sum to 1.0. Test file asserts this.
RUBRIC: list[tuple[str, float, str]] = [
    ("instruction_following", 0.30,
     "Are the features named in instruction.md Core-features and User-flow sections actually present and reachable in the deployed app? A missing feature is a score cut, a hidden-but-implemented feature is a smaller cut. Score against the actual spec passed in, not a generic notion."),
    ("functionality", 0.25,
     "Do the core flows actually WORK when driven -- signup/login, primary CRUD, submit forms, key journeys -- without runtime errors, dead ends, blank screens, or 500s? Console errors and failed network requests during real interaction count heavily."),
    ("ux_flow", 0.15,
     "Navigation reachability, empty states, loading states, error states, feedback on actions (toasts/inline messages), sensible redirects (unauth -> login?next=, login success -> next/home). Judge against the spec's User flow section."),
    ("ui_visual", 0.15,
     "Does the visual design match the UI/UX notes section -- palette hex values, type scale, radii, density, hierarchy? Does it look intentionally designed, or default-Bootstrap / default-Tailwind / default-shadcn slop? Use computed styles as objective evidence, not just screenshots."),
    ("motion", 0.05,
     "Are transitions present with durations and easing near the spec (typically 150ms / 250ms / cubic-bezier(0.16, 1, 0.3, 1))? Does the app respect prefers-reduced-motion when emulated? Zero motion is a cut; bouncy over-motion is also a cut if the spec forbids it."),
    ("accessibility", 0.05,
     "Visible focus indicator on Tab through, labels on icon buttons, WCAG AA text contrast (4.5:1 body), keyboard reachability. Judge against the spec's stated a11y bar."),
    ("responsiveness", 0.05,
     "Does the layout hold at the mobile and tablet viewports without horizontal overflow, overlapping elements, hidden CTAs, or squashed tables? Judge from multi-viewport screenshots."),
]

ADVISORY_NOTE = ("Diagnostic only. PLAN.md 1.4: judge_score never drives training. "
                 "A judge-only reward is trivially gamed. The binary substep grader "
                 "owns the RL reward; this score is for human review only.")

# --------------------------------------------------------------------------
# Pure helpers -- unit-tested without a browser.


def parse_instruction_sections(text: str) -> dict[str, str]:
    """Split instruction.md by ATX H2 (`## Section`). Returns section-name -> body.

    Keys are lowercased with spaces collapsed to underscores for stable lookup:
    "Core features" -> "core_features", "User flow" -> "user_flow",
    "UI/UX notes" -> "ui_ux_notes".
    """
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", raw_line)
        if m and not raw_line.startswith("###"):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            title = m.group(1).strip()
            current_key = _slug(title)
            current_lines = []
        else:
            if current_key is not None:
                current_lines.append(raw_line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()
    return sections


def _slug(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


WORKS_HEADROOM = 0.15


# ---------------------------------------------------------------------------
# Task-authored rubric (tests/rubric.json).
#
# The seven dimensions above are generic: they ask the same questions of every
# task. A task rubric asks about THIS product -- "renders the weekly trend so a
# lifter can tell whether the top load is rising" -- which the generic set cannot
# express. When tests/rubric.json exists it is graded INSTEAD of the generic
# dimensions, one LLM call per criterion, reusing the same evidence bundle.
#
# It stays advisory. PLAN.md 1.4: a judge-driven reward is trivially gamed, and
# score.py never reads anything from here into `reward`. What changes is that the
# advisory number now says something task-specific instead of something generic.

# `importance` -> relative weight. Ratio matters, not the absolute values; the
# weights are normalised so the composite stays in [0, 1] for any rubric.
IMPORTANCE_WEIGHT = {
    "critically_important": 5.0,
    "important": 3.0,
    "somewhat_important": 1.0,
}
DEFAULT_IMPORTANCE_WEIGHT = 1.0


def load_task_rubric(path: Path) -> list[dict]:
    """Read tests/rubric.json into the (name, weight, asks) shape used above.

    Criteria carry `is_positive`. A NEGATIVE criterion describes an anti-pattern
    the app must not exhibit -- "presents a retried set as a second visible
    entry". The judge is asked whether the anti-pattern is PRESENT, and the score
    is inverted, so detecting it lowers the composite. Grading a negative
    criterion the same way as a positive one rewards the app for being broken.
    """
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON array of criteria")

    out: list[dict] = []
    for i, c in enumerate(raw):
        number = str(c.get("number") or f"R{i + 1}")
        criterion = str(c.get("criterion") or "").strip()
        if not criterion:
            raise ValueError(f"{path}: criterion {number} has no `criterion` text")
        positive = bool(c.get("is_positive", True))
        weight = IMPORTANCE_WEIGHT.get(
            str(c.get("importance", "")), DEFAULT_IMPORTANCE_WEIGHT
        )
        if positive:
            asks = (
                f"{criterion}\n\n"
                "Score 1.0 if the deployed app fully satisfies this, 0.0 if it does "
                "not at all, and in between for partial. Judge ONLY this criterion. "
                "Cite concrete evidence -- computed styles, screenshots, the DOM, "
                "console output -- not impressions."
            )
        else:
            asks = (
                f"ANTI-PATTERN -- score how strongly the app AVOIDS this:\n\n"
                f"{criterion}\n\n"
                "Score 1.0 if the app does NOT exhibit this at all, 0.0 if it "
                "clearly does. This describes a defect, so a high score means the "
                "defect is absent. Cite concrete evidence."
            )
        out.append({
            "key": f"{number}_{c.get('dimension', 'unspecified')}",
            "number": number,
            "dimension": str(c.get("dimension", "unspecified")),
            "importance": str(c.get("importance", "")),
            "is_positive": positive,
            "raw_weight": weight,
            "asks": asks,
            "criterion": criterion,
        })

    total = sum(c["raw_weight"] for c in out) or 1.0
    for c in out:
        c["weight"] = round(c["raw_weight"] / total, 6)
    return out


def rubric_verdict(score: float) -> str:
    """A readable label beside the score. Presentation only -- never arithmetic.

    A rubric measures DEGREE, unlike a workflow substep which genuinely passes or
    fails, so `score` stays the source of truth and `judge_score` is computed from
    it alone. But a bare float per criterion is hard to scan, and readers were
    inventing their own cutoffs to answer "which ones failed?" -- so the cutoff is
    stated here once rather than differently by each reader.

    Thresholds match the scoring guide the judge is given:
        1.0 fully meets · 0.8 mostly meets · 0.5 partial · 0.2 barely · 0.0 absent

    `partial` covers 0.5, which is also what the judge is told to return when a
    criterion could not be assessed from the evidence -- so a `partial` deserves a
    look at its rationale before being read as a defect.
    """
    if score >= 0.8:
        return "pass"
    if score > 0.0:
        return "partial"
    return "fail"


def compute_task_rubric_score(criteria: list[dict], graded: dict[str, dict]) -> float:
    """Normalised weighted mean of the per-criterion scores.

    No functionality cap here: unlike the generic rubric there is no single
    `functionality` dimension to tie a ceiling to. The cap existed to stop
    aesthetics disguising a broken app -- a task rubric is mostly behavioural, and
    the reward is set by workflows + pytest regardless, so the guard is redundant.
    """
    total = 0.0
    for c in criteria:
        d = graded.get(c["key"]) or {}
        score = max(0.0, min(1.0, float(d.get("score", 0.0) or 0.0)))
        total += score * c["weight"]
    # Per-criterion weights are rounded to 6dp, so a long rubric can sum to
    # marginally over 1.0 (15 criteria -> 1.000003). Clamp so a perfect run
    # reports exactly 1.0 and the score can never leave [0, 1].
    return round(min(1.0, max(0.0, total)), 4)


def compute_judge_score(dimensions: dict[str, dict]) -> float:
    """Weighted sum capped by how well the app actually works.

    The plain weighted sum has a hole PLAN.md 1.3 mode 1 exists to catch: at a
    0.25 weight, an app that looks beautiful while throwing console errors and
    failed XHRs still lands near 0.85, because the aesthetic dimensions carry it.
    That is exactly the "builds green, runtime 500" app the benchmark is supposed
    to punish, and 1.4 warns a UI-oriented grader will reward things that merely
    look finished.

    Reweighting to fix it would gut the UI/UX read this tool exists to provide,
    so the ceiling is tied to `functionality` instead: presentation can add at
    most WORKS_HEADROOM above how well the thing runs. Polish still moves the
    score; it can no longer disguise a broken app.

    Invariants preserved: all-1.0 -> 1.0, all-0.0 -> 0.0.
    """
    total = 0.0
    functionality = 0.0
    for name, weight, _asks in RUBRIC:
        d = dimensions.get(name) or {}
        score = float(d.get("score", 0.0) or 0.0)
        # Clamp to [0, 1] -- a rogue model returning 1.5 must not inflate the score.
        score = max(0.0, min(1.0, score))
        if name == "functionality":
            functionality = score
        total += score * weight
    return round(min(total, functionality + WORKS_HEADROOM), 4)


def safe_dimension(name: str, weight: float, asks: str,
                   runner: Callable[[], dict]) -> dict:
    """Wrap a per-dimension runner so any exception yields a complete dict.

    Contract: the returned dict is always writable and always contains
    score/weight/rationale/evidence, matching the schema in judge.json.
    """
    try:
        result = runner()
        if not isinstance(result, dict):
            raise TypeError(f"runner returned {type(result).__name__}, not dict")
        score = float(result.get("score", 0.0) or 0.0)
        score = max(0.0, min(1.0, score))
        return {
            "score": score,
            "weight": weight,
            "rationale": str(result.get("rationale", ""))[:2000],
            "evidence": list(result.get("evidence", []))[:20],
            "asks": asks,
        }
    except Exception as exc:
        return {
            "score": 0.0,
            "weight": weight,
            "rationale": f"exception: {exc.__class__.__name__}: {exc}"[:2000],
            "evidence": [],
            "asks": asks,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_viewport(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)x(\d+)", s.strip())
    if not m:
        raise argparse.ArgumentTypeError(f"viewport must be WxH, got {s!r}")
    return int(m.group(1)), int(m.group(2))


def parse_viewport_list(s: str) -> list[tuple[int, int]]:
    return [parse_viewport(x) for x in s.split(",") if x.strip()]


# --------------------------------------------------------------------------
# JudgeAnthropic -- wraps the run_workflows client with a larger max_tokens
# budget. The parent hardcodes 1024, which truncates rationales.


class JudgeAnthropic(Anthropic):
    """Anthropic client with a rubric-sized output budget.

    Only the default max_tokens differs. The transport, including 429/5xx
    backoff, is inherited deliberately -- an independent copy of message() is how
    the judge previously missed the retry and lost every dimension to rate
    limiting.
    """

    def message(self, system: str, messages: list[dict], tools: list[dict],  # type: ignore[override]
                max_tokens: int = JUDGE_MAX_TOKENS) -> dict:
        return super().message(system, messages, tools, max_tokens=max_tokens)



# --------------------------------------------------------------------------
# Extra evidence tools on top of run_workflows.Browser. These operate on the
# Playwright page directly; they are stateless helpers, not methods, because
# the page swaps out per viewport.


def cap_screenshot(page, out_path: Path, max_bytes: int = 900_000) -> tuple[str, str]:
    """Save a viewport screenshot and return (path, base64). Downscale by JPEG
    quality if PNG exceeds max_bytes -- Anthropic image blocks want < 1.5 MB.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    png = page.screenshot(full_page=False, type="png")
    if len(png) <= max_bytes:
        out_path.write_bytes(png)
        return str(out_path), base64.b64encode(png).decode("ascii")
    # Fall back to JPEG at descending quality.
    for q in (85, 70, 55, 40, 25):
        jpg = page.screenshot(full_page=False, type="jpeg", quality=q)
        if len(jpg) <= max_bytes:
            jpg_path = out_path.with_suffix(".jpg")
            jpg_path.write_bytes(jpg)
            return str(jpg_path), base64.b64encode(jpg).decode("ascii")
    # Give up on shrinking; hand back the smallest attempt anyway.
    jpg_path = out_path.with_suffix(".jpg")
    jpg_path.write_bytes(jpg)
    return str(jpg_path), base64.b64encode(jpg).decode("ascii")


_STYLES_JS = r"""
() => {
  const wanted = ['color','background-color','font-family','font-size','font-weight',
                  'line-height','letter-spacing','border-radius','border','box-shadow',
                  'padding','margin','text-transform'];
  const pick = (el) => {
    const cs = getComputedStyle(el);
    const o = {};
    for (const p of wanted) o[p] = cs.getPropertyValue(p).trim();
    return o;
  };
  const selectors = ['body','h1','h2','h3','p','button','input','select','textarea',
                     'a','table','th','td','[role="button"]','.card','main','nav','header'];
  const out = {};
  for (const sel of selectors) {
    const nodes = Array.from(document.querySelectorAll(sel)).filter(e => {
      const r = e.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    }).slice(0, 3);
    if (!nodes.length) continue;
    out[sel] = nodes.map(pick);
  }
  return out;
}
"""

_MOTION_JS = r"""
() => {
  const animations = document.getAnimations().map(a => ({
    id: a.id, playState: a.playState,
    duration: (a.effect && a.effect.getTiming && a.effect.getTiming().duration) || null,
    easing:   (a.effect && a.effect.getTiming && a.effect.getTiming().easing)   || null,
  })).slice(0, 40);
  const tr = new Map();
  const nodes = document.querySelectorAll('*');
  let scanned = 0;
  for (const el of nodes) {
    if (scanned++ > 400) break;
    const cs = getComputedStyle(el);
    const key = [cs.transitionProperty, cs.transitionDuration,
                 cs.transitionTimingFunction].join('|');
    if (cs.transitionDuration && cs.transitionDuration !== '0s') {
      tr.set(key, (tr.get(key) || 0) + 1);
    }
    if (cs.animationName && cs.animationName !== 'none') {
      const k = 'anim|' + [cs.animationName, cs.animationDuration,
                           cs.animationTimingFunction].join('|');
      tr.set(k, (tr.get(k) || 0) + 1);
    }
  }
  const transitions = Array.from(tr.entries())
    .sort((a, b) => b[1] - a[1]).slice(0, 20)
    .map(([k, n]) => ({ key: k, count: n }));
  return { active_animations: animations, transitions,
           reduced_motion: window.matchMedia('(prefers-reduced-motion: reduce)').matches };
}
"""

_A11Y_JS = r"""
() => {
  const iconButtons = [];
  for (const b of document.querySelectorAll('button, a, [role="button"]')) {
    const text = (b.innerText || '').trim();
    const label = b.getAttribute('aria-label') || b.getAttribute('title') || '';
    if (!text && !label) {
      iconButtons.push({
        tag: b.tagName.toLowerCase(),
        html: (b.outerHTML || '').slice(0, 120),
        has_svg: !!b.querySelector('svg,img,i'),
      });
      if (iconButtons.length >= 10) break;
    }
  }
  const inputs = [];
  for (const i of document.querySelectorAll('input, select, textarea')) {
    const id = i.id;
    const labeled = !!(i.getAttribute('aria-label')
                       || (id && document.querySelector(`label[for="${id}"]`))
                       || i.closest('label'));
    if (!labeled) {
      inputs.push({ type: i.type || i.tagName.toLowerCase(), name: i.name || '' });
      if (inputs.length >= 10) break;
    }
  }
  const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4'))
    .slice(0, 20).map(h => ({ level: h.tagName, text: (h.innerText||'').slice(0,80) }));
  const landmarks = ['main','nav','header','footer','aside'].map(t => ({
    tag: t, count: document.querySelectorAll(t).length,
  }));
  return { icon_only_buttons_without_label: iconButtons,
           unlabeled_inputs: inputs, headings, landmarks };
}
"""


def cap_styles(page) -> dict:
    try:
        return page.evaluate(_STYLES_JS) or {}
    except Exception as exc:
        return {"_error": str(exc)}


def cap_motion(page) -> dict:
    try:
        return page.evaluate(_MOTION_JS) or {}
    except Exception as exc:
        return {"_error": str(exc)}


def cap_a11y(page) -> dict:
    try:
        return page.evaluate(_A11Y_JS) or {}
    except Exception as exc:
        return {"_error": str(exc)}


def focus_walk(page, presses: int = 10) -> list[dict]:
    """Tab through and record what receives focus, plus whether outline is visible."""
    out: list[dict] = []
    for _ in range(presses):
        try:
            page.keyboard.press("Tab")
            info = page.evaluate(r"""
              () => {
                const el = document.activeElement;
                if (!el || el === document.body) return null;
                const cs = getComputedStyle(el);
                return {
                  tag: el.tagName.toLowerCase(),
                  text: (el.innerText || el.value || '').slice(0, 40),
                  outline: cs.outline,
                  outline_width: cs.outlineWidth,
                  outline_style: cs.outlineStyle,
                  box_shadow: cs.boxShadow,
                };
              }
            """)
            if info:
                out.append(info)
        except Exception as exc:
            out.append({"_error": str(exc)})
            break
    return out


# --------------------------------------------------------------------------
# Console + network listeners registered at context creation. See spec: "so
# nothing is missed".


class Recorder:
    def __init__(self) -> None:
        self.console: list[dict] = []
        self.failed_requests: list[dict] = []

    def bind(self, context) -> None:
        def _on_console(msg):
            try:
                if msg.type in ("error", "warning"):
                    self.console.append({"type": msg.type, "text": msg.text[:500]})
            except Exception:
                pass
        def _on_pageerror(err):
            self.console.append({"type": "pageerror", "text": str(err)[:500]})
        def _on_requestfailed(req):
            try:
                self.failed_requests.append({
                    "url": req.url[:300],
                    "method": req.method,
                    "failure": (req.failure or "")[:200],
                })
            except Exception:
                pass
        def _on_response(resp):
            try:
                if resp.status >= 500:
                    self.failed_requests.append({
                        "url": resp.url[:300], "method": resp.request.method,
                        "status": resp.status,
                    })
            except Exception:
                pass
        context.on("console", _on_console)
        context.on("pageerror", _on_pageerror)
        context.on("requestfailed", _on_requestfailed)
        context.on("response", _on_response)


# --------------------------------------------------------------------------
# Exploration -- one browser session, gather evidence across viewports.


NAV_ROUTES_JS = r"""
() => {
  const origin = location.origin;
  const seen = new Set();
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    try {
      const u = new URL(a.href, location.href);
      if (u.origin !== origin) continue;
      if (u.pathname.match(/\.(png|jpe?g|svg|ico|css|js|pdf)$/i)) continue;
      if (seen.has(u.pathname)) continue;
      seen.add(u.pathname);
      out.push(u.pathname + (u.search || ''));
      if (out.length >= 12) break;
    } catch (e) {}
  }
  return out;
}
"""


def try_login(page, credentials_text: str) -> str:
    """Best-effort programmatic login using credentials from USER_README.md.

    Extract an email + a password with regex; if a login form is on the current
    page, fill and submit. Returns a status note.
    """
    if not credentials_text:
        return "no credentials file"
    email_m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", credentials_text)
    pw_m = None
    for pat in (r"[Pp]assword\s*[:=]\s*[`\"']?([^\s`\"'\n]+)",
                r"pass(?:word)?\s+is\s+`?([^\s`\n]+)"):
        pw_m = re.search(pat, credentials_text)
        if pw_m:
            break
    if not (email_m and pw_m):
        return "could not parse credentials"
    email, pw = email_m.group(0), pw_m.group(1)
    try:
        # Best guess: navigate to /login if present.
        try:
            page.goto(page.url.rstrip("/") + "/login", timeout=ACTION_TIMEOUT_MS,
                      wait_until="domcontentloaded")
        except Exception:
            pass
        # Find email + password inputs.
        for sel in ('input[type="email"]', 'input[name*="email" i]',
                    'input[name*="user" i]', 'input[type="text"]'):
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.fill(email, timeout=ACTION_TIMEOUT_MS)
                break
        for sel in ('input[type="password"]',):
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.fill(pw, timeout=ACTION_TIMEOUT_MS)
                break
        # Submit.
        for sel in ('button[type="submit"]', 'button:has-text("Sign in")',
                    'button:has-text("Log in")', 'button:has-text("Login")',
                    'input[type="submit"]'):
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.click(timeout=ACTION_TIMEOUT_MS)
                break
        page.wait_for_load_state("domcontentloaded", timeout=8000)
        return f"attempted login as {email}"
    except Exception as exc:
        return f"login attempt failed: {exc}"


def discover_routes(page) -> list[str]:
    try:
        return list(page.evaluate(NAV_ROUTES_JS) or [])
    except Exception:
        return []


def gather_evidence(playwright, url: str, credentials_text: str,
                    viewports: list[tuple[int, int]], routes: list[str] | None,
                    shot_dir: Path) -> dict:
    """One browser session -> screenshots + styles + motion + a11y + console."""
    evidence: dict = {
        "url": url,
        "viewports": [f"{w}x{h}" for w, h in viewports],
        "routes_visited": [],
        "screenshots": [],           # list of {path, viewport, route, b64}
        "styles": {},                # route -> dict
        "motion": {},                # route -> dict (primary viewport)
        "a11y": {},                  # route -> dict
        "focus_walk": [],            # from primary route/viewport
        "console": [],
        "failed_requests": [],
        "reduced_motion": {},        # {route: bool}
        "login_status": "",
    }
    if not viewports:
        viewports = [(1920, 1200)]
    primary_w, primary_h = viewports[0]

    recorder = Recorder()
    browser = playwright.chromium.launch(headless=True)
    try:
        context = browser.new_context(
            viewport={"width": primary_w, "height": primary_h},
            ignore_https_errors=True,
        )
        recorder.bind(context)
        page = context.new_page()
        page.set_default_timeout(ACTION_TIMEOUT_MS)

        try:
            page.goto(url, timeout=ACTION_TIMEOUT_MS, wait_until="domcontentloaded")
        except Exception as exc:
            print(f"  [warn] initial navigate failed: {exc}", file=sys.stderr)

        # Login attempt (best effort). Puts the session inside the app.
        evidence["login_status"] = try_login(page, credentials_text)

        # Re-anchor at "/".
        try:
            page.goto(url, timeout=ACTION_TIMEOUT_MS, wait_until="domcontentloaded")
        except Exception:
            pass

        if not routes:
            discovered = discover_routes(page)
            routes = ["/"] + [r for r in discovered if r not in ("/",)][:8]
        else:
            routes = ["/" if r == "" else r for r in routes]

        for i, route in enumerate(routes):
            try:
                # Normalize
                target = url.rstrip("/") + (route if route.startswith("/") else "/" + route)
                page.goto(target, timeout=ACTION_TIMEOUT_MS, wait_until="domcontentloaded")
                evidence["routes_visited"].append(route)
                time.sleep(0.4)  # settle animations
            except Exception as exc:
                print(f"  [warn] route {route} failed: {exc}", file=sys.stderr)
                continue

            # Primary-viewport rich evidence.
            evidence["styles"][route] = cap_styles(page)
            evidence["motion"][route] = cap_motion(page)
            evidence["a11y"][route]   = cap_a11y(page)

            slug = re.sub(r"[^a-zA-Z0-9]+", "_", route).strip("_") or "root"
            for w, h in viewports:
                try:
                    page.set_viewport_size({"width": w, "height": h})
                    time.sleep(0.2)
                    shot_path = shot_dir / f"{i:02d}_{slug}_{w}x{h}.png"
                    path_str, b64 = cap_screenshot(page, shot_path)
                    evidence["screenshots"].append({
                        "path": path_str, "viewport": f"{w}x{h}",
                        "route": route, "b64": b64,
                    })
                except Exception as exc:
                    print(f"  [warn] shot {route} @ {w}x{h} failed: {exc}", file=sys.stderr)
            # Restore primary viewport before next route.
            try:
                page.set_viewport_size({"width": primary_w, "height": primary_h})
            except Exception:
                pass

        # Focus walk on the current (last) route as a proxy for the app-wide
        # focus indicator. Cheap and better than nothing.
        evidence["focus_walk"] = focus_walk(page, presses=8)

        context.close()

        # Reduced-motion check: fresh context with the media feature set.
        try:
            rm_ctx = browser.new_context(
                viewport={"width": primary_w, "height": primary_h},
                reduced_motion="reduce", ignore_https_errors=True,
            )
            rm_page = rm_ctx.new_page()
            rm_page.goto(url, timeout=ACTION_TIMEOUT_MS, wait_until="domcontentloaded")
            time.sleep(0.5)
            evidence["reduced_motion"]["/"] = cap_motion(rm_page)
            rm_ctx.close()
        except Exception as exc:
            evidence["reduced_motion"]["_error"] = str(exc)

        evidence["console"] = recorder.console[:80]
        evidence["failed_requests"] = recorder.failed_requests[:40]
    finally:
        try:
            browser.close()
        except Exception:
            pass

    return evidence


# --------------------------------------------------------------------------
# LLM-driven per-dimension grading.

REPORT_TOOL = {
    "name": "report_dimension",
    "description": ("MANDATORY final call. Return your score (0.0-1.0), a one-to-three "
                    "sentence rationale, and at least one concrete evidence reference "
                    "(a screenshot filename, a computed-style value, a console error "
                    "string, or a specific route)."),
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "rationale": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "rationale", "evidence"],
    },
}


def _shortlist_styles(styles_by_route: dict, limit_routes: int = 3) -> dict:
    """Return only the first N routes to keep prompts small."""
    out: dict = {}
    for i, (route, styles) in enumerate(styles_by_route.items()):
        if i >= limit_routes:
            break
        out[route] = styles
    return out


def _shortlist_shots(shots: list[dict], limit: int = 6) -> list[dict]:
    """Pick a spread of screenshots that covers EVERY route.

    The previous version grouped by viewport and kept the first N of each. Since
    shots are captured route-by-route, that always kept the first N routes and
    silently dropped the rest -- with three routes and two per viewport, /trend
    never reached the judge. It then scored "renders the weekly trend" 0.00 with
    the rationale "no screenshots of the /trend page were provided", on a page the
    browser grader had just driven successfully (2026-08-06).

    Absence of evidence read as evidence of absence, caused by a silent truncation.

    Route coverage now comes first: one shot per route (widest viewport, where
    layout is most legible), then the remaining budget is spent on additional
    viewports round-robin so responsive checks still get material. A route is only
    dropped when there are more routes than `limit`, and that is a real cap rather
    than an accident of ordering.
    """
    if not shots:
        return []

    by_route: dict[str, list[dict]] = {}
    for s in shots:
        by_route.setdefault(s.get("route", "?"), []).append(s)

    def widest_first(lst: list[dict]) -> list[dict]:
        def width(s: dict) -> int:
            try:
                return int(str(s.get("viewport", "0x0")).split("x")[0])
            except ValueError:
                return 0
        return sorted(lst, key=width, reverse=True)

    ordered = {r: widest_first(lst) for r, lst in by_route.items()}

    picked: list[dict] = []
    # Pass 1: guarantee every route is represented.
    for route, lst in ordered.items():
        if len(picked) >= limit:
            break
        picked.append(lst[0])

    # Pass 2: spend what's left on further viewports, round-robin across routes so
    # no single route monopolises the budget.
    depth = 1
    while len(picked) < limit and any(len(lst) > depth for lst in ordered.values()):
        for lst in ordered.values():
            if len(picked) >= limit:
                break
            if len(lst) > depth:
                picked.append(lst[depth])
        depth += 1

    return picked


def _image_blocks(shots: list[dict], limit: int = 6) -> list[dict]:
    """Turn screenshot records into Anthropic image content blocks."""
    blocks: list[dict] = []
    for s in shots[:limit]:
        # Determine media type from stored extension.
        media = "image/png" if s["path"].endswith(".png") else "image/jpeg"
        blocks.append({"type": "text",
                       "text": f"Screenshot: route={s['route']} viewport={s['viewport']} path={s['path']}"})
        blocks.append({"type": "image",
                       "source": {"type": "base64", "media_type": media, "data": s["b64"]}})
    return blocks


def grade_dimension(llm: JudgeAnthropic, name: str, asks: str,
                    instruction_sections: dict[str, str],
                    evidence: dict, max_steps: int) -> dict:
    """One LLM call per dimension. The model is given the focused rubric plus
    the pre-gathered evidence, and returns a score via report_dimension.
    """
    # Focused system prompt per dimension.
    spec_bits = []
    for key in ("core_features", "user_flow", "ui_ux_notes", "constraints",
                "user_roles", "overview"):
        v = instruction_sections.get(key, "").strip()
        if v:
            spec_bits.append(f"### {key.replace('_', ' ').title()}\n{v[:2500]}")
    spec_text = "\n\n".join(spec_bits)[:9000]

    system = (
        "You are a rigorous UX/QA judge grading a deployed web app against a written spec.\n"
        f"You are scoring exactly ONE dimension: {name}.\n\n"
        f"What this dimension asks: {asks}\n\n"
        "Scoring guide:\n"
        "  1.0 = fully meets the spec on this dimension, no notable issues\n"
        "  0.8 = mostly meets, with one or two small gaps\n"
        "  0.5 = partially meets, real gaps against the spec\n"
        "  0.2 = barely present, wrong direction, or broken in most places\n"
        "  0.0 = absent, unreachable, throws, or blatantly wrong\n\n"
        "Rules:\n"
        "- Ground every claim in the evidence provided. Cite screenshot filenames, "
        "computed-style values, console errors, or specific routes.\n"
        "- Do NOT invent evidence. If evidence is thin, say so and score cautiously.\n"
        "- MISSING EVIDENCE IS NOT A FAILING APP. If the evidence bundle does not "
        "contain what this criterion needs -- no screenshot of the relevant route, "
        "no computed style for the element in question -- you have NOT observed a "
        "defect. Say plainly in the rationale that the criterion could not be "
        "assessed from the evidence, and score 0.5 rather than 0.0. Reserve 0.0 "
        "for a defect you can actually point at. Scoring an unobserved criterion "
        "as absent turns a gap in the harness into a mark against the app, and a "
        "route WAS reachable if it appears in routes_visited.\n"
        "- Score AGAINST THE PROVIDED SPEC below, not a generic notion of good.\n"
        "- Call report_dimension exactly once. That call ends grading.\n\n"
        "=== SPEC EXCERPTS ===\n" + spec_text
    )

    # First user turn: the evidence catalog + images.
    console = evidence.get("console", [])[:20]
    failed = evidence.get("failed_requests", [])[:15]
    shots_summary = _shortlist_shots(evidence.get("screenshots", []))
    styles_summary = _shortlist_styles(evidence.get("styles", {}))
    motion_summary = evidence.get("motion", {})
    reduced_motion = evidence.get("reduced_motion", {})
    a11y_summary = evidence.get("a11y", {})
    focus = evidence.get("focus_walk", [])
    routes = evidence.get("routes_visited", [])

    evidence_json = {
        "app_url": evidence.get("url"),
        "viewports_tested": evidence.get("viewports"),
        "routes_visited": routes,
        "login_status": evidence.get("login_status"),
        "console_errors_and_warnings": console,
        "failed_or_5xx_requests": failed,
        "computed_styles_sample": styles_summary,
        "motion": motion_summary,
        "motion_with_reduced_motion": reduced_motion,
        "a11y_probes": a11y_summary,
        "focus_walk": focus,
        "screenshots_index": [{k: s[k] for k in ("path", "route", "viewport")}
                              for s in shots_summary],
    }
    first_content: list[dict] = [
        {"type": "text",
         "text": f"Grade dimension `{name}`. Evidence follows.\n\n"
                 f"```json\n{json.dumps(evidence_json, indent=2)[:20000]}\n```"},
    ]
    first_content.extend(_image_blocks(shots_summary))
    first_content.append({"type": "text",
                          "text": "Now call report_dimension with score, rationale, evidence."})

    messages: list[dict] = [{"role": "user", "content": first_content}]
    tools = [REPORT_TOOL]

    for step in range(max_steps):
        resp = llm.message(system=system, messages=messages, tools=tools)
        content_blocks = resp.get("content", [])
        messages.append({"role": "assistant", "content": content_blocks})
        tool_uses = [b for b in content_blocks if b.get("type") == "tool_use"]
        if not tool_uses:
            text = " ".join(b.get("text", "") for b in content_blocks
                            if b.get("type") == "text")[:400]
            # Give the model one more chance to comply.
            messages.append({"role": "user",
                             "content": "You must call report_dimension. Do it now."})
            if step >= 1:
                return {"score": 0.0,
                        "rationale": f"model refused to call report_dimension: {text!r}",
                        "evidence": []}
            continue
        for tu in tool_uses:
            if tu.get("name") == "report_dimension":
                inp = tu.get("input", {}) or {}
                return {
                    "score": float(inp.get("score", 0.0)),
                    "rationale": str(inp.get("rationale", "")),
                    "evidence": [str(x) for x in (inp.get("evidence") or [])],
                }
        # Unknown tool -- shouldn't happen; nudge.
        messages.append({"role": "user",
                         "content": "Unknown tool. Call report_dimension."})

    return {"score": 0.0,
            "rationale": f"exceeded {max_steps} LLM steps without report_dimension",
            "evidence": []}


# --------------------------------------------------------------------------
# Missing-features detector: quick keyword-based diff against evidence.


def detect_missing_features(instruction_sections: dict[str, str],
                            evidence: dict) -> list[str]:
    """Cheap heuristic: pull `route` labels from the User flow table and flag
    any that the app never reached (or that 404'd). Not exhaustive; the LLM
    dimensions catch the rest.
    """
    flow = instruction_sections.get("user_flow", "")
    routes_in_spec = set()
    for m in re.finditer(r"`(/[^`\s]+)`", flow):
        r = m.group(1)
        r = re.sub(r":\w+", "", r).rstrip("/") or "/"
        routes_in_spec.add(r)
    visited = set()
    for v in evidence.get("routes_visited", []):
        base = re.sub(r"\?.*$", "", v).rstrip("/") or "/"
        visited.add(base)
    missing = sorted(r for r in routes_in_spec if r not in visited)
    return missing[:20]


# --------------------------------------------------------------------------
# Main


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="run_rubric.py",
        description=(
            "Deku rubric judge -- ADVISORY / DIAGNOSTIC ONLY.\n\n"
            "Writes judge.json with a weighted `judge_score` and per-dimension "
            "breakdown. PLAN.md 1.4: this score is recorded but NEVER drives "
            "training. The binary substep grader (run_workflows.py + score.py) "
            "owns the RL reward; this tool is the human-facing quality read.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--instruction", required=True, type=Path,
                    help="Path to instruction.md -- the spec the app is judged against.")
    ap.add_argument("--url", required=True,
                    help="Base URL of the deployed app.")
    ap.add_argument("--out", required=True, type=Path,
                    help="Where to write judge.json.")
    ap.add_argument("--credentials-path", default=DEFAULT_CREDENTIALS_PATH,
                    help="Path to USER_README.md with default credentials.")
    ap.add_argument("--screenshot-dir", type=Path, default=None,
                    help="Directory for screenshots (default: <out-dir>/shots/).")
    ap.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS,
                    help="Max LLM steps per dimension.")
    ap.add_argument("--rubric", type=Path, default=None,
                    help="tests/rubric.json. When present, the task's own criteria "
                         "are graded INSTEAD of the seven generic dimensions. Still "
                         "advisory -- score.py never reads it into `reward`.")
    ap.add_argument("--routes", default="",
                    help="Comma-separated routes to visit. Auto-discovered if empty.")
    ap.add_argument("--viewports", default=DEFAULT_VIEWPORTS,
                    help=f"Comma-separated WxH list (default: {DEFAULT_VIEWPORTS}). "
                         "First is primary.")
    return ap


def main() -> int:
    args = build_argparser().parse_args()

    started = now_iso()
    shot_dir = args.screenshot_dir or (args.out.parent / "shots")
    viewports = parse_viewport_list(args.viewports)
    routes = [r.strip() for r in args.routes.split(",") if r.strip()] or None
    model = os.environ.get("DEKU_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)

    meta: dict = {
        "grader_model": model,
        "url": args.url,
        "viewports": [f"{w}x{h}" for w, h in viewports],
        "instruction": str(args.instruction),
        "started_at": started,
        "harness": "run_rubric.py",
    }
    # Pre-write a zero-score payload so a mid-run crash still leaves a file.
    payload: dict = {
        "judge_score": 0.0,
        "advisory": True,
        "note": ADVISORY_NOTE,
        "dimensions": {},
        "missing_features": [],
        "console_errors": [],
        "screenshots": [],
        "meta": meta,
    }
    _write_json(args.out, payload)

    # Parse instruction sections.
    try:
        instruction_text = args.instruction.read_text()
    except Exception as exc:
        meta["error"] = f"could not read instruction: {exc}"
        payload["meta"] = meta
        _write_json(args.out, payload)
        return 0
    sections = parse_instruction_sections(instruction_text)

    # Playwright import guarded -- verifier image installs it; local dev may not.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        meta["error"] = f"playwright not installed: {exc}"
        payload["meta"] = meta
        _write_json(args.out, payload)
        print(f"playwright not installed: {exc}; wrote zero-score judge.json",
              file=sys.stderr)
        return 0

    # Gather evidence.
    creds = read_credentials(args.credentials_path)

    print(f"gathering evidence @ {args.url} across {len(viewports)} viewport(s)",
          file=sys.stderr)
    evidence: dict
    try:
        with sync_playwright() as p:
            evidence = gather_evidence(p, args.url, creds, viewports, routes, shot_dir)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        meta["error"] = f"evidence gathering failed: {exc.__class__.__name__}: {exc}"
        evidence = {"url": args.url, "viewports": [f"{w}x{h}" for w, h in viewports],
                    "routes_visited": [], "screenshots": [], "styles": {},
                    "motion": {}, "a11y": {}, "focus_walk": [], "console": [],
                    "failed_requests": [], "reduced_motion": {},
                    "login_status": "n/a (crash)"}

    # Grade each dimension. Any exception per-dimension -> score 0.0.
    llm = JudgeAnthropic(model=model)
    dimensions: dict[str, dict] = {}

    task_criteria: list[dict] = []
    if args.rubric and args.rubric.exists():
        try:
            task_criteria = load_task_rubric(args.rubric)
            print(f"task rubric: {len(task_criteria)} criteria from {args.rubric}",
                  file=sys.stderr)
        except Exception as exc:
            # A malformed rubric must not lose the whole judge pass -- fall back to
            # the generic dimensions and say so, rather than scoring everything 0.
            print(f"  [warn] {args.rubric} unreadable ({exc}); falling back to the "
                  f"generic dimensions", file=sys.stderr)
            meta["rubric_error"] = f"{exc.__class__.__name__}: {exc}"

    try:
        if task_criteria:
            meta["rubric_source"] = str(args.rubric)
            meta["rubric_criteria"] = len(task_criteria)
            for c in task_criteria:
                print(f"grading {c['number']} [{c['dimension']}/{c['importance']}"
                      f"{'' if c['is_positive'] else '/NEGATIVE'}] "
                      f"weight {c['weight']:.3f}", file=sys.stderr)
                def _runner(_c=c) -> dict:
                    return grade_dimension(llm, _c["key"], _c["asks"], sections,
                                           evidence, args.max_steps)
                graded = safe_dimension(c["key"], c["weight"], c["asks"], _runner)
                graded.update({
                    "number": c["number"], "dimension": c["dimension"],
                    "importance": c["importance"], "is_positive": c["is_positive"],
                    "criterion": c["criterion"],
                    "verdict": rubric_verdict(graded.get("score", 0.0)),
                })
                dimensions[c["key"]] = graded
                payload["dimensions"] = dimensions
                payload["judge_score"] = compute_task_rubric_score(task_criteria, dimensions)
                _write_json(args.out, payload)
        else:
            for name, weight, asks in RUBRIC:
                print(f"grading dimension `{name}` (weight {weight})", file=sys.stderr)
                def _runner(_name=name, _asks=asks) -> dict:
                    return grade_dimension(llm, _name, _asks, sections, evidence,
                                           args.max_steps)
                dimensions[name] = safe_dimension(name, weight, asks, _runner)
                payload["dimensions"] = dimensions
                payload["judge_score"] = compute_judge_score(dimensions)
                _write_json(args.out, payload)  # incremental persistence
    finally:
        try:
            llm.close()
        except Exception:
            pass

    payload["judge_score"] = (
        compute_task_rubric_score(task_criteria, dimensions) if task_criteria
        else compute_judge_score(dimensions)
    )
    payload["dimensions"] = dimensions
    payload["missing_features"] = detect_missing_features(sections, evidence)
    payload["console_errors"] = [
        c.get("text", "") for c in evidence.get("console", []) if c.get("type") in
        ("error", "pageerror")
    ][:40]
    payload["screenshots"] = [s["path"] for s in evidence.get("screenshots", [])]
    meta["finished_at"] = now_iso()
    meta["routes_visited"] = evidence.get("routes_visited", [])
    meta["login_status"] = evidence.get("login_status", "")
    # Judge spend. harness/finance/usage.py reads `meta.usage` to build the
    # judge_lines entry finance bills grading against; with it absent the entry
    # is omitted and the run reports agent cost only, understating real spend.
    # Guarded because a missing cost figure must never fail a grading run.
    try:
        meta["usage"] = llm.usage_snapshot()
    except Exception:
        pass
    payload["meta"] = meta

    _write_json(args.out, payload)
    print(f"judge_score = {payload['judge_score']:.4f} (advisory, "
          f"see PLAN.md 1.4). wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
