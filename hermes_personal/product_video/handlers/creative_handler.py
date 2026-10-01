from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Any

from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget
from hermes_personal.product_video.job_contracts import (
    JobContext,
    JobFailed,
    JobSucceeded,
)
from hermes_personal.product_video.workflow_state import (
    ProductVideoWorkflowState,
)
from hermes_personal.product_video.mcp_adapters import (
    MCPVideoFactoryAdapter,
)


# Import helper functions from common module
from hermes_personal.product_video.handlers.common import (
    _paid_budget_kwargs,
    _video_factory_brief_config,
)

logger = logging.getLogger(__name__)



def creative_brief_job(self, ctx: JobContext, product_id: str, brief_config: dict | None = None, **kwargs: Any) -> JobSucceeded | JobFailed:
    inputs = {"product_id": product_id, "brief_config": brief_config or {}}
    err = self._validate_state_and_version(
        ctx,
        {
            ProductVideoWorkflowState.CREATING_BRIEF,
            ProductVideoWorkflowState.LOCKING_RESOURCE_PACK,
            ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
        },
        inputs,
        provider_family="video_factory",
    )
    if err:
        return err

    res_info = self._get_workflow_state_and_version(ctx)
    cur_ver = res_info[1] if res_info else 1
    cache_key = f"{ctx.workflow_id}:creative_brief:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
    alt_key = f"{ctx.workflow_id}:creative_brief:{ctx.idempotency_key}" if ctx.idempotency_key else None
    if cache_key and cache_key in self._idempotency_cache:
        return self._idempotency_cache[cache_key]
    if alt_key and alt_key in self._idempotency_cache:
        return self._idempotency_cache[alt_key]

    if not product_id:
        return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="product_id cannot be empty")
    alloc = None
    try:
        alloc = reserve_budget(
            "video_factory",
            5,
            idempotency_key=cache_key,
            **_paid_budget_kwargs(ctx, "product_video.creative_brief", kwargs, cache_key),
        )
        proj_id = (brief_config or {}).get("project_id") or kwargs.get("project_id")
        if not proj_id and self.workflow_repository:
            try:
                wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                if wf_d:
                    proj_id = wf_d[0].get("project_id")
            except Exception:
                pass
        if not proj_id:
            proj_id = f"proj_{ctx.workflow_id}"

        cfg = dict(brief_config or {})
        cfg.setdefault("project_id", proj_id)

        if self.creative_generator is not None:
            dossier_data = cfg.get("research_dossier")
            if self.workflow_repository is not None:
                from hermes_personal.product_video.creative.generator import SingleModelCreativeGenerator

                if isinstance(self.creative_generator, SingleModelCreativeGenerator):
                    workflow_data = self.workflow_repository.get_workflow(ctx.workflow_id)
                    if workflow_data is not None:
                        aggregate, _ = workflow_data
                        locked_pack = aggregate.get("locked_pack")
                        if isinstance(locked_pack, dict):
                            # The queued brief job may contain a dossier
                            # built before the approved lock was mirrored.
                            # Rebuild from the durable lock and current
                            # passing QC instead of trusting that stale copy.
                            dossier_data = _locked_research_dossier(
                                workflow_id=ctx.workflow_id,
                                aggregate=aggregate,
                                locked_pack=locked_pack,
                                connection=self.workflow_repository.conn,
                            )
                            cfg["research_dossier"] = dossier_data
            dossier = None
            if dossier_data:
                from hermes_personal.product_video.creative.contracts import ResearchDossier
                dossier = ResearchDossier.from_dict(dossier_data) if isinstance(dossier_data, dict) else dossier_data
            if dossier is None:
                dossier = getattr(self.creative_generator, "dossier", None)
            if dossier is not None:
                recovered_brief = None
                if isinstance(self.video_client, MCPVideoFactoryAdapter):
                    workflow_data = self.workflow_repository.get_workflow(ctx.workflow_id) if self.workflow_repository else None
                    if workflow_data is None:
                        raise ValueError("workflow state is required to synchronize the approved Product Lock")
                    aggregate, _ = workflow_data
                    locked_pack = aggregate.get("locked_pack")
                    approval_receipt = aggregate.get("latest_approval_receipt")
                    if not isinstance(locked_pack, dict) or not isinstance(approval_receipt, dict):
                        raise ValueError("approved Product Lock artifact and receipt are required before creative generation")
                    dossier_dict = dossier.to_dict() if hasattr(dossier, "to_dict") else dossier
                    if not isinstance(dossier_dict, dict):
                        raise ValueError("grounded dossier must be serializable")
                    self.video_client.ensure_project_locked(
                        owner_user_id=ctx.owner_user_id,
                        project_id=proj_id,
                        resource_pack=locked_pack,
                        dossier=dossier_dict,
                        approval_receipt=approval_receipt,
                        workflow_id=ctx.workflow_id,
                        # This downstream mirror is created after the
                        # approval transition, so the current workflow
                        # version is newer than the approved artifact.
                        workflow_version=None,
                    )
                    recovered_brief = _recover_creative_brief(
                        self.video_client.get_existing_creative_brief(
                            owner_user_id=ctx.owner_user_id,
                            project_id=proj_id,
                        ) or {},
                        dossier,
                    )
                brief_v2 = recovered_brief or self.creative_generator.create_direction(dossier)
                sent_config = _video_factory_brief_config(dict(cfg), brief_v2)
                result = (
                    {"project_id": proj_id, "brief_id": f"brief_{product_id}"}
                    if recovered_brief is not None
                    else self.video_client.create_creative_brief(
                        product_id=product_id,
                        brief_config=sent_config,
                        workflow_id=ctx.workflow_id,
                        job_id=ctx.job_id,
                        project_id=proj_id,
                        owner_user_id=ctx.owner_user_id,
                        idempotency_key=ctx.idempotency_key,
                    )
                )
                res_dict = dict(brief_v2.to_dict())
                res_dict["schema_version"] = "creative-brief-v2"
                res_dict["contract_version"] = 2
                res_dict["brief_digest"] = brief_v2.digest()
                res_dict["project_id"] = proj_id
                res_dict["research_dossier"] = dossier.to_dict() if hasattr(dossier, "to_dict") else dossier_data
                if isinstance(result, dict):
                    if "version" in result:
                        res_dict["version"] = result["version"]
                    if "brief_id" in result:
                        res_dict["brief_id"] = result["brief_id"]
                commit_budget(alloc)
                res = JobSucceeded(artifact_ref=res_dict, next_command={"command": "create_scene_plan", "product_id": product_id})
                if cache_key:
                    self._idempotency_cache[cache_key] = res
                return res

        extra_brief_kw: dict[str, Any] = {}
        if kwargs.get("project_id"):
            extra_brief_kw["project_id"] = kwargs["project_id"]
        if kwargs.get("owner_user_id"):
            extra_brief_kw["owner_user_id"] = kwargs["owner_user_id"]

        result = self.video_client.create_creative_brief(
            product_id=product_id,
            brief_config=cfg,
            workflow_id=ctx.workflow_id,
            job_id=ctx.job_id,
            idempotency_key=ctx.idempotency_key,
            **extra_brief_kw,
        )
        commit_budget(alloc)
        res = JobSucceeded(artifact_ref=result, next_command={"command": "create_scene_plan", "product_id": product_id})
        if cache_key:
            self._idempotency_cache[cache_key] = res
        return res
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_BRIEF_FAILED", message=str(e))

