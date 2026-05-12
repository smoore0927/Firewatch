"""CAEP receiver endpoint — accepts Security Event Tokens from the IdP."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_db
from app.services.caep_service import process_set

router = APIRouter(prefix="/auth/sso/caep", tags=["CAEP"])


@router.post("", status_code=202)
async def caep_receiver(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Receive a Security Event Token (SET) from the IdP and apply the event."""
    if not settings.CAEP_ENABLED:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)  # type: ignore[return-value]

    content_type = request.headers.get("content-type", "")
    if "application/secevent+jwt" in content_type:
        token = (await request.body()).decode("utf-8").strip()
    else:
        body = await request.json()
        token = body.get("token", "")

    if not token:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)  # type: ignore[return-value]

    try:
        await process_set(token, db)
    except ValueError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)  # type: ignore[return-value]

    db.commit()
    return {"status": "accepted"}
