from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_token: str = Field(
        default="studyguru-concept-visual-service",
        alias="CONCEPT_VISUAL_SERVICE_TOKEN",
    )
    output_dir: Path = Field(
        default=Path("output/concept_visuals"),
        validation_alias=AliasChoices("CONCEPT_VISUAL_OUTPUT_DIR", "CONCEPT_IMAGE_OUTPUT_DIR"),
    )
    hf_api_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HUGGING_FACE_HUB_TOKEN"),
    )
    image_provider: str = Field(default="replicate", alias="CONCEPT_VISUAL_IMAGE_PROVIDER")
    image_model: str = Field(
        default="black-forest-labs/FLUX.1-schnell",
        alias="CONCEPT_VISUAL_IMAGE_MODEL",
    )
    provider_timeout_seconds: float = Field(
        default=90.0,
        alias="CONCEPT_VISUAL_PROVIDER_TIMEOUT_SECONDS",
    )
    canvas_width: int = Field(default=1152, alias="CONCEPT_VISUAL_IMAGE_WIDTH")
    canvas_height: int = Field(default=768, alias="CONCEPT_VISUAL_IMAGE_HEIGHT")
    thumbnail_width: int = Field(default=560, alias="CONCEPT_VISUAL_THUMBNAIL_WIDTH")
    thumbnail_height: int = Field(default=336, alias="CONCEPT_VISUAL_THUMBNAIL_HEIGHT")
    max_variants_per_request: int = Field(default=2, alias="CONCEPT_VISUAL_MAX_VARIANTS")
    num_inference_steps: int = Field(default=4, alias="CONCEPT_VISUAL_INFERENCE_STEPS")
    guidance_scale: float = Field(default=0.0, alias="CONCEPT_VISUAL_GUIDANCE_SCALE")
    output_quality: int = Field(default=100, alias="CONCEPT_VISUAL_OUTPUT_QUALITY")
    negative_prompt: str = Field(
        default=(
            "blurry, low resolution, low detail, distorted anatomy, bad proportions, duplicate objects, "
            "floating objects, extra limbs, unreadable text, letters, captions, watermark, logo, poster, "
            "infographic template, split panels, cluttered composition, cropped subject, oversaturated"
        ),
        alias="CONCEPT_VISUAL_NEGATIVE_PROMPT",
    )

    def ensure_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def hf_token(self) -> str:
        if self.hf_api_token is None:
            return ""
        return self.hf_api_token.get_secret_value().strip()

    @property
    def provider_configured(self) -> bool:
        return bool(self.hf_token)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_output_dir()
    return settings
