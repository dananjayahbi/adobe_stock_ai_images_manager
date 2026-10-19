"""API endpoints exposing the platform catalogue to the frontend."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from platforms.registry import PLATFORMS, Platform, get_platform

router = APIRouter(prefix="/api/platforms", tags=["platforms"])


def _serialize(platform: Platform) -> dict[str, str]:
    """Catalogue entry as JSON — the shape the frontend consumes."""
    return {
        "id": platform.id,
        "name": platform.name,
        "tagline": platform.tagline,
        "status": platform.status,
        "route": platform.route,
    }


@router.get("")
@router.get("/")
def list_platforms() -> list[dict[str, str]]:
    """All platforms in display order (available first, then coming soon).

    Both path forms are served directly so ``/api/platforms`` (no trailing
    slash) answers 200 instead of a 307 redirect round-trip.
    """
    return [_serialize(platform) for platform in PLATFORMS]


@router.get("/{platform_id}")
def read_platform(platform_id: str) -> dict[str, str]:
    """One platform by id; 404 for anything not in the catalogue."""
    platform = get_platform(platform_id)
    if platform is None:
        raise HTTPException(status_code=404, detail="Unknown platform")
    return _serialize(platform)
