from __future__ import annotations
import html as html_lib
import re
from datetime import date
from dateutil import parser as date_parser
from .config import settings
from .models import GrantExtraction

REGIONS = [
    "National", "England", "Scotland", "Wales", "Northern Ireland",
    "North East England", "North West England", "Yorkshire and the Humber",
    "East Midlands", "West Midlands", "East of England", "London",
    "South East England", "South West England",
]

CAUSE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Youth Services": ("young people", "youth", "children and young people", "child-focused"),
    "Mental Health": ("mental health", "wellbeing", "well-being"),
    "Animal Welfare": ("animal welfare", "animal health", "livestock welfare", "biosecurity"),
    "Elderly Support": ("older people", "elderly", "ageing", "aging"),
    "Poverty Relief": ("poverty", "deprivation", "cost of living", "financial hardship"),
    "Education": ("education", "schools", "nursery", "teacher", "learning", "skills", "training"),
    "Arts & Culture": ("arts", "culture", "music", "film", "creative industries", "screen fund"),
    "Environment": ("environment", "climate", "nature", "biodiversity", "forestry", "woodland", "water environment", "net zero", "heat pump"),
    "Community Development": ("community development", "community group", "community organisation", "community organization", "local community", "community hub"),
    "Health": ("health", "healthcare", "medical", "life sciences", "public health"),
    "Sport": ("sport", "sports", "physical activity"),
    "Heritage": ("heritage", "historic", "places of worship", "listed building"),
    "Disability Support": ("disability", "disabled", "wheelchair", "accessibility"),
}


def _clean_text(value: str) -> str:
    value = html_lib.unescape(value or "")
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.DOTALL)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -|\t\r\n")


def _money_values(text: str) -> list[float]:
    """Extract GBP amounts and understand thousand/million suffixes.

    Only values explicitly prefixed by £ are accepted, which avoids mistaking
    percentages, round numbers, years and numbered programme phases for awards.
    """
    values: list[float] = []
    pattern = re.compile(
        r"£\s*([0-9]+(?:,[0-9]{3})*(?:\.\d+)?)\s*(million|m|thousand|k)?\b",
        flags=re.IGNORECASE,
    )
    for number, suffix in pattern.findall(text or ""):
        try:
            value = float(number.replace(",", ""))
        except ValueError:
            continue
        suffix = suffix.lower()
        if suffix in {"million", "m"}:
            value *= 1_000_000
        elif suffix in {"thousand", "k"}:
            value *= 1_000
        values.append(value)
    return values


def _lines(text: str) -> list[str]:
    return [_clean_text(line) for line in (text or "").splitlines() if _clean_text(line)]


def _label_value(text: str, labels: list[str], max_following_lines: int = 2) -> str:
    lines = _lines(text)
    normalised_labels = [label.casefold().rstrip(":") for label in labels]
    for i, line in enumerate(lines):
        current = line.casefold().rstrip(":")
        for label in normalised_labels:
            if current == label:
                following = lines[i + 1:i + 1 + max_following_lines]
                return _clean_text(" ".join(following))
            if current.startswith(label + ":"):
                return _clean_text(line.split(":", 1)[1])
    return ""


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    cleaned = re.sub(
        r"\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:GMT|BST|UTC|UK time)?\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bUK\b", "", cleaned, flags=re.IGNORECASE)
    try:
        return date_parser.parse(cleaned, dayfirst=True, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def _extract_regions(location: str, text: str) -> list[str]:
    haystack = f"{location}\n{text[:6000]}".casefold()
    matches = [region for region in REGIONS if region.casefold() in haystack]
    # Avoid returning National merely because the word appears in an unrelated
    # organisation title when a specific nation/region is present.
    specific = [region for region in matches if region != "National"]
    return specific or (["National"] if "national" in haystack else [])


def _extract_causes(text: str) -> list[str]:
    lower = (text or "").casefold()
    found: list[str] = []
    for cause, keywords in CAUSE_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(keyword.casefold())}\b", lower) for keyword in keywords):
            found.append(cause)
    return found


