"""Settings router - read and update the runtime application settings.

Endpoints:

* ``GET  /api/settings``          - the current configuration, key masked
* ``PUT  /api/settings``          - apply a partial update
* ``POST /api/settings/test``     - probe the endpoint with a text request
* ``POST /api/settings/reset``    - clear overrides and fall back to .env

The API key is never returned in a usable form: ``GET`` hands back a mask, and
``PUT`` treats a blank or masked value as "keep the stored key".
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from schemas import (
    SettingsResponse,
    SettingsTestRequest,
    SettingsTestResponse,
    SettingsUpdateRequest,
)
from services import app_settings, llm_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


@router.get("/api/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """Return the operator-editable settings plus what a request would use."""
    return SettingsResponse(**app_settings.read_public())


@router.put("/api/settings", response_model=SettingsResponse)
async def put_settings(request: SettingsUpdateRequest) -> SettingsResponse:
    """Apply a partial update and return the resulting configuration."""
    payload = request.model_dump(exclude_unset=True)
    try:
        updated = app_settings.update(payload)
    except app_settings.SettingsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SettingsResponse(**updated)


@router.post("/api/settings/test", response_model=SettingsTestResponse)
async def test_settings(request: SettingsTestRequest | None = None) -> SettingsTestResponse:
    """Probe the endpoint so a bad URL, key, or model name surfaces immediately.

    The submitted values are validated but **not persisted** - the probe
    exercises a copy of the configuration, so testing a candidate cannot pin
    values the operator is still experimenting with.

    ``llm_client`` is referenced through the module (not imported by name) so a
    test can substitute the probe without patching the router.
    """
    payload = request.model_dump(exclude_unset=True) if request else {}
    try:
        app_settings.validate(payload)
    except app_settings.SettingsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = llm_client.test_connection(payload)
    return SettingsTestResponse(**result)


@router.post("/api/settings/reset", response_model=SettingsResponse)
async def reset_settings() -> SettingsResponse:
    """Clear every stored override so the environment values take over again."""
    app_settings.save_raw({})
    logger.info("Application settings reset to environment defaults")
    return SettingsResponse(**app_settings.read_public())
