"""Environment-driven hub configuration.

Every knob has a working default, so ``docker run service-hub`` needs no
environment at all. The evaluation harness overrides what it cares about --
most often ``HUB_EAGER_SERVICES`` (pre-warm the services a task will use, so
the agent's first call is not the one that pays the import cost) and
``HUB_IDLE_TTL`` (evict idle services to hold memory down on a long run).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
"""Absolute path to the ``service-hub/`` directory (this file's grandparent)."""

_TRUE = frozenset({"1", "true", "yes", "on", "t", "y"})


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or not value.strip() else value.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in _TRUE


def _env_tuple(name: str) -> Tuple[str, ...]:
    """Comma- or space-separated list, e.g. ``HUB_EAGER_SERVICES=supabase,lago``."""
    raw = os.environ.get(name, "").replace(",", " ").split()
    return tuple(dict.fromkeys(part.strip() for part in raw if part.strip()))


@dataclass(frozen=True)
class HubConfig:
    """Immutable settings for one hub process."""

    repo_root: Path = REPO_ROOT
    services_dir: Path = field(default=REPO_ROOT / "services")
    data_dir: Path = field(default=REPO_ROOT / "data")

    host: str = "0.0.0.0"
    port: int = 8080

    eager_services: Tuple[str, ...] = ()
    """Slugs loaded during startup instead of on first request. Empty = fully lazy."""

    idle_ttl_seconds: int = 0
    """Unload a service after this many seconds without a request. 0 disables eviction.
    Eager services are never evicted -- pinning them is the point."""

    reaper_interval_seconds: int = 30
    load_timeout_seconds: float = 30.0

    audit_enabled: bool = True
    audit_max_entries: int = 10_000
    audit_max_body_bytes: int = 512 * 1024

    expose_docs: bool = True
    """Serve ``/docs`` for the hub and ``/<slug>/docs`` per service."""

    strict_discovery: bool = False
    """Raise on a malformed ``service.toml`` instead of skipping it with a warning.
    Tests and CI set this; a running container prefers to serve 26 good services
    over refusing to boot because of one bad manifest."""

    @classmethod
    def from_env(cls, **overrides) -> "HubConfig":
        """Build config from ``HUB_*`` environment variables, then apply overrides."""
        root = Path(_env_str("HUB_ROOT", str(REPO_ROOT))).resolve()
        values = dict(
            repo_root=root,
            services_dir=Path(_env_str("HUB_SERVICES_DIR", str(root / "services"))),
            data_dir=Path(_env_str("HUB_DATA_DIR", str(root / "data"))),
            host=_env_str("HUB_HOST", "0.0.0.0"),
            port=_env_int("HUB_PORT", 8080),
            eager_services=_env_tuple("HUB_EAGER_SERVICES"),
            idle_ttl_seconds=_env_int("HUB_IDLE_TTL", 0),
            reaper_interval_seconds=_env_int("HUB_REAPER_INTERVAL", 30),
            load_timeout_seconds=float(_env_int("HUB_LOAD_TIMEOUT", 30)),
            audit_enabled=_env_bool("HUB_AUDIT", True),
            audit_max_entries=_env_int("HUB_AUDIT_MAX_ENTRIES", 10_000),
            audit_max_body_bytes=_env_int("HUB_AUDIT_MAX_BODY", 512 * 1024),
            expose_docs=_env_bool("HUB_EXPOSE_DOCS", True),
            strict_discovery=_env_bool("HUB_STRICT_DISCOVERY", False),
        )
        values.update(overrides)
        return cls(**values)

    def data_dir_for(self, name: str) -> Path:
        return self.data_dir / name
