"""Supabase service suite.

Exercised through the hub (``/supabase/...``) rather than against the router in
isolation, because the mount is part of what is under test: a service that only
works when its routes are at the root is a service that is broken in the hub.

Every assertion is on upstream-visible behaviour -- status codes, PostgREST error
codes, RLS-scoped row counts -- not on the simulator's internals.
"""

from __future__ import annotations

import pytest

BASE = "/supabase"

# Seeded shape. Restated here so a seed edit fails loudly with a readable diff
# instead of quietly weakening every count assertion below.
TOTAL_PROJECTS = 5
PUBLIC_PROJECTS = 2          # 103 web-app, 104 engineering-docs
TOTAL_DOCUMENTS = 8
PUBLISHED_DOCUMENTS = 5      # 501, 502, 504, 506, 507
TOTAL_PROFILES = 6
TOTAL_BUCKETS = 4
PUBLIC_BUCKETS = 1           # avatars


@pytest.fixture
def svc(client, service_key):
    """Client bound to the service key -- the `service_role`, which bypasses RLS."""
    client.headers.update({"apikey": service_key})
    return client


# --- health ----------------------------------------------------------------


def test_health(client):
    body = client.get(f"{BASE}/health").json()
    assert body == {
        "service": "supabase",
        "status": "ok",
        "checks": {
            "project_ref": "orbitlabsselfhost01",
            "rows": {"profiles": 6, "projects": 5, "documents": 8, "comments": 7},
            "buckets": 4,
            "functions": 4,
        },
    }


def test_rest_root_advertises_the_exposed_schema(client):
    body = client.get(f"{BASE}/rest/v1/").json()
    assert body["basePath"] == "/rest/v1"
    assert set(body["definitions"]) == {"profiles", "projects", "documents", "comments"}


# --- RLS -------------------------------------------------------------------


def test_anon_sees_only_public_projects(client):
    """RLS is enforced, not decorative: anon gets the public rows and no others."""
    rows = client.get(f"{BASE}/rest/v1/projects").json()
    assert len(rows) == PUBLIC_PROJECTS
    assert {r["visibility"] for r in rows} == {"public"}


def test_service_role_sees_everything(svc):
    assert len(svc.get(f"{BASE}/rest/v1/projects").json()) == TOTAL_PROJECTS


def test_unknown_token_is_authenticated_not_rejected(client):
    """Fleet rule: an unfamiliar token maps onto a role rather than 401-ing.
    A simulator that rejects unknown credentials turns every task into a
    credential hunt instead of the task it was meant to be."""
    rows = client.get(f"{BASE}/rest/v1/projects",
                      headers={"Authorization": "Bearer whatever-token"}).json()
    assert len(rows) == TOTAL_PROJECTS


def test_anon_key_is_still_anon(client, anon_key):
    rows = client.get(f"{BASE}/rest/v1/projects", headers={"apikey": anon_key}).json()
    assert len(rows) == PUBLIC_PROJECTS


def test_anon_sees_only_published_documents(client):
    rows = client.get(f"{BASE}/rest/v1/documents").json()
    assert len(rows) == PUBLISHED_DOCUMENTS
    assert {r["status"] for r in rows} == {"published"}


def test_comments_inherit_their_documents_visibility(client, svc):
    """9004 hangs off draft document 503, so anon must not see it."""
    anon_ids = {r["id"] for r in client.get(f"{BASE}/rest/v1/comments",
                                            headers={"apikey": ""}).json()}
    assert 9004 not in anon_ids
    assert 9004 in {r["id"] for r in svc.get(f"{BASE}/rest/v1/comments").json()}


# --- PostgREST query grammar ----------------------------------------------


def test_content_range_header(svc):
    response = svc.get(f"{BASE}/rest/v1/projects")
    assert response.headers["content-range"] == "0-4/5"


def test_eq_filter(svc):
    rows = svc.get(f"{BASE}/rest/v1/documents", params={"status": "eq.draft"}).json()
    assert {r["status"] for r in rows} == {"draft"}


def test_not_negation(svc):
    rows = svc.get(f"{BASE}/rest/v1/documents", params={"status": "not.eq.draft"}).json()
    assert "draft" not in {r["status"] for r in rows}


def test_numeric_operand_is_coerced_to_the_column_type(svc):
    """Everything arrives as text; without coercion this compares str to int."""
    rows = svc.get(f"{BASE}/rest/v1/documents", params={"word_count": "gt.2000"}).json()
    assert rows and all(r["word_count"] > 2000 for r in rows)


def test_in_filter(svc):
    rows = svc.get(f"{BASE}/rest/v1/projects", params={"id": "in.(101,103)"}).json()
    assert {r["id"] for r in rows} == {101, 103}


