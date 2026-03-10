from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from src.config.settings import Settings


class ConceptVisualStorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
