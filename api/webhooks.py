"""
Webhook receiver para OpenDataManager (ODM).

Endpoint: POST /webhooks/odmgr
  - Verifica la firma HMAC-SHA256 (header X-ODM-Signature)
  - Delega el procesamiento a services/odmgr_sync.py
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from services.odmgr_sync import handle_odmgr_webhook, verify_hmac

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/odmgr", status_code=status.HTTP_200_OK)
async def odmgr_webhook(
    request: Request,
    x_odm_signature: str = Header(..., alias="X-ODM-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Recibe notificaciones de ODM cuando un dataset es publicado o actualizado.

    ODM firma el payload con HMAC-SHA256 usando el secreto compartido.
    Si la firma no es válida, devuelve 401.
    """
    settings = get_settings()
    payload_bytes = await request.body()

    if not verify_hmac(payload_bytes, x_odm_signature, settings.odmgr_webhook_secret):
        logger.warning("odmgr_webhook_invalid_signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC signature",
        )

    import json
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        )

    result = await handle_odmgr_webhook(
        payload=payload,
        db=db,
        odmgr_base_url=settings.odmgr_base_url,
    )
    await db.commit()
    return result
