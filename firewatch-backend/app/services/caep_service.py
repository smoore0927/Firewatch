"""CAEP (Continuous Access Evaluation Protocol) SET processing."""

from datetime import datetime, timezone

from joserfc import jwt
from joserfc import errors as jose_errors
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.oidc import get_discovery_document, get_jwks, _JWKS_CACHE
from app.models.user import User

_SESSION_REVOKED = "https://schemas.openid.net/secevent/caep/event-type/session-revoked"
_CREDENTIAL_CHANGE = "https://schemas.openid.net/secevent/caep/event-type/credential-change"
_ACCOUNT_DISABLED = "https://schemas.openid.net/secevent/caep/event-type/account-disabled"
_ACCOUNT_PURGED = "https://schemas.openid.net/secevent/caep/event-type/account-purged"


async def process_set(token: str, db: Session) -> None:
    """Verify a Security Event Token and apply the described action to the user."""
    discovery = await get_discovery_document()
    jwks_uri: str = discovery["jwks_uri"]
    keys = await get_jwks(jwks_uri)

    try:
        decoded = jwt.decode(token, keys)
    except jose_errors.JoseError:
        # Attempt key refresh once on verification failure
        if jwks_uri in _JWKS_CACHE:
            del _JWKS_CACHE[jwks_uri]
        keys = await get_jwks(jwks_uri)
        try:
            decoded = jwt.decode(token, keys)
        except jose_errors.JoseError as exc:
            raise ValueError(f"SET signature verification failed: {exc}") from exc

    claims = dict(decoded.claims)

    # Verify audience
    expected_aud = settings.CAEP_AUDIENCE or settings.OIDC_CLIENT_ID
    aud = claims.get("aud")
    aud_list = aud if isinstance(aud, list) else [aud]
    if expected_aud not in aud_list:
        raise ValueError("SET audience mismatch")

    events: dict = claims.get("events", {})
    if not events:
        raise ValueError("SET contains no events claim")

    # Extract subject — prefer event-level subject.sub, fall back to top-level sub
    subject_sub: str | None = None
    for event_value in events.values():
        if isinstance(event_value, dict):
            subject = event_value.get("subject", {})
            if isinstance(subject, dict) and subject.get("sub"):
                subject_sub = subject["sub"]
                break
    if subject_sub is None:
        subject_sub = claims.get("sub")
    if not subject_sub:
        raise ValueError("SET contains no identifiable subject")

    user = db.query(User).filter(User.external_id == subject_sub).first()
    if user is None:
        return  # unknown user — not an error

    now = datetime.now(timezone.utc)
    for event_type in events:
        if event_type in (_SESSION_REVOKED, _CREDENTIAL_CHANGE):
            user.last_logout_at = now
        elif event_type in (_ACCOUNT_DISABLED, _ACCOUNT_PURGED):
            user.is_active = False
    db.add(user)
