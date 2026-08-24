from __future__ import annotations
import pytest
from hermes_personal.product_video.handlers import (
    JobContext,
    JobSucceeded,
    JobFailed,
    research_job,
    resource_pack_job,
    lock_job,
    creative_brief_job,
    scene_plan_job,
    storyboard_job,
    render_job,
    export_job,
    verify_job_digests,
    _compute_digest
)
from hermes_personal.workflows.budgets import init_default_engine, BudgetPolicy

@pytest.fixture(autouse=True)
def setup_budget():
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))

def test_research_job():
    ctx = JobContext(workflow_id="wf1", job_id="j1")
    result = research_job(ctx, "Smart Watch", ["health", "fitness"])
    assert isinstance(result, JobSucceeded)
    assert "summary" in result.artifact_ref

def test_resource_pack_job():
    ctx = JobContext(workflow_id="wf1", job_id="j2")
    research_result = {"report": '{"product_name": "Watch", "keywords": ["fitness"]}'}
    result = resource_pack_job(ctx, research_result)
    assert isinstance(result, JobSucceeded)
    assert "assets_mapping" in result.artifact_ref

def test_lock_job():
    ctx = JobContext(workflow_id="wf1", job_id="j3")
    pack_dict = {"summary": "test pack", "assets_mapping": {"a1": "url1"}}
    result = lock_job(ctx, pack_dict)
    assert isinstance(result, JobSucceeded)
    assert result.artifact_ref["status"] == "locked"

def test_creative_brief_job():
    ctx = JobContext(workflow_id="wf1", job_id="j4")
    result = creative_brief_job(ctx, "p1")
    assert isinstance(result, JobSucceeded)
    assert "artifact_ref" in result.artifact_ref

def test_scene_plan_job():
    ctx = JobContext(workflow_id="wf1", job_id="j5")
    result = scene_plan_job(ctx, "brief_ref")
    assert isinstance(result, JobSucceeded)

def test_storyboard_job():
    ctx = JobContext(workflow_id="wf1", job_id="j6")
    result = storyboard_job(ctx, "scene_ref")
    assert isinstance(result, JobSucceeded)

def test_render_job():
    ctx = JobContext(workflow_id="wf1", job_id="j7")
    result = render_job(ctx, "story_ref")
    assert isinstance(result, JobSucceeded)

def test_export_job():
    ctx = JobContext(workflow_id="wf1", job_id="j8")
    result = export_job(ctx, "render_ref")
    assert isinstance(result, JobSucceeded)

def test_job_idempotency_via_deterministic_clients():
    ctx = JobContext(workflow_id="wf1", job_id="j9")
    res1 = creative_brief_job(ctx, "p1")
    res2 = creative_brief_job(ctx, "p1")
    assert res1.artifact_ref["artifact_ref"] == res2.artifact_ref["artifact_ref"]

def test_verify_job_digests():
    data = {"key": "value"}
    digest = _compute_digest(data)
    assert verify_job_digests("test", {"key": data}, {"key": digest}) is True
    assert verify_job_digests("test", {"key": data}, {"key": "wrong"}) is False

def test_budget_exhaustion_fails_job():
    init_default_engine(BudgetPolicy(max_total=10, per_channel={"video_factory": 5}))
    ctx = JobContext(workflow_id="wf1", job_id="j10")
    # Render job requires 50
    result = render_job(ctx, "story_ref")
    assert isinstance(result, JobFailed)
    assert result.code == "VF_RENDER_FAILED"
