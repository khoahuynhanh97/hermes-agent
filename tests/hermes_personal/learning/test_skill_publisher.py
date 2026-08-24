from __future__ import annotations

import json
from pathlib import Path
import pytest

from hermes_personal.learning.models import (
    EvidenceRef,
    LearningCandidate,
    LearningVersion,
)
from hermes_personal.learning.skill_publisher import ProceduralSkillPublisher


@pytest.fixture
def publisher(tmp_path):
    return ProceduralSkillPublisher(output_dir=tmp_path / "skills")


def sample_evidence():
    return EvidenceRef(
        evidence_id="ev_sp1",
        source_type="workflow",
        source_id="wf_1",
        digest="sha256:001122",
        excerpt="procedure steps executed",
    )


def test_publish_procedural_skill(publisher, tmp_path):
    cand = LearningCandidate(
        candidate_id="cand_proc_1",
        owner_user_id="user1",
        kind="procedure",
        title="Product Research Pipeline",
        content="1. Fetch product metadata.\n2. Query competitor pricing.\n3. Generate summary.",
        evidence=(sample_evidence(),),
        status="approved",
    )
    version = LearningVersion(
        version_id="v_proc_1",
        candidate_id="cand_proc_1",
        owner_user_id="user1",
        version=1,
        content=cand.content,
        digest="sha256:feedbeef",
        status="active",
    )

    active_skill_file = publisher.publish(cand, version)
    assert active_skill_file.exists()
    assert active_skill_file.name == "SKILL.md"

    content = active_skill_file.read_text(encoding="utf-8")
    assert "name: product-research-pipeline" in content
    assert "description: Product Research Pipeline" in content
    assert "version: 1" in content
    assert "owner: user1" in content
    assert "allowed-capabilities:" in content
    assert "product.research" in content

    # Check versioned directory
    versioned_file = tmp_path / "skills" / "product-research-pipeline" / "versions" / "1" / "SKILL.md"
    assert versioned_file.exists()

    # Check manifest
    manifest_file = tmp_path / "skills" / "product-research-pipeline" / "manifest.json"
    assert manifest_file.exists()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["active_version"] == 1
    assert manifest["candidate_id"] == "cand_proc_1"


def test_publish_rejects_non_procedure_or_inactive(publisher):
    cand_pref = LearningCandidate(
        candidate_id="cand_pref",
        owner_user_id="user1",
        kind="preference",
        title="Style",
        content="Concise answers",
        evidence=(sample_evidence(),),
    )
    v1 = LearningVersion(
        version_id="v1",
        candidate_id="cand_pref",
        owner_user_id="user1",
        version=1,
        content="Concise answers",
        digest="sha256:123",
        status="active",
    )
    with pytest.raises(ValueError, match="Only procedure candidates"):
        publisher.publish(cand_pref, v1)

    cand_proc = LearningCandidate(
        candidate_id="cand_proc_inact",
        owner_user_id="user1",
        kind="procedure",
        title="Scaling Pipeline",
        content="Steps to scale",
        evidence=(sample_evidence(),),
    )
    v_rev = LearningVersion(
        version_id="v2",
        candidate_id="cand_proc_inact",
        owner_user_id="user1",
        version=2,
        content="Steps to scale",
        digest="sha256:456",
        status="revoked",
    )
    with pytest.raises(ValueError, match="Only active versions"):
        publisher.publish(cand_proc, v_rev)


def test_publish_rejects_unsafe_code(publisher):
    cand_unsafe = LearningCandidate(
        candidate_id="cand_unsafe",
        owner_user_id="user1",
        kind="procedure",
        title="Cleanup Procedure",
        content="Run rm -rf /tmp/test to clean up cache",
        evidence=(sample_evidence(),),
        status="approved",
    )
    version = LearningVersion(
        version_id="v_unsafe",
        candidate_id="cand_unsafe",
        owner_user_id="user1",
        version=1,
        content=cand_unsafe.content,
        digest="sha256:bad",
        status="active",
    )
    with pytest.raises(ValueError, match="Unsafe executable command"):
        publisher.publish(cand_unsafe, version)


def test_rollback_publication(publisher, tmp_path):
    cand1 = LearningCandidate(
        candidate_id="cand_rb_skill",
        owner_user_id="user1",
        kind="procedure",
        title="Video Factory Flow",
        content="v1 steps",
        evidence=(sample_evidence(),),
        status="approved",
    )
    v1 = LearningVersion(
        version_id="v1",
        candidate_id="cand_rb_skill",
        owner_user_id="user1",
        version=1,
        content="v1 steps",
        digest="sha256:v1",
        status="active",
    )
    publisher.publish(cand1, v1)

    cand2 = LearningCandidate(
        candidate_id="cand_rb_skill",
        owner_user_id="user1",
        kind="procedure",
        title="Video Factory Flow",
        content="v2 steps",
        evidence=(sample_evidence(),),
        status="approved",
    )
    v2 = LearningVersion(
        version_id="v2",
        candidate_id="cand_rb_skill",
        owner_user_id="user1",
        version=2,
        content="v2 steps",
        digest="sha256:v2",
        status="active",
    )
    publisher.publish(cand2, v2)

    # Rollback to v1
    v1_restored = LearningVersion(
        version_id="v1",
        candidate_id="cand_rb_skill",
        owner_user_id="user1",
        version=1,
        content="v1 steps",
        digest="sha256:v1",
        status="active",
    )
    active_path = publisher.rollback(
        skill_name="video-factory-flow",
        prior_candidate=cand1,
        prior_version=v1_restored,
    )
    assert active_path is not None
    assert "v1 steps" in active_path.read_text(encoding="utf-8")

    # Rollback when no prior version exists
    empty_path = publisher.rollback(skill_name="video-factory-flow")
    assert empty_path is None
    active_file = tmp_path / "skills" / "video-factory-flow" / "SKILL.md"
    assert not active_file.exists()
