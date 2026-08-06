"""Capability adapters — the design move that makes the service matrix affordable.

PLAN.md 3.3: workflows and pytest substeps are written **once per capability, not
once per provider**. A substep asserts `inbox.find(to=..., subject_contains=...)`
and runs unchanged against Mailpit, MailHog or Inbucket. The **assertion** is
capability-level; only the **adapter** is provider-specific, and it lives here.

Without this, 11 slots x N providers fragments the verifier into hundreds of
bespoke test files and the matrix costs more than it returns.

Only adapters an authored task actually selects are implemented. Add a provider
when a task selects it, not before.

Provider selection comes from `[metadata.services]` in task.toml, surfaced to the
verifier as `DEKU_SERVICE_<SLOT>` environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

TIMEOUT = 30.0


class InfrastructureUnavailable(RuntimeError):
    """Backing service is unreachable or refused our credentials.

    Raised by adapters so pytest surfaces the failure as a harness/infrastructure
    fault, not an app-quality failure. If this bubbles up as a bare AssertionError
    the agent gets billed for a sidecar the harness never brought up.
    """


def selected(slot: str) -> str:
    """Provider chosen for a slot, from task.toml [metadata.services]."""
    key = f"DEKU_SERVICE_{slot.upper()}"
    provider = os.environ.get(key)
    if not provider:
        raise RuntimeError(
            f"slot {slot!r} is not selected for this task: {key} is unset. "
            f"A test may only use a capability the task declares in "
            f"[metadata.services]."
        )
    return provider


# =============================================================== backend / BaaS


class Backend:
    """Generic persisted-state primitives.

    Deliberately narrow: `count`, `rows`, `one`. Domain queries ("employees with
    no active seat") belong in a task's conftest.py, composed from these. That is
    the seam that keeps the adapter provider-swappable while task assertions stay
    readable.
    """

    def count(self, table: str, **where: Any) -> int:
        raise NotImplementedError

    def rows(self, table: str, limit: int | None = None, **where: Any) -> list[dict]:
        raise NotImplementedError

    def one(self, table: str, **where: Any) -> dict | None:
        found = self.rows(table, limit=1, **where)
        return found[0] if found else None


class PostgresBackend(Backend):
    def __init__(self, dsn: str) -> None:
        import psycopg  # imported here so tasks not using postgres need no driver

        self._psycopg = psycopg
        self._dsn = dsn

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            columns = [column.name for column in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def _where(self, where: dict) -> tuple[str, tuple]:
        if not where:
            return "", ()
        clause = " AND ".join(f"{key} = %s" for key in where)
        return f" WHERE {clause}", tuple(where.values())

    def count(self, table: str, **where: Any) -> int:
        clause, params = self._where(where)
        return self.query(f"SELECT count(*) AS n FROM {table}{clause}", params)[0]["n"]

    def rows(self, table: str, limit: int | None = None, **where: Any) -> list[dict]:
        clause, params = self._where(where)
        sql = f"SELECT * FROM {table}{clause} ORDER BY id"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self.query(sql, params)


class PocketBaseBackend(Backend):
    """PocketBase exposes collections over REST; the admin token is the escape hatch.

    `credential` is either a ready-made admin token or, more usefully,
    `email:password`. PocketBase mints admin tokens at runtime and expires them,
    so a token cannot be baked into task.toml ahead of time -- the credential
    pair is the only thing stable enough to declare. Exchange happens here so no
    task's conftest has to know PocketBase's auth endpoint.
    """

    def __init__(self, base_url: str, credential: str) -> None:
        base_url = base_url.rstrip("/")
        token = credential
        if ":" in credential and not credential.startswith("ey"):
            identity, password = credential.split(":", 1)
            try:
                response = httpx.post(
                    f"{base_url}/api/admins/auth-with-password",
                    json={"identity": identity, "password": password},
                    timeout=TIMEOUT,
                )
            except httpx.HTTPError as exc:
                raise InfrastructureUnavailable(
                    f"PocketBase sidecar at {base_url} unreachable "
                    f"({exc.__class__.__name__}: {exc}); this is a harness/"
                    f"infrastructure fault, not an app fault"
                ) from exc
            if response.status_code != 200:
                raise InfrastructureUnavailable(
                    f"PocketBase admin auth for {identity!r} at {base_url} "
                    f"returned {response.status_code}: {response.text[:300]}; "
                    f"this is a harness/infrastructure fault "
                    f"(sidecar down or wrong credentials), not an app fault"
                )
            token = response.json()["token"]
        self._client = httpx.Client(
            base_url=base_url,
            timeout=TIMEOUT,
            headers={"Authorization": token},
        )

    @staticmethod
    def _literal(value: Any) -> str:
        """Render a Python value as a PocketBase filter literal.

        PocketBase's filter language is TEXT -- there is no parameter binding, so
        the adapter is responsible for typing. Wrapping every value in quotes (the
        original implementation) turns a boolean into the string "False", and a
        boolean column never equals a string, so the query matched nothing and
        returned [] instead of erroring.

        Measured cost of that one line: every substep filtering `deleted=False`
        was unpassable by ANY app. On streak-habit-tracker that silently capped
        the reward and read as "the app stores data outside PocketBase" -- three
        of four pytest failures on 2026-08-06 were this, not the app.

        `bool` MUST be tested before `int`: in Python bool subclasses int, so an
        isinstance(v, int) check first renders False as `0` and reintroduces the
        bug in a subtler form.
        """
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        # Escape embedded quotes so a value cannot terminate the literal early.
        return '"{}"'.format(str(value).replace('"', '\\"'))

    def _fetch(self, table: str, where: dict, per_page: int) -> dict:
        params: dict[str, Any] = {"perPage": per_page}
        if where:
            params["filter"] = " && ".join(
                f"{k}={self._literal(v)}" for k, v in where.items()
            )
        response = self._client.get(f"/api/collections/{table}/records", params=params)
        assert response.status_code == 200, (
            f"PocketBase {table} query returned {response.status_code}: "
            f"{response.text[:300]}"
        )
        return response.json()

    def count(self, table: str, **where: Any) -> int:
        return int(self._fetch(table, where, per_page=1).get("totalItems", 0))

    def rows(self, table: str, limit: int | None = None, **where: Any) -> list[dict]:
        return self._fetch(table, where, per_page=limit or 200).get("items", [])


def make_backend() -> Backend:
    provider = selected("backend")
    if provider == "postgres":
        return PostgresBackend(os.environ["DB_ADMIN_URL"])
    if provider == "pocketbase":
        return PocketBaseBackend(
            os.environ["BACKEND_URL"], os.environ["BACKEND_ADMIN_KEY"]
        )
    raise RuntimeError(f"no backend adapter for provider {provider!r}")


# ========================================================================= email


@dataclass(frozen=True)
class Message:
    to: list[str]
    subject: str
    body: str


class Inbox:
    def find(self, to: str, subject_contains: str = "") -> Message | None:
        raise NotImplementedError

    def count(self, to: str | None = None) -> int:
        raise NotImplementedError


class HttpInbox(Inbox):
    """Mailpit and MailHog both expose a JSON inbox API; the shapes differ slightly."""

    def __init__(self, base_url: str, provider: str) -> None:
        self._provider = provider
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=TIMEOUT)

    def _messages(self) -> list[Message]:
        if self._provider == "mailpit":
            payload = self._client.get("/api/v1/messages", params={"limit": 200}).json()
            return [
                Message(
                    to=[addr.get("Address", "") for addr in item.get("To", [])],
                    subject=item.get("Subject", ""),
                    body=item.get("Snippet", ""),
                )
                for item in payload.get("messages", [])
            ]
        payload = self._client.get("/api/v2/messages", params={"limit": 200}).json()
        messages = []
        for item in payload.get("items", []):
            headers = item.get("Content", {}).get("Headers", {})
            messages.append(
                Message(
                    to=headers.get("To", []),
                    subject=" ".join(headers.get("Subject", [])),
                    body=item.get("Content", {}).get("Body", ""),
                )
            )
        return messages

    def find(self, to: str, subject_contains: str = "") -> Message | None:
        needle = subject_contains.lower()
        for message in self._messages():
            if any(to.lower() in addr.lower() for addr in message.to) and (
                needle in message.subject.lower()
            ):
                return message
        return None

    def count(self, to: str | None = None) -> int:
        messages = self._messages()
        if to is None:
            return len(messages)
        return sum(
            1
            for message in messages
            if any(to.lower() in addr.lower() for addr in message.to)
        )


def make_inbox() -> Inbox:
    provider = selected("email")
    if provider in ("mailpit", "mailhog"):
        return HttpInbox(os.environ["EMAIL_INBOX_API_URL"], provider)
    raise RuntimeError(f"no inbox adapter for provider {provider!r}")


# ====================================================================== payments


@dataclass(frozen=True)
class Charge:
    id: str
    amount: int
    currency: str
    status: str
    metadata: dict


class Payments:
    def charges(self) -> list[Charge]:
        raise NotImplementedError

    def find_charge(
        self, amount: int, currency: str = "usd", status: str | None = None
    ) -> Charge | None:
        for charge in self.charges():
            if charge.amount != amount or charge.currency.lower() != currency.lower():
                continue
            if status and charge.status != status:
                continue
            return charge
        return None

    def refunds_for(self, charge_id: str) -> list[dict]:
        raise NotImplementedError


class DekuPay(Payments):
    """deku-pay: the in-house, credential-free, adversarial payment provider (3.3.1).

    Not a mock by the 3.3 definition -- a real service with real persisted state
    that the agent must integrate and cannot control. The verifier interrogates it
    directly, which is what makes the no-mocks rule enforceable.
    """

    def __init__(self, base_url: str, secret_key: str) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=TIMEOUT,
            headers={"Authorization": f"Bearer {secret_key}"},
        )

    def charges(self) -> list[Charge]:
        response = self._client.get("/v1/charges", params={"limit": 200})
        assert response.status_code == 200, (
            f"deku-pay /v1/charges returned {response.status_code}: "
            f"{response.text[:300]}"
        )
        return [
            Charge(
                id=item["id"],
                amount=int(item["amount"]),
                currency=item.get("currency", "usd"),
                status=item.get("status", ""),
                metadata=item.get("metadata", {}) or {},
            )
            for item in response.json().get("data", [])
        ]

    def refunds_for(self, charge_id: str) -> list[dict]:
        response = self._client.get("/v1/refunds", params={"charge": charge_id})
        assert response.status_code == 200, (
            f"deku-pay /v1/refunds returned {response.status_code}: "
            f"{response.text[:300]}"
        )
        return response.json().get("data", [])


def make_payments() -> Payments:
    provider = selected("payments")
    if provider == "deku-pay":
        return DekuPay(os.environ["PAYMENTS_API_URL"], os.environ["PAYMENTS_SECRET_KEY"])
    raise RuntimeError(f"no payments adapter for provider {provider!r}")


# ================================================================ object storage


class ObjectStore:
    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def list(self, prefix: str = "") -> list[str]:
        raise NotImplementedError


class S3Store(ObjectStore):
    """MinIO, SeaweedFS, Garage and LocalStack are all S3-compatible -> one adapter."""

    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def list(self, prefix: str = "") -> list[str]:
        pages = self._client.get_paginator("list_objects_v2").paginate(
            Bucket=self._bucket, Prefix=prefix
        )
        return [obj["Key"] for page in pages for obj in page.get("Contents", [])]

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False


def make_store() -> ObjectStore:
    provider = selected("storage")
    if provider in ("minio", "seaweedfs", "garage", "localstack"):
        return S3Store(
            os.environ["STORAGE_ENDPOINT"],
            os.environ["STORAGE_BUCKET"],
            os.environ["STORAGE_ACCESS_KEY"],
            os.environ["STORAGE_SECRET_KEY"],
        )
    raise RuntimeError(f"no object-store adapter for provider {provider!r}")
