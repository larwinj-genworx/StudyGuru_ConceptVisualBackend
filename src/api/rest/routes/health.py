from fastapi import APIRouter

from src.config.settings import get_settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "concept-visual-backend",
        "provider": settings.image_provider,
        "provider_configured": "true" if settings.provider_configured else "false",
    }
