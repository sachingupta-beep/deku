"""Scaffold a service module from its catalog manifest.

    python tools/new_service.py keycloak

Reads the existing ``services/<pkg>/service.toml`` -- which already carries the
name, category, upstream, auth scheme and advertised route prefixes for all 27
catalog entries -- and writes the package around it: ``data.py``, ``routes.py``,
``service.py``, a seed file and a test module. The manifest's ``status`` flips
from ``declared`` to ``implemented`` last, so a half-written service is never
advertised as working.

The generated code runs as-is: load it and ``GET /<slug>/health`` answers, one
seeded table is queryable, and the test module passes. That is the point --
you start from something green and replace it endpoint by endpoint, rather than
from an empty file that fails for six different reasons at once.

``--force`` overwrites existing files. Without it, files that already exist are
left alone and reported, so re-running after adding a route is safe.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hub.manifest import load_manifest  # noqa: E402


def class_name(slug: str) -> str:
    return "".join(part.capitalize() for part in slug.split("-")) + "Service"


DATA_PY = '''"""{name} data layer.

All state lives on this instance -- never at module scope. See ``hub/base.py``
for why: module globals survive an unload, so a service that keeps state there
cannot be reset between benchmark tasks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from hub.base import ServiceContext
from hub.store import opt_int, opt_str, strict_bool

Row = Dict[str, Any]


def _strip_ctx(row: Row) -> Row:
    """Drop the loader's ``__api__``/``__table__``/``__file__`` bookkeeping keys."""
    return {{k: v for k, v in row.items() if not k.startswith("__")}}


def _coerce_records(rows) -> List[Row]:
    """Seed cells arrive as strings so a CSV overlay can shadow the JSON.
    Coerce once, here -- route handlers must never re-parse a seed value."""
    return [
        {{**_strip_ctx(r), "id": opt_str(r, "id"), "name": opt_str(r, "name"),
          "enabled": strict_bool(r, "enabled")}}
        for r in rows
    ]


def _error(message: str, code: str, **extra: Any) -> Row:
    """Data functions RETURN errors, never raise. ``routes.py`` maps ``code``
    onto an HTTP status. Match the upstream product's error shape here."""
    return {{"error": message, "code": code, **extra}}


class {cls}Data:
    """Instance-scoped {name} state."""

    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx
        self.store = ctx.store
        self._register_tables()

    def _register_tables(self) -> None:
        seed = self.ctx.seed
        self.ctx.register_table(
            "records", "id", lambda: _coerce_records(seed("records.json", "records"))
        )

    # -- roles -------------------------------------------------------------

    def resolve_role(self, authorization: Optional[str] = None) -> str:
        """Map a credential onto a role.

        Fleet rule: never reject a request purely because a token is unfamiliar.
        Map unknown tokens onto a role instead, so the auth layer stays
        observable without making the service unreachable.
        """
        token = (authorization or "").split(None, 1)
        if len(token) == 2 and token[0].lower() == "bearer" and token[1].strip():
            return "user"
        return "anonymous"

    # -- CRUD --------------------------------------------------------------

    def list_records(self) -> List[Row]:
        return self.store.table("records").rows()

    def get_record(self, record_id: str) -> Row:
        row = self.store.table("records").get(record_id)
        return row if row else _error(f"record {{record_id}} not found", "404")

    def create_record(self, payload: Row, role: str) -> Row:
        if role == "anonymous":
            return _error("authentication required", "401")
        if not payload.get("name"):
            return _error("name is required", "400")
        row = {{
            "id": payload.get("id") or f"rec_{{len(self.list_records()) + 1:04d}}",
            "name": payload["name"],
            "enabled": bool(payload.get("enabled", True)),
        }}
        if self.store.table("records").get(row["id"]):
            return _error(f"record {{row['id']}} already exists", "409")
        return self.store.table("records").upsert(row)

    def update_record(self, record_id: str, payload: Row, role: str) -> Row:
        if role == "anonymous":
            return _error("authentication required", "401")
        updated = self.store.table("records").patch(record_id, payload)
        return updated if updated else _error(f"record {{record_id}} not found", "404")

    def delete_record(self, record_id: str, role: str) -> Row:
        if role == "anonymous":
            return _error("authentication required", "401")
        if not self.store.table("records").delete(record_id):
            return _error(f"record {{record_id}} not found", "404")
        return {{"deleted": record_id}}
