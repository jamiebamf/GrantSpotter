from __future__ import annotations
import asyncio
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import settings
from .crawler import crawl_govuk
from .db import Database
from .fact_check_routes import router as fact_check_router
from .models import ReviewAction
from .publisher import publish_to_website

scheduler = AsyncIOScheduler(timezone="UTC")
crawl_thread: threading.Thread | None = None
crawl_lock = threading.Lock()
crawl_state: dict = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "result": None,
    "error": None,
}

ADMIN_HTML = Path(__file__).with_name("admin_dashboard.html")
EDITABLE_GRANT_FIELDS = {
    "grant_title",
    "funder_name",
    "summary",
    "minimum_amount",
    "maximum_amount",
    "opening_date",
    "deadline",
    "deadline_type",
    "application_url",
    "eligible_regions",
    "eligible_causes",
    "eligible_organisation_types",
    "turnover_requirements",
    "charity_registration_required",
    "match_funding_required",
    "application_process",
    "is_currently_open",
}


def require_admin(x_admin_key: str = Header(default="")) -> None:
    if not x_admin_key or x_admin_key != settings().admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


def execute_crawl_in_thread() -> None:
    global crawl_thread
    crawl_state.update({
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "result": None,
        "error": None,
    })
    try:
        result = asyncio.run(crawl_govuk())
        crawl_state.update({
            "status": "completed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "result": result.model_dump(mode="json"),
            "error": None,
        })
    except Exception as exc:
        crawl_state.update({
            "status": "failed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": str(exc)[:2000],
        })
        print(f"Crawl failed: {exc}")
    finally:
        with crawl_lock:
            crawl_thread = None


def start_crawl_thread() -> dict:
    global crawl_thread
    with crawl_lock:
        if crawl_thread and crawl_thread.is_alive():
            return {
                "status": "already_running",
                "started_at": crawl_state["started_at"],
            }

        started_at = datetime.now(timezone.utc).isoformat()
        crawl_state.update({
            "status": "starting",
            "started_at": started_at,
            "finished_at": None,
            "result": None,
            "error": None,
        })
        crawl_thread = threading.Thread(
            target=execute_crawl_in_thread,
            name="grantspotter-crawl",
            daemon=True,
        )
        crawl_thread.start()
        return {"status": "started", "started_at": started_at}


async def scheduled_crawl() -> None:
    result = start_crawl_thread()
    if result["status"] == "already_running":
        print("Scheduled crawl skipped because another crawl is already running")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        scheduled_crawl,
        "cron",
        hour=settings().schedule_hour_utc,
        minute=0,
        id="govuk-daily",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="GrantSpotter Crawler API", version="1.4.0", lifespan=lifespan)
app.include_router(fact_check_router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/admin/dashboard")


@app.get("/admin/dashboard", include_in_schema=False)
def admin_dashboard():
    if not ADMIN_HTML.exists():
        raise HTTPException(status_code=500, detail="Admin dashboard file is missing")
    return FileResponse(ADMIN_HTML, media_type="text/html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
        "crawl_status": crawl_state["status"],
    }


@app.post("/admin/crawl/govuk", dependencies=[Depends(require_admin)], status_code=202)
def run_govuk_crawl():
    return start_crawl_thread()


@app.get("/admin/crawl/status", dependencies=[Depends(require_admin)])
def get_crawl_status():
    return crawl_state


@app.get("/admin/grants", dependencies=[Depends(require_admin)])
def list_grants(status: str | None = Query(default=None), limit: int = Query(default=100, le=500)):
    return Database().list_grants(status=status, limit=limit)


@app.patch("/admin/grants/{grant_id}", dependencies=[Depends(require_admin)])
def edit_grant(grant_id: str, payload: dict[str, Any] = Body(...)):
    db = Database()
    grant = db.get_grant(grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")

    unknown = set(payload) - EDITABLE_GRANT_FIELDS
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported fields: {', '.join(sorted(unknown))}",
        )

    clean_payload = {key: value for key, value in payload.items() if key in EDITABLE_GRANT_FIELDS}
    if not clean_payload:
        raise HTTPException(status_code=422, detail="No editable fields supplied")

    if not clean_payload.get("grant_title", grant.get("grant_title")):
        raise HTTPException(status_code=422, detail="Grant title cannot be empty")
    if not clean_payload.get("funder_name", grant.get("funder_name")):
        raise HTTPException(status_code=422, detail="Funder name cannot be empty")

    clean_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    return db.update_grant(grant_id, clean_payload)


@app.post("/admin/grants/{grant_id}/review", dependencies=[Depends(require_admin)])
def review_grant(grant_id: str, action: ReviewAction):
    db = Database()
    grant = db.get_grant(grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    if action.action == "reject":
        return db.update_grant(
            grant_id,
            {
                "verification_status": "rejected",
                "validation_notes": [action.notes] if action.notes else ["Rejected in admin dashboard"],
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    return db.update_grant(
        grant_id,
        {
            "verification_status": "approved",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.post("/admin/grants/{grant_id}/publish", dependencies=[Depends(require_admin)])
async def publish_grant(grant_id: str):
    db = Database()
    grant = db.get_grant(grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    if grant.get("verification_status") not in {"approved", "published"}:
        raise HTTPException(status_code=409, detail="Grant must be approved before publishing")
    website_result = await publish_to_website(grant)
    updated = db.update_grant(
        grant_id,
        {
            "verification_status": "published",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"grant": updated, "website": website_result}
