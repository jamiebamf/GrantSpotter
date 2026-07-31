from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from supabase import create_client

from .config import settings
from .db import Database

router = APIRouter(tags=["customer-portal"])
PORTAL_HTML = Path(__file__).with_name("customer_portal.html")
CONFIRMATION_HTML = Path(__file__).with_name("customer_confirmation.html")
RESET_HTML = Path(__file__).with_name("customer_reset_password.html")
APP_URL = "https://grantspotter-crawler.onrender.com"


class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class EmailPayload(BaseModel):
    email: EmailStr


class ResetPasswordPayload(BaseModel):
    access_token: str = Field(min_length=20)
    refresh_token: str = Field(min_length=20)
    password: str = Field(min_length=8, max_length=200)


def _token_from_header(authorization: str) -> str:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required")
    return token


def current_user_id(authorization: str = Header(default="")) -> str:
    cfg = settings()
    token = _token_from_header(authorization)
    try:
        client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
        result = client.auth.get_user(token)
        user = getattr(result, "user", None)
        if not user or not user.id:
            raise HTTPException(status_code=401, detail="Your session has expired")
        return str(user.id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Your session has expired") from exc


@router.get("/login", include_in_schema=False)
def login_page():
    if not PORTAL_HTML.exists():
        raise HTTPException(status_code=500, detail="Customer portal page is missing")
    return FileResponse(PORTAL_HTML, media_type="text/html")


@router.get("/portal", include_in_schema=False)
def portal_page():
    return login_page()


@router.get("/confirmation-complete", include_in_schema=False)
def confirmation_complete_page():
    if not CONFIRMATION_HTML.exists():
        raise HTTPException(status_code=500, detail="Confirmation page is missing")
    return FileResponse(CONFIRMATION_HTML, media_type="text/html")


@router.get("/reset-password", include_in_schema=False)
def reset_password_page():
    if not RESET_HTML.exists():
        raise HTTPException(status_code=500, detail="Password reset page is missing")
    return FileResponse(RESET_HTML, media_type="text/html")


@router.post("/api/customer/login")
def customer_login(payload: LoginPayload):
    cfg = settings()
    if not cfg.supabase_anon_key:
        raise HTTPException(status_code=503, detail="Customer login is not configured")
    try:
        client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
        result = client.auth.sign_in_with_password({"email": str(payload.email), "password": payload.password})
        session = getattr(result, "session", None)
        user = getattr(result, "user", None)
        if not session or not user:
            raise HTTPException(status_code=401, detail="Email or password is incorrect")
        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "expires_in": session.expires_in,
            "user": {"id": str(user.id), "email": user.email},
        }
    except HTTPException:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "email not confirmed" in message:
            raise HTTPException(status_code=403, detail="Confirm your email before signing in") from exc
        raise HTTPException(status_code=401, detail="Email or password is incorrect") from exc


@router.post("/api/customer/resend-confirmation")
def resend_confirmation(payload: EmailPayload):
    cfg = settings()
    try:
        client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
        client.auth.resend({
            "type": "signup",
            "email": str(payload.email),
            "options": {"email_redirect_to": f"{APP_URL}/confirmation-complete"},
        })
    except Exception as exc:
        if "rate limit" in str(exc).lower():
            raise HTTPException(status_code=429, detail="Please wait before requesting another confirmation email") from exc
    return {"message": "If the account still needs confirmation, a new email has been sent."}


@router.post("/api/customer/password/forgot")
def forgot_password(payload: EmailPayload):
    cfg = settings()
    try:
        client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
        client.auth.reset_password_email(str(payload.email), {"redirect_to": f"{APP_URL}/reset-password"})
    except Exception as exc:
        if "rate limit" in str(exc).lower():
            raise HTTPException(status_code=429, detail="Please wait before requesting another reset email") from exc
    return {"message": "If an account exists for that email, a password reset link has been sent."}


@router.post("/api/customer/password/reset")
def reset_password(payload: ResetPasswordPayload):
    cfg = settings()
    try:
        client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
        client.auth.set_session(payload.access_token, payload.refresh_token)
        client.auth.update_user({"password": payload.password})
        client.auth.sign_out()
        return {"message": "Your password has been updated. You can now sign in."}
    except Exception as exc:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.") from exc


@router.post("/api/customer/refresh")
def refresh_session(payload: dict[str, Any] = Body(...)):
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not refresh_token:
        raise HTTPException(status_code=422, detail="Refresh token is required")
    cfg = settings()
    try:
        client = create_client(cfg.supabase_url, cfg.supabase_anon_key)
        result = client.auth.refresh_session(refresh_token)
        session = getattr(result, "session", None)
        if not session:
            raise HTTPException(status_code=401, detail="Session could not be refreshed")
        return {"access_token": session.access_token, "refresh_token": session.refresh_token, "expires_in": session.expires_in}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Session could not be refreshed") from exc


