from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from .config import settings
from .db import Database
from .fact_checker import fact_check_grant

router = APIRouter(prefix="/admin", tags=["fact-checking"])


def require_admin(x_admin_key: str = Header(default="")) -> None:
    if not x_admin_key or x_admin_key != settings().admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.post("/grants/{grant_id}/fact-check", dependencies=[Depends(require_admin)])
async def run_fact_check(grant_id: str):
    db = Database()
    grant = db.get_grant(grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    try:
        result = await fact_check_grant(grant)
        return db.create_fact_check(grant_id, result)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Fact check failed: {str(exc)[:1200]}") from exc


@router.get("/grants/{grant_id}/fact-check", dependencies=[Depends(require_admin)])
def get_latest_fact_check(grant_id: str):
    db = Database()
    if not db.get_grant(grant_id):
        raise HTTPException(status_code=404, detail="Grant not found")
    return db.latest_fact_check(grant_id) or {"status": "not_run", "fields": []}


@router.post("/grants/{grant_id}/fact-check/{fact_check_id}/accept", dependencies=[Depends(require_admin)])
def accept_fact_check(grant_id: str, fact_check_id: str, payload: dict[str, Any] = Body(...)):
    field_names = payload.get("field_names")
    if not isinstance(field_names, list) or not all(isinstance(item, str) for item in field_names):
        raise HTTPException(status_code=422, detail="field_names must be a list of field names")
    try:
        return Database().accept_fact_check_fields(grant_id, fact_check_id, field_names)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
