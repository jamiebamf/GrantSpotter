from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .adapters.catalogue import CatalogueAdapter, CatalogueSource, SOURCES
from .adapters.govuk import GovUkFindAGrantAdapter
from .config import settings
from .db import Database
from .extractor import ai_extract, deterministic_extract
from .models import CrawlResult
from .utils import content_hash, fingerprint
from .validator import validate_and_score


async def _process_source(
    *,
    source_slug: str,
    source_name: str,
    adapter: Any,
    max_pages: int,
    max_items: int,
) -> CrawlResult:
    started = datetime.now(timezone.utc)
    result = CrawlResult(source=source_name, started_at=started)
    db = Database()
    source = db.get_source_by_slug(source_slug)
    if not source:
        raise RuntimeError(
            f"Source seed '{source_slug}' is missing. Run the latest sql/schema.sql in Supabase."
        )

    try:
        urls = await adapter.discover_detail_urls(max_pages=max_pages)
        urls = urls[:max_items]
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
                try:
                    extracted = ai_extract(page_title, clean_text, final_url, baseline)
                except Exception as ai_exc:
                    extracted = baseline
                    extraction_notes.append(
                        f"AI extraction unavailable; deterministic fallback used: {str(ai_exc)[:500]}"
                    )

                source_domain = urlparse(final_url).netloc.lower()
                score, reasons = validate_and_score(extracted, source_domain)
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


async def crawl_govuk() -> CrawlResult:
    adapter = GovUkFindAGrantAdapter()
    return await _process_source(
        source_slug=GovUkFindAGrantAdapter.slug,
        source_name="GOV.UK Find a Grant",
        adapter=adapter,
        max_pages=max(1, settings().max_pages_per_run // 10 + 1),
        max_items=settings().max_pages_per_run,
    )


async def crawl_catalogue_source(source: CatalogueSource) -> CrawlResult:
    return await _process_source(
        source_slug=source.slug,
        source_name=source.name,
        adapter=CatalogueAdapter(source),
        max_pages=source.max_listing_pages,
        max_items=settings().max_pages_per_run,
    )


async def crawl_all_sources() -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    source_results: list[dict[str, Any]] = []
    source_errors: list[dict[str, str]] = []

    try:
        govuk_result = await crawl_govuk()
        source_results.append(govuk_result.model_dump(mode="json"))
    except Exception as exc:
        source_errors.append({"source": "GOV.UK Find a Grant", "error": str(exc)[:1200]})

    for source in SOURCES:
        try:
            result = await crawl_catalogue_source(source)
            source_results.append(result.model_dump(mode="json"))
        except Exception as exc:
            source_errors.append({"source": source.name, "error": str(exc)[:1200]})

    totals = {
        key: sum(int(item.get(key, 0)) for item in source_results)
        for key in (
            "discovered",
            "processed",
            "created",
            "updated",
            "unchanged",
            "review_required",
            "failed",
        )
    }
    return {
        "source": "All configured grant sources",
        **totals,
        "sources_completed": len(source_results),
        "sources_failed": len(source_errors),
        "source_results": source_results,
        "source_errors": source_errors,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
