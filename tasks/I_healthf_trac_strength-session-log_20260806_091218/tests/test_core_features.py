"""Business rules and state machines the brief pins: the set write, the idempotent replay,
and the session lifecycle.

The assertion picks the file. A test that asserts a row survives a re-read, or that the trend
reconciles, lives in test_data_integrity.py even when it logs a set to get there.
"""

from conftest import (
    HEALTH_PATH,
    SESSIONS_PATH,
    SETS_PATH,
    SLUG_SQUAT,
    STATUS_FINISHED,
    field_of,
    log_set,
    open_session,
    request,
    set_id_of,
    unique_uid,
)


def test_health_is_served_unauthenticated(lifter_token):
    # cov: C-TR-05, C-DC-05, C-DC-01, C-DC-04, C-TR-06, C-DC-02, C-DC-03
    r = request("GET", HEALTH_PATH)
    assert r.status_code == 200, (
        f"GET {HEALTH_PATH} with no Authorization header: expected 200, observed "
        f"{r.status_code}; the health route is unauthenticated and answers once the app "
        f"can serve; body: {r.excerpt()}")


def test_log_set_returns_201_and_stores_the_set(lifter_token, session_id):
    # cov: C-CF-02
    uid = unique_uid("new-set")
    r = log_set(lifter_token, session_id, uid, slug=SLUG_SQUAT, weight_kg=100, reps=5)
    assert r.status_code == 201, (
        f"POST {SETS_PATH} for a new set_uid {uid!r}: expected 201, observed "
        f"{r.status_code}; body: {r.excerpt()}")
    assert field_of(r.json, "weight_kg") in (100, 100.0), (
        f"POST {SETS_PATH} for {uid!r}: stored weight_kg is "
        f"{field_of(r.json, 'weight_kg')!r}, expected the submitted 100; "
        f"body: {r.excerpt()}")
    assert field_of(r.json, "reps") == 5, (
        f"POST {SETS_PATH} for {uid!r}: stored reps is {field_of(r.json, 'reps')!r}, "
        f"expected the submitted 5; body: {r.excerpt()}")


def test_replayed_set_uid_returns_200_with_the_stored_set(lifter_token, session_id):
    # cov: C-CF-13
    uid = unique_uid("replay")
    first = log_set(lifter_token, session_id, uid, weight_kg=100, reps=5)
    assert first.status_code == 201, (
        f"POST {SETS_PATH} first write of {uid!r}: expected 201, observed "
        f"{first.status_code}; body: {first.excerpt()}")

    replay = log_set(lifter_token, session_id, uid, weight_kg=100, reps=5)
    assert replay.status_code == 200, (
        f"POST {SETS_PATH} replay of {uid!r}: expected 200 for an already stored set_uid, "
        f"observed {replay.status_code}; body: {replay.excerpt()}")
    assert str(set_id_of(replay.json)) == str(set_id_of(first.json)), (
        f"POST {SETS_PATH} replay of {uid!r}: returned set id "
        f"{set_id_of(replay.json)!r}, expected the originally stored "
        f"{set_id_of(first.json)!r}; body: {replay.excerpt()}")


def test_replay_with_different_body_returns_the_original_values(lifter_token, session_id):
    # cov: C-CF-16
    uid = unique_uid("conflict")
    first = log_set(lifter_token, session_id, uid, weight_kg=100, reps=5)
    assert first.status_code == 201, (
        f"POST {SETS_PATH} first write of {uid!r}: expected 201, observed "
        f"{first.status_code}; body: {first.excerpt()}")

    conflicting = log_set(lifter_token, session_id, uid, weight_kg=140, reps=1)
    assert conflicting.status_code == 200, (
        f"POST {SETS_PATH} conflicting replay of {uid!r}: expected 200, observed "
        f"{conflicting.status_code}; body: {conflicting.excerpt()}")
    assert field_of(conflicting.json, "weight_kg") in (100, 100.0), (
        f"POST {SETS_PATH} conflicting replay of {uid!r}: returned weight_kg "
        f"{field_of(conflicting.json, 'weight_kg')!r}, expected the originally stored 100 "
        f"(first write wins, bodies are never merged); body: {conflicting.excerpt()}")
    assert field_of(conflicting.json, "reps") == 5, (
        f"POST {SETS_PATH} conflicting replay of {uid!r}: returned reps "
        f"{field_of(conflicting.json, 'reps')!r}, expected the originally stored 5; "
        f"body: {conflicting.excerpt()}")


def test_set_into_finished_session_is_rejected_409(lifter_token):
    # cov: C-CF-43
    finished = open_session(lifter_token)
    closing = request("POST", f"{SESSIONS_PATH}/{finished}/finish", token=lifter_token,
                      payload={})
    assert closing.status_code == 200, (
        f"POST {SESSIONS_PATH}/{finished}/finish: expected 200, observed "
        f"{closing.status_code}; body: {closing.excerpt()}")

    rejected = log_set(lifter_token, finished, unique_uid("into-finished"))
    assert rejected.status_code == 409, (
        f"POST {SETS_PATH} into session {finished} with status {STATUS_FINISHED!r}: "
        f"expected 409, observed {rejected.status_code}; body: {rejected.excerpt()}")


def test_second_open_session_is_rejected_409(lifter_token, session_id):
    # cov: C-CF-33
    second = request("POST", SESSIONS_PATH, token=lifter_token, payload={})
    assert second.status_code == 409, (
        f"POST {SESSIONS_PATH} while session {session_id} is already open: expected 409, "
        f"observed {second.status_code}; body: {second.excerpt()}")
