"""Export each implemented service's OpenAPI schema to its package directory.

    python tools/export_openapi.py            # write services/<pkg>/openapi.json
    python tools/export_openapi.py --check    # fail if any file is stale (CI)

The schemas are generated at runtime by FastAPI, so committing them is
redundant *for the server* -- but not for everyone else. A checked-in
``openapi.json`` can be diffed in review (an accidental route removal shows up
as a deleted path), fed to a client generator, and read by a task author
without booting anything. ``--check`` is what stops it drifting.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hub.config import HubConfig  # noqa: E402
from service_registry import ServiceRegistry  # noqa: E402


async def collect() -> dict:
    registry = ServiceRegistry(HubConfig.from_env(strict_discovery=True))
    registry.discover()
    schemas = {}
    for descriptor in registry.descriptors():
        if not descriptor.implemented:
            continue
        record = await registry.acquire(descriptor.slug)
        schemas[descriptor.slug] = (descriptor.package_dir, record.app.openapi())
        await registry.unload(descriptor.slug)
    return schemas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if any committed schema is out of date")
    args = parser.parse_args()

    schemas = asyncio.run(collect())
    if not schemas:
        print("no implemented services found")
        return 0

    stale = []
    for slug, (package_dir, schema) in schemas.items():
        target = package_dir / "openapi.json"
        rendered = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        paths = len(schema.get("paths", {}))
        operations = sum(
            len([m for m in ops if m.lower() != "parameters"])
            for ops in schema.get("paths", {}).values()
        )
        if args.check:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != rendered:
                stale.append(target)
                print(f"STALE  {target.relative_to(ROOT)}")
            else:
                print(f"ok     {target.relative_to(ROOT)}  {paths} paths / {operations} ops")
        else:
            target.write_text(rendered, encoding="utf-8")
            print(f"wrote  {target.relative_to(ROOT)}  {paths} paths / {operations} ops")

    if stale:
        print(f"\n{len(stale)} schema(s) out of date. Run: python tools/export_openapi.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