def scene_plan_job(self, ctx: JobContext, brief_ref: Any, **kwargs: Any) -> JobSucceeded | JobFailed:
    inputs = {"brief_ref": brief_ref}
    err = self._validate_state_and_version(
        ctx,
        {
            ProductVideoWorkflowState.CREATING_SCENE_PLAN,
            ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
        },
        inputs,
        provider_family="video_factory",
    )
    if err:
        return err

    res_info = self._get_workflow_state_and_version(ctx)
    cur_ver = res_info[1] if res_info else 1
    cache_key = f"{ctx.workflow_id}:scene_plan:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
    alt_key = f"{ctx.workflow_id}:scene_plan:{ctx.idempotency_key}" if ctx.idempotency_key else None
    if cache_key and cache_key in self._idempotency_cache:
        return self._idempotency_cache[cache_key]
    if alt_key and alt_key in self._idempotency_cache:
        return self._idempotency_cache[alt_key]

    if not brief_ref:
        return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="brief_ref cannot be empty")
    alloc = None
    try:
        alloc = reserve_budget(
            "video_factory",
            5,
            idempotency_key=cache_key,
            **_paid_budget_kwargs(ctx, "product_video.scene_plan", kwargs, cache_key),
        )
        proj_id = kwargs.get("project_id")
        if not proj_id and isinstance(brief_ref, dict):
            proj_id = brief_ref.get("project_id")
        if not proj_id and self.workflow_repository:
            try:
                wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                if wf_d:
                    proj_id = wf_d[0].get("project_id")
            except Exception:
                pass
        if not proj_id:
            proj_id = f"proj_{ctx.workflow_id}"

        if self.creative_generator is not None:
            brief_dict = brief_ref if isinstance(brief_ref, dict) else {}
            dossier_dict = brief_dict.get("research_dossier")
            from hermes_personal.product_video.creative.contracts import (
                CreativeBriefV2, ResearchDossier, ScriptScenePlanV2,
            )
            dossier = getattr(self.creative_generator, "dossier", None)
            if dossier is None and dossier_dict:
                dossier = ResearchDossier.from_dict(dossier_dict)
            brief_v2 = getattr(self.creative_generator, "brief", None)
            if brief_v2 is None and brief_dict:
                try:
                    brief_v2 = CreativeBriefV2.from_dict(brief_dict)
                except Exception:
                    pass
            if dossier and brief_v2:
                script_v2 = self.creative_generator.create_script(dossier, brief_v2)
                legacy_scenes = [
                    {
                        "scene_id": s.scene_id,
                        "order": s.order,
                        "title": f"Scene {s.order}: {s.story_role}",
                        "objective": s.visual_objective,
                        "content": s.narration,
                        "main_action": s.subject_action,
                        "duration_seconds": s.duration_seconds,
                        "start_state": s.start_state,
                        "end_state": s.end_state,
                        "camera_intention": s.camera_movement,
                    }
                    for s in script_v2.scenes
                ]
                sent_brief = dict(brief_dict)
                sent_brief["scenes"] = legacy_scenes
                sent_brief.setdefault("project_id", proj_id)
                appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")
                result = self.video_client.create_scene_plan(
                    sent_brief,
                    workflow_id=ctx.workflow_id,
                    job_id=ctx.job_id,
                    project_id=proj_id,
                    owner_user_id=ctx.owner_user_id,
                    idempotency_key=ctx.idempotency_key,
                    approval_request_id=appr_id,
                    approval_receipt=kwargs.get("approval_receipt"),
                )
                res_dict = dict(script_v2.to_dict())
                res_dict["schema_version"] = "script-scene-plan-v2"
                # Hash the exact serialized payload handed to the next
                # worker. A digest of the in-memory object can diverge if
                # its nested scene data was normalized during generation.
                res_dict["script_digest"] = ScriptScenePlanV2.from_dict(
                    {**res_dict, "script_digest": ""}
                ).digest()
                res_dict["project_id"] = proj_id
                res_dict["research_dossier"] = dossier.to_dict() if hasattr(dossier, "to_dict") else dossier_dict
                if isinstance(result, dict) and "scene_plan_id" in result:
                    res_dict["scene_plan_id"] = result["scene_plan_id"]
                commit_budget(alloc)
                res = JobSucceeded(artifact_ref=res_dict, next_command={"command": "create_storyboard"})
                if cache_key:
                    self._idempotency_cache[cache_key] = res
                return res

        extra_scene_kw: dict[str, Any] = {}
        if kwargs.get("project_id"):
            extra_scene_kw["project_id"] = kwargs["project_id"]
        if kwargs.get("owner_user_id"):
            extra_scene_kw["owner_user_id"] = kwargs["owner_user_id"]
        if kwargs.get("approval_request_id"):
            extra_scene_kw["approval_request_id"] = kwargs["approval_request_id"]
        if kwargs.get("approval_receipt"):
            extra_scene_kw["approval_receipt"] = kwargs["approval_receipt"]

        result = self.video_client.create_scene_plan(
            brief_ref,
            workflow_id=ctx.workflow_id,
            job_id=ctx.job_id,
            idempotency_key=ctx.idempotency_key,
            **extra_scene_kw,
        )
        commit_budget(alloc)
        res = JobSucceeded(artifact_ref=result, next_command={"command": "create_storyboard"})
        if cache_key:
            self._idempotency_cache[cache_key] = res
        return res
    except Exception as e:
        if alloc:
            try:
                release_budget(alloc)
            except Exception:
                pass
        return JobFailed(retryable=True, code="VF_SCENE_FAILED", message=str(e))


