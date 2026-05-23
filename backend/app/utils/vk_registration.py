import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException

from backend.app.core.config import settings
from backend.app.utils.max_registration import normalize_phone
from backend.app.utils.utils import redis


AUTHORIZATION_URL = "https://id.vk.ru/authorize"
TOKEN_URL = "https://id.vk.ru/oauth2/auth"
USER_INFO_URL = "https://id.vk.ru/oauth2/user_info"
SESSION_PREFIX = "vk_registration:"
VERIFIED_PREFIX = "vk_registration_verified:"
STATUS_PENDING = "pending"
STATUS_VERIFIED = "verified"
STATUS_USED = "used"


def generate_token() -> str:
    return secrets.token_urlsafe(24)


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64).rstrip("=")


def build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


async def create_registration_session(
    phone_number: str | None = None,
    return_path: str | None = None,
) -> dict[str, Any]:
    if not settings.VK_APP_ID:
        raise HTTPException(status_code=500, detail="VK_APP_ID is not configured")
    if not settings.VK_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="VK_REDIRECT_URI is not configured")

    normalized_phone = normalize_phone(phone_number or "") if phone_number else None
    state = generate_token()
    code_verifier = generate_code_verifier()
    code_challenge = build_code_challenge(code_verifier)
    session = {
        "state": state,
        "code_verifier": code_verifier,
        "phone_number": normalized_phone,
        "return_path": sanitize_return_path(return_path),
        "status": STATUS_PENDING,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _save_session(state, session)

    params = {
        "response_type": "code",
        "client_id": settings.VK_APP_ID,
        "redirect_uri": settings.VK_REDIRECT_URI,
        "state": state,
        "scope": settings.VK_SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return {
        "registration_token": state,
        "authorization_url": f"{AUTHORIZATION_URL}?{urlencode(params)}",
        "status": STATUS_PENDING,
    }


async def complete_registration_callback(
    *,
    code: str,
    state: str,
    device_id: str | None,
) -> dict[str, Any]:
    session = await get_registration_session(state)
    if not session:
        raise HTTPException(status_code=400, detail="VK registration session not found")
    if session.get("status") != STATUS_PENDING:
        raise HTTPException(status_code=400, detail="VK registration session is not pending")

    token_data = await exchange_code_for_tokens(
        code=code,
        code_verifier=session["code_verifier"],
        device_id=device_id,
    )
    user_info = await fetch_user_info(token_data["access_token"])
    vk_id = extract_vk_id(token_data, user_info)
    vk_phone = extract_vk_phone(user_info)

    expected_phone = session.get("phone_number")
    if expected_phone and vk_phone and normalize_phone(vk_phone) != expected_phone:
        raise HTTPException(status_code=400, detail="VK phone does not match signup phone")

    verified_token = generate_token()
    verified_session = {
        "registration_token": verified_token,
        "state": state,
        "status": STATUS_VERIFIED,
        "verified": True,
        "vk_id": vk_id,
        "phone_number": expected_phone,
        "vk_phone_number": normalize_phone(vk_phone) if vk_phone else None,
        "return_path": session.get("return_path") or "/registration",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _save_verified_session(verified_token, verified_session)

    session["status"] = STATUS_VERIFIED
    session["verified_token"] = verified_token
    session["vk_id"] = vk_id
    await _save_session(state, session)
    return verified_session


async def exchange_code_for_tokens(
    *,
    code: str,
    code_verifier: str,
    device_id: str | None,
) -> dict[str, Any]:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.VK_APP_ID,
        "redirect_uri": settings.VK_REDIRECT_URI,
        "code_verifier": code_verifier,
    }
    if device_id:
        payload["device_id"] = device_id

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(TOKEN_URL, data=payload)
        if response.status_code >= 400 and settings.VK_CLIENT_SECRET:
            payload_with_secret = {**payload, "client_secret": settings.VK_CLIENT_SECRET}
            response = await client.post(TOKEN_URL, data=payload_with_secret)

    data = _json_or_error(response, "Failed to exchange VK authorization code")
    if not data.get("access_token"):
        raise HTTPException(status_code=400, detail="VK token response has no access_token")
    return data


async def fetch_user_info(access_token: str) -> dict[str, Any]:
    payload = {
        "access_token": access_token,
        "client_id": settings.VK_APP_ID,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(USER_INFO_URL, data=payload)

    return _json_or_error(response, "Failed to fetch VK user info")


async def get_registration_session(token: str) -> dict[str, Any] | None:
    raw = await redis.get(_session_key(token))
    if not raw:
        return None
    return json.loads(raw)


async def require_verified_registration(
    *,
    registration_token: str,
    phone_number: str,
) -> dict[str, Any]:
    session = await get_verified_registration_session(registration_token)
    if not session:
        raise HTTPException(status_code=400, detail="VK registration session not found")
    if session.get("status") != STATUS_VERIFIED or not session.get("verified"):
        raise HTTPException(status_code=400, detail="VK registration is not verified")

    expected_phone = session.get("phone_number")
    if expected_phone and normalize_phone(phone_number) != expected_phone:
        raise HTTPException(
            status_code=400,
            detail="VK registration phone does not match signup phone",
        )
    return session


async def get_verified_registration_session(token: str) -> dict[str, Any] | None:
    raw = await redis.get(_verified_key(token))
    if not raw:
        return None
    return json.loads(raw)


async def mark_registration_used(registration_token: str) -> None:
    session = await get_verified_registration_session(registration_token)
    if not session:
        return
    session["status"] = STATUS_USED
    session["verified"] = False
    await _save_verified_session(registration_token, session)


def extract_vk_id(token_data: dict[str, Any], user_info: dict[str, Any]) -> int:
    candidates = [
        token_data.get("user_id"),
        token_data.get("uid"),
        user_info.get("user_id"),
        user_info.get("id"),
        user_info.get("sub"),
    ]
    user = user_info.get("user")
    if isinstance(user, dict):
        candidates.extend([user.get("user_id"), user.get("id"), user.get("sub")])

    id_token = token_data.get("id_token")
    if id_token:
        try:
            claims = jwt.decode(id_token, options={"verify_signature": False})
            candidates.extend([claims.get("user_id"), claims.get("uid"), claims.get("sub")])
        except jwt.PyJWTError:
            pass

    for candidate in candidates:
        if candidate is None:
            continue
        value = str(candidate)
        if value.isdigit():
            return int(value)

    raise HTTPException(status_code=400, detail="VK profile has no numeric user id")


def extract_vk_phone(user_info: dict[str, Any]) -> str | None:
    user = user_info.get("user")
    if isinstance(user, dict):
        for key in ("phone", "phone_number", "phoneNumber"):
            value = user.get(key)
            if isinstance(value, str) and value:
                return value
    for key in ("phone", "phone_number", "phoneNumber"):
        value = user_info.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def build_frontend_redirect(path: str = "/registration", **params: str) -> str:
    frontend_host = settings.FRONTEND_HOST.rstrip("/")
    separator = "&" if "?" in settings.FRONTEND_HOST else "?"
    safe_path = sanitize_return_path(path)
    return f"{frontend_host}{safe_path}{separator}{urlencode(params)}"


def sanitize_return_path(path: str | None) -> str:
    if not path:
        return "/registration"
    if not path.startswith("/") or path.startswith("//"):
        return "/registration"
    if "://" in path:
        return "/registration"
    return path


def _json_or_error(response: httpx.Response, default_detail: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(status_code=400, detail=default_detail)

    if response.status_code >= 400 or data.get("error"):
        detail = data.get("error_description") or data.get("error") or default_detail
        raise HTTPException(status_code=400, detail=detail)
    return data


async def _save_session(token: str, session: dict[str, Any]) -> None:
    await redis.set(
        _session_key(token),
        json.dumps(session),
        ex=settings.VK_REGISTRATION_TTL_SECONDS,
    )


async def _save_verified_session(token: str, session: dict[str, Any]) -> None:
    await redis.set(
        _verified_key(token),
        json.dumps(session),
        ex=settings.VK_REGISTRATION_TTL_SECONDS,
    )


def _session_key(token: str) -> str:
    return f"{SESSION_PREFIX}{token}"


def _verified_key(token: str) -> str:
    return f"{VERIFIED_PREFIX}{token}"
