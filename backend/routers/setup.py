"""Setup router - the in-app dependency/model installer's HTTP surface.

Endpoints:

* ``GET    /api/setup/dependencies``          - full status payload
* ``POST   /api/setup/dependencies/install``  - start a background install (202)
* ``POST   /api/setup/dependencies/cancel``   - request cooperative cancel
* ``POST   /api/setup/dependencies/probe``    - import-check the matting stack

The install runs as a **server-side background job**: the frontend modal only
renders the state returned here, so closing it never stops the work.  The
payload shape (``running``/``install``/``groups``/``models``/``environment``/
``probe``) is a contract the frontend is already built against — the engine's
``snapshot()`` is returned verbatim.

``vitmatte_ready`` in the environment block means the whole chain can run:
torch importable, transformers importable, **and** the ViTMatte weights on
disk.  Detection never imports the heavy packages (``find_spec`` +
``importlib.metadata`` only).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import model_installer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["setup"])


class InstallRequest(BaseModel):
    """Body of the install endpoint: which groups to fetch."""

    groups: list[str]


@router.get("/api/setup/dependencies")
async def get_dependencies() -> dict:
    """Full setup status: live install state, groups, storage, environment."""
    return model_installer.snapshot()


@router.post("/api/setup/dependencies/install", status_code=202)
async def install_dependencies(request: InstallRequest) -> dict:
    """Start installing the requested groups on a background thread.

    202 with the status payload (the job continues server-side), 409 when one
    is already running, 422 on an empty or unknown group list.
    """
    try:
        return model_installer.start(request.groups)
    except model_installer.AlreadyRunning as exc:
        raise HTTPException(status_code=409, detail="install already running") from exc
    except model_installer.UnknownGroup as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/setup/dependencies/cancel")
async def cancel_dependencies() -> dict:
    """Request cooperative cancellation; 409 when no install is running."""
    try:
        return model_installer.cancel()
    except model_installer.NotRunning as exc:
        raise HTTPException(status_code=409, detail="no install is running") from exc


@router.post("/api/setup/dependencies/probe")
async def probe_dependencies() -> dict:
    """Import-check torch/transformers/ViTMatte in a subprocess (no downloads)."""
    return model_installer.run_probe()
