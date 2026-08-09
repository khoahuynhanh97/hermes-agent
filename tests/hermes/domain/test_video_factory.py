import pytest

from hermes.domain.video_factory import Claim, ClaimStatus, CreativeBrief, Scene, ScenePlan


def test_scene_plan_requires_contiguous_order_and_calculates_duration():
    plan = ScenePlan((Scene("s1", 1, "Hook", "orient", "show", "open", 3),
                      Scene("s2", 2, "Demo", "prove", "demo", "turn", 5)))
    assert plan.total_duration_seconds == 8

    with pytest.raises(ValueError, match="contiguous"):
        ScenePlan((Scene("s1", 1, "Hook", "orient", "show", "open", 3),
                   Scene("s3", 3, "End", "close", "cta", "point", 2)))


def test_claim_requires_reason_when_not_usable():
    with pytest.raises(ValueError, match="reason"):
        Claim("unverified promise", ClaimStatus.UNSUPPORTED)


def test_brief_is_not_a_scene_plan():
    brief = CreativeBrief("sell", "makers", "save time", "direct", "fast", "buy",
                          ("hook", "demo"),
                          (Claim("has a timer", ClaimStatus.VERIFIED, ("product-1",)),))
    assert not hasattr(brief, "scenes")
