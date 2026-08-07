"""Denial at the API: the unauthenticated surface and ownership scoping between the two
seeded lifters.

Every denial here is asserted at the HTTP boundary, never by inspecting the agent's source
(INV6). Where the brief is tolerant about which refusal status applies, the assertion is
tolerant too.
"""

from conftest import (
    LIFTER2_EMAIL,
    SEED_WEEK,
    SETS_PATH,
    SLUG_SQUAT,
    TREND_PATH,
    log_set,
    open_session,
    request,
    trend_series,
    unique_uid,
    week_entry,
)


def test_trend_without_token_is_denied_401(lifter_token):
    # cov: C-RL-10
    r = request("GET", f"{TREND_PATH}?exercise={SLUG_SQUAT}")
    assert r.status_code == 401, (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT} with no Authorization header: expected 401, "
        f"observed {r.status_code}; an unauthenticated read of a lifter's training log must "
        f"be refused at the API; body: {r.excerpt()}")


def test_set_into_another_lifters_session_is_denied_404(lifter_token, lifter2_token):
    # cov: C-CF-44
    foreign_session = open_session(lifter_token)
    uid = unique_uid("cross-owner")

    r = log_set(lifter2_token, foreign_session, uid, weight_kg=90, reps=6)
    assert r.status_code == 404, (
        f"POST {SETS_PATH} as {LIFTER2_EMAIL} into session {foreign_session}, which belongs "
        f"to the other seeded lifter: expected 404, observed {r.status_code}; body: "
        f"{r.excerpt()}")

    owner_view = trend_series(lifter_token, SLUG_SQUAT)
    owner_week = week_entry(owner_view, SEED_WEEK)
    assert owner_week is not None, (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT} as the session owner: the seeded week "
        f"{SEED_WEEK!r} is missing after a refused cross-owner write; series: {owner_view!r}")
    assert owner_week.get("set_count") == 2, (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT} week {SEED_WEEK}: set_count is "
        f"{owner_week.get('set_count')!r} after a refused cross-owner write, expected the "
        f"unchanged 2; the refusal must leave the owner's rows untouched")


def test_trend_is_scoped_to_the_calling_lifter(lifter2_token):
    # cov: C-CF-22
    series = trend_series(lifter2_token, SLUG_SQUAT)
    assert series == [], (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT} as {LIFTER2_EMAIL}, who is seeded with no "
        f"sessions and no sets: expected an empty series, observed {series!r}; a trend that "
        f"returns another lifter's weeks is not scoped to the caller")
