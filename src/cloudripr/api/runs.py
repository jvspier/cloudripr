from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse

from cloudripr.auth import require_auth
from cloudripr.errors import ApiError
from cloudripr.runs.service import GATE_SAMPLE_KEY
from cloudripr.services import Services, get_services
from cloudripr.store.db import RunRecord


router = APIRouter(prefix="/runs", tags=["runs"], dependencies=[Depends(require_auth)])


def _get_or_404(svc: Services, run_id: str) -> RunRecord:
    record = svc.db.get_run(run_id)
    if record is None:
        raise ApiError("Run not found", status_code=404)
    return record


def _gate_review(svc: Services, record: RunRecord) -> dict[str, Any] | None:
    if record.status != "gate_blocked":
        return None
    sample = svc.db.kv_get_json(GATE_SAMPLE_KEY.format(policy=record.policy))
    return sample if sample and sample.get("run_id") == record.id else None


@router.get("")
def list_runs(
    request: Request,
    policy: str | None = None,
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict[str, Any]]:
    return [r.to_json() for r in get_services(request).db.list_runs(policy=policy, limit=limit)]


@router.get("/{run_id}")
def get_run(run_id: str, request: Request) -> dict[str, Any]:
    svc = get_services(request)
    record = _get_or_404(svc, run_id)
    data = record.to_json()
    data["file_count"] = len(svc.db.run_files(run_id))
    data["gate_review"] = _gate_review(svc, record)
    return data


@router.get("/{run_id}/log")
def get_log(run_id: str, request: Request) -> FileResponse:
    svc = get_services(request)
    record = _get_or_404(svc, run_id)
    if not record.log_path:
        raise ApiError("Log not available", status_code=404)
    path = Path(record.log_path).resolve()
    if not path.is_relative_to(svc.paths.runs.resolve()) or not path.is_file():
        raise ApiError("Log not available", status_code=404)
    return FileResponse(path, media_type="text/plain")


@router.get("/{run_id}/items")
def get_items(run_id: str, request: Request) -> dict[str, list[str]]:
    svc = get_services(request)
    _get_or_404(svc, run_id)
    return {"files": svc.db.run_files(run_id)}


@router.post("/{run_id}/stop")
async def stop_run(run_id: str, request: Request) -> dict[str, bool]:
    if not await get_services(request).runs.stop(run_id):
        raise ApiError("This run is not active.", status_code=404)
    return {"ok": True}


@router.post("/{run_id}/approve")
async def approve(run_id: str, request: Request) -> dict[str, Any]:
    svc = get_services(request)
    record = _get_or_404(svc, run_id)
    latest = svc.db.last_run(record.policy)
    if (
        record.status != "gate_blocked"
        or svc.gate.state(record.policy) != "blocked"
        or latest is None
        or latest.id != record.id
    ):
        raise ApiError("Nothing to approve for this run.", status_code=409)
    new = await svc.runs.approve_gate(record.policy)
    return new.to_json()
