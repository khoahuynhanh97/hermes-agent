from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    wire_name: str
    owner: str
    source: Literal["native", "hermes_mcp", "external_mcp", "generated"]
    trust: Literal["first_party", "configured_external", "untrusted"]
    version: str
    toolset: str
    side_effects: Literal["read", "write", "external", "paid"]
    principal_mode: Literal["session", "server", "none"]
    idempotency: Literal["required", "supported", "none"]
    approval_policy: str
    data_classification: str


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    wire_name: str
    owner: str
    source: Literal["native", "hermes_mcp", "external_mcp", "generated"]
    trust: Literal["first_party", "configured_external", "untrusted"]
    version: str
    toolset: str
    side_effects: Literal["read", "write", "external", "paid"]
    principal_mode: Literal["session", "server", "none"]
    idempotency: Literal["required", "supported", "none"]
    approval_policy: str
    data_classification: str
