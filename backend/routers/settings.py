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

    # The search half is only probed when asked for. It is a *different* vendor
    # with a different credential, so folding it into every connection test would
    # spend a Brave query every time the operator checks their LLM endpoint.
    if payload.get("probe_search"):
        result["search"] = _probe_search(payload)

    return SettingsTestResponse(**result)


def _probe_search(payload: dict) -> dict:
    """Exercise the search provider chain and report which one answered.

    Candidate values are applied to a *copy* of the configuration, matching the
    LLM probe's non-destructive contract: testing a key the operator is still
    experimenting with must not pin it.
    """
    from services.research import search as search_module

    submitted_key = str(payload.get("brave_search_api_key") or "").strip()
    current = app_settings.resolve_search()
    # A blank or masked key means "use the saved one", the same contract the
    # settings save uses, so probing without retyping the key still works.
    key = (
        current.api_key
        if (not submitted_key or submitted_key == app_settings.mask_brave_key(current.api_key))
        else submitted_key
    )

    response = search_module.search(
        "stock photography market trends",
        limit=3,
        brave_api_key=key,
        use_brave=bool(key),
    )
    if not response.ok:
        return {
            "ok": False,
            "provider": response.provider,
            "provider_label": response.provider_label,
            "results": 0,
            "error": response.error
            + (
                " — what each provider said: "
                + "; ".join(response.provider_errors)
                if response.provider_errors
                else ""
            ),
        }
    return {
        "ok": True,
        "provider": response.provider,
        "provider_label": response.provider_label,
        "results": len(response.results),
        "error": None,
    }


@router.post("/api/settings/reset", response_model=SettingsResponse)
async def reset_settings() -> SettingsResponse:
    """Clear every stored override so the environment values take over again."""
    app_settings.save_raw({})
    logger.info("Application settings reset to environment defaults")
    return SettingsResponse(**app_settings.read_public())
