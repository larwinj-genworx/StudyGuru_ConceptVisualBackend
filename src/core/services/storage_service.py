from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from src.config.settings import Settings

_STORAGE_SCOPES = ("https://www.googleapis.com/auth/devstorage.read_write",)


class ConceptVisualStorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._bucket = None

    def save_visual(
        self,
        *,
        image: Image.Image,
        subject_id: str,
        concept_material_id: str,
        file_stem: str,
    ) -> dict:
        output_dir = self.settings.output_dir / subject_id / concept_material_id
        output_dir.mkdir(parents=True, exist_ok=True)

        full_path = output_dir / f"{file_stem}.png"
        thumb_path = output_dir / f"{file_stem}_thumb.png"
        image.save(full_path, format="PNG", optimize=True)

        thumbnail = image.copy()
        thumbnail.thumbnail(
            (self.settings.thumbnail_width, self.settings.thumbnail_height),
            Image.Resampling.LANCZOS,
        )
        thumb_canvas = Image.new(
            "RGB",
            (self.settings.thumbnail_width, self.settings.thumbnail_height),
            "#f4f7fb",
        )
        offset_x = max((self.settings.thumbnail_width - thumbnail.width) // 2, 0)
        offset_y = max((self.settings.thumbnail_height - thumbnail.height) // 2, 0)
        thumb_canvas.paste(thumbnail, (offset_x, offset_y))
        thumb_canvas.save(thumb_path, format="PNG", optimize=True)

        if self.settings.gcs_enabled:
            self._upload_file(full_path)
            self._upload_file(thumb_path)

        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        digest = hashlib.sha1(buffer.getvalue()).hexdigest()

        return {
            "relative_image_path": self._relative(full_path),
            "relative_thumbnail_path": self._relative(thumb_path),
            "width": image.width,
            "height": image.height,
            "file_size_bytes": full_path.stat().st_size,
            "fingerprint": digest,
        }

    def _relative(self, path: Path) -> str:
        return str(path.relative_to(self.settings.output_dir)).replace("\\", "/")

    def _upload_file(self, path: Path) -> None:
        blob = self._bucket_client().blob(self._object_name(self._relative(path)))
        blob.cache_control = "private, max-age=3600"
        blob.upload_from_filename(
            filename=str(path),
            content_type="image/png",
            timeout=self.settings.gcs_request_timeout_seconds,
        )

    def _bucket_client(self):
        if self._bucket is not None:
            return self._bucket
        try:
            import google.auth
            from google.auth import impersonated_credentials
            from google.cloud import storage
        except ImportError as exc:  # pragma: no cover - dependency is runtime configured
            raise RuntimeError(
                "Missing dependency 'google-cloud-storage'. Install ConceptVisualBackend dependencies."
            ) from exc

        source_credentials, detected_project = google.auth.default(scopes=_STORAGE_SCOPES)
        active_project = self.settings.gcs_project_id or detected_project
        if not active_project:
            raise RuntimeError("Unable to determine the Google Cloud project for concept visuals.")

        credentials = source_credentials
        if (self.settings.gcs_target_service_account or "").strip():
            credentials = impersonated_credentials.Credentials(
                source_credentials=source_credentials,
                target_principal=self.settings.gcs_target_service_account.strip(),
                target_scopes=list(_STORAGE_SCOPES),
                lifetime=3600,
            )

        client = storage.Client(project=active_project, credentials=credentials)
        self._bucket = client.bucket(self.settings.gcs_bucket_name)
        return self._bucket

    def _object_name(self, relative_path: str) -> str:
        prefix = self.settings.gcs_bucket_prefix.strip("/")
        if prefix:
            return f"{prefix}/concept_visuals/{relative_path}"
        return f"concept_visuals/{relative_path}"
