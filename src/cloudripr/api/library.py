"""Read-only library endpoints for the Photos tab.

Files are only ever found through the index, and must resolve to a path inside the
policy root they were indexed under. Nothing here writes to the library.
"""

from __future__ import annotations

import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from cloudripr.auth import require_auth
from cloudripr.errors import ApiError, ValidationError
from cloudripr.library.index import Item
from cloudripr.runs.service import ICLOUD_TOTAL_KEY
from cloudripr.services import Services, get_services


router = APIRouter(prefix="/library", tags=["library"], dependencies=[Depends(require_auth)])

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_RECENT_RUNS = 10
_SAMPLE = 6
_IMMUTABLE = {"Cache-Control": "private, max-age=31536000, immutable"}
mimetypes.add_type("image/heic", ".heic")
mimetypes.add_type("image/heif", ".heif")


def _item_json(item: Item, run_id: str | None = None) -> dict[str, Any]:
    rel = PurePosixPath(item.rel)
    return {
        "id": item.id,
        "name": rel.name,
        "folder": str(rel.parent),
        "kind": item.kind,
        "size": item.size,
        "taken_at": datetime.fromtimestamp(item.taken_at, UTC).isoformat(),
        "duration": item.duration,
        "problem": item.problem,
        "run_id": run_id,
    }


def _icloud_total(svc: Services) -> dict[str, Any] | None:
    totals = [
        svc.db.kv_get_json(ICLOUD_TOTAL_KEY.format(policy=p.name)) for p in svc.policies.all()
    ]
    found = [t for t in totals if t]
    return max(found, key=lambda t: t["count"]) if found else None


def _file(svc: Services, item_id: int) -> tuple[Item, Path]:
    """The item and its file, or 404 if it's gone or would leave the policy root."""
    item = svc.library.get(item_id)
    if item is None:
        raise ApiError("Not found", status_code=404)
    root = Path(item.root).resolve()
    path = (Path(item.root) / item.rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ApiError("Not found", status_code=404)
    return item, path


@router.get("/summary")
def summary(request: Request) -> dict[str, Any]:
    svc = get_services(request)
    s = svc.library.summary()
    return {
        "on_disk": s["total"],
        "unreadable": s["unreadable"],
        "scanned_at": s["scanned_at"],
        "icloud": _icloud_total(svc),
    }


@router.get("/runs")
def recent_runs(request: Request) -> list[dict[str, Any]]:
    svc = get_services(request)
    runs = [
        r
        for r in svc.db.list_runs(limit=100)
        if r.status == "success" and not r.dry_run and r.downloaded > 0
    ][:_RECENT_RUNS]
    result = []
    for run in runs:
        items = svc.library.items_for_paths(svc.db.run_files(run.id))
        result.append(
            {
                "run": run.to_json(),
                "count": len(items),
                "unreadable": run.unreadable,
                "sample": [_item_json(i, run.id) for i in items[:_SAMPLE]],
            }
        )
    return result


@router.get("/months")
def months(request: Request) -> list[dict[str, Any]]:
    return get_services(request).library.months()


@router.get("/items")
def items(request: Request, month: str | None = None, run: str | None = None) -> list[dict]:
    svc = get_services(request)
    if (month is None) == (run is None):
        raise ValidationError("Give either a month or a run.")
    if month is not None:
        if not _MONTH.match(month):
            raise ValidationError("Month must look like 2026-11.", field="month")
        return [_item_json(i) for i in svc.library.items_in_month(month)]
    return [_item_json(i, run) for i in svc.library.items_for_paths(svc.db.run_files(run or ""))]


def _rendered(request: Request, item_id: int, *, preview: bool) -> FileResponse:
    svc = get_services(request)
    item, _ = _file(svc, item_id)
    out = svc.thumbs.ensure(item, preview=preview)
    if out is None:
        raise ApiError("This file can't be read.", status_code=404)
    return FileResponse(out, media_type="image/jpeg", headers=_IMMUTABLE)


@router.get("/items/{item_id}/thumb")
def thumb(item_id: int, request: Request) -> FileResponse:
    return _rendered(request, item_id, preview=False)


@router.get("/items/{item_id}/preview")
def preview(item_id: int, request: Request) -> FileResponse:
    return _rendered(request, item_id, preview=True)


@router.get("/items/{item_id}/original")
def original(item_id: int, request: Request) -> FileResponse:
    _, path = _file(get_services(request), item_id)
    media_type = mimetypes.guess_type(path.name.lower())[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)
