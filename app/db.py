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
        # Supabase/PostgREST commonly caps a single response at 1,000 rows.
        # The dashboard asks for 500 records, which historically truncated totals.
        # Treat a request of 500 or more as "all" and fetch in safe pages.
        if limit < 500:
            query = self.client.table("grants").select("*").order("created_at", desc=True).limit(limit)
            if status:
                query = query.eq("verification_status", status)
            return query.execute().data or []

        rows: list[dict[str, Any]] = []
        page_size = 1000
        start = 0
        while True:
            query = self.client.table("grants").select("*").order("created_at", desc=True).range(start, start + page_size - 1)
            if status:
                query = query.eq("verification_status", status)
            batch = query.execute().data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size
        return rows

    def get_grant(self, grant_id: str) -> dict[str, Any] | None:
        result = self.client.table("grants").select("*").eq("id", grant_id).limit(1).execute()
        return result.data[0] if result.data else None

    def update_grant(self, grant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.client.table("grants").update(payload).eq("id", grant_id).execute()
        if not result.data:
            raise KeyError("Grant not found")
        return result.data[0]

    def create_fact_check(self, grant_id: str, result: dict[str, Any]) -> dict[str, Any]:
        run = self.client.table("grant_fact_checks").insert({
            "grant_id": grant_id,
            "overall_verdict": result["overall_verdict"],
            "overall_confidence": result["overall_confidence"],
            "summary": result["summary"],
            "source_url": result["source_url"],
            "source_snapshot_hash": result["source_snapshot_hash"],
            "raw_result": result.get("raw_result", {}),
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).execute().data[0]

        rows = []
        for field in result["fields"]:
            rows.append({
                "fact_check_id": run["id"],
                "grant_id": grant_id,
                "field_name": field["field_name"],
                "current_value": field.get("current_value"),
                "suggested_value": field.get("suggested_value"),
                "verdict": field["verdict"],
                "evidence": field.get("evidence", ""),
                "evidence_url": field.get("evidence_url", result["source_url"]),
                "confidence": field["confidence"],
                "accepted": False,
            })
        if rows:
            self.client.table("grant_field_checks").insert(rows).execute()
        return self.get_fact_check(run["id"])

    def get_fact_check(self, fact_check_id: str) -> dict[str, Any]:
        run_result = self.client.table("grant_fact_checks").select("*").eq("id", fact_check_id).limit(1).execute()
        if not run_result.data:
            raise KeyError("Fact check not found")
        run = run_result.data[0]
        fields = self.client.table("grant_field_checks").select("*").eq("fact_check_id", fact_check_id).order("field_name").execute().data or []
        run["fields"] = fields
        return run

    def latest_fact_check(self, grant_id: str) -> dict[str, Any] | None:
        result = self.client.table("grant_fact_checks").select("id").eq("grant_id", grant_id).eq("status", "completed").order("created_at", desc=True).limit(1).execute()
        if not result.data:
            return None
        return self.get_fact_check(result.data[0]["id"])

    def accept_fact_check_fields(self, grant_id: str, fact_check_id: str, field_names: list[str]) -> dict[str, Any]:
        check = self.get_fact_check(fact_check_id)
        if check["grant_id"] != grant_id:
            raise ValueError("Fact check does not belong to this grant")

        allowed = {
            "grant_title", "funder_name", "summary", "minimum_amount", "maximum_amount",
            "opening_date", "deadline", "deadline_type", "application_url", "eligible_regions",
            "eligible_causes", "eligible_organisation_types", "turnover_requirements",
            "charity_registration_required", "match_funding_required", "application_process",
            "is_currently_open",
        }
        selected = [field for field in check["fields"] if field["field_name"] in field_names and field["field_name"] in allowed]
        payload = {field["field_name"]: field.get("suggested_value") for field in selected}
        if payload:
            payload["verification_status"] = "review"
            payload["reviewed_at"] = None
            self.update_grant(grant_id, payload)
        if selected:
            ids = [field["id"] for field in selected]
            self.client.table("grant_field_checks").update({
                "accepted": True,
                "accepted_at": datetime.now(timezone.utc).isoformat(),
            }).in_("id", ids).execute()
        return {
            "grant": self.get_grant(grant_id),
            "fact_check": self.get_fact_check(fact_check_id),
        }