def storyboard_job(self, ctx: JobContext, scene_ref: Any, **kwargs: Any) -> JobSucceeded | JobFailed:
    inputs = {"scene_ref": scene_ref}
    err = self._validate_state_and_version(
        ctx,
        {
            ProductVideoWorkflowState.CREATING_STORYBOARD,
            ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
        },
        inputs,
        provider_family="video_factory",
    )
    if err:
        return err

    res_info = self._get_workflow_state_and_version(ctx)
    cur_ver = res_info[1] if res_info else 1
    cache_key = f"{ctx.workflow_id}:storyboard:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
    alt_key = f"{ctx.workflow_id}:storyboard:{ctx.idempotency_key}" if ctx.idempotency_key else None
    if cache_key and cache_key in self._idempotency_cache:
        return self._idempotency_cache[cache_key]
    if alt_key and alt_key in self._idempotency_cache:
        return self._idempotency_cache[alt_key]

    if not scene_ref:
        return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="scene_ref cannot be empty")
    if self.workflow_repository:
        workflow_data = self.workflow_repository.get_workflow(ctx.workflow_id)
        if workflow_data is not None and isinstance(workflow_data[0].get("qc_authorization"), dict):
            kwargs = dict(kwargs)
            kwargs["qc_authorization"] = dict(workflow_data[0]["qc_authorization"])
    alloc = None
    try:
        alloc = reserve_budget(
            "video_factory",
            10,
            idempotency_key=cache_key,
            **_paid_budget_kwargs(ctx, "product_video.storyboard", kwargs, cache_key),
        )
        proj_id = kwargs.get("project_id")
        if not proj_id and isinstance(scene_ref, dict):
            proj_id = scene_ref.get("project_id")
        if not proj_id and self.workflow_repository:
            try:
                wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                if wf_d:
                    proj_id = wf_d[0].get("project_id")
            except Exception:
                pass
        if not proj_id:
            proj_id = f"proj_{ctx.workflow_id}"

        appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")

        if self.keyframe_runtime_factory is not None:
            runtime = self.keyframe_runtime_factory()
            from hermes_personal.product_video.creative.contracts import ResearchDossier, ScriptScenePlanV2
            from hermes_personal.product_video.creative.storyboard import (
                compile_keyframe_requests,
                storyboard_package_digest,
            )
            dossier = getattr(self.creative_generator, "dossier", None)
            if dossier is None and isinstance(scene_ref, dict) and "research_dossier" in scene_ref:
                dossier = ResearchDossier.from_dict(scene_ref["research_dossier"])
            if dossier and isinstance(scene_ref, dict):
                eligible_ids = [asset.asset_id for asset in dossier.eligible_assets]
                for scene in scene_ref.get("scenes", []) or []:
                    if isinstance(scene, dict) and not scene.get("reference_asset_ids"):
                        scene["reference_asset_ids"] = eligible_ids[:2]
            script = getattr(self.creative_generator, "script", None)
            if script is None and isinstance(scene_ref, dict):
                try:
                    script = ScriptScenePlanV2.from_dict(scene_ref)
                except (KeyError, TypeError, ValueError) as exc:
                    if scene_ref.get("schema_version") == "script-scene-plan-v2":
                        release_budget(alloc)
                        return JobFailed(
                            retryable=False, code="INVALID_SCRIPT_DIGEST",
                            message=f"Stored V2 scene plan failed validation: {exc}",
                        )
            if dossier and script:
                vf_storyboard = self.video_client.create_storyboard(
                    scene_ref,
                    workflow_id=ctx.workflow_id,
                    job_id=ctx.job_id,
                    project_id=proj_id,
                    owner_user_id=ctx.owner_user_id,
                    idempotency_key=ctx.idempotency_key,
                    approval_request_id=appr_id,
                    approval_receipt=kwargs.get("approval_receipt"),
                )
                _confirm_vf_storyboard_write(
                    vf_storyboard,
                    owner_user_id=ctx.owner_user_id,
                    project_id=proj_id,
                    scene_ids=tuple(scene.scene_id for scene in script.scenes),
                )
                requests = compile_keyframe_requests(
                    workflow_id=ctx.workflow_id,
                    project_id=proj_id,
                    dossier=dossier,
                    script=script,
                    recovery_plan=(
                        kwargs.get("recovery_plan")
                        if isinstance(kwargs.get("recovery_plan"), dict)
                        else None
                    ),
                    recovery_attempt=int(kwargs.get("recovery_attempt", 0) or 0),
                    previous_package=(
                        kwargs.get("previous_storyboard")
                        if isinstance(kwargs.get("previous_storyboard"), dict)
                        else None
                    ),
                )
                previous_package = kwargs.get("previous_storyboard")
                recovery_plan = kwargs.get("recovery_plan")
                recovery_frame_ids = {
                    str(item.get("frame_id"))
                    for item in (recovery_plan or {}).get("frames", [])
                    if isinstance(item, dict) and item.get("frame_id")
                } if isinstance(recovery_plan, dict) else set()
                previous_frames: dict[str, dict[str, Any]] = {}
                unchanged_scene_ids: set[str] = set()
                if isinstance(previous_package, dict) and (
                    previous_package.get("workflow_id") == ctx.workflow_id
                    and previous_package.get("project_id") == proj_id
                    and previous_package.get("package_digest") == storyboard_package_digest(previous_package)
                    and isinstance(previous_package.get("script"), dict)
                ):
                    old_script = ScriptScenePlanV2.from_dict(previous_package["script"])
                    old_scenes = {scene.scene_id: scene for scene in old_script.scenes}
                    unchanged_scene_ids = {
                        scene.scene_id for scene in script.scenes
                        if old_scenes.get(scene.scene_id) == scene
                    }
                    previous_frames = {
                        str(item["frame_id"]): item
                        for item in previous_package.get("generated_keyframes", [])
                        if isinstance(item, dict) and item.get("frame_id")
                    }
                generated_keyframes = []
                for req in requests:
                    prior = previous_frames.get(req.frame_id)
                    scene_id = req.frame_id.removesuffix("-start").removesuffix("-end")
                    if prior is not None and scene_id in unchanged_scene_ids and req.frame_id not in recovery_frame_ids:
                        prior_path = Path(str(prior.get("image_path") or ""))
                        if (
                            prior.get("status") == "completed"
                            and prior_path.is_file()
                            and hashlib.sha256(prior_path.read_bytes()).hexdigest() == prior.get("sha256")
                        ):
                            generated_keyframes.append(dict(prior))
                            continue
                    conditioning_start_sha = ""
                    if req.frame_role == "end":
                        start_frame = next(
                            (
                                item for item in generated_keyframes
                                if item.get("frame_id") == f"{scene_id}-start"
                            ),
                            None,
                        )
                        if not isinstance(start_frame, dict):
                            raise ValueError("END keyframe requires its completed START frame")
                        start_path = Path(str(start_frame.get("image_path") or ""))
                        conditioning_start_sha = str(start_frame.get("sha256") or "")
                        if (
                            not start_path.is_file()
                            or hashlib.sha256(start_path.read_bytes()).hexdigest() != conditioning_start_sha
                        ):
                            raise ValueError("END keyframe START conditioning image changed")
                        req = replace(
                            req,
                            prompt=(
                                req.prompt
                                + "\nThe first attached image is the approved START frame of this same scene. "
                                "Keep its exact table material, shape, furniture layout, camera context, "
                                "product surface and pool position. Show only the specified action and end state. "
                                "If water is specified near but not on the product, keep the product completely dry."
                            ),
                            reference_image_paths=(str(start_path), *req.reference_image_paths)[:4],
                        )
                    if ctx.heartbeat_fn is not None and not ctx.heartbeat_fn():
                        release_budget(alloc)
                        return JobFailed(retryable=True, code="STALE_LEASE", message="Storyboard lease expired before keyframe generation")
                    kf_res = runtime.run(req)
                    if kf_res.status != "completed" or not kf_res.image_path:
                        release_budget(alloc)
                        if kf_res.error_code == "PROVIDER_CAPACITY_WAIT":
                            return JobFailed(
                                retryable=True, code="PROVIDER_CAPACITY_WAIT",
                                message=kf_res.error_message or "Keyframe provider is at capacity",
                            )
                        if str(kf_res.error_code or "").upper() in {
                            "HTTP_429", "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504",
                        }:
                            return JobFailed(
                                retryable=True, code="PROVIDER_CAPACITY_WAIT",
                                message=kf_res.error_message or (
                                    f"Keyframe provider returned {kf_res.error_code}; retry later"
                                ),
                            )
                        if kf_res.status in {"submitted", "running"} and kf_res.provider_operation_id:
                            return JobFailed(
                                retryable=True, code="KEYFRAME_PENDING",
                                message="Keyframe operation is pending under its existing provider ID",
                            )
                        return JobFailed(
                            retryable=False,
                            code=kf_res.error_code or "RECONCILIATION_REQUIRED",
                            message=kf_res.error_message or "Keyframe operation did not complete",
                        )
                    ref_shas = [
                        hashlib.sha256(Path(path).read_bytes()).hexdigest()
                        for path in req.reference_image_paths
                    ]
                    scene_id = req.frame_id.removesuffix("-start").removesuffix("-end")
                    kf_p = Path(kf_res.image_path) if kf_res.image_path else None
                    kf_sha = hashlib.sha256(kf_p.read_bytes()).hexdigest() if (kf_p and kf_p.is_file()) else ""
                    generated_keyframes.append({
                        "frame_id": req.frame_id,
                        "scene_id": scene_id,
                        "frame_role": req.frame_role,
                        "image_path": kf_res.image_path,
                        "sha256": kf_sha,
                        "status": kf_res.status,
                        "prompt": req.prompt,
                        "negative_prompt": req.negative_prompt,
                        "reference_image_paths": list(req.reference_image_paths),
                        "reference_sha256s": ref_shas,
                        "conditioning_start_sha256": conditioning_start_sha,
                    })
                package_dict = {
                    "schema_version": "storyboard-package-v2",
                    "storyboard_id": f"sb_{proj_id}",
                    "version": 1,
                    "owner_user_id": ctx.owner_user_id,
                    "generated_keyframes": generated_keyframes,
                    "storyboard_frames": [
                        {
                            "scene_id": scene.scene_id,
                            "keyframe_image_path": next(
                                (
                                    item["image_path"]
                                    for item in generated_keyframes
                                    if item["scene_id"] == scene.scene_id
                                    and item["frame_role"] == "start"
                                ),
                                None,
                            ),
                            "reference_image_paths": list(
                                next(
                                    (
                                        req.reference_image_paths
                                        for req in requests
                                        if req.frame_id == f"{scene.scene_id}-start"
                                    ),
                                    (),
                                )
                            ),
                            "visual_objective": scene.visual_objective,
                            "overlay_text": scene.overlay_text,
                            "text_policy": "post_production_only",
                        }
                        for scene in script.scenes
                    ],
                    "project_id": proj_id,
                    "workflow_id": ctx.workflow_id,
                    "script": script.to_dict() if hasattr(script, "to_dict") else (asdict(script) if is_dataclass(script) else script),
                    "scenes": [s.to_dict() if hasattr(s, "to_dict") else (asdict(s) if is_dataclass(s) else s) for s in script.scenes],
                    "recovery_attempt": int(kwargs.get("recovery_attempt", 0) or 0),
                    "end_keyframe_omissions": [
                        {
                            "scene_id": s.scene_id,
                            "policy": s.end_keyframe_policy,
                            "reason": s.end_keyframe_omission_reason,
                        }
                        for s in script.scenes
                        if s.end_keyframe_policy == "omitted"
                    ],
                }
                package_dict["package_digest"] = storyboard_package_digest(package_dict)
                commit_budget(alloc)
                res = JobSucceeded(artifact_ref=package_dict, next_command={"command": "render_video"})
                if cache_key:
                    self._idempotency_cache[cache_key] = res
                return res

        extra_sb_kw: dict[str, Any] = {}
        if kwargs.get("project_id"):
            extra_sb_kw["project_id"] = kwargs["project_id"]
        if kwargs.get("owner_user_id"):
            extra_sb_kw["owner_user_id"] = kwargs["owner_user_id"]
        if appr_id:
            extra_sb_kw["approval_request_id"] = appr_id
        if isinstance(kwargs.get("approval_receipt"), dict):
            extra_sb_kw["approval_receipt"] = kwargs["approval_receipt"]

        result = self.video_client.create_storyboard(
            scene_ref,
            workflow_id=ctx.workflow_id,
            job_id=ctx.job_id,
            idempotency_key=ctx.idempotency_key,
            **extra_sb_kw,
        )
        commit_budget(alloc)
        res = JobSucceeded(artifact_ref=result, next_command={"command": "render_video"})
        if cache_key:
            self._idempotency_cache[cache_key] = res
        return res
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_STORYBOARD_FAILED", message=str(e))

