from __future__ import annotations
import httpx
from .config import settings


async def publish_to_website(grant: dict) -> dict:
    cfg = settings()
    if not cfg.website_import_url or not cfg.website_import_secret:
        raise RuntimeError("WEBSITE_IMPORT_URL and WEBSITE_IMPORT_SECRET are not configured")
    payload = {
        "title": grant["grant_title"],
        "funder": grant["funder_name"],
        "amount": grant.get("maximum_amount") or grant.get("minimum_amount") or 0,
        "regions": grant.get("eligible_regions") or ["National"],
        "causes": grant.get("eligible_causes") or ["Community Development"],
        "deadline": grant.get("deadline"),
        "deadline_type": grant.get("deadline_type", "unknown"),
        "url": grant.get("application_url") or grant.get("official_source_url"),
        "source_url": grant.get("official_source_url"),
        "status": "Active",
        "summary": grant.get("summary", ""),
        "external_id": grant["id"],
        "verified_at": grant.get("last_verified_at"),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            cfg.website_import_url,
            json=payload,
            headers={"X-GrantSpotter-Secret": cfg.website_import_secret},
        )
        response.raise_for_status()
        return response.json()
