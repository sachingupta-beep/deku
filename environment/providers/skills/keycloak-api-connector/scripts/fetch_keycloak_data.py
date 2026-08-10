#!/usr/bin/env python3
"""CLI helper for the Keycloak API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$KEYCLOAK_API_URL (override with --url). POST/PUT bodies are read from --data
(JSON string) or --data-file.

Everything is realm-scoped; --realm defaults to orbit-labs. Admin API calls need
a bearer -- --token defaults to the seeded master admin token, which administers
any realm. OIDC token calls need none.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MASTER_TOKEN = "kc-at-master-admin-cli-8f0c31d47a92"
DEFAULT_REALM = "orbit-labs"


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, token=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    if not raw:
        return {"status": resp.status}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _body(args):
    if getattr(args, "data_file", None):
        with open(args.data_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if getattr(args, "data", None):
        return json.loads(args.data)
    return {}


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data)
    return 0


def main():
    p = argparse.ArgumentParser(description="Query the Keycloak API (Mock) mock API")
    # OIDC
    p.add_argument("--realm-info", action="store_true", help="GET /realms/{realm}")
    p.add_argument("--discovery", action="store_true",
                   help="GET /realms/{realm}/.well-known/openid-configuration")
    p.add_argument("--certs", action="store_true",
                   help="GET /realms/{realm}/protocol/openid-connect/certs")
    p.add_argument("--token-request", action="store_true",
                   help="POST /realms/{realm}/protocol/openid-connect/token")
    p.add_argument("--introspect", action="store_true",
                   help="POST .../token/introspect")
    p.add_argument("--userinfo", action="store_true", help="GET .../userinfo")
    p.add_argument("--logout", action="store_true", help="POST .../logout")
    # Admin
    p.add_argument("--serverinfo", action="store_true", help="GET /admin/serverinfo")
    p.add_argument("--realms", action="store_true", help="GET /admin/realms")
    p.add_argument("--realm", action="store_true", help="GET /admin/realms/{realm}")
    p.add_argument("--update-realm", action="store_true",
                   help="PUT /admin/realms/{realm}")
    p.add_argument("--users", action="store_true", help="GET .../users")
    p.add_argument("--users-count", action="store_true", help="GET .../users/count")
    p.add_argument("--create-user", action="store_true", help="POST .../users")
    p.add_argument("--user", metavar="USER_ID", nargs=1, help="GET .../users/{id}")
    p.add_argument("--update-user", metavar="USER_ID", nargs=1,
                   help="PUT .../users/{id}")
    p.add_argument("--delete-user", metavar="USER_ID", nargs=1,
                   help="DELETE .../users/{id}")
    p.add_argument("--reset-password", metavar="USER_ID", nargs=1,
                   help="PUT .../users/{id}/reset-password")
    p.add_argument("--execute-actions", metavar="USER_ID", nargs=1,
                   help="PUT .../users/{id}/execute-actions-email")
    p.add_argument("--user-sessions", metavar="USER_ID", nargs=1,
                   help="GET .../users/{id}/sessions")
    p.add_argument("--user-offline-sessions", metavar="USER_ID", nargs=1,
                   help="GET .../users/{id}/offline-sessions")
    p.add_argument("--logout-user", metavar="USER_ID", nargs=1,
                   help="POST .../users/{id}/logout")
    p.add_argument("--role-mappings", metavar="USER_ID", nargs=1,
                   help="GET .../users/{id}/role-mappings")
    p.add_argument("--effective-roles", metavar="USER_ID", nargs=1,
                   help="GET .../users/{id}/role-mappings/effective")
    p.add_argument("--grant-realm-roles", metavar="USER_ID", nargs=1,
                   help="POST .../users/{id}/role-mappings/realm")
    p.add_argument("--revoke-realm-roles", metavar="USER_ID", nargs=1,
                   help="DELETE .../users/{id}/role-mappings/realm")
    p.add_argument("--client-role-mappings", metavar=("USER_ID", "CLIENT_UUID"),
                   nargs=2, help="GET .../users/{id}/role-mappings/clients/{uuid}")
    p.add_argument("--grant-client-roles", metavar=("USER_ID", "CLIENT_UUID"),
                   nargs=2, help="POST .../users/{id}/role-mappings/clients/{uuid}")
    p.add_argument("--user-groups", metavar="USER_ID", nargs=1,
                   help="GET .../users/{id}/groups")
    p.add_argument("--join-group", metavar=("USER_ID", "GROUP_ID"), nargs=2,
                   help="PUT .../users/{id}/groups/{groupId}")
    p.add_argument("--leave-group", metavar=("USER_ID", "GROUP_ID"), nargs=2,
                   help="DELETE .../users/{id}/groups/{groupId}")
    p.add_argument("--roles", action="store_true", help="GET .../roles")
    p.add_argument("--create-role", action="store_true", help="POST .../roles")
    p.add_argument("--role", metavar="ROLE_NAME", nargs=1, help="GET .../roles/{name}")
    p.add_argument("--role-composites", metavar="ROLE_NAME", nargs=1,
                   help="GET .../roles/{name}/composites")
    p.add_argument("--delete-role", metavar="ROLE_NAME", nargs=1,
                   help="DELETE .../roles/{name}")
    p.add_argument("--groups", action="store_true", help="GET .../groups")
    p.add_argument("--create-group", action="store_true", help="POST .../groups")
    p.add_argument("--group", metavar="GROUP_ID", nargs=1, help="GET .../groups/{id}")
    p.add_argument("--create-subgroup", metavar="GROUP_ID", nargs=1,
                   help="POST .../groups/{id}/children")
    p.add_argument("--delete-group", metavar="GROUP_ID", nargs=1,
                   help="DELETE .../groups/{id}")
    p.add_argument("--group-members", metavar="GROUP_ID", nargs=1,
                   help="GET .../groups/{id}/members")
    p.add_argument("--group-roles", metavar="GROUP_ID", nargs=1,
                   help="GET .../groups/{id}/role-mappings")
    p.add_argument("--clients", action="store_true", help="GET .../clients")
    p.add_argument("--client", metavar="CLIENT_UUID", nargs=1,
                   help="GET .../clients/{uuid}")
    p.add_argument("--client-secret", metavar="CLIENT_UUID", nargs=1,
                   help="GET .../clients/{uuid}/client-secret")
    p.add_argument("--client-roles", metavar="CLIENT_UUID", nargs=1,
                   help="GET .../clients/{uuid}/roles")
    p.add_argument("--client-sessions", metavar="CLIENT_UUID", nargs=1,
                   help="GET .../clients/{uuid}/user-sessions")
    p.add_argument("--identity-providers", action="store_true",
                   help="GET .../identity-provider/instances")
    p.add_argument("--identity-provider", metavar="ALIAS", nargs=1,
                   help="GET .../identity-provider/instances/{alias}")
    p.add_argument("--required-actions", action="store_true",
                   help="GET .../authentication/required-actions")
    p.add_argument("--brute-force", metavar="USER_ID", nargs=1,
                   help="GET .../attack-detection/brute-force/users/{id}")
    p.add_argument("--clear-brute-force", metavar="USER_ID", nargs=1,
                   help="DELETE .../attack-detection/brute-force/users/{id}")
    p.add_argument("--events", action="store_true", help="GET .../events")
    p.add_argument("--admin-events", action="store_true", help="GET .../admin-events")
    p.add_argument("--query", metavar="QS", default="",
                   help="Query string appended to reads, e.g. 'max=5&search=park'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--realm-name", default=DEFAULT_REALM,
                   help="Realm to act on (default: orbit-labs)")
    p.add_argument("--token", default=MASTER_TOKEN,
                   help="Bearer token (default: the seeded master admin token)")
    p.add_argument("--url", default=os.environ.get("KEYCLOAK_API_URL",
                                                   "http://localhost:8117"),
                   help="API base URL (default: $KEYCLOAK_API_URL or http://localhost:8117)")
    args = p.parse_args()
    base = args.url.rstrip("/")

    try:
        return _dispatch(args, base)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        return 1


def _qs(args, path):
    return f"{path}?{args.query}" if args.query else path


def _oidc(args, suffix):
    realm = urllib.parse.quote(args.realm_name, safe="")
    return f"/realms/{realm}/protocol/openid-connect{suffix}"


def _admin(args, suffix=""):
    realm = urllib.parse.quote(args.realm_name, safe="")
    return f"/admin/realms/{realm}{suffix}"


_OIDC_GETS = [("realm_info", None), ("discovery", "/.well-known/openid-configuration"),
              ("certs", "certs"), ("userinfo", "userinfo")]

_ADMIN_GETS = [("realm", ""), ("users", "/users"), ("users_count", "/users/count"),
               ("roles", "/roles"), ("groups", "/groups"), ("clients", "/clients"),
               ("identity_providers", "/identity-provider/instances"),
               ("required_actions", "/authentication/required-actions"),
               ("events", "/events"), ("admin_events", "/admin-events")]

_ONE_ARG = [("user", "/users/{id}", "GET"),
            ("update_user", "/users/{id}", "PUT"),
            ("delete_user", "/users/{id}", "DELETE"),
            ("reset_password", "/users/{id}/reset-password", "PUT"),
            ("execute_actions", "/users/{id}/execute-actions-email", "PUT"),
            ("user_sessions", "/users/{id}/sessions", "GET"),
            ("user_offline_sessions", "/users/{id}/offline-sessions", "GET"),
            ("logout_user", "/users/{id}/logout", "POST"),
            ("role_mappings", "/users/{id}/role-mappings", "GET"),
            ("effective_roles", "/users/{id}/role-mappings/effective", "GET"),
            ("grant_realm_roles", "/users/{id}/role-mappings/realm", "POST"),
            ("revoke_realm_roles", "/users/{id}/role-mappings/realm", "DELETE"),
            ("user_groups", "/users/{id}/groups", "GET"),
            ("role", "/roles/{name}", "GET"),
            ("role_composites", "/roles/{name}/composites", "GET"),
            ("delete_role", "/roles/{name}", "DELETE"),
            ("group", "/groups/{id}", "GET"),
            ("create_subgroup", "/groups/{id}/children", "POST"),
            ("delete_group", "/groups/{id}", "DELETE"),
            ("group_members", "/groups/{id}/members", "GET"),
            ("group_roles", "/groups/{id}/role-mappings", "GET"),
            ("client", "/clients/{uuid}", "GET"),
            ("client_secret", "/clients/{uuid}/client-secret", "GET"),
            ("client_roles", "/clients/{uuid}/roles", "GET"),
            ("client_sessions", "/clients/{uuid}/user-sessions", "GET"),
            ("identity_provider", "/identity-provider/instances/{alias}", "GET"),
            ("brute_force", "/attack-detection/brute-force/users/{id}", "GET"),
            ("clear_brute_force", "/attack-detection/brute-force/users/{id}",
             "DELETE")]

_TWO_ARGS = [("client_role_mappings", "/users/{id}/role-mappings/clients/{uuid}",
              "GET"),
             ("grant_client_roles", "/users/{id}/role-mappings/clients/{uuid}",
              "POST"),
             ("join_group", "/users/{id}/groups/{groupId}", "PUT"),
             ("leave_group", "/users/{id}/groups/{groupId}", "DELETE")]


def _dispatch(args, base):
    token = args.token
    if args.realm_info:
        realm = urllib.parse.quote(args.realm_name, safe="")
        return show(_request(base, f"/realms/{realm}", "GET"))
    if args.discovery:
        realm = urllib.parse.quote(args.realm_name, safe="")
        return show(_request(base, f"/realms/{realm}/.well-known/openid-configuration",
                             "GET"))
    if args.certs:
        return show(_request(base, _oidc(args, "/certs"), "GET"))
    if args.userinfo:
        return show(_request(base, _oidc(args, "/userinfo"), "GET", token=token))
    if args.token_request:
        return show(_request(base, _oidc(args, "/token"), "POST", _body(args)))
    if args.introspect:
        return show(_request(base, _oidc(args, "/token/introspect"), "POST",
                             _body(args)))
    if args.logout:
        return show(_request(base, _oidc(args, "/logout"), "POST", _body(args)))
    if args.serverinfo:
        return show(_request(base, "/admin/serverinfo", "GET", token=token))
    if args.realms:
        return show(_request(base, "/admin/realms", "GET", token=token))
    if args.update_realm:
        return show(_request(base, _admin(args), "PUT", _body(args), token=token))
    if args.create_user:
        return show(_request(base, _admin(args, "/users"), "POST", _body(args),
                             token=token))
    if args.create_role:
        return show(_request(base, _admin(args, "/roles"), "POST", _body(args),
                             token=token))
    if args.create_group:
        return show(_request(base, _admin(args, "/groups"), "POST", _body(args),
                             token=token))
    for flag, suffix in _ADMIN_GETS:
        if getattr(args, flag):
            return show(_request(base, _qs(args, _admin(args, suffix)), "GET",
                                 token=token))
    for flag, suffix, method in _ONE_ARG:
        value = getattr(args, flag)
        if value:
            path = _admin(args, _fill(suffix, value))
            payload = _body(args) if method in ("POST", "PUT", "DELETE") else None
            if method == "GET":
                return show(_request(base, _qs(args, path), "GET", token=token))
            return show(_request(base, path, method, payload, token=token))
    for flag, suffix, method in _TWO_ARGS:
        value = getattr(args, flag)
        if value:
            path = _admin(args, _fill(suffix, value))
            payload = _body(args) if method in ("POST", "PUT") else None
            return show(_request(base, path, method, payload, token=token))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
