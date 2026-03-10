from __future__ import annotations

import inspect
from io import BytesIO

from huggingface_hub import InferenceClient, InferenceTimeoutError
from huggingface_hub.errors import HfHubHTTPError
from PIL import Image, ImageFilter, ImageOps

from src.config.settings import Settings


class ConceptVisualProviderError(RuntimeError):
    """Base error for provider-backed concept visual generation."""


class ProviderConfigurationError(ConceptVisualProviderError):
    """Raised when the provider credentials or configuration are invalid."""


class ProviderExecutionError(ConceptVisualProviderError):
    """Raised when the provider cannot return an image successfully."""


class HuggingFaceImageProviderService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_image(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        seed: int,
    ) -> Image.Image:
        if not self.settings.provider_configured:
            raise ProviderConfigurationError(
                "Hugging Face token is not configured. Set HF_TOKEN in ConceptVisualBackend/.env."
            )

        client = self._build_client()
        inference_steps, guidance_scale = self._resolved_sampling_config()
        request_kwargs = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "height": self.settings.canvas_height,
            "width": self.settings.canvas_width,
            "num_inference_steps": inference_steps,
            "guidance_scale": guidance_scale,
            "model": self.settings.image_model,
            "seed": seed,
        }
        extra_body = self._extra_body()
        if extra_body:
            request_kwargs["extra_body"] = extra_body

        try:
            result = client.text_to_image(**request_kwargs)
        except InferenceTimeoutError as exc:
            raise ProviderExecutionError(
                "The image provider timed out while generating the visual. Try again."
            ) from exc
        except HfHubHTTPError as exc:
            raise self._translate_http_error(exc) from exc
        except Exception as exc:  # pragma: no cover - provider/network edge cases
            raise ProviderExecutionError(
                "The image provider could not generate the visual at the moment."
            ) from exc

        return self._normalize_image(result)

    def _build_client(self) -> InferenceClient:
        signature = inspect.signature(InferenceClient)
        kwargs = {
            "api_key": self.settings.hf_token,
            "timeout": self.settings.provider_timeout_seconds,
        }
        if "provider" in signature.parameters:
            kwargs["provider"] = self.settings.image_provider
        return InferenceClient(**kwargs)

    def _extra_body(self) -> dict[str, int] | None:
        if self.settings.image_provider.lower() != "replicate":
            return None
        return {"output_quality": self.settings.output_quality}

    def _resolved_sampling_config(self) -> tuple[int, float]:
        model_name = self.settings.image_model.strip().lower()
        if model_name.endswith("flux.1-schnell") or model_name.endswith("flux-schnell"):
            return min(self.settings.num_inference_steps, 4), 0.0
        return self.settings.num_inference_steps, self.settings.guidance_scale

    def _translate_http_error(self, exc: HfHubHTTPError) -> ConceptVisualProviderError:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        detail = str(exc).strip()
        if status_code in {401, 403}:
            return ProviderConfigurationError(
                "The Hugging Face token is invalid or does not have access to the configured model."
            )
        if status_code in {402, 429} or "credit" in detail.lower():
            return ProviderExecutionError(
                "The Hugging Face free-tier credits or provider quota are exhausted. Wait or top up the account."
            )
        if status_code == 404:
            return ProviderConfigurationError(
                "The configured image model is not available through the selected Hugging Face provider."
            )
        return ProviderExecutionError(
            detail or "The image provider returned an unexpected response."
        )

    def _normalize_image(self, result: Image.Image | bytes | bytearray | object) -> Image.Image:
        image: Image.Image
        if isinstance(result, Image.Image):
            image = result
        elif isinstance(result, (bytes, bytearray)):
            image = Image.open(BytesIO(result))
        elif hasattr(result, "read"):
            image = Image.open(BytesIO(result.read()))
        else:  # pragma: no cover - defensive guard for provider changes
            raise ProviderExecutionError("The image provider returned an unsupported image payload.")

        normalized = ImageOps.fit(
            image.convert("RGB"),
            (self.settings.canvas_width, self.settings.canvas_height),
            method=Image.Resampling.LANCZOS,
        )
        return normalized.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=3))
