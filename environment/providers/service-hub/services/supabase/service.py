"""The Supabase :class:`~hub.base.ServiceModule` -- the reference implementation.

Every other service should look like this file: a small class that wires a data
layer to a router and implements the lifecycle hooks. The interesting code is in
``data.py``; this is the seam between it and the hub.

Read it as the four things the hub asks of a service:

===================  ===========================================================
``on_startup``       build the data layer and force the seeds to load
``build_router``     hand back the routes
``health``           answer a cheap liveness probe
``on_shutdown``      drop what startup built
===================  ===========================================================
"""

from __future__ import annotations

from fastapi import APIRouter

from hub.base import HealthReport, ServiceModule

from .data import REST_TABLES, SupabaseData
from .routes import build_router


class SupabaseService(ServiceModule):
    """Self-hosted Supabase data plane: PostgREST, Storage, Functions, Realtime."""

    data: SupabaseData

    async def on_startup(self) -> None:
        """Construct the data layer and load every seed *now*.

        ``eager_load`` is the important line. Without it the first seed read
        happens inside whatever request touches that table first, so a malformed
        ``documents.json`` surfaces as a confusing 500 halfway through a task.
        With it, a bad seed fails the load itself, and the hub reports the
        service as ``failed`` with the file, row and column named -- which is a
        two-second fix instead of a debugging session.
        """
        self.data = SupabaseData(self.ctx)
        self.ctx.eager_load()
        self.log.info(
            "seeded %d profiles, %d projects, %d documents, %d comments",
            len(self.ctx.table("profiles")),
            len(self.ctx.table("projects")),
            len(self.ctx.table("documents")),
            len(self.ctx.table("comments")),
        )

    def build_router(self) -> APIRouter:
        return build_router(self.data)

    def health(self) -> HealthReport:
        """Report row counts for the REST-exposed tables plus the project ref.

        Cheap by construction -- ``len`` on the store's dict, no seed re-read --
        because ``GET /hub/health`` calls this for every loaded service.
        """
        settings = self.data.settings()
        return HealthReport(
            status="ok",
            checks={
                "project_ref": settings.get("ref"),
                "rows": {table: len(self.ctx.table(table)) for table in REST_TABLES},
                "buckets": len(self.ctx.table("buckets")),
                "functions": len(self.ctx.table("functions")),
            },
        )

    async def on_shutdown(self) -> None:
        """Release the data layer. The store is dropped by the registry, so this
        only has to let go of our reference to it."""
        self.data = None  # type: ignore[assignment]
        self.log.info("supabase service torn down")
