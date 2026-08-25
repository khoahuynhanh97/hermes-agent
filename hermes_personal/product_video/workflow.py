"""hermes_personal/product_video/workflow.py

Gate 5 Task 4 -- state-machine handlers and invalidation rules for the
product-to-video pipeline workflow.

State transitions:
    AWAITING_PRODUCT_LOCK
        -> (product lock received)
    AWAITING_BRIEF_APPROVAL
        -> (brief approved)  -> CREATING_SCENE_PLAN
        -> (brief rejected)  -> AWAITING_PRODUCT_LOCK
    CREATING_SCENE_PLAN
        -> AWAITING_SCENE_APPROVAL
    AWAITING_SCENE_APPROVAL
        -> (scene approved)  -> CREATING_STORYBOARD
        -> (scene rejected)  -> CREATING_SCENE_PLAN
    CREATING_STORYBOARD
        -> AWAITING_STORYBOARD_APPROVAL
    AWAITING_STORYBOARD_APPROVAL
        -> (storyboard approved) -> RENDERING
        -> (storyboard rejected) -> CREATING_STORYBOARD
    RENDERING
        -> AWAITING_FINAL_APPROVAL
    AWAITING_FINAL_APPROVAL
        -> (final approved)  -> EXPORTING
        -> (final rejected)  -> RENDERING
    EXPORTING
        -> DONE
"""
from __future__ import annotations

from enum import Enum


class ProductVideoWorkflowState(str, Enum):
    AWAITING_PRODUCT_LOCK = "AWAITING_PRODUCT_LOCK"
    CREATING_CREATIVE_BRIEF = "CREATING_CREATIVE_BRIEF"
    AWAITING_BRIEF_APPROVAL = "AWAITING_BRIEF_APPROVAL"
    CREATING_SCENE_PLAN = "CREATING_SCENE_PLAN"
    AWAITING_SCENE_APPROVAL = "AWAITING_SCENE_APPROVAL"
    CREATING_STORYBOARD = "CREATING_STORYBOARD"
    AWAITING_STORYBOARD_APPROVAL = "AWAITING_STORYBOARD_APPROVAL"
    RENDERING = "RENDERING"
    AWAITING_FINAL_APPROVAL = "AWAITING_FINAL_APPROVAL"
    EXPORTING = "EXPORTING"
    DONE = "DONE"
    FAILED = "FAILED"


# States in which no job may be dispatched (human gate required first)
HITL_BLOCKING_STATES: frozenset[ProductVideoWorkflowState] = frozenset({
    ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
    ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
    ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
    ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
    ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
})


# Legal next states for each current state
_TRANSITIONS: dict[ProductVideoWorkflowState, frozenset[ProductVideoWorkflowState]] = {
    ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK: frozenset({
        ProductVideoWorkflowState.CREATING_CREATIVE_BRIEF,
    }),
    ProductVideoWorkflowState.CREATING_CREATIVE_BRIEF: frozenset({
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
    }),
    ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL: frozenset({
        ProductVideoWorkflowState.RENDERING,
        ProductVideoWorkflowState.CREATING_STORYBOARD,
    }),
    ProductVideoWorkflowState.RENDERING: frozenset({
        ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
    }),
    ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL: frozenset({
        ProductVideoWorkflowState.EXPORTING,
        ProductVideoWorkflowState.RENDERING,
    }),
    ProductVideoWorkflowState.EXPORTING: frozenset({
        ProductVideoWorkflowState.DONE,
    }),
    ProductVideoWorkflowState.DONE: frozenset(),
    ProductVideoWorkflowState.FAILED: frozenset(),
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