@router.get("/api/customer/me")
def customer_me(authorization: str = Header(default="")):
    user_id = current_user_id(authorization)
    db = Database()
    profile_result = db.client.table("customer_profiles").select("*").eq("user_id", user_id).limit(1).execute()
    membership_result = db.client.table("customer_organisation_members").select("organisation_id,member_role").eq("user_id", user_id).limit(1).execute()
    profile = profile_result.data[0] if profile_result.data else None
    membership = membership_result.data[0] if membership_result.data else None
    organisation = None
    if membership:
        org_result = db.client.table("customer_organisations").select("*").eq("id", membership["organisation_id"]).limit(1).execute()
        organisation = org_result.data[0] if org_result.data else None
    return {"profile": profile, "membership": membership, "organisation": organisation}


@router.patch("/api/customer/me")
def update_customer(payload: dict[str, Any] = Body(...), authorization: str = Header(default="")):
    user_id = current_user_id(authorization)
    db = Database()
    now = datetime.now(timezone.utc).isoformat()
    profile_allowed = {"first_name", "last_name", "phone", "job_title", "marketing_consent"}
    organisation_allowed = {
        "trading_name", "operating_address", "website", "contact_phone", "description",
        "turnover_band", "employee_band", "geographic_areas", "causes", "beneficiaries",
        "preferred_grant_min", "preferred_grant_max", "match_funding_available", "previous_grant_experience",
    }
    profile_payload = {k: v for k, v in (payload.get("profile") or {}).items() if k in profile_allowed}
    org_payload = {k: v for k, v in (payload.get("organisation") or {}).items() if k in organisation_allowed}
    if profile_payload:
        profile_payload["updated_at"] = now
        db.client.table("customer_profiles").update(profile_payload).eq("user_id", user_id).execute()
    if org_payload:
        membership = db.client.table("customer_organisation_members").select("organisation_id,member_role").eq("user_id", user_id).limit(1).execute().data
        if not membership or membership[0].get("member_role") not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="You cannot update this organisation")
        org_payload["updated_at"] = now
        db.client.table("customer_organisations").update(org_payload).eq("id", membership[0]["organisation_id"]).execute()
    return customer_me(authorization)


def _normalise(values: list[str] | None) -> set[str]:
    return {str(value).strip().lower() for value in (values or []) if str(value).strip()}


def _match_score(grant: dict[str, Any], organisation: dict[str, Any]) -> tuple[int, list[str]]:
    score = 20
    reasons: list[str] = []
    org_regions = _normalise(organisation.get("geographic_areas"))
    grant_regions = _normalise(grant.get("eligible_regions"))
    if not grant_regions or "uk wide" in grant_regions or "united kingdom" in grant_regions:
        score += 15
        reasons.append("Available nationally")
    elif org_regions & grant_regions:
        score += 25
        reasons.append("Matches your operating area")
    org_causes = _normalise(organisation.get("causes"))
    grant_causes = _normalise(grant.get("eligible_causes"))
    cause_matches = org_causes & grant_causes
    if cause_matches:
        score += min(30, 10 + len(cause_matches) * 5)
        reasons.append("Matches your funding interests")
    org_type = str(organisation.get("organisation_type") or "").replace("_", " ").lower()
    grant_types = _normalise(grant.get("eligible_organisation_types"))
    if not grant_types or any(org_type in value or value in org_type for value in grant_types):
        score += 20
        reasons.append("Suitable for your organisation type")
    preferred_min = organisation.get("preferred_grant_min")
    preferred_max = organisation.get("preferred_grant_max")
    grant_min = grant.get("minimum_amount")
    grant_max = grant.get("maximum_amount")
    if preferred_min is not None or preferred_max is not None:
        lower = grant_min if grant_min is not None else grant_max
        upper = grant_max if grant_max is not None else grant_min
        if lower is not None and upper is not None:
            wanted_low = preferred_min if preferred_min is not None else 0
            wanted_high = preferred_max if preferred_max is not None else float("inf")
            if upper >= wanted_low and lower <= wanted_high:
                score += 10
                reasons.append("Funding amount fits your preference")
    if grant.get("verification_status") in {"approved", "published"}:
        score += 5
    return min(score, 100), reasons


@router.get("/api/customer/matches")
def customer_matches(authorization: str = Header(default="")):
    user_id = current_user_id(authorization)
    db = Database()
    membership = db.client.table("customer_organisation_members").select("organisation_id").eq("user_id", user_id).limit(1).execute().data
    if not membership:
        return []
    org_rows = db.client.table("customer_organisations").select("*").eq("id", membership[0]["organisation_id"]).limit(1).execute().data
    if not org_rows:
        return []
    organisation = org_rows[0]
    grants = db.list_grants(limit=500)
    matches = []
    for grant in grants:
        if grant.get("verification_status") not in {"approved", "published", "review"} or grant.get("is_currently_open") is False:
            continue
        score, reasons = _match_score(grant, organisation)
        if score < 40:
            continue
        matches.append({
            "id": grant.get("id"), "grant_title": grant.get("grant_title"), "funder_name": grant.get("funder_name"),
            "summary": grant.get("summary"), "minimum_amount": grant.get("minimum_amount"), "maximum_amount": grant.get("maximum_amount"),
            "deadline": grant.get("deadline"), "deadline_type": grant.get("deadline_type"), "application_url": grant.get("application_url"),
            "match_score": score, "match_reasons": reasons,
        })
    matches.sort(key=lambda item: (-item["match_score"], item.get("deadline") or "9999-12-31"))
    return matches[:100]
