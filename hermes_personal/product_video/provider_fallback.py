"""Multi-model video provider fallback chain for resilient rendering.

Supports automatic failover across multiple video generation providers when
a render fails or times out. Records each attempt and preserves budget tracking.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from hermes_personal.product_video.job_contracts import TerminalJobError

logger = logging.getLogger(__name__)


DEFAULT_PROVIDER_CHAIN = ["google_flow", "kling", "wan", "vertex_ai"]


class ProviderFallbackChain:
    """Manages automatic failover across multiple video generation providers."""

    def __init__(
        self,
        providers: list[str] | None = None,
        attempt_recorder: Callable[[str, str, str, dict[str, Any]], None] | None = None,
    ):
        """Initialize fallback chain.
        
        Args:
            providers: Ordered list of provider names to try. Defaults to DEFAULT_PROVIDER_CHAIN.
            attempt_recorder: Optional callback to record failed attempts.
                Signature: (workflow_id, provider_kind, failure_code, context) -> None
        """
        self.providers = providers if providers is not None else DEFAULT_PROVIDER_CHAIN.copy()
        self.attempt_recorder = attempt_recorder

    def execute_with_fallback(
        self,
        operation_fn: Callable[[str], Any],
        workflow_id: str,
        operation_name: str = "render_video",
        context: dict[str, Any] | None = None,
    ) -> tuple[Any, str]:
        """Execute an operation with automatic provider fallback.
        
        Args:
            operation_fn: Function that takes provider_kind and returns the result.
            workflow_id: Workflow ID for logging and attempt recording.
            operation_name: Human-readable operation name for logging.
            context: Additional context for attempt recording.
        
        Returns:
            Tuple of (result, successful_provider_kind)
        
        Raises:
            TerminalJobError: When all providers in the chain have failed.
        """
        ctx = context or {}
        failures = []
        
        if not self.providers:
            raise TerminalJobError(
                "Provider chain is empty; no providers available to attempt",
                code="EMPTY_PROVIDER_CHAIN",
            )
        
        for idx, provider_kind in enumerate(self.providers):
            is_last = idx == len(self.providers) - 1
            
            try:
                logger.info(
                    f"Attempting {operation_name} with provider '{provider_kind}' "
                    f"(attempt {idx + 1}/{len(self.providers)}) for workflow {workflow_id}"
                )
                result = operation_fn(provider_kind)
                
                if idx > 0:
                    logger.warning(
                        f"Provider '{provider_kind}' succeeded after {idx} failed attempt(s) "
                        f"for workflow {workflow_id}"
                    )
                
                return result, provider_kind
                
            except TerminalJobError as e:
                failure_info = {
                    "provider": provider_kind,
                    "code": e.code,
                    "message": str(e),
                    "attempt": idx + 1,
                }
                failures.append(failure_info)
                
                logger.warning(
                    f"Provider '{provider_kind}' failed with TerminalJobError "
                    f"[{e.code}]: {e} for workflow {workflow_id}"
                )
                
                if self.attempt_recorder:
                    self.attempt_recorder(
                        workflow_id,
                        provider_kind,
                        e.code,
                        {**ctx, "error": str(e), "attempt": idx + 1},
                    )
                
                if is_last:
                    failure_summary = "; ".join(
                        f"{f['provider']}:{f['code']}" for f in failures
                    )
                    raise TerminalJobError(
                        f"All {len(self.providers)} providers failed for {operation_name}: {failure_summary}",
                        code="ALL_PROVIDERS_EXHAUSTED",
                    ) from e
                
            except RuntimeError as e:
                failure_info = {
                    "provider": provider_kind,
                    "code": "RUNTIME_ERROR",
                    "message": str(e),
                    "attempt": idx + 1,
                }
                failures.append(failure_info)
                
                logger.warning(
                    f"Provider '{provider_kind}' failed with RuntimeError: {e} "
                    f"for workflow {workflow_id}"
                )
                
                if self.attempt_recorder:
                    self.attempt_recorder(
                        workflow_id,
                        provider_kind,
                        "RUNTIME_ERROR",
                        {**ctx, "error": str(e), "attempt": idx + 1},
                    )
                
                if is_last:
                    failure_summary = "; ".join(
                        f"{f['provider']}:{f['code']}" for f in failures
                    )
                    raise TerminalJobError(
                        f"All {len(self.providers)} providers failed for {operation_name}: {failure_summary}",
                        code="ALL_PROVIDERS_EXHAUSTED",
                    ) from e


def create_fallback_chain(
    providers: list[str] | None = None,
    workflow_repository: Any | None = None,
) -> ProviderFallbackChain:
    """Factory function to create a fallback chain with optional attempt recording.
    
    Args:
        providers: Ordered list of provider names. Defaults to DEFAULT_PROVIDER_CHAIN.
        workflow_repository: Optional repository for recording failed attempts.
    
    Returns:
        Configured ProviderFallbackChain instance.
    """
    attempt_recorder = None
    
    if workflow_repository and hasattr(workflow_repository, "conn"):
        def record_attempt(workflow_id: str, provider_kind: str, code: str, context: dict[str, Any]) -> None:
            """Record a failed provider attempt in the database."""
            try:
                from datetime import datetime, timezone
                
                attempt_id = f"attempt_{workflow_id}_{provider_kind}_{datetime.now(timezone.utc).timestamp()}"
                now = datetime.now(timezone.utc).isoformat()
                
                workflow_repository.conn.execute(
                    """
                    INSERT INTO product_video_operation_attempt (
                        attempt_id, authorization_id, campaign_id, owner_user_id,
                        workflow_id, capability_id, attempt_number, input_fingerprint,
                        estimated_cost, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt_id,
                        context.get("authorization_id", "fallback_auth"),
                        context.get("campaign_id", "fallback_campaign"),
                        context.get("owner_user_id", "unknown"),
                        workflow_id,
                        f"video.render.{provider_kind}",
                        context.get("attempt", 1),
                        context.get("input_fingerprint", ""),
                        context.get("estimated_cost", 0),
                        f"provider_failed:{code}",
                        now,
                        now,
                    ),
                )
                workflow_repository.conn.commit()
            except Exception as e:
                logger.warning(f"Failed to record attempt for workflow {workflow_id}: {e}")
        
        attempt_recorder = record_attempt
    
    return ProviderFallbackChain(providers=providers, attempt_recorder=attempt_recorder)
