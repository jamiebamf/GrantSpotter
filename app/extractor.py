from __future__ import annotations
import json
import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse
from dateutil import parser as date_parser
from .config import settings
from .models import GrantExtraction

REGIONS = [
    "National", "England", "Scotland", "Wales", "Northern Ireland",
    "North East England", "North West England", "Yorkshire and the Humber",
    "East Midlands", "West Midlands", "East of England", "London",
    "South East England", "South West England",
]
CAUSES = [
    "Youth Services", "Mental Health", "Animal Welfare", "Elderly Support",
    "Poverty Relief", "Education", "Arts & Culture", "Environment",
    "Community Development", "Health", "Sport", "Heritage", "Disability Support",
]


def _money_values(text: str) -> list[float]:
    values = []
    for raw in re.findall(r"£\s?([0-9][0-9,]*(?:\.\d{1,2})?)", text):
        try:
            values.append(float(raw.replace(",", "")))
        except ValueError:
            pass
    return values


def _label_value(text: str, labels: list[str]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        for label in labels:
            if line.lower() == label.lower() and i + 1 < len(lines):
                return lines[i + 1]
            if line.lower().startswith(label.lower() + ":"):
                return line.split(":", 1)[1].strip()
    return ""


def deterministic_extract(title: str, text: str, source_url: str) -> GrantExtraction:
    heading = title.split(" - ")[0].strip() or _label_value(text, ["Grant title", "Title"])
    funder = _label_value(text, ["Funding organisation", "Funder", "Organisation"])
    location = _label_value(text, ["Location", "Locations"])
    who = _label_value(text, ["Who can apply", "Eligibility"])
    closing = _label_value(text, ["Closing date", "Application deadline", "Deadline"])
    opening = _label_value(text, ["Opening date"])
    amount_text = _label_value(text, ["How much you can get", "Funding amount", "Grant amount"])
    amounts = _money_values(amount_text or text[:5000])
    min_amount = min(amounts[:3]) if amounts else None
    max_amount = max(amounts[:3]) if amounts else None
    deadline = None
    opening_date = None
    for value, target in [(closing, "deadline"), (opening, "opening")]:
        if not value:
            continue
        try:
            parsed = date_parser.parse(value, dayfirst=True, fuzzy=True).date()
            if target == "deadline": deadline = parsed
            else: opening_date = parsed
        except (ValueError, OverflowError):
            pass
    lower = text.lower()
    rolling = any(p in lower for p in ["rolling basis", "applications are open year-round", "open all year", "no closing date"])
    regions = [r for r in REGIONS if r.lower() in (location or text[:4000]).lower()]
    causes = [c for c in CAUSES if c.lower().replace("&", "and") in lower.replace("&", "and")]
    application_url = source_url
    summary_lines = [x.strip() for x in text.splitlines() if len(x.strip()) > 80]
    summary = summary_lines[0][:700] if summary_lines else heading
    is_open = None
    if deadline:
        is_open = deadline >= date.today()
    elif rolling:
        is_open = True
    return GrantExtraction(
        grant_title=heading,
        funder_name=funder or "UK Government",
        summary=summary,
        minimum_amount=min_amount,
        maximum_amount=max_amount,
        opening_date=opening_date,
        deadline=deadline,
        deadline_type="rolling" if rolling else ("fixed" if deadline else "unknown"),
        application_url=application_url,
        official_source_url=source_url,
        eligible_regions=regions or ([location] if location else ["National"]),
        eligible_causes=causes,
        eligible_organisation_types=[x.strip() for x in re.split(r",|/", who) if x.strip()],
        is_currently_open=is_open,
    )


def ai_extract(title: str, text: str, source_url: str, baseline: GrantExtraction) -> GrantExtraction:
    cfg = settings()
    if not cfg.openai_api_key:
        return baseline
    from openai import OpenAI
    client = OpenAI(api_key=cfg.openai_api_key)
    prompt = f"""Extract one UK grant opportunity from the official page below.
Use only facts present in the page. Do not invent missing values.
Normalise regions to common UK region names and causes to concise categories.
The application_url should be the official application link when explicitly present; otherwise use the source URL.
Today is {date.today().isoformat()}.

PAGE TITLE: {title}
SOURCE URL: {source_url}

PAGE TEXT:
{text[:30000]}
"""
    response = client.responses.parse(
        model=cfg.openai_model,
        input=[
            {"role": "system", "content": "You are a meticulous UK grant data extraction engine. Return only evidence-grounded structured data."},
            {"role": "user", "content": prompt},
        ],
        text_format=GrantExtraction,
    )
    parsed = response.output_parsed
    return parsed if parsed else baseline
