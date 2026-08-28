from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from hermes_personal.integrations.product_intelligence.client import ProductIntelligenceClient
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.workflows.approvals import ApprovalService
from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.envelope import (
    MalformedEnvelopeError,
    OutboxEnvelope,
    build_envelope,
)
from hermes_personal.workflows.jobs import JobDispatcher, JobResult, JobSpec, JobStatus
from hermes_personal.workflows.repository import WorkflowRepository


class ProductVideoWorkflowState(str, Enum):
    IDLE = "idle"
    RESEARCHING = "researching"
    AWAITING_PRODUCT_LOCK = "AwaitingProductLock"
    BUILDING_RESOURCE_PACK = "building_resource_pack"
    CREATING_BRIEF = "creating_brief"
    AWAITING_BRIEF_APPROVAL = "AwaitingBriefApproval"
    CREATING_SCENE_PLAN = "creating_scene_plan"
    AWAITING_SCENE_APPROVAL = "AwaitingSceneApproval"
    CREATING_STORYBOARD = "creating_storyboard"
    AWAITING_STORYBOARD_APPROVAL = "AwaitingStoryboardApproval"
    RENDERING = "rendering"
    AWAITING_FINAL_APPROVAL = "AwaitingFinalApproval"
    EXPORTING = "exporting"
    COMPLETED = "completed"


HITL_WAITING_STATES = {
    ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
    ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
    ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
    ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
    ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
}


def validate_provider_mode(mode: Any) -> str:
    if isinstance(mode, bool) or not isinstance(mode, str):
        raise ValueError(f"Invalid provider_mode type {type(mode).__name__}: {mode!r}. Must be 'configured' or 'fake'.")
    normalized = mode.strip().lower()
    if not normalized:
        raise ValueError("Invalid provider_mode: empty string. Must be strictly 'configured' or 'fake'.")
    if normalized not in ("configured", "fake"):
        raise ValueError(f"Invalid provider_mode '{mode}'. Must be strictly 'configured' or 'fake'.")
    return normalized


def resolve_provider_mode(
    cli_arg: Any = None,
    config: dict[str, Any] | None = None,
    env_val: Any = None,
) -> str:
    """Resolve provider_mode explicitly across sources without truthiness fallback."""
    cfg = config or {}
    wf_cfg = cfg.get("workflows") if isinstance(cfg.get("workflows"), dict) else {}

    if cli_arg is not None:
        return validate_provider_mode(cli_arg)
    if "provider_mode" in cfg and cfg["provider_mode"] is not None:
        return validate_provider_mode(cfg["provider_mode"])
    if "provider_mode" in wf_cfg and wf_cfg["provider_mode"] is not None:
        return validate_provider_mode(wf_cfg["provider_mode"])
    if env_val is not None:
        return validate_provider_mode(env_val)
    return "configured"


def validate_polling_setting(name: str, value: Any, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"Invalid {name} type bool: {value!r}. Must be a positive number.")
    try:
        val = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {name} value: {value!r}. Must be a positive number.")
    import math
    if math.isnan(val) or math.isinf(val) or val <= 0:
        raise ValueError(f"Invalid {name} value {val}. Must be finite and > 0.")
    return val


def resolve_polling_setting(
    name: str,
    cli_val: Any = None,
    cfg_val: Any = None,
    default: float = 60.0,
) -> float:
    """Resolve polling setting explicitly across sources without truthiness fallback."""
    if cli_val is not None:
        return validate_polling_setting(name, cli_val, default)
    if cfg_val is not None:
        return validate_polling_setting(name, cfg_val, default)
    return default


@dataclass(frozen=True)
class JobContext:
    workflow_id: str
    job_id: str
    owner_user_id: str = "user"
    expected_version: int | None = None
    expected_digests: dict[str, str] | None = None
    idempotency_key: str | None = None
    heartbeat_fn: Callable[[], bool] | None = None


@dataclass(frozen=True)
class JobSucceeded:
    artifact_ref: Any
    next_command: dict | None = None


@dataclass(frozen=True)
class JobFailed:
    retryable: bool
    code: str
    message: str | None = None


