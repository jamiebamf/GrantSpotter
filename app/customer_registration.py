from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from supabase import create_client

from .config import settings
from .db import Database

router = APIRouter(tags=["customer-registration"])
REGISTER_HTML = Path(__file__).with_name("customer_registration.html")

REGISTERED_TYPES = {"limited_company", "cic", "limited_partnership"}
ALL_TYPES = REGISTERED_TYPES | {
    "registered_charity", "sole_trader", "community_group", "school",
    "local_authority", "other",
}


class RegistrationPayload(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(default="", max_length=40)
    job_title: str = Field(default="", max_length=120)
    password: str = Field(min_length=8, max_length=200)
    organisation_type: str
    company_number: str | None = None
    charity_number: str | None = None
    legal_name: str = Field(min_length=1, max_length=250)
    trading_name: str = Field(default="", max_length=250)
    registered_address: dict[str, Any] = Field(default_factory=dict)
    website: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=3000)
    turnover_band: str = Field(default="", max_length=100)
    employee_band: str = Field(default="", max_length=100)
    geographic_areas: list[str] = Field(default_factory=list)
    causes: list[str] = Field(default_factory=list)
    beneficiaries: list[str] = Field(default_factory=list)
    marketing_consent: bool = False
    terms_accepted: bool
    organisation_confirmed: bool = False
    official_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("organisation_type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in ALL_TYPES:
            raise ValueError("Unsupported organisation type")
        return value

    @field_validator("terms_accepted")
    @classmethod
    def validate_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Terms must be accepted")
        return value


def clean_company_number(value: str) -> str:
    number = re.sub(r"[^A-Za-z0-9]", "", value or "").upper()
    if not 6 <= len(number) <= 8:
        raise HTTPException(status_code=422, detail="Enter a valid Companies House number")
    return number.zfill(8) if number.isdigit() else number


def address_from_company(data: dict[str, Any]) -> dict[str, Any]:
    address = data.get("registered_office_address") or {}
    return {
        "address_line_1": address.get("address_line_1"),
        "address_line_2": address.get("address_line_2"),
        "locality": address.get("locality"),
        "region": address.get("region"),
        "postal_code": address.get("postal_code"),
        "country": address.get("country"),
    }


@router.get("/register", include_in_schema=False)
def registration_page():
    if not REGISTER_HTML.exists():
        raise HTTPException(status_code=500, detail="Registration page is missing")
    return FileResponse(REGISTER_HTML, media_type="text/html")


@router.get("/api/register/company/{company_number}")
async def lookup_company(company_number: str):
    cfg = settings()
    if not cfg.companies_house_api_key:
        raise HTTPException(status_code=503, detail="Companies House lookup is not configured")
    number = clean_company_number(company_number)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"https://api.company-information.service.gov.uk/company/{number}",
            auth=(cfg.companies_house_api_key, ""),
            headers={"Accept": "application/json"},
        )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="No company was found with that number")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Companies House lookup failed")
    data = response.json()
    return {
        "company_number": data.get("company_number", number),
        "legal_name": data.get("company_name"),
        "company_status": data.get("company_status"),
        "company_type": data.get("type"),
        "incorporation_date": data.get("date_of_creation"),
        "sic_codes": data.get("sic_codes") or [],
        "registered_address": address_from_company(data),
        "official_data": data,
    }


def _friendly_database_error(exc: Exception) -> str:
    message = str(exc)
    lower = message.lower()
    if "customer_profiles" in lower or "customer_organisations" in lower or "customer_organisation_members" in lower:
        if "does not exist" in lower or "schema cache" in lower or "could not find" in lower:
            return "Customer database tables are missing. Run supabase/customer_registration.sql in the Supabase SQL Editor."
    if "duplicate key" in lower and "company" in lower:
        return "This organisation is already linked to another GrantSpotter account."
    if "duplicate key" in lower or "unique constraint" in lower:
        return "An account or organisation with these details already exists."
    if "row-level security" in lower or "permission denied" in lower:
        return f"Supabase permissions error: {message[:500]}"
    return f"The account could not be completed: {message[:500]}"


