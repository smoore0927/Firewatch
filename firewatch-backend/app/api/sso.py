"""
OIDC SSO routes — config, login redirect, and IdP callback.

State is held entirely in a signed, short-lived HTTP-only cookie scoped to the
callback path; no Starlette SessionMiddleware is required.
"""

from __future__ import annotations

import logging
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_db
from app.core.limiter import limiter
from app.core.oidc import (
    OIDC_FLOW_COOKIE,
    OIDC_FLOW_COOKIE_PATH,
    OIDC_FLOW_TTL_SECONDS,
    build_authorization_url,
    exchange_code_for_tokens,
    generate_flow_secrets,
    get_discovery_document,
    read_flow_cookie,
    sign_flow_cookie,
    verify_id_token,
)
from app.core.security import set_auth_cookies
from app.services.sso_service import (
    SSOAccountDisabledError,
    SSOEmailNotVerifiedError,
    SSOMissingSubError,
    SSONoEmailError,
    provision_sso_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sso", tags=["SSO"])


def _login_error_redirect(error: str) -> RedirectResponse:
    return RedirectResponse(
        f"{settings.FRONTEND_URL}/login?sso_error={quote(error, safe='')}",
        status_code=302,
    )


@router.get("/config")
def sso_config() -> dict:
    """Public — frontend uses this to decide whether to render the SSO button."""
    if not settings.oidc_is_configured:
        return {"enabled": False, "provider_name": None}
    return {"enabled": True, "provider_name": settings.OIDC_PROVIDER_NAME}


@router.get("/login")
@limiter.limit("10/minute")
async def sso_login(request: Request) -> RedirectResponse:
    """Kick off the OIDC authorization-code+PKCE flow."""
    if not settings.oidc_is_configured:
        return _login_error_redirect("not_configured")

    try:
        discovery = await get_discovery_document()
    except Exception:
        logger.exception("OIDC discovery fetch failed")
        return _login_error_redirect("discovery_failed")

    auth_endpoint = discovery.get("authorization_endpoint")
    if not auth_endpoint:
        return _login_error_redirect("discovery_invalid")

    secrets_bundle = generate_flow_secrets()
    auth_url = build_authorization_url(auth_endpoint, secrets_bundle)

    response = RedirectResponse(auth_url, status_code=302)
    response.set_cookie(
        key=OIDC_FLOW_COOKIE,
        value=sign_flow_cookie(
            {
                "state": secrets_bundle["state"],
                "nonce": secrets_bundle["nonce"],
                "code_verifier": secrets_bundle["code_verifier"],
            }
        ),
        max_age=OIDC_FLOW_TTL_SECONDS,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        path=OIDC_FLOW_COOKIE_PATH,
    )
    return response


@router.get("/callback")
@limiter.limit("10/minute")
async def sso_callback(
    request: Request,
    *,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,  # noqa: ARG001  # NOSONAR -- accepted by FastAPI, surfaced via `error`
    oidc_flow: Annotated[str | None, Cookie()] = None,
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    """Exchange the authorization code for tokens, validate the id_token, sign the user in."""
    if error:
        return _login_error_redirect("provider_error")

    if not settings.oidc_is_configured:
        return _login_error_redirect("not_configured")

    if not oidc_flow:
        return _login_error_redirect("invalid_state")

    flow = read_flow_cookie(oidc_flow)
    if not flow:
        return _login_error_redirect("invalid_state")

    if not state or state != flow.get("state"):
        return _login_error_redirect("state_mismatch")

    if not code:
        return _login_error_redirect("missing_code")

    try:
        discovery = await get_discovery_document()
        token_response = await exchange_code_for_tokens(
            discovery["token_endpoint"], code, flow["code_verifier"]
        )
    except Exception:
        logger.exception("OIDC token exchange failed")
        return _login_error_redirect("token_exchange_failed")

    id_token = token_response.get("id_token")
    if not id_token:
        return _login_error_redirect("no_id_token")

    try:
        claims = await verify_id_token(
            id_token,
            issuer=discovery["issuer"],
            jwks_uri=discovery["jwks_uri"],
            expected_nonce=flow["nonce"],
            access_token=token_response.get("access_token"),
        )
    except Exception:
        logger.exception("OIDC id_token validation failed")
        return _login_error_redirect("invalid_id_token")

    try:
        user = provision_sso_user(db, claims)
    except SSOMissingSubError:
        return _login_error_redirect("invalid_id_token")
    except SSONoEmailError:
        return _login_error_redirect("no_email")
    except SSOEmailNotVerifiedError:
        return _login_error_redirect("email_not_verified")
    except SSOAccountDisabledError:
        return _login_error_redirect("account_disabled")

    response = RedirectResponse(f"{settings.FRONTEND_URL}/dashboard", status_code=302)
    # Drop the one-shot flow cookie before issuing the auth cookies on the same response.
    response.delete_cookie(OIDC_FLOW_COOKIE, path=OIDC_FLOW_COOKIE_PATH)
    set_auth_cookies(response, user.id)
    return response
