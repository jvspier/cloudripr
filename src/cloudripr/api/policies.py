from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from typing import Any

import tomli_w
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from cloudripr.auth import require_auth
from cloudripr.engine.argv import naming_signature
from cloudripr.errors import ApiError, ValidationError
from cloudripr.migration import NAMING_FROZEN_KEY
from cloudripr.runs.service import GATE_SAMPLE_KEY
from cloudripr.services import Services, get_services
from cloudripr.store.models import Policy


router = APIRouter(prefix="/policies", tags=["policies"], dependencies=[Depends(require_auth)])

UNLOCK_KEY = "unlock:{policy}"
SECRET_ICLOUDPD_KEYS = frozenset({"smtp_password"})


class UnlockBody(BaseModel):
    confirm: str


def naming_locked(svc: Services, name: str) -> bool:
    has_library = (
        svc.db.last_success(name) is not None
        or svc.db.kv_get(NAMING_FROZEN_KEY.format(policy=name)) is not None
    )
    return has_library and svc.db.kv_get(UNLOCK_KEY.format(policy=name)) is None


def _public(policy: Policy) -> dict[str, Any]:
    data = policy.to_toml_dict()
    data["icloudpd"] = {
        k: v for k, v in data.get("icloudpd", {}).items() if k not in SECRET_ICLOUDPD_KEYS
    }
    return data


def _summary(svc: Services, policy: Policy) -> dict[str, Any]:
    data = _public(policy)
    data["next_run_at"] = (
        svc.scheduler.next_run_at(policy, after=datetime.now(UTC)).isoformat()
        if policy.enabled
        else None
    )
    last = svc.db.last_run(policy.name)
    success = svc.db.last_success(policy.name)
    active = svc.runs.active_for(policy.name)
    gate = svc.gate.state(policy.name)
    data["last_run"] = last.to_json() if last else None
    data["last_success"] = success.to_json() if success else None
    data["active_run"] = active.to_json() if active else None
    data["gate"] = gate
    data["gate_review"] = (
        svc.db.kv_get_json(GATE_SAMPLE_KEY.format(policy=policy.name))
        if gate == "blocked"
        else None
    )
    data["naming_locked"] = naming_locked(svc, policy.name)
    return data


def _get_or_404(svc: Services, name: str) -> Policy:
    policy = svc.policies.get(name)
    if policy is None:
        raise ApiError("Policy not found", status_code=404)
    return policy


def _build(svc: Services, data: dict[str, Any], existing: Policy | None) -> Policy:
    data = dict(data)
    account = svc.account_store.load()
    if account is not None:
        data["username"] = account.apple_id
    data.setdefault("username", "")
    icloudpd = dict(data.get("icloudpd") or {})
    # Rollback compatibility only; the engine ignores it.
    icloudpd["cookie_directory"] = str(svc.paths.session)
    if existing is not None:
        for key in SECRET_ICLOUDPD_KEYS:
            if key in existing.icloudpd and key not in icloudpd:
                icloudpd[key] = existing.icloudpd[key]
    data["icloudpd"] = icloudpd
    try:
        return Policy(**data)
    except PydanticValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(x) for x in first["loc"]) or None
        raise ValidationError(first["msg"].removeprefix("Value error, "), field=field) from None


@router.get("")
def list_policies(request: Request) -> list[dict[str, Any]]:
    svc = get_services(request)
    return [_summary(svc, p) for p in sorted(svc.policies.all(), key=lambda p: p.name)]


@router.get("/export")
def export_policies(request: Request) -> Response:
    svc = get_services(request)
    bundle = {"policy": [_public(p) for p in sorted(svc.policies.all(), key=lambda p: p.name)]}
    return Response(
        content=tomli_w.dumps(bundle),
        media_type="application/toml",
        headers={"Content-Disposition": 'attachment; filename="icloudpd-policies.toml"'},
    )


@router.post("/import")
async def import_policies(request: Request) -> dict[str, Any]:
    svc = get_services(request)
    raw = await request.body()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ApiError(f"Not a valid TOML file: {exc}", status_code=400) from None
    entries = data["policy"] if isinstance(data.get("policy"), list) else [data]
    created: list[str] = []
    errors: list[dict[str, Any]] = []
    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(entry, dict):
            errors.append({"name": None, "error": "entry is not a table"})
            continue
        if name and svc.policies.get(name) is not None:
            errors.append({"name": name, "error": "already exists"})
            continue
        try:
            policy = _build(svc, entry, None)
        except ValidationError as exc:
            errors.append({"name": name, "error": exc.message})
            continue
        svc.gate.arm(policy.name)
        svc.policies.put(policy)
        created.append(policy.name)
    return {"created": created, "errors": errors}


@router.get("/{name}")
def get_policy(name: str, request: Request) -> dict[str, Any]:
    svc = get_services(request)
    return _summary(svc, _get_or_404(svc, name))


@router.put("/{name}")
def put_policy(name: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
    svc = get_services(request)
    if body.get("name") != name:
        raise ValidationError("The name in the URL must match the policy name.", field="name")
    existing = svc.policies.get(name)
    policy = _build(svc, body, existing)
    if existing is not None and naming_signature(existing) != naming_signature(policy):
        if naming_locked(svc, name):
            raise ApiError(
                "File naming settings are locked to protect your existing downloads. "
                "Unlock them first.",
                status_code=409,
                field="naming",
            )
        svc.gate.arm(name)
        svc.db.kv_delete(UNLOCK_KEY.format(policy=name))
    elif existing is None:
        # A new (or recreated) policy always starts with a safety dry run.
        svc.gate.arm(name)
    svc.policies.put(policy)
    return _summary(svc, policy)


@router.delete("/{name}")
def delete_policy(name: str, request: Request) -> dict[str, bool]:
    svc = get_services(request)
    _get_or_404(svc, name)
    if svc.runs.active_for(name) is not None:
        raise ApiError("Stop the running backup first.", status_code=409)
    svc.policies.delete(name)
    svc.secrets.delete(name)
    svc.db.kv_delete(UNLOCK_KEY.format(policy=name))
    return {"ok": True}


@router.post("/{name}/run", status_code=202)
async def run_policy(name: str, request: Request) -> dict[str, Any]:
    svc = get_services(request)
    _get_or_404(svc, name)
    record = await svc.runs.trigger(name, "manual")
    return record.to_json()


@router.post("/{name}/unlock")
def unlock_naming(name: str, body: UnlockBody, request: Request) -> dict[str, Any]:
    svc = get_services(request)
    policy = _get_or_404(svc, name)
    if body.confirm.strip() != name:
        raise ValidationError("Type the policy name to confirm.", field="confirm")
    svc.db.kv_set(UNLOCK_KEY.format(policy=name), datetime.now(UTC).isoformat())
    return _summary(svc, policy)