'''

ROUTES_PY = '''"""HTTP surface for the simulated {name}.

Paths are relative to the mount: ``/records`` here is ``{base}/records`` in the
hub. Never write the slug into a path -- the mount adds it.

Keep this layer thin. Read the request, call one data method, map the returned
``code`` onto a status. Logic belongs in ``data.py``, where it is testable
without a client.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from .data import {cls}Data

#: Upstream error code -> HTTP status. One table, so a code cannot mean 404 on
#: one endpoint and 401 on the next.
STATUS_BY_CODE: Dict[str, int] = {{
    "400": 400,
    "401": 401,
    "403": 403,
    "404": 404,
    "409": 409,
    "429": 429,
}}


def _result(value: Any) -> Any:
    if isinstance(value, dict) and "error" in value:
        return JSONResponse(status_code=STATUS_BY_CODE.get(value.get("code"), 400),
                            content=value)
    return value


def build_router(data: {cls}Data) -> APIRouter:
    router = APIRouter()

    @router.get("/records", tags=["records"], summary="List records")
    def list_records() -> List[Dict[str, Any]]:
        return data.list_records()

    @router.get("/records/{{record_id}}", tags=["records"], summary="Get a record")
    def get_record(record_id: str) -> Any:
        return _result(data.get_record(record_id))

    @router.post("/records", status_code=201, tags=["records"], summary="Create a record")
    def create_record(
        body: Dict[str, Any] = Body(...),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _result(data.create_record(body, data.resolve_role(authorization)))

    @router.patch("/records/{{record_id}}", tags=["records"], summary="Update a record")
    def update_record(
        record_id: str,
        body: Dict[str, Any] = Body(...),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _result(data.update_record(record_id, body, data.resolve_role(authorization)))

    @router.delete("/records/{{record_id}}", tags=["records"], summary="Delete a record")
    def delete_record(
        record_id: str,
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _result(data.delete_record(record_id, data.resolve_role(authorization)))

    return router
'''

SERVICE_PY = '''"""The {name} service module."""

from __future__ import annotations

from fastapi import APIRouter

from hub.base import HealthReport, ServiceModule

from .data import {cls}Data
from .routes import build_router


class {cls}Service(ServiceModule):
    """{summary}"""

    data: {cls}Data

    async def on_startup(self) -> None:
        """Build the data layer and force the seeds to load.

        ``eager_load`` turns a malformed seed into a clear load-time failure
        naming the file, row and column, instead of a confusing 500 during
        whichever request happens to touch that table first.
        """
        self.data = {cls}Data(self.ctx)
        self.ctx.eager_load()
        self.log.info("seeded %d record(s)", len(self.ctx.table("records")))

    def build_router(self) -> APIRouter:
        return build_router(self.data)

    def health(self) -> HealthReport:
        """Must be cheap -- /hub/health calls this for every loaded service."""
        return HealthReport(
            status="ok",
            checks={{"rows": {{"records": len(self.ctx.table("records"))}}}},
        )

    async def on_shutdown(self) -> None:
        self.data = None  # type: ignore[assignment]
'''

TEST_PY = '''"""{name} service suite.