class JobDispatchError(RuntimeError):
    """Base error for job dispatch failures."""
    def __init__(self, message: str, code: str = "JOB_FAILED", retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class TerminalJobError(JobDispatchError):
    """Non-retryable terminal job error requiring quarantine and operator intervention."""
    def __init__(self, message: str, code: str = "TERMINAL_JOB_ERROR"):
        super().__init__(message, code=code, retryable=False)


class LeaseLostError(JobDispatchError):
    """Raised when lease renewal fails / lease is lost to another worker."""
    def __init__(self, message: str = "Lease lost during execution"):
        super().__init__(message, code="LEASE_LOST", retryable=False)


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


def _get_global_tool_registry() -> Any | None:
    try:
        from tools.registry import registry
        return registry
    except ImportError:
        return None


def _get_tool_names_from_registry(registry: Any) -> set[str]:
    if hasattr(registry, "get_all_tool_names"):
        return set(registry.get_all_tool_names())
    if hasattr(registry, "get_all_entries"):
        return {entry.name for entry in registry.get_all_entries()}
    if isinstance(registry, dict):
        return set(registry.keys())
    return set()


def _check_for_errors(obj: Any) -> None:
    if isinstance(obj, dict):
        if obj.get("status") in ("failed", "error", "cancelled"):
            err_msg = obj.get("error") or obj.get("message") or f"Operation terminated with status '{obj.get('status')}'"
            raise TerminalJobError(f"Tool operation failed with status '{obj.get('status')}': {err_msg}", code="TOOL_OPERATION_TERMINAL_FAILED")

        if obj.get("isError") is True or obj.get("is_error") is True:
            err_text = ""
            if isinstance(obj.get("content"), list):
                err_text = " ".join(
                    item.get("text", "") for item in obj["content"] if isinstance(item, dict) and item.get("type") == "text"
                )
            err_text = err_text or obj.get("error") or obj.get("message") or "MCP tool reported an error"
            raise RuntimeError(f"MCP tool error: {err_text}")

        if "error" in obj and obj["error"]:
            raise RuntimeError(f"Tool error: {obj['error']}")


def _decode_mcp_output(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {"output": raw}

    _check_for_errors(raw)

    if isinstance(raw, dict):
        # If structuredContent is present, use it as primary structured payload
        if isinstance(raw.get("structuredContent"), dict):
            res = dict(raw["structuredContent"])
            _check_for_errors(res)
            if "_meta" in raw:
                res["_meta"] = raw["_meta"]
            return res

        # If content list is present (e.g. standard MCP CallToolResult format)
        if isinstance(raw.get("content"), list):
            for block in raw["content"]:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    text_val = block["text"]
                    try:
                        parsed_block = json.loads(text_val)
                        if isinstance(parsed_block, dict):
                            _check_for_errors(parsed_block)
                            return parsed_block
                    except json.JSONDecodeError:
                        return {"output": text_val}

        # If result field is present
        if "result" in raw:
            res_val = raw["result"]
            if isinstance(res_val, dict):
                _check_for_errors(res_val)
                return res_val
            if isinstance(res_val, str):
                try:
                    parsed_res = json.loads(res_val)
                    if isinstance(parsed_res, dict):
                        _check_for_errors(parsed_res)
                        return parsed_res
                except json.JSONDecodeError:
                    return {"output": res_val}

        return raw

    return {"output": str(raw)}


def _dispatch_tool(registry: Any, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if hasattr(registry, "dispatch"):
        raw = registry.dispatch(tool_name, payload)
    elif isinstance(registry, dict) and callable(registry.get(tool_name)):
        raw = registry[tool_name](payload)
    else:
        raise RuntimeError(f"Tool '{tool_name}' cannot be dispatched on registry {registry!r}")

    decoded = _decode_mcp_output(raw)
    if not decoded:
        raise RuntimeError(f"Tool '{tool_name}' returned empty response")
    _check_for_errors(decoded)
    return decoded


class MCPProductIntelligenceAdapter:
    """Live provider adapter bridging ProductVideoJobHandlers to real/MCP ProductIntelligence tools."""

    def __init__(self, registry: Any, wire_tools: dict[str, str]) -> None:
        self.registry = registry
        self.wire_tools = wire_tools

    def research(
        self,
        product_name: str,
        keywords: list[str],
        pdp_url: str | None = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        tool_name = self.wire_tools.get("research", "mcp__product_intelligence__research_product")

        # Deterministic space-join for query from keywords
        query = " ".join(k.strip() for k in keywords if k and k.strip()) if keywords else None

        # Mapped outgoing payload conforming strictly to located server signature:
        # url from pdp_url, product_name, query from keywords
        # Do NOT send unsupported 'keywords' or 'pdp_url' keys to the server
        payload: dict[str, Any] = {}
        if product_name:
            payload["product_name"] = product_name
        if pdp_url:
            payload["url"] = pdp_url
        if query:
            payload["query"] = query

        raw = _dispatch_tool(self.registry, tool_name, payload)

        # Extract snapshot_id and persistence_status strictly from raw result
        # Do NOT relabel generic id/research_id as snapshot_id or infer persistence from an ID
        snapshot_id = raw.get("snapshot_id")
        persistence_status = raw.get("persistence_status")
        research_status = raw.get("status")

        if research_status in ("failed", "error", "cancelled"):
            err_msg = raw.get("error") or raw.get("reason") or f"Research failed with status '{research_status}'"
            raise TerminalJobError(f"PI research operation failed: {err_msg}", code="PI_RESEARCH_FAILED")

        # Validate that persistence is explicit and successful (service returns 'saved' or 'persisted')
        if not snapshot_id:
            raise TerminalJobError("PI research tool returned no snapshot_id", code="MISSING_SNAPSHOT_ID")

        if persistence_status not in ("saved", "persisted"):
            raise TerminalJobError(
                f"PI research persistence unsuccessful or unconfirmed (persistence_status={persistence_status!r})",
                code="PERSISTENCE_FAILED",
            )

        # Serialized report text for report field
        report_data = raw.get("report") or raw
        if isinstance(report_data, dict):
            report_str = json.dumps(report_data)
        else:
            report_str = str(report_data)

        if not report_str.strip() or report_str == "{}":
            raise TerminalJobError(f"Tool '{tool_name}' returned empty research report", code="EMPTY_RESEARCH_REPORT")

        return {
            "owner": "product_intelligence",
            "schema": "product_research_result",
            "version": 1,
            "product_name": product_name,
            "keywords": keywords,
            "pdp_url": pdp_url,
            "report": report_str,
            "snapshot_id": str(snapshot_id),
            "persistence_status": persistence_status,
            "research_id": raw.get("research_id"),
            "canonical_products": raw.get("canonical_products", []),
            "media_assets": raw.get("media_assets", []),
            "raw_result": raw,
            "external_provider_id": raw.get("id") or raw.get("external_id") or str(snapshot_id),
        }

    def build_resource_pack(
        self,
        research_result: dict,
        variant_id: str | None = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        tool_name = self.wire_tools.get("build_resource_pack")
        if not tool_name or tool_name not in _get_tool_names_from_registry(self.registry):
            raise RuntimeError(
                "MISSING_PROVIDER_CONFIG: Wire tool for 'product.resource_pack.build' is not registered in ToolRegistry. "
                "Fails closed without generating mock assets in configured mode."
            )

        # Validate snapshot_id and persistence_status prerequisites strictly
        snapshot_id = research_result.get("snapshot_id")
        persistence_status = research_result.get("persistence_status")
        if not snapshot_id:
            raise TerminalJobError("Cannot build resource pack: missing snapshot_id in research_result", code="MISSING_SNAPSHOT_ID")
        if persistence_status not in ("saved", "persisted"):
            raise TerminalJobError(
                f"Cannot build resource pack: research snapshot is not successfully persisted (persistence_status={persistence_status!r})",
                code="PERSISTENCE_FAILED",
            )

        payload: dict[str, Any] = {"snapshot_id": str(snapshot_id)}
        if variant_id:
            payload["variant_id"] = str(variant_id)

        raw = _dispatch_tool(self.registry, tool_name, payload)

        status_val = raw.get("status")
        if status_val == "not_found":
            raise TerminalJobError(f"Resource pack build failed: snapshot '{snapshot_id}' not found by provider", code="SNAPSHOT_NOT_FOUND")
        if status_val in ("failed", "error", "cancelled"):
            err_msg = raw.get("error") or raw.get("reason") or f"status '{status_val}'"
            raise TerminalJobError(f"Resource pack build failed: {err_msg}", code="PI_PACK_BUILD_FAILED")

        pack_id = raw.get("resource_pack_id")
        if not pack_id:
            raise TerminalJobError(f"Tool '{tool_name}' returned resource pack without resource_pack_id: {raw!r}", code="MISSING_PACK_ID")

        pack_status = raw.get("pack_status") or raw.get("status")
        if not pack_status:
            raise TerminalJobError(f"Tool '{tool_name}' returned resource pack without pack_status", code="MISSING_PACK_STATUS")

        return {
            "owner": "product_intelligence",
            "schema": "product_resource_pack",
            "version": 1,
            "resource_pack_id": str(pack_id),
            "pack_status": str(pack_status),
            "canonical_product_id": raw.get("canonical_product_id"),
            "variant_id": raw.get("variant_id") or variant_id,
            "snapshot_id": str(snapshot_id),
            "summary": raw.get("summary", ""),
            "media_count": raw.get("media_count", len(raw.get("assets", []) or raw.get("assets_mapping", []))),
            "claims": raw.get("claims", []),
            "restrictions": raw.get("restrictions", []),
            "completeness": raw.get("completeness", {}),
            "assets_mapping": raw.get("assets_mapping") or raw.get("assets", {}),
            "scene_plan": raw.get("scene_plan", []),
            "raw_result": raw,
            "external_provider_id": raw.get("id") or raw.get("external_id") or str(pack_id),
        }

    def lock_resource_pack(
        self,
        pack_dict: dict,
        owner_user_id: str | None = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not owner_user_id or not str(owner_user_id).strip():
            raise TerminalJobError("Cannot lock resource pack: explicit owner_user_id is required", code="MISSING_OWNER")

        resource_pack_id = pack_dict.get("resource_pack_id")
        if not resource_pack_id:
            raise TerminalJobError("Cannot lock resource pack: missing resource_pack_id in pack_dict", code="MISSING_PACK_ID")

        pack_status = pack_dict.get("pack_status")
        if pack_status != "ready_to_lock":
            raise TerminalJobError(
                f"Cannot lock resource pack with status '{pack_status}': only 'ready_to_lock' status is lockable",
                code="NON_LOCKABLE_STATUS",
            )

        tool_name = self.wire_tools.get("lock_resource_pack")
        if not tool_name or tool_name not in _get_tool_names_from_registry(self.registry):
            raise RuntimeError(
                "MISSING_PROVIDER_CONFIG: Wire tool for 'product.resource_pack.lock' is not registered in ToolRegistry. "
                "Fails closed without generating mock lock in configured mode."
            )

        effective_owner = str(owner_user_id).strip()
        payload = {
            "resource_pack_id": str(resource_pack_id),
            "owner_user_id": effective_owner,
        }

        raw = _dispatch_tool(self.registry, tool_name, payload)

        status_val = raw.get("status")
        if status_val == "not_found":
            raise TerminalJobError(f"Resource pack lock failed: resource_pack '{resource_pack_id}' not found by provider", code="PACK_NOT_FOUND")
        if status_val in ("failed", "error", "cancelled"):
            err_msg = raw.get("error") or raw.get("reason") or f"status '{status_val}'"
            raise TerminalJobError(f"Resource pack lock failed: {err_msg}", code="PI_PACK_LOCK_FAILED")

        lock_id = raw.get("lock_id") or raw.get("id")
        if not lock_id:
            raise TerminalJobError(f"Tool '{tool_name}' returned lock without lock_id: {raw!r}", code="MISSING_LOCK_ID")

        # Validate returned owner matches requested owner
        ret_owner = raw.get("owner_user_id")
        if ret_owner and ret_owner != effective_owner:
            raise TerminalJobError(
                f"Resource pack lock owner mismatch: requested '{effective_owner}', provider returned '{ret_owner}'",
                code="OWNER_MISMATCH",
            )

        # Validate returned pack ID matches requested pack ID
        ret_pack_id = raw.get("resource_pack_id")
        if ret_pack_id and ret_pack_id != str(resource_pack_id):
            raise TerminalJobError(
                f"Resource pack lock ID mismatch: requested '{resource_pack_id}', provider returned '{ret_pack_id}'",
                code="PACK_ID_MISMATCH",
            )

        # Validate snapshot_id and canonical_product_id match input pack if returned
        ret_snapshot = raw.get("snapshot_id")
        expected_snapshot = pack_dict.get("snapshot_id")
        if ret_snapshot and expected_snapshot and ret_snapshot != expected_snapshot:
            raise TerminalJobError(
                f"Resource pack lock snapshot mismatch: pack has '{expected_snapshot}', provider returned '{ret_snapshot}'",
                code="SNAPSHOT_MISMATCH",
            )

        ret_product = raw.get("canonical_product_id")
        expected_product = pack_dict.get("canonical_product_id")
        if ret_product and expected_product and ret_product != expected_product:
            raise TerminalJobError(
                f"Resource pack lock product mismatch: pack has '{expected_product}', provider returned '{ret_product}'",
                code="PRODUCT_MISMATCH",
            )

        manifest_digest = raw.get("manifest_digest")
        if not manifest_digest:
            raise TerminalJobError(f"Tool '{tool_name}' returned lock without manifest_digest: {raw!r}", code="MISSING_MANIFEST_DIGEST")

        assets = raw.get("assets") or raw.get("assets_mapping")
        if not assets:
            raise TerminalJobError(f"Tool '{tool_name}' returned lock without valid assets", code="MISSING_ASSETS")

        return {
            "owner": "product_intelligence",
            "schema": "product_resource_pack_locked",
            "version": raw.get("version", 1),
            "lock_id": str(lock_id),
            "resource_pack_id": str(resource_pack_id),
            "snapshot_id": ret_snapshot or expected_snapshot,
            "canonical_product_id": ret_product or expected_product,
            "variant_id": pack_dict.get("variant_id"),
            "owner_user_id": effective_owner,
            "manifest_digest": str(manifest_digest),
            "created_at": raw.get("created_at") or datetime.now(timezone.utc).isoformat(),
            "status": "locked",
            "summary": pack_dict.get("summary", ""),
            "assets": assets,
            "assets_mapping": assets if isinstance(assets, dict) else {a.get("asset_id", f"asset_{i}"): a.get("local_path", "") for i, a in enumerate(assets)},
            "scene_plan": pack_dict.get("scene_plan", []),
            "raw_result": raw,
            "external_provider_id": raw.get("id") or raw.get("external_id") or str(lock_id),
        }


class MCPVideoFactoryAdapter:
    """Live provider adapter bridging ProductVideoJobHandlers to real/MCP VideoFactory tools."""

    def __init__(self, registry: Any, wire_tools: dict[str, str], poll_timeout: float = 60.0, poll_interval: float = 0.5) -> None:
        self.registry = registry
        self.wire_tools = wire_tools
        self.poll_timeout = poll_timeout
        self.poll_interval = poll_interval

    @staticmethod
    def _run_heartbeat(heartbeat_fn: Callable[[], bool] | None, job_id_val: str, stage: str, poll_interval: float = 0.0) -> None:
        if heartbeat_fn is None:
            if poll_interval:
                time.sleep(poll_interval)
            return
        try:
            hb_ok = heartbeat_fn()
        except Exception as exc:
            raise LeaseLostError(f"Heartbeat failure during async video {stage} job '{job_id_val}' polling: {exc}") from exc
        if hb_ok is False:
            raise LeaseLostError(f"Lease lost during async video {stage} job '{job_id_val}' polling. Halting execution.")
        if poll_interval:
            time.sleep(poll_interval)

    def create_creative_brief(self, product_id: str = "", brief_config: dict | None = None, **kwargs: Any) -> dict[str, Any]:
        tool_name = self.wire_tools.get("brief", "mcp__video_factory__create_brief")
        payload = {"product_id": product_id, "brief_config": brief_config or {}}
        raw = _dispatch_tool(self.registry, tool_name, payload)

        brief_id = raw.get("brief_id") or raw.get("id")
        has_content = bool(raw.get("script") or raw.get("angle") or raw.get("scenes") or raw.get("brief_config") or raw.get("content") or raw.get("brief_id"))
        if not has_content and not brief_id:
            raise RuntimeError(f"Tool '{tool_name}' returned empty creative brief content")

        return {
            "owner": "video_factory",
            "schema": "creative_brief",
            "version": 1,
            "product_id": product_id,
            "brief_id": brief_id or f"brief_{product_id}",
            "payload": json.dumps({"product_id": product_id, "brief_config": brief_config or {}, "result": raw}),
            "external_provider_id": raw.get("id") or raw.get("external_id"),
        }

    def create_scene_plan(self, brief_result: dict, **kwargs: Any) -> dict[str, Any]:
        tool_name = self.wire_tools.get("scene_plan", "mcp__video_factory__create_scene_plan")
        raw = _dispatch_tool(self.registry, tool_name, {"brief_result": brief_result})

        scene_plan_id = raw.get("scene_plan_id") or raw.get("id")
        if not scene_plan_id and not raw.get("scenes") and not raw.get("steps"):
            raise RuntimeError(f"Tool '{tool_name}' returned empty scene plan output")

        return {
            "owner": "video_factory",
            "schema": "scene_plan",
            "version": 1,
            "scene_plan_id": scene_plan_id or f"scene_{brief_result.get('product_id', 'unknown')}",
            "payload": json.dumps(raw),
            "external_provider_id": raw.get("id") or raw.get("external_id"),
        }

    def create_storyboard(self, scene_plan_result: dict, **kwargs: Any) -> dict[str, Any]:
        tool_name = self.wire_tools.get("storyboard", "mcp__video_factory__create_storyboard")
        raw = _dispatch_tool(self.registry, tool_name, {"scene_plan_result": scene_plan_result})

        storyboard_id = raw.get("storyboard_id") or raw.get("id")
        if not storyboard_id and not raw.get("frames") and not raw.get("scenes"):
            raise RuntimeError(f"Tool '{tool_name}' returned empty storyboard output")

        return {
            "owner": "video_factory",
            "schema": "storyboard",
            "version": 1,
            "storyboard_id": storyboard_id or "sb_custom",
            "payload": json.dumps(raw),
            "external_provider_id": raw.get("id") or raw.get("external_id"),
        }

    def render_video(
        self,
        storyboard_result: dict,
        render_params: dict | None = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        params = dict(render_params or {})
        existing_job_id = params.get("active_job_id") or params.get("job_id") or kwargs.get("active_job_id")
        on_job_accepted: Callable[[str, str], None] | None = kwargs.get("on_job_accepted")
        heartbeat_fn: Callable[[], bool] | None = kwargs.get("heartbeat_fn")

        if existing_job_id:
            # Job already accepted by provider — resume polling directly without re-submitting paid job
            raw = {"status": "pending", "job_id": existing_job_id}
        else:
            tool_name = self.wire_tools.get("render", "mcp__video_factory__render")
            payload: dict[str, Any] = {"storyboard_result": storyboard_result, "render_params": params}
            if idempotency_key:
                payload["idempotency_key"] = idempotency_key
            raw = _dispatch_tool(self.registry, tool_name, payload)

        # Handle async job status polling
        if isinstance(raw, dict) and raw.get("status") in ("pending", "processing", "in_progress", "queued"):
            job_id_val = str(raw.get("job_id") or raw.get("id") or existing_job_id or "")
            if not job_id_val:
                raise TerminalJobError("Async video render job returned pending status but missing job_id in response", code="MISSING_JOB_ID")

            # Checkpoint provider job_id immediately upon receipt BEFORE starting polling
            if not existing_job_id and on_job_accepted is not None:
                on_job_accepted("render", job_id_val)

            poll_tool = self.wire_tools.get("get_job_status", "mcp__video_factory__get_job_status")
            if poll_tool in _get_tool_names_from_registry(self.registry):
                start_mono = time.monotonic()
                deadline = start_mono + self.poll_timeout
                while True:
                    self._run_heartbeat(heartbeat_fn, job_id_val, "render", self.poll_interval)
                    status_raw = _dispatch_tool(self.registry, poll_tool, {"job_id": job_id_val})
                    st = str(status_raw.get("status", "")).lower()
                    if st in ("completed", "ready", "succeeded"):
                        raw = status_raw
                        break
                    if st in ("failed", "error", "cancelled"):
                        err_detail = status_raw.get("error") or status_raw.get("message") or f"status '{st}'"
                        raise TerminalJobError(f"Async video render job '{job_id_val}' failed: {err_detail}", code="VF_RENDER_TERMINAL_FAILED")
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            f"Async video render job '{job_id_val}' timed out after {self.poll_timeout}s. "
                            f"Action required: operator intervention or resume polling with active_job_id='{job_id_val}'. Do not resubmit paid job."
                        )
            else:
                raise TerminalJobError(
                    f"Async render job '{job_id_val}' returned status '{raw.get('status')}', but no status polling tool "
                    f"('{poll_tool}') is registered. Cannot mark render completed without final video output reference.",
                    code="MISSING_POLLING_TOOL",
                )

        # Enforce that output reference is present and non-empty
        video_url = raw.get("video_url") or raw.get("output_url") or raw.get("url")
        render_id = raw.get("render_id") or (raw.get("id") if raw.get("status") in ("completed", "ready", "succeeded") and not raw.get("job_id") else None)
        if not render_id and not video_url:
            raise RuntimeError(f"Video render response missing required output reference (render_id or video_url): {raw!r}")

        return {
            "owner": "video_factory",
            "schema": "video_render",
            "version": 1,
            "render_id": render_id or f"render_{raw.get('job_id', 'output')}",
            "video_url": video_url,
            "payload": json.dumps(raw),
            "external_provider_id": raw.get("id") or raw.get("external_id") or raw.get("job_id"),
        }

    def export_video(
        self,
        render_result: dict,
        export_params: dict | None = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        params = dict(export_params or {})
        existing_job_id = params.get("active_job_id") or params.get("job_id") or params.get("export_id") or kwargs.get("active_job_id")
        on_job_accepted: Callable[[str, str], None] | None = kwargs.get("on_job_accepted")
        heartbeat_fn: Callable[[], bool] | None = kwargs.get("heartbeat_fn")

        if existing_job_id:
            # Job already accepted by provider — resume polling directly without re-submitting paid job
            raw = {"status": "pending", "job_id": existing_job_id}
        else:
            tool_name = self.wire_tools.get("export", "mcp__video_factory__export")
            payload: dict[str, Any] = {"render_result": render_result, "export_params": params}
            if idempotency_key:
                payload["idempotency_key"] = idempotency_key
            raw = _dispatch_tool(self.registry, tool_name, payload)

        # Handle async export status polling if applicable
        if isinstance(raw, dict) and raw.get("status") in ("pending", "processing", "in_progress", "queued"):
            job_id_val = str(raw.get("job_id") or raw.get("export_id") or raw.get("id") or existing_job_id or "")
            if not job_id_val:
                raise TerminalJobError("Async video export job returned pending status but missing job_id in response", code="MISSING_JOB_ID")

            # Checkpoint provider job_id immediately upon receipt BEFORE starting polling
            if not existing_job_id and on_job_accepted is not None:
                on_job_accepted("export", job_id_val)

            poll_tool = self.wire_tools.get("get_export_status") or self.wire_tools.get("get_job_status", "mcp__video_factory__get_job_status")
            if poll_tool and poll_tool in _get_tool_names_from_registry(self.registry):
                start_mono = time.monotonic()
                deadline = start_mono + self.poll_timeout
                while True:
                    self._run_heartbeat(heartbeat_fn, job_id_val, "export", self.poll_interval)
                    status_raw = _dispatch_tool(self.registry, poll_tool, {"job_id": job_id_val, "export_id": job_id_val})
                    st = str(status_raw.get("status", "")).lower()
                    if st in ("completed", "ready", "succeeded"):
                        raw = status_raw
                        break
                    if st in ("failed", "error", "cancelled"):
                        err_detail = status_raw.get("error") or status_raw.get("message") or f"status '{st}'"
                        raise TerminalJobError(f"Async video export job '{job_id_val}' failed: {err_detail}", code="VF_EXPORT_TERMINAL_FAILED")
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            f"Async video export job '{job_id_val}' timed out after {self.poll_timeout}s. "
                            f"Action required: operator intervention or resume polling with active_job_id='{job_id_val}'. Do not resubmit paid job."
                        )
            else:
                raise TerminalJobError(
                    f"Async export job '{job_id_val}' returned status '{raw.get('status')}', but no status polling tool is registered. "
                    "Cannot mark export completed without final exported video output reference.",
                    code="MISSING_POLLING_TOOL",
                )

        final_video_url = raw.get("final_video_url") or raw.get("export_url") or raw.get("url")
        export_id = raw.get("export_id") or (raw.get("id") if raw.get("status") in ("completed", "ready", "succeeded") and not raw.get("job_id") else None)
        if not export_id and not final_video_url:
            raise RuntimeError(f"Video export response missing required final output reference (export_id or final_video_url): {raw!r}")

        return {
            "owner": "video_factory",
            "schema": "video_export",
            "version": 1,
            "export_id": export_id or f"export_{render_result.get('render_id', 'output')}",
            "final_video_url": final_video_url,
            "payload": json.dumps(raw),
            "external_provider_id": raw.get("id") or raw.get("external_id") or raw.get("job_id"),
        }



class ProductVideoJobHandlers:
    """Deterministic product-to-video job handlers with injected dependencies and workflow state loading."""

    def __init__(
        self,
        pi_client: ProductIntelligenceClient | None = None,
        video_client: VideoFactoryClient | None = None,
        workflow_engine: WorkflowEngine | None = None,
        workflow_repository: WorkflowRepository | None = None,
        dispatcher: JobDispatcher | None = None,
        tool_registry: Any | None = None,
        provider_mode: str = "fake",
        poll_timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> None:
        self.provider_mode = validate_provider_mode(provider_mode)
        self.tool_registry = tool_registry
        self.poll_timeout = validate_polling_setting("poll_timeout", poll_timeout, 60.0)
        self.poll_interval = validate_polling_setting("poll_interval", poll_interval, 0.5)

        if self.provider_mode == "configured":
            if pi_client is None:
                pi_client = self._resolve_pi_adapter(tool_registry)
            if video_client is None:
                video_client = self._resolve_video_adapter(tool_registry)

            self._missing_live_provider = (pi_client is None or video_client is None)
            if self._missing_live_provider:
                missing = []
                if pi_client is None:
                    missing.append("ProductIntelligence (accepted wire tools: mcp__product_intelligence__*, product_intelligence_*)")
                if video_client is None:
                    missing.append("VideoFactory (accepted wire tools: mcp__video_factory__*, video_factory_*, video_generate)")
                self._missing_provider_details = ", ".join(missing)
            else:
                self._missing_provider_details = None
        else:
            self._missing_live_provider = False
            self._missing_provider_details = None

        self.pi_client = pi_client or ProductIntelligenceClient()
        self.video_client = video_client or VideoFactoryClient()
        self.workflow_engine = workflow_engine
        self.workflow_repository = workflow_repository or (workflow_engine.repo if workflow_engine else None)
        self.dispatcher = dispatcher
        self._idempotency_cache: dict[str, JobSucceeded] = {}

    def _resolve_pi_adapter(self, registry: Any | None) -> Any | None:
        effective_registry = registry or _get_global_tool_registry()
        if effective_registry is None:
            return None
        available = _get_tool_names_from_registry(effective_registry)
        wire_map: dict[str, str] = {}
        for candidate in ("mcp__product_intelligence__research_product", "product_intelligence_research"):
            if candidate in available:
                wire_map["research"] = candidate
                break
        for candidate in ("mcp__product_intelligence__build_resource_pack", "product_intelligence_build_resource_pack"):
            if candidate in available:
                wire_map["build_resource_pack"] = candidate
                break
        for candidate in ("mcp__product_intelligence__lock_resource_pack", "product_intelligence_lock_resource_pack"):
            if candidate in available:
                wire_map["lock_resource_pack"] = candidate
                break
        if "research" in wire_map:
            return MCPProductIntelligenceAdapter(effective_registry, wire_map)
        return None

    def _resolve_video_adapter(self, registry: Any | None) -> Any | None:
        effective_registry = registry or _get_global_tool_registry()
        if effective_registry is None:
            return None
        available = _get_tool_names_from_registry(effective_registry)
        wire_map: dict[str, str] = {}
        for candidate in (
            "mcp__video_factory__create_brief",
            "mcp__hermes_video_factory__create_brief",
            "video_factory_create_brief",
            "hermes_video_factory_create_brief",
        ):
            if candidate in available:
                wire_map["brief"] = candidate
                break
        for candidate in (
            "mcp__video_factory__create_scene_plan",
            "mcp__hermes_video_factory__create_scene_plan",
            "video_factory_create_scene_plan",
            "hermes_video_factory_create_scene_plan",
        ):
            if candidate in available:
                wire_map["scene_plan"] = candidate
                break
        for candidate in (
            "mcp__video_factory__create_storyboard",
            "mcp__hermes_video_factory__create_storyboard",
            "video_factory_create_storyboard",
            "hermes_video_factory_create_storyboard",
        ):
            if candidate in available:
                wire_map["storyboard"] = candidate
                break
        for candidate in (
            "mcp__video_factory__render",
            "mcp__hermes_video_factory__render",
            "video_factory_render",
            "hermes_video_factory_render",
            "video_generate",
        ):
            if candidate in available:
                wire_map["render"] = candidate
                break
        for candidate in (
            "mcp__video_factory__export",
            "mcp__hermes_video_factory__export",
            "video_factory_export",
            "hermes_video_factory_export",
        ):
            if candidate in available:
                wire_map["export"] = candidate
                break
        for candidate in (
            "mcp__video_factory__get_job_status",
            "mcp__hermes_video_factory__get_job_status",
            "video_factory_get_job_status",
            "hermes_video_factory_get_job_status",
        ):
            if candidate in available:
                wire_map["get_job_status"] = candidate
                break
        if "render" in wire_map or "brief" in wire_map:
            return MCPVideoFactoryAdapter(effective_registry, wire_map, poll_timeout=self.poll_timeout, poll_interval=self.poll_interval)
        return None


    def _get_workflow_state_and_version(self, ctx: JobContext) -> tuple[str, int] | None:
        """Load state and version through public WorkflowEngine or WorkflowRepository methods."""
        if self.workflow_engine:
            return self.workflow_engine.get_workflow_state(ctx.workflow_id)
        if self.workflow_repository:
            data = self.workflow_repository.get_workflow(ctx.workflow_id)
            if data is not None:
                agg, ver = data
                return agg.get("state", "initial"), ver
        return None

    def _validate_state_and_version(
        self,
        ctx: JobContext,
        legal_states: set[str | ProductVideoWorkflowState],
        inputs: dict[str, Any] | None = None,
    ) -> JobFailed | None:
        if getattr(self, "_missing_live_provider", False):
            details = getattr(self, "_missing_provider_details", None) or "live API provider adapters unconfigured"
            raise RuntimeError(
                f"MISSING_PROVIDER_CONFIG: {details} for provider_mode='configured'. "
                "Register the required MCP tools in config.yaml under 'mcp_servers' or set provider_mode='fake' for explicit offline/test verification."
            )

        res = self._get_workflow_state_and_version(ctx)
        if res is None:
            return JobFailed(
                retryable=False,
                code="WORKFLOW_NOT_FOUND",
                message=f"Workflow '{ctx.workflow_id}' not found in engine/repository",
            )

        current_state, current_version = res

        # 1. Reject if state is in HITL waiting states
        for hitl_st in HITL_WAITING_STATES:
            if current_state == hitl_st.value or current_state == hitl_st:
                return JobFailed(
                    retryable=False,
                    code="HITL_APPROVAL_REQUIRED",
                    message=f"Cannot dispatch job from HITL waiting state: {current_state}",
                )

        # 2. Reject if state is not legal for this job
        legal_state_values = {s.value if isinstance(s, ProductVideoWorkflowState) else str(s) for s in legal_states}
        if current_state not in legal_state_values:
            return JobFailed(
                retryable=False,
                code="ILLEGAL_WORKFLOW_STATE",
                message=f"State '{current_state}' is not legal for this stage. Allowed: {legal_state_values}",
            )

        # 3. Check version mismatch if expected_version is provided
        if ctx.expected_version is not None and ctx.expected_version != current_version:
            return JobFailed(
                retryable=False,
                code="VERSION_CONFLICT",
                message=f"Stale workflow version: expected {ctx.expected_version}, current {current_version}",
            )

        # 4. Check expected digests if provided
        if ctx.expected_digests and inputs:
            if not verify_job_digests(ctx.job_id, inputs, ctx.expected_digests):
                return JobFailed(
                    retryable=False,
                    code="DIGEST_MISMATCH",
                    message="Input digest verification failed",
                )

        return None

    def research_job(self, ctx: JobContext, product_name: str, keywords: list[str], pdp_url: str | None = None) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:research:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"product_name": product_name, "keywords": keywords}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.RESEARCHING}, inputs)
        if err:
            return err
        if not product_name:
            return JobFailed(retryable=False, code="INVALID_INPUT", message="product_name cannot be empty")
        try:
            extra_kwargs = {"pdp_url": pdp_url} if pdp_url is not None else {}
            result = self.pi_client.research(
                product_name,
                keywords,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_kwargs,
            )
            if pdp_url and not result.get("pdp_url"):
                result["pdp_url"] = pdp_url
            res = JobSucceeded(artifact_ref=result, next_command={"command": "build_resource_pack", "product_name": product_name})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as e:
            return JobFailed(retryable=False, code=e.code, message=str(e))
        except ValueError as e:
            return JobFailed(retryable=False, code="INVALID_INPUT", message=str(e))
        except Exception as e:
            return JobFailed(retryable=True, code="PI_RESEARCH_FAILED", message=str(e))

    def resource_pack_job(self, ctx: JobContext, research_result: dict) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:resource_pack:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"research_result": research_result}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK}, inputs)
        if err:
            return err
        if not research_result:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="research_result cannot be empty")

        # In configured provider_mode, validate research snapshot persistence prerequisite before dispatch
        if getattr(self, "provider_mode", "fake") == "configured":
            snapshot_id = research_result.get("snapshot_id")
            persistence_status = research_result.get("persistence_status")
            if not snapshot_id:
                return JobFailed(
                    retryable=False,
                    code="PREREQUISITE_FAILED",
                    message="Missing snapshot_id in research_result for configured mode",
                )
            if persistence_status not in ("saved", "persisted"):
                return JobFailed(
                    retryable=False,
                    code="PREREQUISITE_FAILED",
                    message=f"Research snapshot is not successfully persisted (persistence_status={persistence_status!r})",
                )

        try:
            result = self.pi_client.build_resource_pack(
                research_result,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            res = JobSucceeded(artifact_ref=result, next_command={"command": "lock_resource_pack"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as e:
            return JobFailed(retryable=False, code=e.code, message=str(e))
        except ValueError as e:
            return JobFailed(retryable=False, code="PREREQUISITE_FAILED", message=str(e))
        except Exception as e:
            return JobFailed(retryable=True, code="PI_PACK_FAILED", message=str(e))

    def lock_job(self, ctx: JobContext, pack_dict: dict) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:lock:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"pack_dict": pack_dict}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK}, inputs)
        if err:
            return err
        if not pack_dict:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="pack_dict cannot be empty")

        # In configured provider_mode, validate resource_pack_id and ready_to_lock status before dispatch
        if getattr(self, "provider_mode", "fake") == "configured":
            resource_pack_id = pack_dict.get("resource_pack_id")
            if not resource_pack_id:
                return JobFailed(
                    retryable=False,
                    code="PREREQUISITE_FAILED",
                    message="Cannot lock resource pack: missing resource_pack_id in pack_dict",
                )

            pack_status = pack_dict.get("pack_status")
            if pack_status != "ready_to_lock":
                return JobFailed(
                    retryable=False,
                    code="NON_LOCKABLE_STATUS",
                    message=f"Cannot lock resource pack with status '{pack_status}': only 'ready_to_lock' status is lockable",
                )

        try:
            result = self.pi_client.lock_resource_pack(
                pack_dict,
                ctx.owner_user_id,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_creative_brief"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as e:
            return JobFailed(retryable=False, code=e.code, message=str(e))
        except ValueError as e:
            return JobFailed(retryable=False, code="PREREQUISITE_FAILED", message=str(e))
        except Exception as e:
            return JobFailed(retryable=True, code="PI_LOCK_FAILED", message=str(e))

    def creative_brief_job(self, ctx: JobContext, product_id: str, brief_config: dict | None = None) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:creative_brief:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"product_id": product_id, "brief_config": brief_config or {}}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_BRIEF}, inputs)
        if err:
            return err
        if not product_id:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="product_id cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 5, idempotency_key=cache_key)
            result = self.video_client.create_creative_brief(
                product_id=product_id,
                brief_config=brief_config,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
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

    def scene_plan_job(self, ctx: JobContext, brief_ref: Any) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:scene_plan:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"brief_ref": brief_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_SCENE_PLAN}, inputs)
        if err:
            return err
        if not brief_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="brief_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 5, idempotency_key=cache_key)
            result = self.video_client.create_scene_plan(
                brief_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_storyboard"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_SCENE_FAILED", message=str(e))

    def storyboard_job(self, ctx: JobContext, scene_ref: Any) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:storyboard:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"scene_ref": scene_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_STORYBOARD}, inputs)
        if err:
            return err
        if not scene_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="scene_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 10, idempotency_key=cache_key)
            result = self.video_client.create_storyboard(
                scene_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
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

    def render_job(self, ctx: JobContext, story_ref: Any, render_params: dict | None = None) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:render:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"story_ref": story_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.RENDERING}, inputs)
        if err:
            return err
        if not story_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="story_ref cannot be empty")

        params = dict(render_params or {})
        active_job_id = params.get("active_job_id")
        if not active_job_id and self.workflow_repository:
            data = self.workflow_repository.get_workflow(ctx.workflow_id)
            if data:
                active_job_id = data[0].get("active_render_job_id")
        if active_job_id:
            params["active_job_id"] = active_job_id

        def _checkpoint_accepted(job_type: str, prov_job_id: str) -> None:
            if not self.workflow_repository or not ctx.workflow_id:
                return
            try:
                data = self.workflow_repository.get_workflow(ctx.workflow_id)
                if not data:
                    raise RuntimeError(f"Workflow '{ctx.workflow_id}' not found during checkpoint")
                agg, ver = data
                agg_dict = dict(agg)
                agg_dict["active_render_job_id"] = prov_job_id
                self.workflow_repository.commit_workflow(
                    workflow_id=ctx.workflow_id,
                    aggregate_json=json.dumps(agg_dict),
                    events=[],
                    expected_version=ver,
                )
            except Exception as ex:
                raise TerminalJobError(
                    f"CHECKPOINT_PERSISTENCE_FAILED: Failed to checkpoint accepted provider job_id '{prov_job_id}' in workflow repository: {ex}. "
                    "Auto-resubmission halted to prevent duplicate provider job submission.",
                    code="VF_CHECKPOINT_FAILED",
                ) from ex

        alloc = None
        try:
            alloc = reserve_budget("video_factory", 50, idempotency_key=cache_key)
            result = self.video_client.render_video(
                story_ref,
                render_params=params,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                on_job_accepted=_checkpoint_accepted,
                heartbeat_fn=ctx.heartbeat_fn,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "export_video"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as te:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=False, code=te.code, message=str(te))
        except LeaseLostError as le:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=False, code="LEASE_LOST", message=str(le))
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))

    def export_job(self, ctx: JobContext, render_ref: Any, export_params: dict | None = None) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:export:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"render_ref": render_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.EXPORTING}, inputs)
        if err:
            return err
        if not render_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="render_ref cannot be empty")

        params = dict(export_params or {})
        active_job_id = params.get("active_job_id")
        if not active_job_id and self.workflow_repository:
            data = self.workflow_repository.get_workflow(ctx.workflow_id)
            if data:
                active_job_id = data[0].get("active_export_job_id")
        if active_job_id:
            params["active_job_id"] = active_job_id

        def _checkpoint_accepted(job_type: str, prov_job_id: str) -> None:
            if not self.workflow_repository or not ctx.workflow_id:
                return
            try:
                data = self.workflow_repository.get_workflow(ctx.workflow_id)
                if not data:
                    raise RuntimeError(f"Workflow '{ctx.workflow_id}' not found during checkpoint")
                agg, ver = data
                agg_dict = dict(agg)
                agg_dict["active_export_job_id"] = prov_job_id
                self.workflow_repository.commit_workflow(
                    workflow_id=ctx.workflow_id,
                    aggregate_json=json.dumps(agg_dict),
                    events=[],
                    expected_version=ver,
                )
            except Exception as ex:
                raise TerminalJobError(
                    f"CHECKPOINT_PERSISTENCE_FAILED: Failed to checkpoint accepted provider job_id '{prov_job_id}' in workflow repository: {ex}. "
                    "Auto-resubmission halted to prevent duplicate provider job submission.",
                    code="VF_CHECKPOINT_FAILED",
                ) from ex

        alloc = None
        try:
            alloc = reserve_budget("video_factory", 20, idempotency_key=cache_key)
            result = self.video_client.export_video(
                render_ref,
                export_params=params,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                on_job_accepted=_checkpoint_accepted,
                heartbeat_fn=ctx.heartbeat_fn,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "complete"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as te:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=False, code=te.code, message=str(te))
        except LeaseLostError as le:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=False, code="LEASE_LOST", message=str(le))
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_EXPORT_FAILED", message=str(e))

    def get_handlers_map(self) -> dict[str, Callable[..., Any]]:
        return {
            "product_video.research": self.research_job,
            "product_video.resource_pack": self.resource_pack_job,
            "product_video.lock": self.lock_job,
            "product_video.creative_brief": self.creative_brief_job,
            "product_video.scene_plan": self.scene_plan_job,
            "product_video.storyboard": self.storyboard_job,
            "product_video.render": self.render_job,
            "product_video.export": self.export_job,
        }

    def __len__(self) -> int:
        return len(self.get_handlers_map())

    def __getitem__(self, item: str) -> Callable[..., Any]:
        return self.get_handlers_map()[item]

    def __contains__(self, item: str) -> bool:
        return item in self.get_handlers_map()

    def dispatch_registered_job(self, job_name: str, ctx: JobContext, *args: Any, **kwargs: Any) -> JobResult:
        """Create a Gate 4 JobSpec and dispatch it through JobDispatcher."""
        handlers = self.get_handlers_map()
        if job_name not in handlers:
            raise ValueError(f"Unknown job handler: {job_name}")
        handler_fn = handlers[job_name]
        spec = JobSpec(
            job_id=ctx.job_id,
            func=handler_fn,
            args=(ctx, *args),
            kwargs=kwargs,
        )
        if not self.dispatcher:
            raise RuntimeError("No JobDispatcher attached to ProductVideoJobHandlers")
        return self.dispatcher.dispatch(spec)

    def wait_for_job(self, job_id: str, timeout: float = 2.0) -> JobResult | None:
        """Wait for a dispatched job to reach terminal state."""
        if not self.dispatcher:
            return None
        start = time.time()
        while time.time() - start < timeout:
            res = self.dispatcher.get_result(job_id)
            if res and res.status in (JobStatus.SUCCESS, JobStatus.FAILURE):
                return res
            time.sleep(0.01)
        return self.dispatcher.get_result(job_id)


