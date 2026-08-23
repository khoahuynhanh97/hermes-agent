from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.contracts.capability import CapabilitySource, HealthStatus


class UpstreamToolRegistry(Protocol):
    def get_all_tool_names(self) -> list[str]:
        ...

    def get_definitions(
        self, tool_names: set[str], quiet: bool = False
    ) -> list[dict[str, Any]]:
        ...

    def get_schema(self, name: str) -> dict[str, Any] | None:
        ...

    def get_toolset_for_tool(self, name: str) -> str | None:
        ...


@dataclass(frozen=True)
class WireBindingRule:
    capability_id: str
    accepted_wire_names: tuple[str, ...]
    provider: str
    source: CapabilitySource = "hermes_mcp"

    def __post_init__(self) -> None:
        if self.capability_id not in INITIAL_CAPABILITIES:
            raise ValueError(
                f"unknown capability_id outside INITIAL_CAPABILITIES: {self.capability_id}"
            )
        if not self.accepted_wire_names:
            raise ValueError("accepted_wire_names must not be empty")


DEFAULT_WIRE_BINDING_RULES: tuple[WireBindingRule, ...] = (
    WireBindingRule(
        capability_id="product.research",
        accepted_wire_names=(
            "mcp__product_intelligence__research_product",
            "product_intelligence_research",
        ),
        provider="product_intelligence",
    ),
    WireBindingRule(
        capability_id="product.resource_pack.build",
        accepted_wire_names=(
            "mcp__product_intelligence__build_resource_pack",
            "product_intelligence_build_resource_pack",
        ),
        provider="product_intelligence",
    ),
    WireBindingRule(
        capability_id="product.resource_pack.lock",
        accepted_wire_names=(
            "mcp__product_intelligence__lock_resource_pack",
            "product_intelligence_lock_resource_pack",
        ),
        provider="product_intelligence",
    ),
    WireBindingRule(
        capability_id="video.brief.create",
        accepted_wire_names=(
            "mcp__video_factory__create_brief",
            "video_factory_create_brief",
        ),
        provider="video_factory",
    ),
    WireBindingRule(
        capability_id="video.scene_plan.create",
        accepted_wire_names=(
            "mcp__video_factory__create_scene_plan",
            "video_factory_create_scene_plan",
        ),
        provider="video_factory",
    ),
    WireBindingRule(
        capability_id="video.storyboard.create",
        accepted_wire_names=(
            "mcp__video_factory__create_storyboard",
            "video_factory_create_storyboard",
        ),
        provider="video_factory",
    ),
    WireBindingRule(
        capability_id="video.render",
        accepted_wire_names=(
            "mcp__video_factory__render",
            "video_factory_render",
        ),
        provider="video_factory",
    ),
    WireBindingRule(
        capability_id="video.export",
        accepted_wire_names=(
            "mcp__video_factory__export",
            "video_factory_export",
        ),
        provider="video_factory",
    ),
    WireBindingRule(
        capability_id="knowledge.candidate.create",
        accepted_wire_names=(
            "mcp__learning__create_candidate",
            "learning_create_candidate",
        ),
        provider="learning",
    ),
    WireBindingRule(
        capability_id="knowledge.retrieve",
        accepted_wire_names=(
            "mcp__learning__retrieve",
            "learning_retrieve",
        ),
        provider="learning",
    ),
)


@dataclass(frozen=True)
class DiscoveryDiagnostic:
    capability_id: str
    code: str
    message: str
    wire_name: str | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    bindings: tuple[ImplementationBinding, ...]
    by_capability_id: Mapping[str, ImplementationBinding]
    diagnostics: tuple[DiscoveryDiagnostic, ...]