def _extract_funder(text: str) -> str:
    funder = _label_value(
        text,
        [
            "Funding organisation",
            "Funding organization",
            "Funded by",
            "Funder",
            "Awarding organisation",
            "Awarding organization",
            "Department",
        ],
        max_following_lines=1,
    )
    return _clean_text(funder)


def deterministic_extract(title: str, text: str, source_url: str) -> GrantExtraction:
    heading = _clean_text(title.split(" - ")[0]) or _label_value(text, ["Grant title", "Title"], 1)
    funder = _extract_funder(text)
    location = _label_value(text, ["Location", "Locations", "Where the grant is available"], 2)
    who = _label_value(text, ["Who can apply", "Eligibility", "Eligible applicants", "Who is eligible"], 3)
    closing = _label_value(
        text,
        ["Closing date", "Application deadline", "Deadline", "Applications close", "Closing time"],
        2,
    )
    opening = _label_value(text, ["Opening date", "Applications open", "Opening time"], 2)
    amount_text = _label_value(
        text,
        ["How much you can get", "Funding amount", "Grant amount", "Award amount", "How much is available"],
        4,
    )

    amounts = _money_values(amount_text)
    if not amounts:
        # Search only the first relevant section, not the whole page, to reduce
        # false matches from examples and unrelated costs.
        amounts = _money_values(text[:8000])
    min_amount = min(amounts) if amounts else None
    max_amount = max(amounts) if amounts else None

    deadline = _parse_date(closing)
    opening_date = _parse_date(opening)
    lower = (text or "").casefold()
    rolling = any(
        phrase in lower
        for phrase in (
            "rolling basis",
            "applications are open year-round",
            "applications are open all year",
            "open all year",
            "no closing date",
            "apply at any time",
        )
    )

    regions = _extract_regions(location, text)
    causes = _extract_causes(f"{heading}\n{text[:12000]}")
    organisation_types = [
        _clean_text(item)
        for item in re.split(r"[,;/]|\band\b", who, flags=re.IGNORECASE)
        if _clean_text(item)
    ]

    summary_candidates = [
        line for line in _lines(text)
        if len(line) >= 80
        and not line.casefold().startswith(("cookies", "we use", "find a grant"))
    ]
    summary = summary_candidates[0][:700] if summary_candidates else heading

    is_open: bool | None = None
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
        application_url=source_url,
        official_source_url=source_url,
        eligible_regions=regions or ([location] if location else ["National"]),
        eligible_causes=causes,
        eligible_organisation_types=organisation_types,
        turnover_requirements="",
        charity_registration_required=None,
        match_funding_required=None,
        application_process="",
        is_currently_open=is_open,
    )


def ai_extract(title: str, text: str, source_url: str, baseline: GrantExtraction) -> GrantExtraction:
    cfg = settings()
    if not cfg.openai_api_key:
        return baseline

    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai_api_key)
    prompt = f"""Extract one current UK grant opportunity from the official page below.
Use only facts present in the page and return null or an empty value when the page does not state something.
Important rules:
- Convert amounts such as £1.5 million to 1500000 and £250k to 250000.
- Do not confuse percentages, years, round numbers, programme phases or match-funding ratios with grant amounts.
- Identify the actual awarding organisation, not simply 'UK Government', whenever the page names a department, council, agency or funder.
- Extract the fixed closing date even when it includes a time, BST, GMT, UTC or 'UK time'.
- Keep cause categories relevant to the programme's purpose; do not infer unrelated causes from generic words.
- Remove HTML comments, markup and navigation text from titles and summaries.
- The application_url should be the official application link when explicitly present; otherwise use the source URL.
Today is {date.today().isoformat()}.

BASELINE EXTRACTION:
{baseline.model_dump_json()}

PAGE TITLE: {_clean_text(title)}
SOURCE URL: {source_url}

PAGE TEXT:
{text[:30000]}
"""
    response = client.responses.parse(
        model=cfg.openai_model,
        input=[
            {
                "role": "system",
                "content": "You are a meticulous UK grant data extraction engine. Return only source-grounded structured data.",
            },
            {"role": "user", "content": prompt},
        ],
        text_format=GrantExtraction,
    )
    parsed = response.output_parsed
    return parsed if parsed else baseline
