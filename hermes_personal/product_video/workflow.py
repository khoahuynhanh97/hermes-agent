"""hermes_personal/product_video/workflow.py

Gate 5 Task 4 -- state-machine helpers for the product-to-video pipeline.

The canonical state enum lives in workflow_state.py. This module re-exports
those types and adds the stateless transition() / is_hitl_blocked() helpers
used by binding and tests.
"""
from __future__ import annotations

from hermes_personal.product_video.workflow_state import (
    ProductVideoWorkflowState,
    HITL_WAITING_STATES,
)

__all__ = [
    "ProductVideoWorkflowState",
    "HITL_WAITING_STATES",
    "HITL_BLOCKING_STATES",
    "WorkflowTransitionError",
    "transition",
    "is_hitl_blocked",
]

# Alias for backward compat with Gate 5 Task 4 tests
HITL_BLOCKING_STATES: frozenset[ProductVideoWorkflowState] = frozenset(HITL_WAITING_STATES)

# Legal next states for each current state
_TRANSITIONS: dict[ProductVideoWorkflowState, frozenset[ProductVideoWorkflowState]] = {
    ProductVideoWorkflowState.IDLE: frozenset({
        ProductVideoWorkflowState.RESEARCHING,
    }),
    ProductVideoWorkflowState.RESEARCHING: frozenset({
        ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
        ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
    }),
    ProductVideoWorkflowState.BUILDING_RESOURCE_PACK: frozenset({
        ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
        ProductVideoWorkflowState.CREATING_BRIEF,
        ProductVideoWorkflowState.WAITING_FOR_OPERATOR,
    }),
    ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK: frozenset({
        ProductVideoWorkflowState.LOCKING_RESOURCE_PACK,
        ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
    }),
    ProductVideoWorkflowState.LOCKING_RESOURCE_PACK: frozenset({
        ProductVideoWorkflowState.CREATING_BRIEF,
    }),
    ProductVideoWorkflowState.CREATING_BRIEF: frozenset({
        ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
    }),
    ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL: frozenset({
        ProductVideoWorkflowState.CREATING_SCENE_PLAN,
        ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
    }),
    ProductVideoWorkflowState.CREATING_SCENE_PLAN: frozenset({
        ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
    }),
    ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL: frozenset({
        ProductVideoWorkflowState.CREATING_STORYBOARD,
        ProductVideoWorkflowState.CREATING_SCENE_PLAN,
    }),
    ProductVideoWorkflowState.CREATING_STORYBOARD: frozenset({
        ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
        ProductVideoWorkflowState.WAITING_FOR_OPERATOR,
    }),
    ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL: frozenset({
        ProductVideoWorkflowState.RENDERING,
        ProductVideoWorkflowState.CREATING_STORYBOARD,
    }),
    ProductVideoWorkflowState.RENDERING: frozenset({
        ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
        ProductVideoWorkflowState.WAITING_FOR_OPERATOR,
    }),
    ProductVideoWorkflowState.WAITING_FOR_OPERATOR: frozenset({
        ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
        ProductVideoWorkflowState.CREATING_STORYBOARD,
        ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
        ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
        ProductVideoWorkflowState.RENDERING,
    }),
    ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL: frozenset({
        ProductVideoWorkflowState.EXPORTING,
        ProductVideoWorkflowState.RENDERING,
    }),
    ProductVideoWorkflowState.EXPORTING: frozenset({
        ProductVideoWorkflowState.COMPLETED,
    }),
    ProductVideoWorkflowState.COMPLETED: frozenset(),
}


class WorkflowTransitionError(Exception):
    """Raised when a state transition is not permitted."""


def transition(
    current: ProductVideoWorkflowState,
    target: ProductVideoWorkflowState,
) -> ProductVideoWorkflowState:
    """Validate and return the target state.

    Raises WorkflowTransitionError if the transition is not in the legal set.
    """
    allowed = _TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise WorkflowTransitionError(
            f"Cannot transition from {current!r} to {target!r}; "
            f"allowed: {sorted(s.value for s in allowed)}"
        )
    return target


def is_hitl_blocked(state: ProductVideoWorkflowState) -> bool:
    """Return True if the state requires human approval before any job runs."""
    return state in HITL_BLOCKING_STATES
