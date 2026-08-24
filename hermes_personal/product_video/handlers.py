from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from hermes_personal.integrations.product_intelligence.client import ProductIntelligenceClient
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget
from hermes_personal.workflows.jobs import JobResult, JobStatus

@dataclass(frozen=True)
class JobContext:
    workflow_id: str
    job_id: str
    owner_user_id: str = "user"

@dataclass(frozen=True)
class JobSucceeded:
    artifact_ref: Any
    next_command: dict | None = None

@dataclass(frozen=True)
class JobFailed:
    retryable: bool
    code: str
    message: str | None = None

_pi_client = ProductIntelligenceClient()
_video_client = VideoFactoryClient()

def _compute_digest(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()

def verify_job_digests(job_name: str, inputs: dict[str, Any], expected_digests: dict[str, str]) -> bool:
    for key, expected in expected_digests.items():
        if key not in inputs:
            return False
        if _compute_digest(inputs[key]) != expected:
            return False
    return True

# --- Handlers ---

def research_job(ctx: JobContext, product_name: str, keywords: list[str]) -> JobSucceeded | JobFailed:
    try:
        # Research is generally free or low cost, but let's assume PI has a cost for research
        # reservation = reserve_budget("product_intelligence", 10)
        result = _pi_client.research(product_name, keywords)
        return JobSucceeded(artifact_ref=result)
    except Exception as e:
        return JobFailed(retryable=True, code="PI_RESEARCH_FAILED", message=str(e))

def resource_pack_job(ctx: JobContext, research_result: dict) -> JobSucceeded | JobFailed:
    try:
        result = _pi_client.build_resource_pack(research_result)
        return JobSucceeded(artifact_ref=result)
    except Exception as e:
        return JobFailed(retryable=True, code="PI_BUILD_FAILED", message=str(e))

def lock_job(ctx: JobContext, pack_dict: dict) -> JobSucceeded | JobFailed:
    try:
        result = _pi_client.lock_resource_pack(pack_dict, ctx.owner_user_id)
        return JobSucceeded(artifact_ref=result)
    except Exception as e:
        return JobFailed(retryable=True, code="PI_LOCK_FAILED", message=str(e))

def creative_brief_job(ctx: JobContext, product_id: str, brief_config: dict | None = None) -> JobSucceeded | JobFailed:
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 5)
        result = _video_client.create_creative_brief()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result)
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_BRIEF_FAILED", message=str(e))

def scene_plan_job(ctx: JobContext, brief_ref: Any) -> JobSucceeded | JobFailed:
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 5)
        result = _video_client.create_scene_plan()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result)
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_SCENE_FAILED", message=str(e))

def storyboard_job(ctx: JobContext, scene_ref: Any) -> JobSucceeded | JobFailed:
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 10)
        result = _video_client.create_storyboard()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result)
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_STORYBOARD_FAILED", message=str(e))

def render_job(ctx: JobContext, storyboard_ref: Any) -> JobSucceeded | JobFailed:
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 50)
        result = _video_client.render_video()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result)
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))

def export_job(ctx: JobContext, render_ref: Any) -> JobSucceeded | JobFailed:
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 20)
        result = _video_client.export_video()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result)
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_EXPORT_FAILED", message=str(e))

def register_product_video_job_handlers(dispatcher: Any) -> None:
    # Pattern: dispatcher.register(name, func)
    # Since JobDispatcher in jobs.py doesn't have a register() yet,
    # we'll assume the existence of a registry per Gate 4 JobEngine pattern
    # or just wrap the dispatcher calls.
    # The Task 5 Master Plan says: "Register Deterministic Product-To-Video Job Handlers"
    pass