def test_ilike_filter(svc):
    rows = svc.get(f"{BASE}/rest/v1/documents", params={"title": "ilike.*rotation*"}).json()
    assert [r["id"] for r in rows] == [501]


def test_is_null_filter(svc):
    rows = svc.get(f"{BASE}/rest/v1/documents", params={"published_at": "is.null"}).json()
    assert rows and all(r["published_at"] in (None, "") for r in rows)


def test_cs_contains_filter_on_an_array_column(svc):
    rows = svc.get(f"{BASE}/rest/v1/documents", params={"tags": "cs.{security}"}).json()
    assert {r["id"] for r in rows} == {501, 507}


def test_malformed_filter_returns_pgrst100(svc):
    response = svc.get(f"{BASE}/rest/v1/documents", params={"status": "published"})
    assert response.status_code == 400
    assert response.json()["code"] == "PGRST100"


def test_order_desc(svc):
    rows = svc.get(f"{BASE}/rest/v1/projects", params={"order": "star_count.desc"}).json()
    counts = [r["star_count"] for r in rows]
    assert counts == sorted(counts, reverse=True)


def test_limit_and_offset(svc):
    response = svc.get(f"{BASE}/rest/v1/projects",
                       params={"order": "id.asc", "limit": 2, "offset": 1})
    assert [r["id"] for r in response.json()] == [102, 103]
    assert response.headers["content-range"] == "1-2/5"


def test_select_projection(svc):
    rows = svc.get(f"{BASE}/rest/v1/projects", params={"select": "id,name"}).json()
    assert set(rows[0]) == {"id", "name"}


def test_embedding_a_child_resource(svc):
    rows = svc.get(f"{BASE}/rest/v1/projects",
                   params={"select": "id,name,documents(id,title)", "id": "eq.101"}).json()
    assert {d["id"] for d in rows[0]["documents"]} == {501, 502, 503}


def test_embedding_a_parent_resource(svc):
    rows = svc.get(f"{BASE}/rest/v1/documents",
                   params={"select": "id,profiles(username)", "id": "eq.501"}).json()
    assert rows[0]["profiles"]["username"]


def test_embed_join_key_survives_being_projected_away(svc):
    """`select=id,profiles(username)` drops author_id from the output, but the
    join must still resolve -- the key is read from the source row."""
    rows = svc.get(f"{BASE}/rest/v1/documents",
                   params={"select": "id,profiles(username)", "id": "eq.501"}).json()
    assert "author_id" not in rows[0]
    assert rows[0]["profiles"] is not None


def test_embeds_respect_rls(client):
    """An anon embed must not become a back door into draft documents."""
    rows = client.get(f"{BASE}/rest/v1/projects",
                      params={"select": "id,documents(id,status)", "id": "eq.103"}).json()
    assert all(d["status"] == "published" for d in rows[0]["documents"])


def test_unknown_table_is_42p01(client):
    response = client.get(f"{BASE}/rest/v1/nope")
    assert response.status_code == 404
    assert response.json()["code"] == "42P01"


# --- writes ----------------------------------------------------------------


def test_anon_insert_is_denied_with_42501(client):
    response = client.post(f"{BASE}/rest/v1/projects", json={"name": "Nope"})
    assert response.status_code == 401
    assert response.json()["code"] == "42501"


def test_insert_assigns_the_next_serial(svc):
    response = svc.post(f"{BASE}/rest/v1/projects",
                        json={"name": "Realtime Gateway", "visibility": "public"})
    assert response.status_code == 201
    created = response.json()[0]
    assert created["id"] == 106
    assert created["slug"] == "realtime-gateway"


def test_insert_accepts_an_array(svc):
    response = svc.post(f"{BASE}/rest/v1/profiles",
                        json=[{"username": "a"}, {"username": "b"}])
    assert response.status_code == 201
    assert len(response.json()) == 2


def test_prefer_return_minimal_suppresses_the_body(svc):
    response = svc.post(f"{BASE}/rest/v1/profiles", json={"username": "quiet"},
                        headers={"Prefer": "return=minimal"})
    assert response.status_code == 201
    assert response.json() == []


def test_foreign_key_violation_is_23503(svc):
    response = svc.post(f"{BASE}/rest/v1/documents",
                        json={"title": "Orphan", "project_id": 999})
    assert response.status_code == 409
    assert response.json()["code"] == "23503"
    assert "documents_project_id_fkey" in response.json()["error"]


def test_patch_updates_matching_rows(svc):
    response = svc.patch(f"{BASE}/rest/v1/projects?id=eq.101",
                         json={"description": "rewritten"})
    assert response.status_code == 200
    assert response.json()[0]["description"] == "rewritten"
    assert response.json()[0]["updated_at"]


