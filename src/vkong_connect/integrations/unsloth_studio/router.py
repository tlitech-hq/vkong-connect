"""FastAPI routes that Unsloth Studio mounts for the "Train on VKong" button.

These are Studio's own local endpoints. Every VKong operation behind them goes
through the VKong CLI (see ``service.py``); nothing here calls a VKong API.
"""

from __future__ import annotations

from typing import Any, Callable

from vkong_connect.errors import BridgeError, ConfigurationError, VKongNotInstalledError

from .service import RemoteTrainingService


def create_router(auth_dependency: Callable[..., Any], service: RemoteTrainingService | None = None):
    from fastapi import APIRouter, Body, Depends, HTTPException

    svc = service or RemoteTrainingService()
    router = APIRouter()

    def _http_error(exc: BridgeError) -> HTTPException:
        if isinstance(exc, VKongNotInstalledError):
            return HTTPException(status_code=503, detail=str(exc))
        if isinstance(exc, ConfigurationError):
            return HTTPException(status_code=400, detail=str(exc))
        return HTTPException(status_code=502, detail=str(exc))

    # Sync handlers: FastAPI runs them in its threadpool, so CLI subprocesses
    # never block the event loop.
    @router.get("/readiness")
    def readiness(_subject: Any = Depends(auth_dependency)) -> dict:
        return svc.readiness()

    @router.post("/jobs")
    def start_job(body: dict = Body(...), _subject: Any = Depends(auth_dependency)) -> dict:
        training = body.get("training")
        if not isinstance(training, dict):
            raise HTTPException(status_code=400, detail="training payload is required")
        try:
            return svc.start(
                training,
                output_repo_id=body.get("output_repo_id", ""),
                compute=body.get("compute") if isinstance(body.get("compute"), dict) else None,
            )
        except BridgeError as exc:
            raise _http_error(exc) from exc

    @router.get("/jobs")
    def list_jobs(_subject: Any = Depends(auth_dependency)) -> dict:
        return {"jobs": svc.list_jobs()}

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str, _subject: Any = Depends(auth_dependency)) -> dict:
        try:
            return svc.get_job(job_id)
        except BridgeError as exc:
            raise _http_error(exc) from exc

    @router.post("/jobs/{job_id}/stop")
    def stop_job(job_id: str, _subject: Any = Depends(auth_dependency)) -> dict:
        try:
            return svc.stop_job(job_id)
        except BridgeError as exc:
            raise _http_error(exc) from exc

    return router
