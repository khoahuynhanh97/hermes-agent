"""A/B variant engine: generate, select, and manage scene plan variants."""
from __future__ import annotations

import copy
import json
import random
import uuid
from enum import Enum
from pathlib import Path
from typing import Any


class VariantSelection(Enum):
    """Variant selection strategy."""
    FIRST = "first"
    RANDOM = "random"
    MANUAL = "manual"


class ScenePlanVariant:
    """A single scene plan variant with metadata."""

    def __init__(
        self,
        variant_id: str,
        label: str,
        scene_plan: dict[str, Any],
        variant_scenes: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ):
        self.variant_id = variant_id
        self.label = label
        self.scene_plan = scene_plan
        self.variant_scenes = variant_scenes
        self.metadata = metadata or {}


# Variant labels and scene shuffling strategies
_VARIANT_CONFIGS = [
    {"label": "Variant A (Default)", "strategy": "original", "description": "Original scene order"},
    {"label": "Variant B (Hook-First)", "strategy": "hook_first", "description": "Lead with strongest hook"},
    {"label": "Variant C (Fast-Cut)", "strategy": "fast_cut", "description": "Shorter scenes, faster pace"},
]


class ABVariantEngine:
    """Generate and manage A/B test variants of a scene plan."""

    def generate_variants(self, scene_plan: dict[str, Any]) -> list[ScenePlanVariant]:
        """Generate 3 variants from a base scene plan.

        Each variant modifies scene durations and ordering while preserving
        the total duration.
        """
        base_scenes = scene_plan.get("scenes", [])
        total_duration = scene_plan.get("total_duration", 30)
        variants = []

        for i, config in enumerate(_VARIANT_CONFIGS):
            variant_id = f"variant_{chr(65 + i)}_{uuid.uuid4().hex[:8]}"
            scenes = copy.deepcopy(base_scenes)

            if config["strategy"] == "hook_first":
                # Move the first scene (hook) to remain first, shuffle middle
                if len(scenes) > 2:
                    middle = scenes[1:-1]
                    random.shuffle(middle)
                    scenes = [scenes[0]] + middle + [scenes[-1]]

            elif config["strategy"] == "fast_cut":
                # Redistribute durations: shorter scenes, faster pace
                if scenes:
                    avg_dur = total_duration / len(scenes)
                    for j, scene in enumerate(scenes):
                        if j < len(scenes) - 1:
                            scene["duration_seconds"] = round(avg_dur * 0.9, 1)
                        else:
                            # Last scene absorbs the remainder
                            used = sum(s["duration_seconds"] for s in scenes[:-1])
                            scene["duration_seconds"] = round(total_duration - used, 1)

            # Ensure total duration is preserved
            current_total = sum(s["duration_seconds"] for s in scenes)
            if abs(current_total - total_duration) > 0.1 and scenes:
                diff = total_duration - current_total
                scenes[-1]["duration_seconds"] = round(scenes[-1]["duration_seconds"] + diff, 1)

            variant_scene_plan = {
                "scenes": scenes,
                "total_duration": total_duration,
            }

            variant = ScenePlanVariant(
                variant_id=variant_id,
                label=config["label"],
                scene_plan=variant_scene_plan,
                variant_scenes=scenes,
                metadata={
                    "strategy": config["strategy"],
                    "description": config["description"],
                    "base_project_id": scene_plan.get("project_id", ""),
                },
            )
            variants.append(variant)

        return variants

    def select_variant(
        self,
        variants: list[ScenePlanVariant],
        selection: VariantSelection,
        variant_index: int = 0,
    ) -> ScenePlanVariant:
        """Select a variant using the specified strategy."""
        if not variants:
            raise ValueError("No variants available for selection")

        if selection == VariantSelection.FIRST:
            return variants[0]

        if selection == VariantSelection.RANDOM:
            return random.choice(variants)

        if selection == VariantSelection.MANUAL:
            if variant_index < 0 or variant_index >= len(variants):
                raise ValueError(
                    f"Invalid variant_index {variant_index}; valid range: 0-{len(variants) - 1}"
                )
            return variants[variant_index]

        raise ValueError(f"Unknown selection strategy: {selection}")

    def generate_all_variants(
        self,
        scene_plan: dict[str, Any],
        output_dir: str,
    ) -> list[str]:
        """Generate all 3 variants and persist them as JSON files.

        Returns list of output file paths.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        variants = self.generate_variants(scene_plan)
        paths: list[str] = []

        for variant in variants:
            filename = f"{variant.variant_id}.json"
            filepath = out / filename
            payload = {
                "variant_id": variant.variant_id,
                "label": variant.label,
                "scene_plan": variant.scene_plan,
                "metadata": variant.metadata,
            }
            filepath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            paths.append(str(filepath))

        return paths
