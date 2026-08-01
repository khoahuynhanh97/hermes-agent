from __future__ import annotations

from hermes.domain.affiliate_research import ReferenceMetadata


def _reference(
    *,
    title: str,
    caption: str,
    reference_id: str = "reference-1",
) -> ReferenceMetadata:
    return ReferenceMetadata(
        id=reference_id,
        owner_user_id="42",
        product_id="product-1",
        platform="tiktok",
        source_url=f"https://example.test/{reference_id}",
        title=title,
        author_name="Creator",
        author_url="https://example.test/creator",
        thumbnail_url="https://example.test/thumb.jpg",
        caption=caption,
        embed_html="",
        authorization_scope="public_metadata",
        rights_status="reference_only",
        media_local_path="",
        collected_at="2026-08-01T00:00:00+00:00",
        source_type="tiktok_oembed",
        content_hash=f"hash-{reference_id}",
    )


def test_abstractor_derives_semantic_structure_without_copying_source_wording():
    from hermes.application.reference_pattern_abstractor import (
        ReferencePatternAbstractor,
    )

    reference = _reference(
        title="Before and after fixing a cluttered cable desk",
        caption=(
            "First show the tangled charging cables, then install the hub, "
            "and finally reveal the clean working area. COPY EXACT PHRASE."
        ),
    )

    result = ReferencePatternAbstractor().abstract((reference,))

    assert len(result) == 1
    assert result[0].hook == "transformation reveal"
    assert result[0].pacing == "stepwise demonstration"
    assert result[0].story == "baseline-intervention-result"
    rendered = " ".join(
        (result[0].hook, result[0].pacing, result[0].story)
    ).lower()
    assert "copy exact phrase" not in rendered
    assert reference.title.lower() not in rendered
    assert reference.caption.lower() not in rendered
    assert result[0].provenance == {
        "reference_id": "reference-1",
        "source_type": "tiktok_oembed",
        "content_hash": "hash-reference-1",
        "collected_at": "2026-08-01T00:00:00+00:00",
        "observable_fields": ("title", "caption", "platform"),
        "matched_signals": (
            "before_after",
            "sequence",
            "problem_solution",
        ),
    }


def test_abstractor_maps_comparison_evidence_to_comparison_story():
    from hermes.application.reference_pattern_abstractor import (
        ReferencePatternAbstractor,
    )

    reference = _reference(
        title="Mouse A versus Mouse B",
        caption="Compare comfort, controls, and desk space before the verdict.",
    )

    result = ReferencePatternAbstractor().abstract((reference,))[0]

    assert result.hook == "comparative evaluation"
    assert result.story == "criteria-comparison-verdict"
    assert "comparison" in result.provenance["matched_signals"]
