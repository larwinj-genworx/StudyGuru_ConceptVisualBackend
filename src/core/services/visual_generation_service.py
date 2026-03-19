from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass

from src.config.settings import Settings
from src.core.services.image_provider_service import (
    HuggingFaceImageProviderService,
    ProviderExecutionError,
)
from src.core.services.storage_service import ConceptVisualStorageService
from src.schemas.visuals import (
    ConceptVisualRenderAsset,
    ConceptVisualRenderRequest,
    ConceptVisualRenderResponse,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PromptVariant:
    visual_style: str
    title_suffix: str
    explanation: str
    composition: str
    camera: str
    subject_treatment: str
    pedagogical_score: float


@dataclass(slots=True)
class VisualBlueprint:
    focus_area: str
    complexity_level: str
    summary: str
    key_points: list[str]
    steps: list[str]
    labels: list[str]
    formulas: list[str]
    variants: list[PromptVariant]


class ConceptVisualGenerationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = ConceptVisualStorageService(settings)
        self.provider = HuggingFaceImageProviderService(settings)
        self.generator_name = (
            f"StudyGuru Visual AI ({settings.image_model} via {settings.image_provider})"
        )

    def render(self, payload: ConceptVisualRenderRequest) -> ConceptVisualRenderResponse:
        blueprint = self._build_blueprint(payload)
        assets: list[ConceptVisualRenderAsset] = []
        max_variants = min(
            payload.max_variants,
            max(self.settings.max_variants_per_request, 1),
            len(blueprint.variants),
        )

        for index, variant in enumerate(blueprint.variants[:max_variants], start=1):
            seed = self._build_seed(payload, variant, index)
            prompt = self._compose_prompt(payload, blueprint, variant)
            negative_prompt = self._compose_negative_prompt(variant.visual_style)
            fingerprint_seed = (
                f"{payload.subject_id}|{payload.concept_material_id}|{variant.visual_style}|"
                f"{blueprint.focus_area}|{prompt}|{seed}"
            )
            file_stem = (
                f"{variant.visual_style}-"
                f"{hashlib.sha1(fingerprint_seed.encode('utf-8')).hexdigest()[:12]}"
            )

            try:
                image = self.provider.generate_image(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    seed=seed,
                )
                stored = self.storage.save_visual(
                    image=image,
                    subject_id=payload.subject_id,
                    concept_material_id=payload.concept_material_id,
                    file_stem=file_stem,
                )
            except ProviderExecutionError as exc:
                logger.error(
                    "Concept visual generation failed for %s (%s): %s",
                    payload.concept_name,
                    variant.visual_style,
                    exc,
                    exc_info=True,
                )
                if not assets:
                    raise
                break

            learning_points = blueprint.key_points[:4]
            assets.append(
                ConceptVisualRenderAsset(
                    title=f"{payload.concept_name} - {variant.title_suffix}",
                    caption=blueprint.summary,
                    alt_text=(
                        f"{payload.concept_name} study visual focused on {blueprint.focus_area}"
                    ),
                    focus_area=blueprint.focus_area,
                    complexity_level=blueprint.complexity_level,
                    visual_style=variant.visual_style,
                    generator_name=self.generator_name,
                    explanation=f"{variant.explanation} Focus remains on {blueprint.focus_area.lower()}.",
                    learning_points=learning_points,
                    pedagogical_score=variant.pedagogical_score,
                    render_spec={
                        "style": variant.visual_style,
                        "focus_area": blueprint.focus_area,
                        "complexity_level": blueprint.complexity_level,
                        "provider": self.settings.image_provider,
                        "model": self.settings.image_model,
                        "seed": seed,
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "composition": variant.composition,
                        "camera": variant.camera,
                        "subject_treatment": variant.subject_treatment,
                        "labels": blueprint.labels[:6],
                        "steps": blueprint.steps[:5],
                        "key_points": learning_points,
                    },
                    **stored,
                )
            )

        if not assets:
            raise ProviderExecutionError(
                "The configured image provider could not generate any visual candidates."
            )

        return ConceptVisualRenderResponse(
            prompt=payload.prompt,
            focus_area=blueprint.focus_area,
            complexity_level=blueprint.complexity_level,
            assets=assets,
        )

    def _build_blueprint(self, payload: ConceptVisualRenderRequest) -> VisualBlueprint:
        highlights = [self._clean_line(item) for item in payload.content.highlights if item.strip()]
        sections = self._flatten_sections(payload.content.sections)
        section_titles = [self._clean_line(item["title"]) for item in sections if item["title"].strip()]
        paragraphs = [self._clean_line(text) for text in self._extract_block_text(payload.content.sections)]
        formulas = [item for item in paragraphs if any(symbol in item for symbol in ("=", "+", "-", "/", "^"))][:3]
        steps = self._extract_steps(paragraphs, section_titles)
        key_points = self._collect_key_points(highlights, section_titles, paragraphs, payload.concept_description)
        focus_source = payload.prompt or (highlights[0] if highlights else "")
        focus_area = self._build_focus_area(payload.concept_name, focus_source, key_points)

        complexity_score = len(sections) + len(key_points) + (len(formulas) * 2) + (len(steps) * 2)
        if complexity_score >= 16:
            complexity_level = "high"
        elif complexity_score >= 9:
            complexity_level = "medium"
        else:
            complexity_level = "low"

        return VisualBlueprint(
            focus_area=focus_area,
            complexity_level=complexity_level,
            summary=self._build_summary(payload, key_points, focus_area),
            key_points=key_points,
            steps=steps,
            labels=section_titles[:8] or key_points[:8],
            formulas=formulas,
            variants=self._build_variants(
                payload=payload,
                section_titles=section_titles,
                formulas=formulas,
                steps=steps,
                complexity_level=complexity_level,
            ),
        )

    def _build_variants(
        self,
        *,
        payload: ConceptVisualRenderRequest,
        section_titles: list[str],
        formulas: list[str],
        steps: list[str],
        complexity_level: str,
    ) -> list[PromptVariant]:
        joined = " ".join(section_titles).lower()
        concept_text = f"{payload.concept_name} {payload.concept_description or ''} {payload.prompt or ''}".lower()

        primary_style = "immersive_overview"
        if formulas:
            primary_style = "symbolic_scene"
        elif steps or any(token in joined for token in ("process", "cycle", "workflow", "sequence", "steps")):
            primary_style = "process_progression"
        elif any(token in joined + concept_text for token in ("compare", "difference", "types", "classification")):
            primary_style = "comparison_scene"
        elif any(token in joined + concept_text for token in ("parts", "layers", "structure", "components")):
            primary_style = "mechanism_cutaway"

        library = {
            "immersive_overview": PromptVariant(
                visual_style="immersive_overview",
                title_suffix="Immersive Overview",
                explanation="Best for building a quick mental model of the whole topic.",
                composition="a single coherent hero scene that shows the full concept and its most important parts",
                camera="wide three-quarter composition with clear depth separation",
                subject_treatment="premium educational illustration, realistic and polished, with clear object separation",
                pedagogical_score=0.95,
            ),
            "mechanism_cutaway": PromptVariant(
                visual_style="mechanism_cutaway",
                title_suffix="Mechanism Cutaway",
                explanation="Best for understanding the inner structure and hidden relationships.",
                composition="a realistic cutaway or cross-sectional view that reveals the internal mechanism clearly",
                camera="focused semi-close composition with the core structure centered",
                subject_treatment="scientifically grounded, layered, and easy to parse visually",
                pedagogical_score=0.9,
            ),
            "process_progression": PromptVariant(
                visual_style="process_progression",
                title_suffix="Process Progression",
                explanation="Best for understanding sequence, movement, and cause-and-effect flow.",
                composition="a continuous scene that communicates progression from one stage to the next without using template panels",
                camera="left-to-right narrative composition with motion cues and clear stage separation",
                subject_treatment="dynamic but disciplined, with each stage visibly connected",
                pedagogical_score=0.88,
            ),
            "comparison_scene": PromptVariant(
                visual_style="comparison_scene",
                title_suffix="Comparison Visual",
                explanation="Best for learning differences between states, types, or outcomes.",
                composition="a balanced two-state composition that contrasts the key differences in one image without poster-like panels",
                camera="symmetrical comparison framing with a strong central divide",
                subject_treatment="clean contrast between variants while preserving realism",
                pedagogical_score=0.86,
            ),
            "symbolic_scene": PromptVariant(
                visual_style="symbolic_scene",
                title_suffix="Conceptual Interpretation",
                explanation="Best for abstract or formula-heavy topics that need a concrete visual interpretation.",
                composition="a symbolic but accurate visual metaphor grounded in the concept meaning rather than decorative abstraction",
                camera="center-weighted composition with one dominant focal element",
                subject_treatment="highly legible visual symbolism tied to the academic concept",
                pedagogical_score=0.84,
            ),
            "focus_closeup": PromptVariant(
                visual_style="focus_closeup",
                title_suffix="Focused Close-Up",
                explanation="Best for revising the exact area that needs the most attention.",
                composition="a close-up educational shot that isolates the highest-value study area and removes distractions",
                camera="tight focal framing around the most important region",
                subject_treatment="crisply detailed, uncluttered, and visually emphatic",
                pedagogical_score=0.82,
            ),
        }

        candidates = [primary_style]
        if primary_style != "mechanism_cutaway":
            candidates.append("mechanism_cutaway")
        if primary_style != "focus_closeup":
            candidates.append("focus_closeup")
        if steps and "process_progression" not in candidates:
            candidates.append("process_progression")
        if formulas and "symbolic_scene" not in candidates:
            candidates.append("symbolic_scene")
        if complexity_level == "high" and "immersive_overview" not in candidates:
            candidates.insert(1, "immersive_overview")
        if "comparison" in joined and "comparison_scene" not in candidates:
            candidates.append("comparison_scene")

        ordered: list[PromptVariant] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            ordered.append(library[candidate])
        return ordered

    def _extract_block_text(self, sections: list) -> list[str]:
        texts: list[str] = []
        for section in sections:
            for block in section.blocks:
                block_type = str(block.get("type", "")).lower()
                if block_type == "paragraph":
                    text = str(block.get("text", "")).strip()
                    if text:
                        texts.append(text)
                elif block_type == "list":
                    items = block.get("items") or []
                    texts.extend(str(item).strip() for item in items if str(item).strip())
                elif block_type == "formula":
                    formula = str(block.get("formula", "")).strip()
                    if formula:
                        texts.append(formula)
                    explanation = str(block.get("explanation", "")).strip()
                    if explanation:
                        texts.append(explanation)
                elif block_type == "example":
                    steps = block.get("steps") or []
                    texts.extend(str(item).strip() for item in steps if str(item).strip())
                    result = str(block.get("result", "")).strip()
                    if result:
                        texts.append(result)
            texts.extend(self._extract_block_text(section.children))
        return texts

    def _extract_steps(self, paragraphs: list[str], section_titles: list[str]) -> list[str]:
        candidates = [item for item in section_titles if item.lower().startswith("step ")]
        candidates.extend(item for item in paragraphs if item.lower().startswith("step "))
        if candidates:
            return candidates[:5]
        return [item for item in paragraphs if 40 <= len(item) <= 140][:5]

    def _collect_key_points(
        self,
        highlights: list[str],
        section_titles: list[str],
        paragraphs: list[str],
        concept_description: str | None,
    ) -> list[str]:
        items: list[str] = []
        if concept_description:
            items.append(self._clean_line(concept_description))
        items.extend(highlights)
        items.extend(section_titles[:4])
        items.extend([item for item in paragraphs if 35 <= len(item) <= 150][:4])
        seen: set[str] = set()
        deduped: list[str] = []
        for item in items:
            normalized = " ".join(item.lower().split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(item)
        return deduped[:8] or ["Understand the core idea, the key parts, and the learning sequence."]

    def _flatten_sections(self, sections: list) -> list[dict]:
        flattened: list[dict] = []
        for section in sections:
            flattened.append({"title": section.title, "level": section.level})
            flattened.extend(self._flatten_sections(section.children))
        return flattened

    def _build_focus_area(self, concept_name: str, prompt: str, key_points: list[str]) -> str:
        seed = self._clean_line(prompt) if prompt else ""
        if seed:
            return seed[:80]
        if key_points:
            first = key_points[0]
            if concept_name.lower() in first.lower():
                return "Core concept understanding"
            return first[:80]
        return f"Core understanding of {concept_name}"

    def _build_summary(
        self,
        payload: ConceptVisualRenderRequest,
        key_points: list[str],
        focus_area: str,
    ) -> str:
        return (
            f"This visual translates {payload.concept_name} into an AI-generated study image with emphasis on "
            f"{focus_area.lower()}. It keeps the explanation grounded in the main learning points so the student "
            f"can understand the concept faster and revise it with less confusion."
        )

    def _compose_prompt(
        self,
        payload: ConceptVisualRenderRequest,
        blueprint: VisualBlueprint,
        variant: PromptVariant,
    ) -> str:
        facts = "; ".join(blueprint.key_points[:4])
        labels = ", ".join(blueprint.labels[:4])
        steps = "; ".join(blueprint.steps[:4])
        formulas = "; ".join(blueprint.formulas[:2])
        prompt_parts = [
            "Create a premium, high-clarity educational image for students.",
            f"Subject: {payload.subject_name}.",
            f"Grade level: {payload.grade_level}.",
            f"Topic: {payload.concept_name}.",
            f"Primary study focus: {blueprint.focus_area}.",
            f"Show {variant.composition}.",
            f"Use {variant.camera}.",
            f"Visual treatment: {variant.subject_treatment}.",
            f"Complexity level: {blueprint.complexity_level}.",
            self._subject_style_hint(payload.subject_name),
            "The image should feel like a modern AI-generated teaching visual, not a flat poster or generic stock art.",
            "Keep the scene scientifically grounded, visually understandable, and easy to study at a glance.",
            "Do not put any written text, letters, numbers, labels, watermark, or logo inside the image.",
        ]
        if facts:
            prompt_parts.append(f"Core facts to preserve visually: {facts}.")
        if labels:
            prompt_parts.append(f"Important components or ideas: {labels}.")
        if steps:
            prompt_parts.append(f"Progression or sequence cues: {steps}.")
        if formulas:
            prompt_parts.append(
                f"Formula or abstract relationship to interpret visually without drawing equations as text: {formulas}."
            )
        if payload.prompt:
            prompt_parts.append(
                f"Admin focus preference to honor without ignoring the topic context: {self._clean_line(payload.prompt)}."
            )
        if payload.concept_description:
            prompt_parts.append(
                f"Concept description: {self._clean_line(payload.concept_description)}."
            )
        return " ".join(part for part in prompt_parts if part)

    def _compose_negative_prompt(self, visual_style: str) -> str:
        style_specific = {
            "comparison_scene": "triptych, comic panels, infographic board",
            "process_progression": "disconnected frames, storyboard boxes",
            "mechanism_cutaway": "opaque exterior hiding the key mechanism",
            "symbolic_scene": "random fantasy symbolism unrelated to the concept",
        }
        extra = style_specific.get(visual_style, "")
        if not extra:
            return self.settings.negative_prompt
        return f"{self.settings.negative_prompt}, {extra}"

    def _subject_style_hint(self, subject_name: str) -> str:
        subject = (subject_name or "").lower()
        if any(token in subject for token in ("biology", "botany", "zoology", "science")):
            return (
                "Use realistic scientific textures, natural color fidelity, anatomical clarity, and "
                "clean environmental separation."
            )
        if any(token in subject for token in ("physics", "chemistry")):
            return (
                "Make invisible processes visually understandable through light, energy, particles, motion, "
                "and controlled scientific staging."
            )
        if any(token in subject for token in ("history", "civics", "social", "geography")):
            return (
                "Use historically or contextually grounded environments, accurate objects, and a clear sense "
                "of cause, place, or change over time."
            )
        if any(token in subject for token in ("math", "mathematics")):
            return (
                "Translate the concept into an accurate spatial or geometric interpretation instead of relying "
                "on written formulas."
            )
        return (
            "Use a clear, realistic, study-friendly composition with strong focal hierarchy and minimal clutter."
        )

    def _build_seed(
        self,
        payload: ConceptVisualRenderRequest,
        variant: PromptVariant,
        index: int,
    ) -> int:
        digest = hashlib.sha1(
            f"{payload.subject_id}|{payload.concept_id}|{variant.visual_style}|{index}|{random.random()}".encode(
                "utf-8"
            )
        ).hexdigest()
        return int(digest[:8], 16)

    def _clean_line(self, value: str) -> str:
        return " ".join((value or "").replace("\n", " ").split()).strip(" -:")[:180]
