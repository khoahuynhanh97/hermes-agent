from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

CapabilitySource = Literal["native", "plugin", "hermes_mcp", "external_mcp"]
CapabilityTrust = Literal["first_party", "configured_external", "untrusted"]
SideEffects = Literal["read", "write", "external", "paid"]
PrincipalMode = Literal["session", "server", "none"]
Idempotency = Literal["required", "supported", "none"]
RiskLevel = Literal["low", "medium", "high", "critical"]
CostClass = Literal["free", "metered", "paid"]
HealthStatus = Literal["unknown", "healthy", "degraded", "unavailable"]


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    wire_name: str
    owner: str
    source: CapabilitySource
    trust: CapabilityTrust
    version: str
    toolset: str
    side_effects: SideEffects
    principal_mode: PrincipalMode
    idempotency: Idempotency
    approval_policy: str
    data_classification: str
    input_schema_version: str
    output_schema_version: str
    risk: RiskLevel
    cost_class: CostClass
    provider_policy: str
    health: HealthStatus
    allowed_skills: tuple[str, ...] = ()
    allowed_workflows: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "capability_id",
            "wire_name",
            "owner",
            "version",
            "input_schema_version",
            "output_schema_version",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be blank")


class CapabilityCatalog:
    def __init__(self) -> None:
        self._by_id: dict[str, CapabilityDescriptor] = {}
        self._wire_to_id: dict[str, str] = {}

    def register(self, descriptor: CapabilityDescriptor) -> None:
        existing = self._by_id.get(descriptor.capability_id)
        if existing is not None and existing != descriptor:
            raise ValueError(f"capability ID already registered: {descriptor.capability_id}")
        owner_id = self._wire_to_id.get(descriptor.wire_name)
        if owner_id is not None and owner_id != descriptor.capability_id:
            raise ValueError(f"wire name already bound: {descriptor.wire_name}")
        self._by_id[descriptor.capability_id] = descriptor
        self._wire_to_id[descriptor.wire_name] = descriptor.capability_id

    def resolve(self, identifier: str) -> CapabilityDescriptor:
        capability_id = identifier
        if identifier not in self._by_id:
            capability_id = self._wire_to_id.get(identifier, "")
        descriptor = self._by_id.get(capability_id)
        if descriptor is None:
            raise KeyError(f"unknown capability: {identifier}")
        return descriptor

    def rebind_wire(self, capability_id: str, wire_name: str) -> CapabilityDescriptor:
        current = self.resolve(capability_id)
        owner_id = self._wire_to_id.get(wire_name)
        if owner_id is not None and owner_id != capability_id:
            raise ValueError(f"wire name already bound: {wire_name}")
        self._wire_to_id.pop(current.wire_name, None)
        rebound = replace(current, wire_name=wire_name)
        self._by_id[capability_id] = rebound
        self._wire_to_id[wire_name] = capability_id
        return rebound