@router.post("/api/register", status_code=201)
def register_customer(payload: RegistrationPayload):
    cfg = settings()
    if not cfg.supabase_url:
        raise HTTPException(status_code=503, detail="SUPABASE_URL is not configured")
    if not cfg.supabase_anon_key:
        raise HTTPException(status_code=503, detail="SUPABASE_ANON_KEY is not configured")
    if not cfg.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="SUPABASE_SERVICE_ROLE_KEY is not configured")

    company_number = None
    verification_source = None
    verification_status = "manual_review"
    if payload.organisation_type in REGISTERED_TYPES:
        if not payload.company_number:
            raise HTTPException(status_code=422, detail="Company number is required")
        company_number = clean_company_number(payload.company_number)
        verification_source = "companies_house"
        verification_status = "customer_confirmed" if payload.organisation_confirmed else "register_found"
    elif payload.organisation_type == "registered_charity":
        verification_source = "charity_commission"

    auth_client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
    created_user_id: str | None = None
    try:
        auth_result = auth_client.auth.sign_up({
            "email": str(payload.email),
            "password": payload.password,
            "options": {
                "email_redirect_to": "https://grantspotter-crawler.onrender.com/confirmation-complete",
                "data": {
                    "first_name": payload.first_name.strip(),
                    "last_name": payload.last_name.strip(),
                },
            },
        })
        user = getattr(auth_result, "user", None)
        if not user or not user.id:
            raise HTTPException(status_code=502, detail="Supabase did not return a customer account")
        created_user_id = str(user.id)
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc)
        if "already" in message.lower() or "registered" in message.lower():
            raise HTTPException(status_code=409, detail="An account already exists for this email") from exc
        raise HTTPException(status_code=502, detail=f"We could not create the account: {message[:350]}") from exc

    now = datetime.now(timezone.utc).isoformat()
    db: Database | None = None
    try:
        db = Database()
        profile = {
            "user_id": created_user_id,
            "first_name": payload.first_name.strip(),
            "last_name": payload.last_name.strip(),
            "phone": payload.phone.strip() or None,
            "job_title": payload.job_title.strip() or None,
            "marketing_consent": payload.marketing_consent,
            "terms_accepted_at": now,
            "onboarding_status": "complete" if payload.organisation_confirmed or payload.organisation_type not in REGISTERED_TYPES else "manual_review",
            "updated_at": now,
        }
        db.client.table("customer_profiles").insert(profile).execute()

        organisation = {
            "owner_user_id": created_user_id,
            "organisation_type": payload.organisation_type,
            "legal_name": payload.legal_name.strip(),
            "trading_name": payload.trading_name.strip() or None,
            "company_number": company_number,
            "charity_number": (payload.charity_number or "").strip() or None,
            "verification_source": verification_source,
            "verification_status": verification_status,
            "verified_at": now if verification_status == "customer_confirmed" else None,
            "official_data": payload.official_data,
            "registered_address": payload.registered_address,
            "website": payload.website.strip() or None,
            "description": payload.description.strip() or None,
            "turnover_band": payload.turnover_band or None,
            "employee_band": payload.employee_band or None,
            "geographic_areas": payload.geographic_areas,
            "causes": payload.causes,
            "beneficiaries": payload.beneficiaries,
            "updated_at": now,
        }
        org_result = db.client.table("customer_organisations").insert(organisation).execute()
        if not org_result.data:
            raise RuntimeError("Supabase did not return the saved organisation")
        organisation_id = org_result.data[0]["id"]
        db.client.table("customer_organisation_members").insert({
            "organisation_id": organisation_id,
            "user_id": created_user_id,
            "member_role": "owner",
        }).execute()
    except Exception as exc:
        if db is not None and created_user_id:
            try:
                db.client.auth.admin.delete_user(created_user_id)
            except Exception:
                pass
        raise HTTPException(status_code=502, detail=_friendly_database_error(exc)) from exc

    return {
        "status": "confirmation_required",
        "message": "Account created. Check your email to confirm your address.",
        "organisation_id": organisation_id,
        "verification_status": verification_status,
    }
