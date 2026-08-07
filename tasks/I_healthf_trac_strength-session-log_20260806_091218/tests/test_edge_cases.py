"""Contention and validation rejection.

The concurrency test is the one that separates a database constraint from a check performed
before the insert: an app that reads first and writes second passes every sequential replay
test in this suite and fails here.
"""

from concurrent.futures import ThreadPoolExecutor

from conftest import (
    SETS_PATH,
    SLUG_SQUAT,
    log_set,
    total_set_count,
    unique_uid,
)


def test_concurrent_same_set_uid_stores_exactly_one_row(lifter_token, session_id):
    # cov: C-CF-18
    uid = unique_uid("race")
    before = total_set_count(lifter_token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(log_set, lifter_token, session_id, uid, SLUG_SQUAT, 110, 3)
                   for _ in range(2)]
        responses = [f.result() for f in futures]

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 201], (
        f"POST {SETS_PATH} twice concurrently with one set_uid {uid!r}: observed statuses "
        f"{statuses}, expected exactly one 201 and one 200; bodies: "
        f"{[r.excerpt(120) for r in responses]}")

    after = total_set_count(lifter_token)
    assert after - before == 1, (
        f"POST {SETS_PATH} twice concurrently with one set_uid {uid!r}: the trend set_count "
        f"total moved by {after - before}, expected exactly 1; a check performed before the "
        f"insert loses this race and stores two rows")


def test_non_positive_weight_is_rejected_422(lifter_token, session_id):
    # cov: C-CF-38
    r = log_set(lifter_token, session_id, unique_uid("zero-weight"), weight_kg=0, reps=5)
    assert r.status_code == 422, (
        f"POST {SETS_PATH} with weight_kg 0: expected 422, observed {r.status_code}; "
        f"body: {r.excerpt()}")


def test_non_positive_reps_is_rejected_422(lifter_token, session_id):
    # cov: C-CF-39
    r = log_set(lifter_token, session_id, unique_uid("zero-reps"), weight_kg=100, reps=0)
    assert r.status_code == 422, (
        f"POST {SETS_PATH} with reps 0: expected 422, observed {r.status_code}; "
        f"body: {r.excerpt()}")


def test_unknown_exercise_slug_is_rejected_422(lifter_token, session_id):
    # cov: C-CF-40
    r = log_set(lifter_token, session_id, unique_uid("unknown-slug"),
                slug="overhead-press", weight_kg=50, reps=5)
    assert r.status_code == 422, (
        f"POST {SETS_PATH} with exercise_slug 'overhead-press', which is outside the three "
        f"seeded exercises: expected 422, observed {r.status_code}; body: {r.excerpt()}")


def test_rejected_submission_writes_no_row(lifter_token, session_id):
    # cov: C-CF-42
    before = total_set_count(lifter_token)
    uid = unique_uid("rejected")

    rejected = log_set(lifter_token, session_id, uid, weight_kg=-20, reps=5)
    assert rejected.status_code == 422, (
        f"POST {SETS_PATH} with weight_kg -20: expected 422, observed "
        f"{rejected.status_code}; body: {rejected.excerpt()}")

    after = total_set_count(lifter_token)
    assert after == before, (
        f"POST {SETS_PATH} rejected submission {uid!r}: the trend set_count total moved from "
        f"{before} to {after}, expected no change; a rejected submission writes no row")
