from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, Literal

import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
from pydantic import BaseModel, Field
from trafilatura import extract

from .config import settings


CHECKABLE_FIELDS = (
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
)


class FieldFactCheck(BaseModel):
    field_name: Literal[
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
    ]
    verdict: Literal["confirmed", "incorrect", "missing", "uncertain"]
    suggested_value_json: str
    evidence: str
    confidence: int = Field(ge=0, le=100)


class FactCheckExtraction(BaseModel):
    overall_verdict: Literal["verified", "needs_changes", "insufficient_evidence"]
    overall_confidence: int = Field(ge=0, le=100)
    summary: str
    fields: list[FieldFactCheck]


def _clean_page(html: str, url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in ["nav", "footer", "script", "style", "noscript", ".govuk-cookie-banner"]:
        for node in soup.select(selector):
            node.decompose()
    text = extract(str(soup), url=url, include_links=True, include_tables=True, output_format="txt")
    if not text:
        main = soup.select_one("main") or soup.body or soup
        text = main.get_text("\n", strip=True)
    return text.strip()


def _normalise_suggestion(field_name: str, raw: str) -> Any:
    if raw == "":
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw

    if field_name in {"minimum_amount", "maximum_amount"}:
        if value in (None, ""):
            return None
        return float(value)
    if field_name in {"charity_registration_required", "match_funding_required", "is_currently_open"}:
        return value if isinstance(value, bool) or value is None else None
    if field_name in {"eligible_regions", "eligible_causes", "eligible_organisation_types"}:
        return value if isinstance(value, list) else []
    if field_name in {"opening_date", "deadline"}:
        return value or None
    return value


async def fact_check_grant(grant: dict[str, Any]) -> dict[str, Any]:
    cfg = settings()
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    source_url = grant.get("official_source_url") or grant.get("application_url")
    if not source_url:
        raise RuntimeError("Grant has no official source URL")

    async with httpx.AsyncClient(
        timeout=40,
        follow_redirects=True,
        headers={"User-Agent": cfg.crawler_user_agent, "Accept-Language": "en-GB,en;q=0.9"},
    ) as client:
        response = await client.get(source_url)
        response.raise_for_status()
        final_url = str(response.url)
        source_text = _clean_page(response.text, final_url)

    if len(source_text) < 100:
        raise RuntimeError("The official source page did not contain enough readable text")

    record = {field: grant.get(field) for field in CHECKABLE_FIELDS}
    prompt = f"""Independently fact-check this UK grant record against the newly fetched official source page.

Rules:
- Use only evidence from the supplied official page.
- Check every listed field exactly once.
- A field is confirmed only when the page directly supports the current value.
- Mark incorrect when the page supports a different value.
- Mark missing when the current record is blank but the page supplies a value.
- Mark uncertain when the page does not provide enough evidence.
- suggested_value_json must be valid JSON encoded as a string. Examples: \"50000\", \"null\", \"[\\\"England\\\"]\", \"true\", or \"\\\"Forestry Commission\\\"\".
- For confirmed fields, repeat the confirmed current value in suggested_value_json.
- Evidence must be a short, exact supporting excerpt or a concise description of where the evidence appears. Never invent evidence.
- Convert £1.5 million to 1500000 and £250k to 250000.
- Dates must use YYYY-MM-DD. Do not invent a year.
- The overall verdict is verified only when all critical fields are confirmed and there are no contradictions.
- Critical fields are grant_title, funder_name, funding amounts, deadline/deadline_type, application_url, eligible_regions, and is_currently_open.
- Today is {date.today().isoformat()}.

CURRENT RECORD:
{json.dumps(record, ensure_ascii=False, default=str)}

OFFICIAL SOURCE URL:
{final_url}

OFFICIAL PAGE TEXT:
{source_text[:40000]}
"""

    client = OpenAI(api_key=cfg.openai_api_key)
    result = client.responses.parse(
        model=cfg.openai_model,
        input=[
            {
                "role": "system",
                "content": "You are an evidence-first UK grant auditor. Be conservative and never infer unsupported facts.",
            },
            {"role": "user", "content": prompt},
        ],
        text_format=FactCheckExtraction,
    ).output_parsed

    if result is None:
        raise RuntimeError("Fact checker returned no structured result")

    seen = {item.field_name for item in result.fields}
    missing_fields = [field for field in CHECKABLE_FIELDS if field not in seen]
    if missing_fields:
        raise RuntimeError("Fact checker omitted fields: " + ", ".join(missing_fields))

    fields = []
    for item in result.fields:
        fields.append(
            {
                "field_name": item.field_name,
                "current_value": record.get(item.field_name),
                "suggested_value": _normalise_suggestion(item.field_name, item.suggested_value_json),
                "verdict": item.verdict,
                "evidence": item.evidence,
                "evidence_url": final_url,
                "confidence": item.confidence,
            }
        )

    return {
        "overall_verdict": result.overall_verdict,
        "overall_confidence": result.overall_confidence,
        "summary": result.summary,
        "source_url": final_url,
        "source_snapshot_hash": hashlib.sha256(source_text.encode("utf-8", errors="ignore")).hexdigest(),
        "fields": fields,
        "raw_result": result.model_dump(mode="json"),
    }
