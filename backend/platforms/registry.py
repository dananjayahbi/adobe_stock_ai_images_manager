"""Platform catalogue: the single source of truth for supported platforms.

A :class:`Platform` is pure metadata — identity, display copy, availability,
and the frontend route. Storage and database locations are derived from the
platform ``id`` by :mod:`platforms.paths`, so adding a platform here plus an
adapter is all a future integration needs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    """Immutable description of one stock-marketplace platform.

    ``status`` is one of:

    * ``"available"``   — fully wired pipeline, selectable in the UI.
    * ``"coming_soon"`` — listed in the picker, routes/docs not built yet.

    ``route`` is the frontend path the platform's workspace will live at.
    """

    id: str
    name: str
    tagline: str
    status: str
    route: str

    def __post_init__(self) -> None:
        if self.status not in ("available", "coming_soon"):
            raise ValueError(
                f"Platform {self.id!r}: status must be 'available' or "
                f"'coming_soon', got {self.status!r}"
            )


#: The platform catalogue. Order matters: it is the display order in the UI.
PLATFORMS: tuple[Platform, ...] = (
    Platform(
        id="adobe_stock",
        name="Adobe Stock",
        tagline="The original pipeline — audit, refine, and deliver AI images.",
        status="available",
        route="/adobe-stock",
    ),
    Platform(
        id="freepik",
        name="Freepik",
        tagline="Vector-first marketplace — illustrations, PSDs, and photos, coming soon.",
        status="coming_soon",
        route="/freepik",
    ),
    Platform(
        id="vecteezy",
        name="Vecteezy",
        tagline="Creator-friendly vectors and photos — a fresh lane, coming soon.",
        status="coming_soon",
        route="/vecteezy",
    ),
    Platform(
        id="dreamstime",
        name="Dreamstime",
        tagline="Community-driven stock with deep archives — coming soon.",
        status="coming_soon",
        route="/dreamstime",
    ),
    Platform(
        id="123rf",
        name="123RF",
        tagline="Budget-minded marketplace with global reach — coming soon.",
        status="coming_soon",
        route="/123rf",
    ),
    Platform(
        id="wirestock",
        name="Wirestock",
        tagline="One upload, many marketplaces — the aggregator route, coming soon.",
        status="coming_soon",
        route="/wirestock",
    ),
)


def get_platform(platform_id: str) -> Platform | None:
    """Return the platform with ``platform_id``, or ``None`` if unknown."""
    for platform in PLATFORMS:
        if platform.id == platform_id:
            return platform
    return None


def list_platforms() -> tuple[Platform, ...]:
    """Return the full catalogue in display order."""
    return PLATFORMS