def register_product_video_job_handlers(
    dispatcher: JobDispatcher | Any,
    handlers_service: ProductVideoJobHandlers | None = None,
    workflow_engine: WorkflowEngine | None = None,
    pi_client: ProductIntelligenceClient | None = None,
    video_client: VideoFactoryClient | None = None,
    provider_mode: str = "fake",
) -> ProductVideoJobHandlers:
    """Register all product-to-video pipeline job handlers with the Gate 4 dispatcher/registry."""
    if handlers_service is not None:
        service = handlers_service
        if isinstance(dispatcher, JobDispatcher):
            service.dispatcher = dispatcher
    else:
        service = ProductVideoJobHandlers(
            pi_client=pi_client,
            video_client=video_client,
            workflow_engine=workflow_engine,
            dispatcher=dispatcher if isinstance(dispatcher, JobDispatcher) else None,
            provider_mode=provider_mode,
        )

    if hasattr(dispatcher, "register"):
        for job_name, handler_func in service.get_handlers_map().items():
            dispatcher.register(job_name, handler_func)
    elif isinstance(dispatcher, dict):
        dispatcher.update(service.get_handlers_map())
    return service


def create_product_video_topic_handlers(
    workflow_engine: WorkflowEngine | None = None,
    workflow_repository: WorkflowRepository | None = None,
    handlers_service: ProductVideoJobHandlers | None = None,
    pi_client: ProductIntelligenceClient | None = None,
    video_client: VideoFactoryClient | None = None,
    tool_registry: Any | None = None,
    provider_mode: str = "configured",
    poll_timeout: float = 60.0,
    poll_interval: float = 0.5,
) -> dict[str, Callable[[OutboxEnvelope], None]]:
    """Create production topic handlers for durable outbox delivery.

    Binds topic 'job.dispatch' to ProductVideoJobHandlers.
    """
    if handlers_service is None:
        handlers_service = ProductVideoJobHandlers(
            pi_client=pi_client,
            video_client=video_client,
            workflow_engine=workflow_engine,
            workflow_repository=workflow_repository,
            tool_registry=tool_registry,
            provider_mode=provider_mode,
            poll_timeout=poll_timeout,
            poll_interval=poll_interval,
        )
    handlers_map = handlers_service.get_handlers_map()

    def handle_job_dispatch(envelope: OutboxEnvelope, heartbeat_fn: Callable[[], bool] | None = None) -> None:
        payload = envelope.payload
        job_name = payload.get("job_name")
        if not job_name:
            raise MalformedEnvelopeError("Missing 'job_name' in job.dispatch payload")

        if job_name not in handlers_map:
            raise ValueError(f"Unconfigured product_video job handler: {job_name!r}")

        target_wf = envelope.workflow_id
        current_version = None
        if workflow_engine:
            res = workflow_engine.get_workflow_state(target_wf)
            if res is not None:
                current_version = res[1]
        elif workflow_repository:
            data = workflow_repository.get_workflow(target_wf)
            if data is not None:
                current_version = data[1]

        ctx = JobContext(
            workflow_id=target_wf,
            job_id=f"{job_name}.{envelope.message_id}",
            owner_user_id=payload.get("owner_user_id", "local-owner"),
            expected_version=current_version,
            idempotency_key=envelope.idempotency_key,
            heartbeat_fn=heartbeat_fn,
        )

        handler_fn = handlers_map[job_name]
        args = payload.get("args", [])
        kwargs = payload.get("kwargs", {})

        result = handler_fn(ctx, *args, **kwargs)

        if isinstance(result, JobFailed):
            if not result.retryable:
                raise TerminalJobError(f"Job execution failed [{result.code}]: {result.message}", code=result.code)
            raise JobDispatchError(f"Job execution failed [{result.code}]: {result.message}", code=result.code, retryable=True)

        if isinstance(result, JobSucceeded):
            repo = workflow_repository or (workflow_engine.repo if workflow_engine else None)
            if repo:
                wf_data = repo.get_workflow(target_wf)
                if wf_data:
                    agg, version = wf_data
                    from hermes_personal.product_video.workflow import transition, WorkflowTransitionError

                    is_hitl = False
                    gate_name = None

                    if job_name == "product_video.research":
                        next_validated = transition(ProductVideoWorkflowState.RESEARCHING, ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK)
                        is_hitl = True
                        gate_name = "AwaitingProductLock"
                        outbox_next = None
                    elif job_name == "product_video.resource_pack":
                        curr_st = agg.get("state")
                        if curr_st != ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value and curr_st != ProductVideoWorkflowState.BUILDING_RESOURCE_PACK:
                            raise WorkflowTransitionError(f"Current state '{curr_st}' is not BUILDING_RESOURCE_PACK")
                        next_validated = ProductVideoWorkflowState.BUILDING_RESOURCE_PACK
                        outbox_next = build_envelope(
                            workflow_id=target_wf,
                            topic="job.dispatch",
                            idempotency_key=f"idemp_lock_{target_wf}_v{version + 1}",
                            payload={
                                "job_name": "product_video.lock",
                                "workflow_id": target_wf,
                                "args": [result.artifact_ref],
                                "owner_user_id": payload.get("owner_user_id", "local-owner"),
                            },
                        )
                    elif job_name == "product_video.lock":
                        next_validated = transition(ProductVideoWorkflowState.BUILDING_RESOURCE_PACK, ProductVideoWorkflowState.CREATING_BRIEF)
                        rp_dict = result.artifact_ref.get("resource_pack", result.artifact_ref) if isinstance(result.artifact_ref, dict) else {}
                        product_id = str(rp_dict.get("product_id") or rp_dict.get("resource_pack_id") or rp_dict.get("id") or f"prod_{target_wf}")
                        outbox_next = build_envelope(
                            workflow_id=target_wf,
                            topic="job.dispatch",
                            idempotency_key=f"idemp_brief_{target_wf}_v{version + 1}",
                            payload={
                                "job_name": "product_video.creative_brief",
                                "workflow_id": target_wf,
                                "args": [product_id, {"resource_pack": result.artifact_ref}],
                                "owner_user_id": payload.get("owner_user_id", "local-owner"),
                            },
                        )
                    elif job_name == "product_video.creative_brief":
                        next_validated = transition(ProductVideoWorkflowState.CREATING_BRIEF, ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL)
                        is_hitl = True
                        gate_name = "AwaitingBriefApproval"
                        outbox_next = None
                    elif job_name == "product_video.scene_plan":
                        next_validated = transition(ProductVideoWorkflowState.CREATING_SCENE_PLAN, ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL)
                        is_hitl = True
                        gate_name = "AwaitingSceneApproval"
                        outbox_next = None
                    elif job_name == "product_video.storyboard":
                        next_validated = transition(ProductVideoWorkflowState.CREATING_STORYBOARD, ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL)
                        is_hitl = True
                        gate_name = "AwaitingStoryboardApproval"
                        outbox_next = None
                    elif job_name == "product_video.render":
                        next_validated = transition(ProductVideoWorkflowState.RENDERING, ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL)
                        is_hitl = True
                        gate_name = "AwaitingFinalApproval"
                        outbox_next = None
                    elif job_name == "product_video.export":
                        next_validated = transition(ProductVideoWorkflowState.EXPORTING, ProductVideoWorkflowState.COMPLETED)
                        outbox_next = None
                    else:
                        raise ValueError(f"Unknown job_name in handle_job_dispatch: {job_name}")

                    next_agg = dict(agg)
                    next_agg["state"] = next_validated.value
                    next_agg.pop("active_render_job_id", None)
                    next_agg.pop("active_export_job_id", None)
                    if result.artifact_ref is not None:
                        next_agg["latest_artifact"] = result.artifact_ref

                    with repo.conn:
                        cur = repo.conn.cursor()
                        if is_hitl and gate_name:
                            approval_svc = ApprovalService(repo.conn)
                            req_id = approval_svc.submit_request(
                                {
                                    "workflow_id": target_wf,
                                    "gate": gate_name,
                                    "workflow_version": version + 1,
                                    "artifact_ref": result.artifact_ref,
                                    "owner_user_id": payload.get("owner_user_id", "local-owner"),
                                },
                                cursor=cur,
                            )
                            next_agg["pending_approval_gate"] = gate_name
                            next_agg["pending_approval_id"] = req_id
                        else:
                            next_agg.pop("pending_approval_gate", None)
                            next_agg.pop("pending_approval_id", None)

                        repo.commit_workflow(
                            workflow_id=target_wf,
                            aggregate_json=json.dumps(next_agg),
                            events=[
                                {
                                    "event_id": f"evt_{envelope.message_id}",
                                    "command_id": f"cmd_{envelope.message_id}",
                                    "event_type": "JobSucceeded",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "payload": {"job_name": job_name, "artifact_ref": result.artifact_ref},
                                }
                            ],
                            outbox_message=outbox_next,
                            expected_version=version,
                        )

    return {"job.dispatch": handle_job_dispatch}


