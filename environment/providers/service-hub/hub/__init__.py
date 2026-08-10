"""Service Hub core.

The hub is a single FastAPI process that hosts many *simulated* services --
Supabase, Keycloak, MailHog, Lago and so on -- as lazily-loaded modules behind
one port. Nothing in this package knows about any particular service; the
service-specific code lives under ``services/<package>/``.

Layout of this package:

===================  ======================================================
``config.py``        environment-driven :class:`HubConfig`
``errors.py``        hub-level (as opposed to service-level) error envelope
``manifest.py``      ``service.toml`` parsing into a :class:`ServiceDescriptor`
``base.py``          :class:`ServiceModule` ABC + :class:`ServiceContext`
``audit.py``         mount-aware request/response recorder
``control.py``       the ``/hub/*`` control plane
``store.py``         vendored mutable record store (see its module docstring)
===================  ======================================================

The registry, the dynamic router and the app factory sit at the repository root
(``service_registry.py``, ``router.py``, ``main.py``) because they are the three
files a reader should open first.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