Exercised through the hub, because the mount is part of what is under test: a
service that only works when its routes sit at the root is broken in the hub.
"""

from __future__ import annotations

BASE = "{base}"
AUTH = {{"Authorization": "Bearer test-token"}}


def test_health(client):
    body = client.get(f"{{BASE}}/health").json()
    assert body["service"] == "{slug}"
    assert body["status"] == "ok"


def test_list_records(client):
    rows = client.get(f"{{BASE}}/records").json()
    assert len(rows) == 2


def test_get_record(client):
    assert client.get(f"{{BASE}}/records/rec_0001").json()["name"]


def test_missing_record_is_404(client):
    assert client.get(f"{{BASE}}/records/nope").status_code == 404


def test_create_requires_authentication(client):
    assert client.post(f"{{BASE}}/records", json={{"name": "x"}}).status_code == 401


def test_create_record(client):
    response = client.post(f"{{BASE}}/records", json={{"name": "New"}}, headers=AUTH)
    assert response.status_code == 201
    assert response.json()["name"] == "New"


def test_duplicate_is_409(client):
    client.post(f"{{BASE}}/records", json={{"id": "dup", "name": "a"}}, headers=AUTH)
    response = client.post(f"{{BASE}}/records", json={{"id": "dup", "name": "b"}}, headers=AUTH)
    assert response.status_code == 409


def test_update_record(client):
    response = client.patch(f"{{BASE}}/records/rec_0001", json={{"enabled": False}},
                            headers=AUTH)
    assert response.json()["enabled"] is False


def test_delete_record(client):
    assert client.delete(f"{{BASE}}/records/rec_0002", headers=AUTH).status_code == 200
    assert client.get(f"{{BASE}}/records/rec_0002").status_code == 404
'''

SEED = [
    {"id": "rec_0001", "name": "First record", "enabled": "true"},
    {"id": "rec_0002", "name": "Second record", "enabled": "false"},
]


def write(path: Path, content: str, force: bool, created: list, skipped: list) -> None:
    if path.exists() and not force:
        skipped.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    created.append(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slug", help="service slug, e.g. keycloak or ory-kratos")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    parser.add_argument("--keep-declared", action="store_true",
                        help="do not flip [service].status to implemented")
    args = parser.parse_args()

    slug = args.slug.strip().lower()
    package = slug.replace("-", "_")
    directory = ROOT / "services" / package
    manifest_path = directory / "service.toml"

    if not manifest_path.exists():
        print(f"error: no manifest at {manifest_path}", file=sys.stderr)
        print("Add the catalog entry first -- see docs/SERVICE_AUTHORING.md.", file=sys.stderr)
        return 1

    descriptor = load_manifest(manifest_path)
    cls = class_name(slug)[: -len("Service")]
    fields = {
        "slug": slug,
        "name": descriptor.name,
        "cls": cls,
        "base": descriptor.base_path,
        "summary": " ".join(descriptor.summary.split()) or descriptor.name,
    }

    created: list = []
    skipped: list = []
    write(directory / "__init__.py",
          f'"""Simulated {descriptor.name}."""\n', args.force, created, skipped)
    write(directory / "data.py", DATA_PY.format(**fields), args.force, created, skipped)
    write(directory / "routes.py", ROUTES_PY.format(**fields), args.force, created, skipped)
    write(directory / "service.py", SERVICE_PY.format(**fields), args.force, created, skipped)
    write(directory / "tests" / "__init__.py", "", args.force, created, skipped)
    write(directory / "tests" / f"test_{package}.py",
          TEST_PY.format(**fields), args.force, created, skipped)
    write(ROOT / "data" / (descriptor.data_dir_name or slug) / "records.json",
          json.dumps(SEED, indent=2) + "\n", args.force, created, skipped)

    if not args.keep_declared:
        text = manifest_path.read_text(encoding="utf-8")
        # Anchored and MULTILINE: the manifest's header comment *explains* what
        # status = "declared" means, and an unanchored sub() happily rewrites
        # that instead of the setting, leaving the service silently declared.
        flipped = re.sub(r'^status(\s*)=\s*"declared"', r'status\1= "implemented"',
                         text, count=1, flags=re.MULTILINE)
        if flipped == text:
            print("  manifest: status was already 'implemented'")
        else:
            manifest_path.write_text(flipped, encoding="utf-8")
            print("  manifest: status -> implemented")

    for path in created:
        print(f"  created  {path.relative_to(ROOT)}")
    for path in skipped:
        print(f"  exists   {path.relative_to(ROOT)}  (use --force to overwrite)")

    # ASCII only: this prints to a Windows console under cp1252, where a stray
    # arrow glyph raises UnicodeEncodeError and takes the whole script with it.
    print(f"\n{descriptor.name} scaffolded. Next:")
    print(f"  python -m pytest services/{package}")
    print(f"  uvicorn main:app --port 8080")
    print(f"  curl http://localhost:8080{descriptor.base_path}/health")
    print("\nThen replace the generic /records CRUD with the real surface:")
    for prefix in descriptor.route_prefixes[:6]:
        print(f"    {descriptor.base_path}{prefix}")
    print(f"\nUpstream reference: {descriptor.upstream}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