def start_product_video_workflow(
    workflow_repository: WorkflowRepository,
    workflow_id: str,
    product_name: str,
    keywords: list[str],
    pdp_url: str | None = None,
    owner_user_id: str = "local-owner",
    idempotency_key: str | None = None,
) -> str:
    """Production entrypoint to create and enqueue a durable Product-to-Video workflow.

    Commits aggregate state 'researching', appends 'WorkflowStarted' event,
    and enqueues the 'job.dispatch' OutboxEnvelope for product_video.research.
    """
    idemp = idempotency_key or f"idemp_res_{workflow_id}"
    outbox_msg = build_envelope(
        workflow_id=workflow_id,
        topic="job.dispatch",
        idempotency_key=idemp,
        payload={
            "job_name": "product_video.research",
            "workflow_id": workflow_id,
            "args": [product_name, keywords, pdp_url],
            "owner_user_id": owner_user_id,
        },
    )
    workflow_repository.commit_workflow(
        workflow_id=workflow_id,
        aggregate_json=json.dumps(
            {
                "state": ProductVideoWorkflowState.RESEARCHING.value,
                "owner_user_id": owner_user_id,
                "pdp_url": pdp_url,
            }
        ),
        events=[
            {
                "event_id": f"evt_start_{workflow_id}",
                "command_id": f"cmd_start_{workflow_id}",
                "event_type": "WorkflowStarted",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"product_name": product_name, "keywords": keywords, "pdp_url": pdp_url},
            }
        ],
        outbox_message=outbox_msg,
        expected_version=0,
    )
    return workflow_id
