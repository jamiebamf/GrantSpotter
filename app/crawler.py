from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from .adapters.govuk import GovUkFindAGrantAdapter
from .config import settings
from .db import Database
from .extractor import deterministic_extract, ai_extract
from .models import CrawlResult
from .utils import content_hash, fingerprint
from .validator import validate_and_score


async def crawl_govuk() -> CrawlResult:
    started = datetime.now(timezone.utc)
    result = CrawlResult(source="GOV.UK Find a Grant", started_at=started)
    db = Database()
    source = db.get_source_by_slug(GovUkFindAGrantAdapter.slug)
    if not source:
        raise RuntimeError("Source seed is missing. Run sql/schema.sql in Supabase first.")

    adapter = GovUkFindAGrantAdapter()
    try:
        urls = await adapter.discover_detail_urls(
            max_pages=max(1, settings().max_pages_per_run // 10 + 1)
        )
        urls = urls[: settings().max_pages_per_run]
        result.discovered = len(urls)

        for url in urls:
            final_url = url
            try:
                status_code, final_url, html = await adapter.fetch(url)
                page_title, clean_text = adapter.clean_page(html, final_url)
                if not clean_text.strip():
                    raise ValueError("No readable grant-page content was extracted")

                digest = content_hash(clean_text)
                previous = db.get_page(final_url)

                page_payload: dict[str, Any] = {
                    "source_id": source["id"],
                    "url": final_url,
                    "page_title": page_title,
                    "raw_html": html,
                    "clean_text": clean_text,
                    "http_status": status_code,
                    "content_hash": digest,
                    "last_checked_at": datetime.now(timezone.utc).isoformat(),
                    "processing_status": "processing",
                    "error_message": None,
                }
                page = db.upsert_page(page_payload)

                if (
                    previous
                    and previous.get("content_hash") == digest
                    and previous.get("processing_status") == "processed"
                ):
                    result.unchanged += 1
                    continue

                baseline = deterministic_extract(page_title, clean_text, final_url)
                extraction_notes: list[str] = []

                # AI is an enhancement, not a single point of failure. If the
                # API key, model, schema, quota or response fails, save the
                # deterministic extraction for manual review instead.
                try:
                    extracted = ai_extract(page_title, clean_text, final_url, baseline)
                except Exception as ai_exc:
                    extracted = baseline
                    extraction_notes.append(
                        f"AI extraction unavailable; deterministic fallback used: {str(ai_exc)[:500]}"
                    )

                score, reasons = validate_and_score(
                    extracted, "find-government-grants.service.gov.uk"
                )
                reasons = extraction_notes + reasons

                fp = fingerprint(
                    extracted.grant_title,
                    extracted.funder_name,
                    extracted.deadline,
                    extracted.maximum_amount,
                    extracted.application_url or extracted.official_source_url,
                )

                verification = (
                    "approved"
                    if score >= settings().auto_publish_min_score and not extraction_notes
                    else "review"
                )
                if extracted.is_currently_open is False:
                    verification = "closed"

                payload = extracted.model_dump(mode="json") | {
                    "source_id": source["id"],
                    "source_page_id": page["id"],
                    "fingerprint": fp,
                    "confidence_score": score,
                    "verification_status": verification,
                    "validation_notes": reasons,
                    "last_verified_at": datetime.now(timezone.utc).isoformat(),
                    "content_hash": digest,
                }
                grant, created = db.upsert_grant(payload)

                db.upsert_page(
                    {
                        "source_id": source["id"],
                        "url": final_url,
                        "processing_status": "processed",
                        "error_message": None,
                        "last_checked_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

                if created:
                    result.created += 1
                else:
                    result.updated += 1

                if verification == "review":
                    result.review_required += 1
                    db.add_review(
                        grant["id"],
                        "; ".join(reasons) or "Manual approval required",
                        extracted.model_dump(mode="json"),
                    )
                result.processed += 1

            except Exception as exc:
                result.failed += 1
                try:
                    db.upsert_page(
                        {
                            "source_id": source["id"],
                            "url": final_url,
                            "http_status": 0,
                            "processing_status": "failed",
                            "error_message": str(exc)[:2000],
                            "last_checked_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                except Exception:
                    pass

        db.touch_source(source["id"], True)
    except Exception as exc:
        db.touch_source(source["id"], False, str(exc))
        raise
    finally:
        await adapter.close()

    result.finished_at = datetime.now(timezone.utc)
    return result
