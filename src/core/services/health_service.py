from __future__ import annotations

import asyncio
import logging
from time import perf_counter

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError

from src.config.settings import Settings, get_settings
from src.core.services.image_provider_service import HuggingFaceImageProviderService, ProviderConfigurationError
from src.schemas.health import HealthCheckResult, HealthResponse

logger = logging.getLogger(__name__)

_SERVICE_NAME = "StudyGuru Concept Visual Backend"
_SERVICE_VERSION = "0.1.0"


async def build_health_response(settings: Settings | None = None) -> HealthResponse:
    """Run service readiness checks for Cloud Run and operators."""

    active_settings = settings or get_settings()
    token_check, provider_check = await asyncio.gather(
        _check_service_token(active_settings),
        _check_provider(active_settings),
    )
    checks = {
        "service_token": token_check,
        "image_provider": provider_check,
    }
    overall_status = "ok" if all(item.status == "ok" for item in checks.values()) else "error"
    return HealthResponse(
        status=overall_status,
        service=_SERVICE_NAME,
        version=_SERVICE_VERSION,
        checks=checks,
    )


async def _check_service_token(settings: Settings) -> HealthCheckResult:
    if not settings.service_token.strip():
        return HealthCheckResult(
            status="error",
            detail="CONCEPT_VISUAL_SERVICE_TOKEN is not configured.",
        )
    return HealthCheckResult(
        status="ok",
        detail="Service token is configured.",
    )


async def _check_provider(settings: Settings) -> HealthCheckResult:
    started_at = perf_counter()
    try:
        await asyncio.to_thread(_validate_provider_configuration, settings)
    except ProviderConfigurationError:
        logger.error("Concept visual provider configuration health check failed.", exc_info=True)
        return HealthCheckResult(
            status="error",
            detail="Image provider is not configured correctly.",
            latency_ms=_elapsed_ms(started_at),
        )
    except HfHubHTTPError:
        logger.error("Concept visual provider health check received an HTTP error.", exc_info=True)
        return HealthCheckResult(
            status="error",
            detail="Configured image model is not reachable with the current credentials.",
            latency_ms=_elapsed_ms(started_at),
        )
    except (OSError, RuntimeError, ValueError):
        logger.error("Concept visual provider health check failed unexpectedly.", exc_info=True)
        return HealthCheckResult(
            status="error",
            detail="Image provider health check failed.",
            latency_ms=_elapsed_ms(started_at),
        )

    return HealthCheckResult(
        status="ok",
        detail="Image provider configuration is healthy.",
        latency_ms=_elapsed_ms(started_at),
    )


def _validate_provider_configuration(settings: Settings) -> None:
    if not settings.provider_configured:
        raise ProviderConfigurationError("Provider token is missing.")
    HuggingFaceImageProviderService(settings)._build_client()
    HfApi().model_info(settings.image_model, token=settings.hf_token)


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)
