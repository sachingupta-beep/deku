"""Simulated service modules.

One package per service, each with a ``service.toml`` manifest next to it. The
hub discovers packages by scanning for those manifests, so adding a service is
adding a directory -- there is no central list to edit and nothing to register.

``services/supabase/`` is the worked reference implementation; every other
package should read like it. See ``docs/SERVICE_AUTHORING.md``.
"""
