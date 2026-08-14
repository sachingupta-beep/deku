#!/usr/bin/env python3
"""Deterministic motion assertions for pytest substeps.

    from motion import motion_probe

    def test_reject_modal_animates_in():
        with motion_probe(path="/journals/J-1001") as m:
            m.page.click("button:has-text('Reject')")
            m.settle()
        m.assert_animated(within_ms=200)
        m.assert_duration_between(150, 600)
        m.assert_no_jank()

WHY THIS EXISTS

Motion was graded only by the rubric judge, from a single-instant sample of
`document.getAnimations()` plus computed styles. That answers "does a transition
exist somewhere on this page", never "did the right thing move at the right
moment", and the judge cannot tell those apart. Measured across every run in
output/:

    E_finan_appr_payroll-journal-app  R16_motion:  0.0  1.0  1.0  0.0  0.6  1.0

Six runs of one task, verdicts spanning the whole range. And 157 of 701 rubric
scores corpus-wide are exactly 0.5 -- the judge's "I cannot tell" -- with motion
landing there more than any other dimension.

This module replaces the guess with numbers, from two browser sources:

    CDP Animation domain    an EVENT STREAM. `Animation.animationStarted` fires
                            with a startTime, so "did this click cause motion,
                            and how soon" becomes a measurement.
    LoAF PerformanceObserver  `long-animation-frame` entries. Smooth motion needs
                            a frame every ~16ms; LoAF reports the ones that blew
                            past that, and what blocked them.

Both are objective and reproducible, so unlike judge_score they are safe to feed
the reward through a `kind: pytest` substep (PLAN.md 1.4).

ASSERT RELATIONSHIPS, NOT VALUES

Every helper here takes a BAND or an ORDERING, never an exact number, and that is
deliberate. `duration == 300` fails an app that chose 280ms and looks identical --
the same defect as a test suite pinning route names the brief never gave, which
cost a whole run on 2026-08-13. Assert what the brief actually promises: that
something moved, that it moved when the user acted, that it did not crawl or
flash, that a stagger ran in order. Those survive reasonable implementation
choices while still catching an app that animates nothing.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

# Frame budget for 60fps is ~16.7ms. LoAF only reports frames that already blew
# well past it, so this threshold is about how much overshoot counts as visible
# stutter rather than about the budget itself.
JANK_FRAME_MS = 100.0

# Installed before the interaction so the observer is live when motion starts.
_LOAF_JS = """
() => {
  window.__loaf = [];
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        window.__loaf.push({
          duration: e.duration,
          start: e.startTime,
          blocking: e.blockingDuration || 0,
        });
      }
    }).observe({type: 'long-animation-frame', buffered: true});
    window.__loaf_supported = true;
  } catch (err) {
    // Not in this browser build. Absence of data must read as "not measured",
    // never as "no jank" -- see assert_no_jank.
    window.__loaf_supported = false;
  }
}
"""


class MotionUnavailable(RuntimeError):
    """Motion could not be OBSERVED. Never a statement about the app.

    Raised when the browser exposes no CDP session, i.e. the grader is not on
    Chromium. A test seeing this should skip, not fail: scoring an app on a
    measurement the harness could not take is the thing score.py's `invalid`
    handling exists to prevent.
    """


class MotionProbe:
    """Captures animation starts and long frames around one interaction."""

    def __init__(self, page):
        self.page = page
        self.animations: list[dict] = []
        self.loaf: list[dict] = []
        self._cdp = None
        self._t0: float = 0.0

    # -------------------------------------------------------------- capture
    def start(self) -> "MotionProbe":
        try:
            self._cdp = self.page.context.new_cdp_session(self.page)
        except Exception as exc:  # non-Chromium, or CDP disabled
            raise MotionUnavailable(f"no CDP session available: {exc}") from exc
        self._cdp.send("Animation.enable")
        self._cdp.on("Animation.animationStarted",
                     lambda e: self.animations.append(e))
        self.page.evaluate(_LOAF_JS)
        # The clock every "did it react to the click" assertion is measured
        # against. Taken from the PAGE, because CDP startTime is on the page's
        # timeline and a host-side time would not be comparable.
        self._t0 = self.page.evaluate("() => performance.now()")
        return self

    def settle(self, ms: int = 600) -> None:
        """Wait for motion to play out. Call after the interaction, before exit."""
        self.page.wait_for_timeout(ms)

    def stop(self) -> None:
        try:
            self.loaf = self.page.evaluate("() => window.__loaf || []") or []
            self._loaf_supported = bool(
                self.page.evaluate("() => window.__loaf_supported === true"))
        except Exception:
            self.loaf, self._loaf_supported = [], False
        if self._cdp is not None:
            try:
                self._cdp.send("Animation.disable")
            except Exception:
                pass

    # ------------------------------------------------------------ accessors
    @property
    def starts(self) -> list[float]:
        """Effective start times relative to the interaction, oldest first.

        EFFECTIVE means `startTime + source.delay`, and the distinction is the
        whole ballgame for staggers. A CSS stagger is written as one rule plus
        per-element `animation-delay`, and every one of those animations is
        CREATED at the same instant -- `Animation.animationStarted` reports an
        identical startTime for all of them. Measured:

            startTime=93 delay=0    duration=200
            startTime=93 delay=60   duration=200
            startTime=93 delay=120  duration=200

        Reading startTime alone therefore sees three simultaneous animations and
        calls a correct stagger a failure. The delay is where the sequencing
        lives. Events also arrive out of order, hence the sort.
        """
        out = []
        for e in self.animations:
            a = e.get("animation") or {}
            st = a.get("startTime")
            if st is None:
                continue
            delay = ((a.get("source") or {}).get("delay")) or 0
            out.append(st + float(delay) - self._t0)
        return sorted(out)

    @property
    def durations(self) -> list[float]:
        out = []
        for e in self.animations:
            src = ((e.get("animation") or {}).get("source") or {})
            d = src.get("duration")
            if d is not None:
                out.append(float(d))
        return out

    def describe(self) -> str:
        """Human-readable capture, for assertion messages."""
        if not self.animations:
            return "no animations fired"
        parts = []
        for e in self.animations[:6]:
            a = e.get("animation") or {}
            src = a.get("source") or {}
            eff = (a.get("startTime") or 0) + float(src.get("delay") or 0) - self._t0
            parts.append(f"{a.get('type')} +{eff:.0f}ms for {src.get('duration')}ms "
                         f"{src.get('easing')}")
        return "; ".join(parts)

    # ----------------------------------------------------------- assertions
    def assert_animated(self, within_ms: float = 200, count: int = 1) -> None:
        """At least `count` animations began within `within_ms` of the interaction.

        The window is what separates "this app animates" from "this app animated
        BECAUSE of the click". An idle carousel looping in the corner satisfies
        the former and tells you nothing about the interaction under test.
        """
        prompt = [s for s in self.starts if -50 <= s <= within_ms]
        assert len(prompt) >= count, (
            f"expected at least {count} animation(s) within {within_ms:.0f}ms of "
            f"the interaction, saw {len(prompt)}. Captured: {self.describe()}"
        )

    def assert_not_animated(self) -> None:
        """Nothing moved. For prefers-reduced-motion, and for 'this must be instant'."""
        assert not self.animations, (
            f"expected no motion here, but {len(self.animations)} animation(s) "
            f"fired: {self.describe()}"
        )

    def assert_duration_between(self, lo_ms: float, hi_ms: float) -> None:
        """Every captured duration sits inside a band.

        A band, never an equality: an app that picked 280ms where the brief
        implied 300ms is not wrong. Below `lo` the motion is a flash the user
        cannot follow; above `hi` it is a delay they wait through. That is the
        real requirement, and it is what the band should encode.
        """
        assert self.durations, f"no animation durations captured: {self.describe()}"
        bad = [d for d in self.durations if not (lo_ms <= d <= hi_ms)]
        assert not bad, (
            f"animation duration(s) {bad} outside {lo_ms:.0f}-{hi_ms:.0f}ms. "
            f"Captured: {self.describe()}"
        )

    def assert_staggered(self, count: int, min_gap_ms: float = 10,
                         max_gap_ms: float = 400) -> None:
        """`count` animations began in sequence, each after the last.

        Checks ORDER and spacing, not absolute times, which is what "arriving
        left to right at a short stagger" actually means. Simultaneous starts
        (gap 0) are the failure this catches: the elements appear together and
        no stagger was implemented.
        """
        starts = self.starts
        assert len(starts) >= count, (
            f"expected {count} staggered animations, saw {len(starts)}. "
            f"Captured: {self.describe()}"
        )
        gaps = [b - a for a, b in zip(starts[:count - 1], starts[1:count])]
        bad = [g for g in gaps if not (min_gap_ms <= g <= max_gap_ms)]
        assert not bad, (
            f"stagger gaps {[round(g) for g in gaps]}ms include values outside "
            f"{min_gap_ms:.0f}-{max_gap_ms:.0f}ms; 0 means they started together. "
            f"Captured: {self.describe()}"
        )

    def assert_no_jank(self, max_frame_ms: float = JANK_FRAME_MS,
                       allowed: int = 0) -> None:
        """No more than `allowed` frames overshot the budget during the capture.

        Skips rather than passes when the browser has no LoAF support: an
        unmeasured page must not report as a smooth one.
        """
        if not getattr(self, "_loaf_supported", False):
            import pytest
            pytest.skip("long-animation-frame is unsupported in this browser build")
        long_frames = [f for f in self.loaf if f.get("duration", 0) > max_frame_ms]
        assert len(long_frames) <= allowed, (
            f"{len(long_frames)} frame(s) over {max_frame_ms:.0f}ms during the "
            f"animation (worst {max(f['duration'] for f in long_frames):.0f}ms); "
            f"the motion visibly stutters"
        )


@contextmanager
def motion_probe(path: str = "/", page=None, reduced_motion: str | None = None,
                 viewport: tuple[int, int] = (1280, 800)):
    """Probe around an interaction, opening a browser if one is not supplied.

    `reduced_motion="reduce"` drives the accessibility half of a motion
    requirement: the same interaction must then satisfy assert_not_animated.
    """
    if page is not None:
        probe = MotionProbe(page).start()
        try:
            yield probe
        finally:
            probe.stop()
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - image without playwright
        raise MotionUnavailable(f"playwright not installed: {exc}") from exc

    base = os.environ["APP_PUBLIC_URL"].rstrip("/")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        try:
            context = browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                reduced_motion=reduced_motion,
            )
            pg = context.new_page()
            pg.goto(f"{base}{path}", wait_until="domcontentloaded", timeout=15000)
            probe = MotionProbe(pg).start()
            try:
                yield probe
            finally:
                probe.stop()
        finally:
            browser.close()
