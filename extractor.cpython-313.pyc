from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import settings
from .crawler import crawl_govuk
from .db import Database
from .models import ReviewAction
from .publisher import publish_to_website

scheduler = AsyncIOScheduler(timezone="UTC")


def require_admin(x_admin_key: str = Header(default="")) -> None:
    if not x_admin_key or x_admin_key != settings().admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


async def scheduled_crawl() -> None:
    try:
        await crawl_govuk()
    except Exception as exc:
        print(f"Scheduled crawl failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(scheduled_crawl, "cron", hour=settings().schedule_hour_utc, minute=0, id="govuk-daily", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="GrantSpotter Crawler API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.post("/admin/crawl/govuk", dependencies=[Depends(require_admin)])
async def run_govuk_crawl():
    result = await crawl_govuk()
    return result.model_dump(mode="json")


@app.get("/admin/grants", dependencies=[Depends(require_admin)])
def list_grants(status: str | None = Query(default=None), limit: int = Query(default=100, le=500)):
    return Database().list_grants(status=status, limit=limit)


@app.post("/admin/grants/{grant_id}/review", dependencies=[Depends(require_admin)])
async def review_grant(grant_id: str, action: ReviewAction):
    db = Database()
    grant = db.get_grant(grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    if action.action == "reject":
        return db.update_grant(grant_id, {"verification_status": "rejected", "validation_notes": [action.notes]})
    approved = db.update_grant(grant_id, {"verification_status": "approved", "reviewed_at": datetime.now(timezone.utc).isoformat()})
    return approved


@app.post("/admin/grants/{grant_id}/publish", dependencies=[Depends(require_admin)])
async def publish_grant(grant_id: str):
    db = Database()
    grant = db.get_grant(grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    if grant.get("verification_status") not in {"approved", "published"}:
        raise HTTPException(status_code=409, detail="Grant must be approved before publishing")
    website_result = await publish_to_website(grant)
    updated = db.update_grant(grant_id, {
        "verification_status": "published",
        "published_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"grant": updated, "website": website_result}