def test_anon_patch_is_denied(client):
    assert client.patch(f"{BASE}/rest/v1/projects?id=eq.101",
                        json={"name": "x"}).status_code == 401


def test_delete_requires_the_service_role(client):
    response = client.delete(f"{BASE}/rest/v1/projects?id=eq.101",
                             headers={"Authorization": "Bearer some-user-token"})
    assert response.status_code == 401
    assert "service_role" in response.json()["hint"]


def test_unfiltered_delete_is_refused(svc):
    """A safety rail with no upstream equivalent, and the response says so via
    PGRST109 rather than silently emptying the table."""
    response = svc.delete(f"{BASE}/rest/v1/comments")
    assert response.status_code == 400
    assert response.json()["code"] == "PGRST109"


def test_filtered_delete_removes_the_row(svc):
    assert svc.delete(f"{BASE}/rest/v1/comments?id=eq.9001").json()[0]["id"] == 9001
    assert len(svc.get(f"{BASE}/rest/v1/comments").json()) == 6


# --- RPC -------------------------------------------------------------------


def test_rpc_project_stats(svc):
    body = svc.post(f"{BASE}/rest/v1/rpc/project_stats", json={"project_id": 101}).json()
    assert body == {
        "project_id": 101,
        "name": "Auth Service",
        "document_count": 3,
        "published_count": 2,
        "comment_count": 4,
        "unresolved_comment_count": 3,
        "total_words": 5110,
    }


def test_rpc_project_stats_respects_rls(client):
    """101 is private, so to anon it does not exist -- 404, not an empty result."""
    response = client.post(f"{BASE}/rest/v1/rpc/project_stats", json={"project_id": 101})
    assert response.status_code == 404
    assert response.json()["code"] == "PGRST116"


def test_rpc_missing_argument(svc):
    response = svc.post(f"{BASE}/rest/v1/rpc/project_stats", json={})
    assert response.status_code == 404
    assert response.json()["code"] == "PGRST202"


def test_rpc_search_documents_ranks_hits(svc):
    hits = svc.post(f"{BASE}/rest/v1/rpc/search_documents",
                    json={"query": "token", "limit": 5}).json()
    assert hits
    assert hits == sorted(hits, key=lambda h: (-h["rank"], h["id"]))


def test_rpc_publish_document_changes_state(svc):
    body = svc.post(f"{BASE}/rest/v1/rpc/publish_document", json={"document_id": 503}).json()
    assert body["status"] == "published"
    assert body["published_at"]


def test_rpc_publish_document_twice_is_p0001(svc):
    svc.post(f"{BASE}/rest/v1/rpc/publish_document", json={"document_id": 503})
    response = svc.post(f"{BASE}/rest/v1/rpc/publish_document", json={"document_id": 503})
    assert response.status_code == 400
    assert response.json()["code"] == "P0001"


def test_rpc_publish_denied_for_anon(client):
    response = client.post(f"{BASE}/rest/v1/rpc/publish_document", json={"document_id": 503})
    assert response.status_code == 401
    assert response.json()["code"] == "42501"


def test_unknown_rpc_is_pgrst202(svc):
    response = svc.post(f"{BASE}/rest/v1/rpc/nope", json={})
    assert response.status_code == 404
    assert response.json()["code"] == "PGRST202"


def test_rpc_route_wins_over_the_table_route(svc):
    """`/rest/v1/rpc/x` must not be read as table "rpc". Registration order is
    what guarantees it, so this test guards the ordering in routes.py."""
    assert svc.post(f"{BASE}/rest/v1/rpc/project_stats",
                    json={"project_id": 103}).status_code == 200


# --- storage ---------------------------------------------------------------


def test_anon_sees_only_public_buckets(client):
    assert len(client.get(f"{BASE}/storage/v1/bucket").json()) == PUBLIC_BUCKETS


def test_service_role_sees_all_buckets(svc):
    assert len(svc.get(f"{BASE}/storage/v1/bucket").json()) == TOTAL_BUCKETS


def test_private_bucket_is_404_to_anon(client):
    """404 rather than 403: a private bucket should not confirm its own existence."""
    assert client.get(f"{BASE}/storage/v1/bucket/invoices").status_code == 404


def test_create_bucket(svc):
    response = svc.post(f"{BASE}/storage/v1/bucket", json={"id": "exports", "public": False})
    assert response.status_code == 201
    assert response.json() == {"name": "exports"}


def test_duplicate_bucket_is_409(svc):
    response = svc.post(f"{BASE}/storage/v1/bucket", json={"id": "avatars"})
    assert response.status_code == 409
    assert response.json()["code"] == "Duplicate"


