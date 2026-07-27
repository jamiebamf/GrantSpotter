from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse

from .config import settings
from .db import Database
from .fact_checker import fact_check_grant

router = APIRouter(prefix="/admin", tags=["fact-checking"])
FACT_CHECK_HTML = Path(__file__).with_name("fact_check_dashboard.html")

bulk_lock = threading.Lock()
bulk_thread: threading.Thread | None = None
bulk_state: dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "source_id": None,
    "requested": 0,
    "completed": 0,
    "succeeded": 0,
    "failed": 0,
    "current_grant": None,
    "errors": [],
}


def require_admin(x_admin_key: str = Header(default="")) -> None:
    if not x_admin_key or x_admin_key != settings().admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.get("/fact-checker", include_in_schema=False)
def fact_check_dashboard():
    if not FACT_CHECK_HTML.exists():
        raise HTTPException(status_code=500, detail="Fact check dashboard file is missing")
    return FileResponse(FACT_CHECK_HTML, media_type="text/html")


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


def _run_bulk_fact_check(grants: list[dict[str, Any]], source_id: str | None) -> None:
    global bulk_thread
    bulk_state.update({
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "source_id": source_id,
        "requested": len(grants),
        "completed": 0,
        "succeeded": 0,
        "failed": 0,
        "current_grant": None,
        "errors": [],
    })
    db = Database()
    try:
        for grant in grants:
            bulk_state["current_grant"] = {
                "id": grant.get("id"),
                "title": grant.get("grant_title"),
            }
            try:
                result = asyncio.run(fact_check_grant(grant))
                db.create_fact_check(grant["id"], result)
                bulk_state["succeeded"] += 1
            except Exception as exc:
                bulk_state["failed"] += 1
                errors = bulk_state["errors"]
                if len(errors) < 20:
                    errors.append({
                        "grant_id": grant.get("id"),
                        "title": grant.get("grant_title"),
                        "error": str(exc)[:500],
                    })
            finally:
                bulk_state["completed"] += 1
        bulk_state["status"] = "completed"
    except Exception as exc:
        bulk_state["status"] = "failed"
        bulk_state["errors"].append({"error": str(exc)[:1000]})
    finally:
        bulk_state["current_grant"] = None
        bulk_state["finished_at"] = datetime.now(timezone.utc).isoformat()
        with bulk_lock:
            bulk_thread = None


@router.post("/fact-check/bulk", dependencies=[Depends(require_admin)], status_code=202)
def start_bulk_fact_check(
    source_id: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=25),
):
    global bulk_thread
    with bulk_lock:
        if bulk_thread and bulk_thread.is_alive():
            return {"status": "already_running", **bulk_state}

        grants = Database().list_grants(status="review", limit=500)
        if source_id:
            grants = [grant for grant in grants if grant.get("source_id") == source_id]
        grants = grants[:limit]
        if not grants:
            return {"status": "nothing_to_check", "requested": 0}

        bulk_thread = threading.Thread(
            target=_run_bulk_fact_check,
            args=(grants, source_id),
            name="grantspotter-bulk-fact-check",
            daemon=True,
        )
        bulk_thread.start()
        return {"status": "started", "requested": len(grants), "source_id": source_id}


@router.get("/fact-check/bulk/status", dependencies=[Depends(require_admin)])
def bulk_fact_check_status():
    return bulk_state
