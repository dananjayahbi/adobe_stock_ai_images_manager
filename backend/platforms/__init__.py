"""Platform core for the universal multi-platform image-upload system.

Each platform (Adobe Stock today; Freepik, Vecteezy, Dreamstime, 123RF,
Wirestock coming soon) is a first-class citizen with DEDICATED storage and its
own SQLite database:

* :mod:`platforms.registry` — the platform catalogue (id, name, tagline,
  status, frontend route) served by ``GET /api/platforms``.
* :mod:`platforms.paths` — the data-isolation contract: per-platform roots,
  subdirectories, and database paths instead of the global ``settings.*_DIR``
  fields (which point at Adobe Stock for legacy compatibility).
* :mod:`platforms.routers` — the API endpoints exposing the catalogue.

Shared processing services stay code-level reusable: they receive explicit
paths/sessions from :mod:`platforms.paths` and :mod:`database` helpers so a
platform's data NEVER touches another platform's storage or database.
"""
