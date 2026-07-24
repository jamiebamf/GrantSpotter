from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, model_validator


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

    @model_validator(mode="after")
    def apply_sanity_checks(self):
        today = date.today()
        latest_reasonable_year = today.year + 10

        # Reject obviously malformed AI dates such as 3103-03-31. Grant pages
        # that omit a year should remain unknown rather than inventing one.
        if self.opening_date and not (2000 <= self.opening_date.year <= latest_reasonable_year):
            self.opening_date = None
        if self.deadline and not (2000 <= self.deadline.year <= latest_reasonable_year):
            self.deadline = None
            if self.deadline_type == "fixed":
                self.deadline_type = "unknown"
            self.is_currently_open = None

        # Basic amount guards. These do not prove an amount is correct, but they
        # prevent negative and implausibly large parsing artefacts being stored.
        if self.minimum_amount is not None and not (0 <= self.minimum_amount <= 10_000_000_000):
            self.minimum_amount = None
        if self.maximum_amount is not None and not (0 <= self.maximum_amount <= 10_000_000_000):
            self.maximum_amount = None
        if (
            self.minimum_amount is not None
            and self.maximum_amount is not None
            and self.minimum_amount > self.maximum_amount
        ):
            self.minimum_amount, self.maximum_amount = self.maximum_amount, self.minimum_amount

        if self.deadline_type == "fixed" and self.deadline is None:
            self.deadline_type = "unknown"
        return self


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
