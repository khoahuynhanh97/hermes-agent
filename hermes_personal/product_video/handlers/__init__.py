"""Product Video job handlers - modular implementation.

This package splits the monolithic handlers.py (2,866 lines) into focused modules:
- common.py: Shared helper functions and config builders
- _base.py: ProductVideoJobHandlers base class and infrastructure
- qc_handler.py: QC retry and preview handlers (methods)
- research_handler.py: Research, resource pack, and lock handlers (methods)
- creative_handler.py: Creative brief, scene plan, and storyboard handlers (methods)
- render_handler.py: Video rendering handler (methods)
- export_handler.py: Video export handler (methods)
- registry.py: Module-level registration and workflow starter functions

All methods are mixed into the ProductVideoJobHandlers class via the _base module.
Public API and sub-components are re-exported here for 100% backward compatibility.
"""
from __future__ import annotations

# Import the main class from base
from hermes_personal.product_video.handlers._base import ProductVideoJobHandlers

# Import module-level functions from registry
from hermes_personal.product_video.handlers.registry import (
    create_product_video_topic_handlers,
    register_product_video_job_handlers,
    start_product_video_workflow,
)

# Import public utilities and helpers from common
from hermes_personal.product_video.handlers.common import (
    verify_job_digests,
    create_configured_creative_generator,
    _compute_digest,
    _locked_research_dossier,
    _qc_context,
    _paid_budget_kwargs,
    _is_qc_pass,
    _qc_report_payload,
)

# Re-export workflow state and contracts that tests/external code may import
from hermes_personal.product_video.workflow import (
    ProductVideoWorkflowState,
    HITL_WAITING_STATES,
)
from hermes_personal.product_video.job_contracts import (
    ExecutionBindingPreflight,
    ExecutionBindingPreflightError,
    JobContext,
    JobDispatchError,
    JobFailed,
    JobSucceeded,
    LeaseLostError,
    TerminalJobError,
)
from hermes_personal.product_video.mcp_adapters import (
    MCPProductIntelligenceAdapter,
    MCPVideoFactoryAdapter,
    _check_for_errors,
    _decode_mcp_output,
    _dispatch_tool,
    _get_global_tool_registry,
    _get_tool_names_from_registry,
    _require_snapshot_wire,
    _resolve_snapshot_execution_wire,
)
from hermes_personal.product_video.provider_runtime import (
    resolve_polling_setting,
    resolve_provider_mode,
    validate_polling_setting,
    validate_provider_mode,
)

# Re-export for backward compatibility
__all__ = [
    "ProductVideoJobHandlers",
    "create_product_video_topic_handlers",
    "register_product_video_job_handlers",
    "start_product_video_workflow",
    "verify_job_digests",
    "create_configured_creative_generator",
    "_compute_digest",
    "_locked_research_dossier",
    "_qc_context",
    "_paid_budget_kwargs",
    "_is_qc_pass",
    "_qc_report_payload",
    "ProductVideoWorkflowState",
    "HITL_WAITING_STATES",
    "ExecutionBindingPreflight",
    "ExecutionBindingPreflightError",
    "JobContext",
    "JobDispatchError",
    "JobFailed",
    "JobSucceeded",
    "LeaseLostError",
    "TerminalJobError",
    "MCPProductIntelligenceAdapter",
    "MCPVideoFactoryAdapter",
    "_check_for_errors",
    "_decode_mcp_output",
    "_dispatch_tool",
    "_get_global_tool_registry",
    "_get_tool_names_from_registry",
    "_require_snapshot_wire",
    "_resolve_snapshot_execution_wire",
    "resolve_polling_setting",
    "resolve_provider_mode",
    "validate_polling_setting",
    "validate_provider_mode",
]
