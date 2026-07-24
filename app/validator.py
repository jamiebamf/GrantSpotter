from __future__ import annotations
from datetime import date
from urllib.parse import urlparse
from .models import GrantExtraction


def validate_and_score(grant: GrantExtraction, source_domain: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if grant.grant_title and len(grant.grant_title) >= 5: score += 15
    else: reasons.append("Missing or weak grant title")
    if grant.funder_name and grant.funder_name != "UK Government": score += 12
    else: reasons.append("Funder needs confirmation")
    if grant.summary and len(grant.summary) >= 50: score += 8
    else: reasons.append("Summary is too short")
    if grant.maximum_amount is not None: score += 10
    else: reasons.append("Funding amount was not found")
    if grant.deadline_type == "rolling": score += 15
    elif grant.deadline:
        score += 15
        if grant.deadline < date.today():
            score -= 40
            reasons.append("Deadline has passed")
    else:
        reasons.append("Deadline is unknown")
    if grant.eligible_regions: score += 10
    else: reasons.append("No eligible region found")
    if grant.eligible_organisation_types: score += 8
    else: reasons.append("Applicant types are unclear")
    if grant.eligible_causes: score += 7
    else: reasons.append("Cause categories need review")
    app_domain = urlparse(grant.application_url).netloc.lower()
    if app_domain: score += 8
    else: reasons.append("Application URL is missing")
    source_host = urlparse(grant.official_source_url).netloc.lower()
    if source_domain in source_host: score += 7
    if grant.minimum_amount is not None and grant.maximum_amount is not None and grant.minimum_amount > grant.maximum_amount:
        score -= 25
        reasons.append("Minimum amount exceeds maximum amount")
    if grant.is_currently_open is False:
        score -= 30
        reasons.append("Grant appears closed")
    return max(0, min(100, score)), reasons
