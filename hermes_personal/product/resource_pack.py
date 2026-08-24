"""Phase 5 Task 2 – deterministic product resource pack builder.

Creates a ``ResourcePackResult`` containing a human‑readable summary, a deterministic
mapping of asset identifiers to placeholder URLs, and a simple ``ScenePlan``.
All logic is pure – no external I/O – so tests run quickly and without paid API calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Dict


@dataclass(frozen=True, slots=True)
class ResourcePackSpec:
    """Specification for a resource pack.

    Attributes
    ----------
    product_name: str
        Name of the product the pack belongs to.
    assets: List[str]
        Identifiers of visual assets required.
    scenes: List[str]
        Logical scene names for the video factory flow.
    """

    product_name: str
    assets: List[str]
    scenes: List[str]


@dataclass(frozen=True, slots=True)
class ScenePlan:
    """Simple deterministic plan describing how scenes are sequenced.

    ``steps`` is a list of human‑readable strings, each derived from a scene name.
    """

    steps: List[str]

    def to_json(self) -> str:
        return json.dumps({"steps": self.steps})


@dataclass(frozen=True, slots=True)
class ResourcePackResult:
    """Result of a resource‑pack build.

    ``summary``: short description.
    ``assets_mapping``: deterministic ``asset → URL`` dictionary.
    ``scene_plan``: a :class:`ScenePlan` instance.
    """

    summary: str
    assets_mapping: Dict[str, str]
    scene_plan: ScenePlan

    def to_json(self) -> str:
        return json.dumps(
            {
                "summary": self.summary,
                "assets_mapping": self.assets_mapping,
                "scene_plan": json.loads(self.scene_plan.to_json()),
            }
        )


class ResourcePackBuilder:
    """Pure builder – deterministic, no external calls.

    ``build`` returns a :class:`ResourcePackResult`.
    """

    _base_url = "https://example.com/assets/"

    def _build_assets_mapping(self, assets: List[str]) -> Dict[str, str]:
        # deterministic placeholder URLs
        return {asset: f"{self._base_url}{asset}.png" for asset in assets}

    def _build_scene_plan(self, scenes: List[str]) -> ScenePlan:
        steps = [f"Scene {i + 1}: {name}" for i, name in enumerate(scenes)]
        return ScenePlan(steps=steps)

    def build(self, spec: ResourcePackSpec) -> ResourcePackResult:
        assets_map = self._build_assets_mapping(spec.assets)
        scene_plan = self._build_scene_plan(spec.scenes)
        summary = (
            f"Resource pack for {spec.product_name}: "
            f"{len(spec.assets)} assets, {len(spec.scenes)} scenes"
        )
        return ResourcePackResult(summary=summary, assets_mapping=assets_map, scene_plan=scene_plan)


def run_resource_pack_builder(spec: ResourcePackSpec) -> ResourcePackResult:
    """Convenient entry‑point used by tests/CLI.

    Creates a ``ResourcePackBuilder`` instance and returns its ``build`` result.
    """

    builder = ResourcePackBuilder()
    return builder.build(spec)
