from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from supabase import Client, create_client
from .config import settings


class Database:
    def __init__(self) -> None:
        cfg = settings()
        if not cfg.supabase_url or not cfg.supabase_service_role_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured")
        self.client: Client = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def get_source_by_slug(self, slug: str) -> dict[str, Any] | None:
        result = self.client.table("grant_sources").select("*").eq("slug", slug).limit(1).execute()
        return result.data[0] if result.data else None

    def touch_source(self, source_id: str, success: bool, error: str = "") -> None:
        payload = {
            "last_crawled_at": datetime.now(timezone.utc).isoformat(),
            "last_crawl_success": success,
            "last_error": error[:2000] if error else None,
        }
        self.client.table("grant_sources").update(payload).eq("id", source_id).execute()

    def get_page(self, url: str) -> dict[str, Any] | None:
        result = self.client.table("crawl_pages").select("*").eq("url", url).limit(1).execute()
        return result.data[0] if result.data else None

    def upsert_page(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.client.table("crawl_pages").upsert(payload, on_conflict="url").execute()
        return result.data[0]

    def find_grant_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        result = self.client.table("grants").select("*").eq("fingerprint", fingerprint).limit(1).execute()
        return result.data[0] if result.data else None

    def upsert_grant(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        existing = self.find_grant_by_fingerprint(payload["fingerprint"])
        if existing:
            result = self.client.table("grants").update(payload).eq("id", existing["id"]).execute()
            return result.data[0], False
        result = self.client.table("grants").insert(payload).execute()
        return result.data[0], True

    def add_review(self, grant_id: str, reason: str, extraction: dict[str, Any]) -> None:
        existing = self.client.table("grant_reviews").select("id").eq("grant_id", grant_id).eq("review_status", "pending").limit(1).execute()
        if existing.data:
            return
        self.client.table("grant_reviews").insert({
            "grant_id": grant_id,
            "reason": reason,
            "original_extraction": extraction,
            "review_status": "pending",
        }).execute()

    def list_grants(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = self.client.table("grants").select("*").order("created_at", desc=True).limit(limit)
        if status:
            query = query.eq("verification_status", status)
        return query.execute().data or []

    def get_grant(self, grant_id: str) -> dict[str, Any] | None:
        result = self.client.table("grants").select("*").eq("id", grant_id).limit(1).execute()
        return result.data[0] if result.data else None

    def update_grant(self, grant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.client.table("grants").update(payload).eq("id", grant_id).execute()
        if not result.data:
            raise KeyError("Grant not found")
        return result.data[0]
