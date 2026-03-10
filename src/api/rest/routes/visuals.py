from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.rest.dependencies import require_service_token
from src.config.settings import get_settings
from src.core.services.image_provider_service import (
    ConceptVisualProviderError,
    ProviderConfigurationError,
)
from src.core.services.visual_generation_service import ConceptVisualGenerationService
from src.schemas.visuals import ConceptVisualRenderRequest, ConceptVisualRenderResponse

router = APIRouter(prefix="/v1/concept-visuals", tags=["concept-visuals"])

_service = ConceptVisualGenerationService(get_settings())


@router.post(
    "/render",
    response_model=ConceptVisualRenderResponse,
    dependencies=[Depends(require_service_token)],
)
async def render_concept_visuals(
    payload: ConceptVisualRenderRequest,
) -> ConceptVisualRenderResponse:
    try:
        return _service.render(payload)
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ConceptVisualProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
