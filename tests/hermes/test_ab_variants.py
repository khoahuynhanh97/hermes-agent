"""Tests for A/B variant engine: generation, selection, and multi-variant output."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hermes.video.ab_variants import (
    ABVariantEngine,
    VariantSelection,
    ScenePlanVariant,
)


@pytest.fixture(autouse=True)
def _fake_providers(monkeypatch):
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")


@pytest.fixture
def variant_engine():
    """Create an ABVariantEngine instance."""
    return ABVariantEngine()


@pytest.fixture
def sample_scene_plan():
    """Provide a sample scene plan for variant generation."""
    return {
        "project_id": "test_project",
        "scenes": [
            {"scene_id": "scene_1", "order": 1, "title": "Hook", "duration_seconds": 6},
            {"scene_id": "scene_2", "order": 2, "title": "Features", "duration_seconds": 8},
            {"scene_id": "scene_3", "order": 3, "title": "Benefits", "duration_seconds": 8},
            {"scene_id": "scene_4", "order": 4, "title": "CTA", "duration_seconds": 8},
        ],
        "total_duration": 30,
    }


class TestVariantGeneration:
    """Test variant generation produces correct outputs."""

    def test_generates_three_variants(self, variant_engine, sample_scene_plan):
        """Variant engine should produce exactly 3 variants."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        assert len(variants) == 3, f"Expected 3 variants, got {len(variants)}"

    def test_each_variant_has_unique_id(self, variant_engine, sample_scene_plan):
        """Each variant should have a unique identifier."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        ids = [v.variant_id for v in variants]
        assert len(set(ids)) == 3, "Variant IDs are not unique"

    def test_each_variant_has_scene_plan(self, variant_engine, sample_scene_plan):
        """Each variant must contain a complete scene plan."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        for variant in variants:
            assert hasattr(variant, "scene_plan"), f"Variant {variant.variant_id} missing scene_plan"
            assert isinstance(variant.scene_plan, dict)
            assert len(variant.scene_plan["scenes"]) == 4

    def test_variants_have_unique_scene_durations(self, variant_engine, sample_scene_plan):
        """Each variant should have different duration distributions."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        duration_profiles = []
        for v in variants:
            profile = tuple(s["duration_seconds"] for s in v.scene_plan["scenes"])
            duration_profiles.append(profile)
        # At least 2 variants should have different duration distributions
        assert len(set(duration_profiles)) >= 2, "Variants have identical duration profiles"

    def test_variant_preserves_total_duration(self, variant_engine, sample_scene_plan):
        """All variants should maintain the same total duration."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        for variant in variants:
            total = sum(s["duration_seconds"] for s in variant.variant_scenes)
            assert abs(total - 30) < 0.1, f"Variant {variant.variant_id} duration: {total}"


class TestVariantSelection:
    """Test variant selection strategies."""

    def test_manual_selection(self, variant_engine, sample_scene_plan):
        """Manual selection should return the specified variant."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        selected = variant_engine.select_variant(variants, VariantSelection.MANUAL, variant_index=1)
        assert selected.variant_id == variants[1].variant_id

    def test_random_selection(self, variant_engine, sample_scene_plan):
        """Random selection should return one of the variants."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        selected = variant_engine.select_variant(variants, VariantSelection.RANDOM)
        assert selected.variant_id in [v.variant_id for v in variants]

    def test_first_selection(self, variant_engine, sample_scene_plan):
        """First selection should always return variant A."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        selected = variant_engine.select_variant(variants, VariantSelection.FIRST)
        assert selected.variant_id == variants[0].variant_id

    def test_manual_invalid_index_raises(self, variant_engine, sample_scene_plan):
        """Manual selection with invalid index should raise ValueError."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        with pytest.raises(ValueError):
            variant_engine.select_variant(variants, VariantSelection.MANUAL, variant_index=99)


class TestMultiVariantOutput:
    """Test that running all 3 variants produces separate outputs."""

    def test_generate_all_variants_produces_three_paths(self, variant_engine, sample_scene_plan, tmp_path):
        """generate_all_variants should return 3 output paths."""
        output_dir = tmp_path / "variants"
        output_dir.mkdir()
        paths = variant_engine.generate_all_variants(
            sample_scene_plan, output_dir=str(output_dir)
        )
        assert len(paths) == 3
        for p in paths:
            assert p.endswith(".json") or p.endswith(".mp4")

    def test_variant_metadata_includes_selection(self, variant_engine, sample_scene_plan):
        """Each variant should carry metadata about its selection strategy."""
        variants = variant_engine.generate_variants(sample_scene_plan)
        for v in variants:
            assert hasattr(v, "metadata"), f"Variant {v.variant_id} missing metadata"
            assert "strategy" in v.metadata
