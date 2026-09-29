"""Product Video workflow state values and HITL waiting states."""

from __future__ import annotations

from enum import Enum


class ProductVideoWorkflowState(str, Enum):
    IDLE = "idle"
    RESEARCHING = "researching"
    BUILDING_RESOURCE_PACK = "building_resource_pack"
    RETRYING_IMAGE_QC = "retrying_image_qc"
    AWAITING_PRODUCT_LOCK = "AwaitingProductLock"
    LOCKING_RESOURCE_PACK = "locking_resource_pack"
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
    WAITING_FOR_OPERATOR = "WaitingForOperator"


HITL_WAITING_STATES = {
    ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
    ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
    ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
    ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
    ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
}


__all__ = ["ProductVideoWorkflowState", "HITL_WAITING_STATES"]
