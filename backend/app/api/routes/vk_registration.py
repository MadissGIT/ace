import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.app.utils import vk_registration


router = APIRouter()


class VkRegistrationSessionCreate(BaseModel):
    phone_number: str | None = None


class VkRegistrationSessionPublic(BaseModel):
    registration_token: str
    authorization_url: str
    status: str


class VkRegistrationStatusPublic(BaseModel):
    registration_token: str
    status: str
    verified: bool


@router.post("/session", response_model=VkRegistrationSessionPublic)
async def create_vk_registration_session(
    body: VkRegistrationSessionCreate,
) -> VkRegistrationSessionPublic:
    session = await vk_registration.create_registration_session(body.phone_number)
    return VkRegistrationSessionPublic(
        registration_token=session["registration_token"],
        authorization_url=session["authorization_url"],
        status=session["status"],
    )


@router.get("/status/{registration_token}", response_model=VkRegistrationStatusPublic)
async def get_vk_registration_status(
    registration_token: str,
) -> VkRegistrationStatusPublic:
    session = await vk_registration.get_verified_registration_session(registration_token)
    if not session:
        return VkRegistrationStatusPublic(
            registration_token=registration_token,
            status="expired",
            verified=False,
        )
    return VkRegistrationStatusPublic(
        registration_token=registration_token,
        status=session["status"],
        verified=bool(session.get("verified")),
    )


@router.get("/callback")
async def handle_vk_registration_callback(request: Request) -> RedirectResponse:
    try:
        params = _extract_callback_params(dict(request.query_params))
        verified_session = await vk_registration.complete_registration_callback(
            code=params["code"],
            state=params["state"],
            device_id=params.get("device_id"),
        )
    except HTTPException as exc:
        return RedirectResponse(
            vk_registration.build_frontend_redirect(vk_error=str(exc.detail))
        )

    return RedirectResponse(
        vk_registration.build_frontend_redirect(
            vk_registration_token=verified_session["registration_token"],
            vk_status="verified",
        )
    )


def _extract_callback_params(query_params: dict[str, Any]) -> dict[str, str | None]:
    payload = query_params.get("payload")
    if payload:
        try:
            payload_params = json.loads(payload)
            if isinstance(payload_params, dict):
                query_params = {**query_params, **payload_params}
        except json.JSONDecodeError:
            pass

    code = query_params.get("code")
    state = query_params.get("state")
    device_id = query_params.get("device_id")
    if not code or not state:
        raise HTTPException(status_code=400, detail="VK callback has no code or state")
    return {
        "code": str(code),
        "state": str(state),
        "device_id": str(device_id) if device_id else None,
    }
