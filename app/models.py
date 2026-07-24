from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel


class GrantExtraction(BaseModel):
    grant_title: str
    funder_name: str
    summary: str
    minimum_amount: float | None
    maximum_amount: float | None
    opening_date: date | None
    deadline: date | None
    deadline_type: Literal["fixed", "rolling", "unknown"]
    application_url: str
    official_source_url: str
    eligible_regions: list[str]
    eligible_causes: list[str]
    eligible_organisation_types: list[str]
    turnover_requirements: str
    charity_registration_required: bool | None
    match_funding_required: bool | None
    application_process: str
    is_currently_open: bool | None


class CrawlResult(BaseModel):
    source: str
    discovered: int = 0
    processed: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    review_required: int = 0
    failed: int = 0
    started_at: datetime
    finished_at: datetime | None = None


class ReviewAction(BaseModel):
    action: Literal["approve", "reject"]
    notes: str = ""


class GrantStatusUpdate(BaseModel):
    status: Literal["draft", "review", "approved", "published", "closed", "rejected"]
