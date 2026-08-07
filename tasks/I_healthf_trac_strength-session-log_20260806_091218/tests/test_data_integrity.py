"""Persistence and reconciliation: the weekly trend against the rows behind it, and the
idempotency-by-delta assertion that a replay moves nothing.

This is where a double-count becomes visible. A set list can look right while the number the
lifter reads is wrong, so the trend is what gets interrogated here.
"""

from conftest import (
    SEED_SQUAT_SET_COUNT,
    SEED_SQUAT_TOP_WEIGHT,
    SEED_SQUAT_UID_1,
    SEED_SQUAT_VOLUME,
    SEED_WEEK,
    SETS_PATH,
    SLUG_SQUAT,
    TREND_PATH,
    log_set,
    total_set_count,
    trend_series,
    unique_uid,
    week_counts,
    week_entry,
)


def test_trend_reports_seeded_week_totals(lifter_token):
    # cov: C-CF-26
    series = trend_series(lifter_token, SLUG_SQUAT)
    entry = week_entry(series, SEED_WEEK)
    assert entry is not None, (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT}: no entry for the seeded week "
        f"{SEED_WEEK!r}; series: {series!r}")
    assert entry.get("top_weight_kg") in (SEED_SQUAT_TOP_WEIGHT, float(SEED_SQUAT_TOP_WEIGHT)), (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT} week {SEED_WEEK}: top_weight_kg is "
        f"{entry.get('top_weight_kg')!r}, expected {SEED_SQUAT_TOP_WEIGHT} (the heavier of "
        f"the two seeded squat sets); entry: {entry!r}")
    assert entry.get("volume_kg") in (SEED_SQUAT_VOLUME, float(SEED_SQUAT_VOLUME)), (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT} week {SEED_WEEK}: volume_kg is "
        f"{entry.get('volume_kg')!r}, expected {SEED_SQUAT_VOLUME} (100x5 + 105x3); a value "
        f"above this counts a seeded set twice; entry: {entry!r}")
    assert entry.get("set_count") == SEED_SQUAT_SET_COUNT, (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT} week {SEED_WEEK}: set_count is "
        f"{entry.get('set_count')!r}, expected {SEED_SQUAT_SET_COUNT}; entry: {entry!r}")


def test_trend_orders_weeks_oldest_first(lifter_token):
    # cov: C-CF-24
    series = trend_series(lifter_token, SLUG_SQUAT)
    labels = [e.get("iso_week") for e in series if isinstance(e, dict)]
    assert labels == sorted(labels), (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT}: weeks are ordered {labels!r}, expected "
        f"oldest week first (ISO week labels sort lexicographically)")


def test_replayed_set_uid_adds_no_second_row(lifter_token, session_id):
    # cov: C-CF-15
    uid = unique_uid("delta")
    before_counts = week_counts(lifter_token)
    before_total = total_set_count(lifter_token)

    first = log_set(lifter_token, session_id, uid, weight_kg=120, reps=2)
    assert first.status_code == 201, (
        f"POST {SETS_PATH} first write of {uid!r}: expected 201, observed "
        f"{first.status_code}; body: {first.excerpt()}")
    after_first_counts = week_counts(lifter_token)
    after_first_total = total_set_count(lifter_token)
    assert after_first_total - before_total == 1, (
        f"POST {SETS_PATH} first write of {uid!r}: the trend set_count total moved by "
        f"{after_first_total - before_total}, expected exactly 1; "
        f"before: {before_counts!r} after: {after_first_counts!r}")

    replay = log_set(lifter_token, session_id, uid, weight_kg=120, reps=2)
    assert replay.status_code == 200, (
        f"POST {SETS_PATH} replay of {uid!r}: expected 200, observed "
        f"{replay.status_code}; body: {replay.excerpt()}")
    after_replay_counts = week_counts(lifter_token)
    after_replay_total = total_set_count(lifter_token)
    assert after_replay_total - after_first_total == 0, (
        f"POST {SETS_PATH} replay of {uid!r}: the trend set_count total moved by "
        f"{after_replay_total - after_first_total}, expected 0 (a replayed set stores no row "
        f"and counts once); after first: {after_first_counts!r} "
        f"after replay: {after_replay_counts!r}")


def test_replay_leaves_trend_totals_unchanged(lifter_token, session_id):
    # cov: C-CF-30
    before = week_entry(trend_series(lifter_token, SLUG_SQUAT), SEED_WEEK)
    assert before is not None, (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT}: no entry for the seeded week "
        f"{SEED_WEEK!r} before the replay")

    replay = log_set(lifter_token, session_id, SEED_SQUAT_UID_1, weight_kg=100, reps=5)
    assert replay.status_code == 200, (
        f"POST {SETS_PATH} replay of the seeded set_uid {SEED_SQUAT_UID_1!r}: expected 200, "
        f"observed {replay.status_code}; body: {replay.excerpt()}")

    after = week_entry(trend_series(lifter_token, SLUG_SQUAT), SEED_WEEK)
    assert after is not None, (
        f"GET {TREND_PATH}?exercise={SLUG_SQUAT}: the entry for week {SEED_WEEK!r} vanished "
        f"after replaying {SEED_SQUAT_UID_1!r}")
    for field in ("top_weight_kg", "volume_kg", "set_count"):
        assert after.get(field) == before.get(field), (
            f"GET {TREND_PATH}?exercise={SLUG_SQUAT} week {SEED_WEEK}: {field} moved from "
            f"{before.get(field)!r} to {after.get(field)!r} after replaying the stored "
            f"set_uid {SEED_SQUAT_UID_1!r}; a replay must count once")
