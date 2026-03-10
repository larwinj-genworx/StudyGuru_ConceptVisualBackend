from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.config.settings import get_settings


async def require_service_token(
    x_studyguru_service_token: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if x_studyguru_service_token != settings.service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token.",
        )
