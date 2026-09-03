"""Compatibility shim for hermes_personal.integrations.video_factory.ports.

DEPRECATED / DECLARED_ONLY: This module is a thin re-export compatibility shim.
Production ownership lives in hermes_personal.integrations.video_factory.ports.
"""
from __future__ import annotations

from hermes_personal.integrations.video_factory.ports import (
    VideoGenerationProvider,
    VideoGenerationRequest,
    VideoGenerationJob,
    VideoJobStatus,
    ProviderCapability,
)