def hash_schema_dict(schema: dict[str, Any]) -> str:
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class CapabilityDiscovery:
    def __init__(
        self,
        rules: Iterable[WireBindingRule] = DEFAULT_WIRE_BINDING_RULES,
    ) -> None:
        self._rules = tuple(rules)

    def scan(self, registry: UpstreamToolRegistry) -> DiscoveryResult:
        all_registered_names = set(registry.get_all_tool_names())
        definitions = registry.get_definitions(all_registered_names, quiet=True)
        available_defs = {
            d["function"]["name"]: d["function"]
            for d in definitions
            if isinstance(d, dict) and "function" in d and isinstance(d["function"], dict)
        }

        bindings_by_id: dict[str, ImplementationBinding] = {}
        diagnostics: list[DiscoveryDiagnostic] = []

        rules_by_id = {r.capability_id: r for r in self._rules}

        # Verify wire ownership collisions
        wire_to_capabilities: dict[str, list[str]] = {}
        for rule in self._rules:
            for wire in rule.accepted_wire_names:
                if wire in all_registered_names:
                    wire_to_capabilities.setdefault(wire, []).append(rule.capability_id)

        for cap_id in sorted(INITIAL_CAPABILITIES.keys()):
            rule = rules_by_id.get(cap_id)
            if rule is None:
                rule = WireBindingRule(
                    capability_id=cap_id,
                    accepted_wire_names=(f"mcp__{cap_id.replace('.', '_')}",),
                    provider="unknown",
                )

            matching_wires = [
                w for w in rule.accepted_wire_names if w in all_registered_names
            ]

            if len(matching_wires) > 1:
                wire_name = matching_wires[0]
                health: HealthStatus = "unavailable"
                diag_code = "ambiguous_wire_mapping"
                diag_msg = f"multiple registered tools match rule: {matching_wires}"
                diagnostics.append(
                    DiscoveryDiagnostic(
                        capability_id=cap_id,
                        code=diag_code,
                        message=diag_msg,
                        wire_name=wire_name,
                    )
                )
                bindings_by_id[cap_id] = ImplementationBinding(
                    capability_id=cap_id,
                    wire_name=wire_name,
                    source=rule.source,
                    provider=rule.provider,
                    implementation_version="1.0.0",
                    input_schema_version="1.0",
                    output_schema_version="1.0",
                    schema_digest="sha256:ambiguous",
                    health=health,
                )
                continue

            if not matching_wires:
                wire_name = rule.accepted_wire_names[0]
                health = "unavailable"
                diag_code = "tool_not_found"
                diag_msg = f"wire tool name {wire_name!r} not found in ToolRegistry"
                diagnostics.append(
                    DiscoveryDiagnostic(
                        capability_id=cap_id,
                        code=diag_code,
                        message=diag_msg,
                        wire_name=wire_name,
                    )
                )
                bindings_by_id[cap_id] = ImplementationBinding(
                    capability_id=cap_id,
                    wire_name=wire_name,
                    source=rule.source,
                    provider=rule.provider,
                    implementation_version="1.0.0",
                    input_schema_version="1.0",
                    output_schema_version="1.0",
                    schema_digest="sha256:missing",
                    health=health,
                )
                continue

            wire_name = matching_wires[0]

            # Check if this wire is claimed by multiple capability rules
            claiming_caps = wire_to_capabilities.get(wire_name, [])
            if len(claiming_caps) > 1:
                diagnostics.append(
                    DiscoveryDiagnostic(
                        capability_id=cap_id,
                        code="duplicate_wire_ownership",
                        message=f"wire {wire_name!r} claimed by multiple capabilities: {claiming_caps}",
                        wire_name=wire_name,
                    )
                )
                bindings_by_id[cap_id] = ImplementationBinding(
                    capability_id=cap_id,
                    wire_name=wire_name,
                    source=rule.source,
                    provider=rule.provider,
                    implementation_version="1.0.0",
                    input_schema_version="1.0",
                    output_schema_version="1.0",
                    schema_digest="sha256:duplicate",
                    health="unavailable",
                )
                continue

            provider = (
                registry.get_toolset_for_tool(wire_name) or rule.provider
            )

            if wire_name not in available_defs:
                raw_schema = registry.get_schema(wire_name) or {}
                digest = hash_schema_dict(raw_schema)
                diagnostics.append(
                    DiscoveryDiagnostic(
                        capability_id=cap_id,
                        code="check_failed",
                        message=f"wire tool {wire_name!r} check_fn failed or unavailable",
                        wire_name=wire_name,
                    )
                )
                bindings_by_id[cap_id] = ImplementationBinding(
                    capability_id=cap_id,
                    wire_name=wire_name,
                    source=rule.source,
                    provider=provider,
                    implementation_version="1.0.0",
                    input_schema_version="1.0",
                    output_schema_version="1.0",
                    schema_digest=digest,
                    health="unavailable",
                )
                continue

            schema = available_defs[wire_name]
            parameters = schema.get("parameters")
            if parameters is not None and not isinstance(parameters, dict):
                diagnostics.append(
                    DiscoveryDiagnostic(
                        capability_id=cap_id,
                        code="schema_incompatible",
                        message=f"wire tool {wire_name!r} schema parameters is not a dict",
                        wire_name=wire_name,
                    )
                )
                bindings_by_id[cap_id] = ImplementationBinding(
                    capability_id=cap_id,
                    wire_name=wire_name,
                    source=rule.source,
                    provider=provider,
                    implementation_version="1.0.0",
                    input_schema_version="1.0",
                    output_schema_version="1.0",
                    schema_digest="sha256:incompatible",
                    health="unavailable",
                )
                continue

            digest = hash_schema_dict(schema)
            bindings_by_id[cap_id] = ImplementationBinding(
                capability_id=cap_id,
                wire_name=wire_name,
                source=rule.source,
                provider=provider,
                implementation_version="1.0.0",
                input_schema_version="1.0",
                output_schema_version="1.0",
                schema_digest=digest,
                health="healthy",
            )

        sorted_bindings = tuple(
            bindings_by_id[k] for k in sorted(bindings_by_id.keys())
        )

        return DiscoveryResult(
            bindings=sorted_bindings,
            by_capability_id=MappingProxyType(bindings_by_id),
            diagnostics=tuple(diagnostics),
        )