def test_deleting_a_non_empty_bucket_is_409(svc):
    response = svc.delete(f"{BASE}/storage/v1/bucket/avatars")
    assert response.status_code == 409
    assert "not empty" in response.json()["error"]


def test_delete_empty_bucket(svc):
    svc.post(f"{BASE}/storage/v1/bucket", json={"id": "scratch"})
    assert svc.delete(f"{BASE}/storage/v1/bucket/scratch").json()["message"] == \
        "Successfully deleted"


def test_list_objects_with_a_prefix(svc):
    rows = svc.post(f"{BASE}/storage/v1/object/list/avatars",
                    json={"prefix": "public/"}).json()
    assert rows and all(o["name"].startswith("public/") for o in rows)


def test_object_info(svc):
    body = svc.get(f"{BASE}/storage/v1/object/info/avatars/public/amelia.png").json()
    assert body["bucket_id"] == "avatars"
    assert body["size"] > 0


def test_missing_object_is_404(svc):
    assert svc.get(f"{BASE}/storage/v1/object/info/avatars/nope.png").status_code == 404


def test_sign_object_returns_a_tokenised_url(svc):
    body = svc.post(f"{BASE}/storage/v1/object/sign/avatars/public/amelia.png",
                    json={"expiresIn": 60}).json()
    assert body["signedURL"].startswith("/storage/v1/object/sign/avatars/public/amelia.png?token=")


def test_anon_cannot_sign(client):
    response = client.post(f"{BASE}/storage/v1/object/sign/avatars/public/amelia.png",
                           json={})
    assert response.status_code == 401


# --- edge functions --------------------------------------------------------


def test_list_functions(client):
    assert len(client.get(f"{BASE}/functions/v1").json()) == 4


def test_invoke_function_without_jwt_verification(client):
    body = client.post(f"{BASE}/functions/v1/billing-webhook",
                       json={"type": "invoice.paid"}).json()
    assert body["data"]["received"] is True
    assert body["data"]["event"] == "invoice.paid"


def test_verify_jwt_function_rejects_anon(client):
    response = client.post(f"{BASE}/functions/v1/send-welcome-email",
                           json={"email": "a@b.c"})
    assert response.status_code == 401


def test_verify_jwt_function_accepts_a_token(svc):
    body = svc.post(f"{BASE}/functions/v1/send-welcome-email",
                    json={"email": "amelia@orbitlabs.dev"}).json()
    assert body["data"]["queued"] is True
    assert body["invocation_id"].startswith("inv_")


def test_throttled_function_is_429(svc):
    response = svc.post(f"{BASE}/functions/v1/resize-avatar", json={})
    assert response.status_code == 429


def test_unknown_function_is_404(svc):
    assert svc.post(f"{BASE}/functions/v1/nope", json={}).status_code == 404


def test_generate_report_reads_live_data(svc):
    body = svc.post(f"{BASE}/functions/v1/generate-report", json={"period": "2026-05"}).json()
    assert body["data"]["documents"] == TOTAL_DOCUMENTS
    assert body["data"]["published"] == PUBLISHED_DOCUMENTS


# --- realtime --------------------------------------------------------------


def test_list_channels(client):
    assert len(client.get(f"{BASE}/realtime/v1/channels").json()) == 3


def test_broadcast_to_a_public_channel(client):
    response = client.post(f"{BASE}/realtime/v1/api/broadcast",
                           json={"messages": [{"topic": "public:documents",
                                               "payload": {"id": 501}}]})
    assert response.status_code == 202
    assert response.json() == {"message": "ok", "accepted": 1}


def test_anon_cannot_broadcast_to_a_private_channel(client):
    response = client.post(f"{BASE}/realtime/v1/api/broadcast",
                           json={"messages": [{"topic": "project:101"}]})
    assert response.status_code == 401


def test_service_role_can_broadcast_to_a_private_channel(svc):
    response = svc.post(f"{BASE}/realtime/v1/api/broadcast",
                        json={"messages": [{"topic": "project:101"}]})
    assert response.status_code == 202


# --- project read model ----------------------------------------------------


def test_list_projects(client):
    body = client.get(f"{BASE}/v1/projects").json()
    assert body[0]["id"] == "orbitlabsselfhost01"


def test_project_settings_mask_the_service_key(client, service_key):
    body = client.get(f"{BASE}/v1/projects/orbitlabsselfhost01").json()
    assert body["api"]["service_role_key"] != service_key
    assert "..." in body["api"]["service_role_key"]
    assert body["api"]["anon_key"]  # anon key is public, so it is not masked


def test_unknown_project_ref_is_404(client):
    assert client.get(f"{BASE}/v1/projects/nope").status_code == 404
