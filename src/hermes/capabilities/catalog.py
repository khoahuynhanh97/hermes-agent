from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from hermes.capabilities.models import CapabilityDescriptor


@dataclass(frozen=True)
class CapabilityEntry:
    wire_name: str
    toolset: str = "default"
    description: str = ""
    owner: str = "hermes"
    side_effects: str = "write"
    principal_mode: str = "session"
    provenance: str = "builtin"


class CapabilityCatalog:
    def __init__(self, descriptors: Optional[Dict[str, CapabilityDescriptor]] = None):
        self._descriptors: Dict[str, CapabilityDescriptor] = dict(descriptors or {})

    def register_descriptor(self, desc: CapabilityDescriptor) -> None:
        existing = self._descriptors.get(desc.wire_name)
        if existing is not None and existing != desc:
            raise ValueError(f"Conflicting capability descriptor registration for '{desc.wire_name}'")
        self._descriptors[desc.wire_name] = desc

    @classmethod
    def from_entries(
        cls,
        entries: List[CapabilityEntry],
        managed_servers: Optional[Set[str]] = None,
    ) -> "CapabilityCatalog":
        managed = managed_servers or {"hermes_product", "hermes_research", "hermes_knowledge", "hermes_video", "hermes_video_factory"}
        catalog = cls()

        for entry in entries:
            wire_name = entry.wire_name
            if wire_name.startswith("mcp__"):
                parts = wire_name.split("__", 2)
                server_name = parts[1] if len(parts) > 1 else "unknown"
                if server_name in managed or entry.provenance == "hermes_mcp":
                    source = "hermes_mcp"
                    trust = "first_party"
                    owner = "hermes"
                    principal_mode = entry.principal_mode
                else:
                    source = "external_mcp"
                    trust = "configured_external"
                    owner = server_name
                    principal_mode = "none"
            elif wire_name.startswith("generated_"):
                source = "generated"
                trust = "first_party"
                owner = "hermes"
                principal_mode = entry.principal_mode
            else:
                source = "native"
                trust = "first_party"
                owner = entry.owner
                principal_mode = entry.principal_mode

            desc = CapabilityDescriptor(
                capability_id=f"cap_{wire_name}",
                wire_name=wire_name,
                owner=owner,
                source=source,
                trust=trust,
                version="1.0",
                toolset=entry.toolset,
                side_effects=entry.side_effects,
                principal_mode=principal_mode,
                idempotency="supported",
                approval_policy="default",
                data_classification="internal",
            )
            catalog.register_descriptor(desc)

        return catalog

    @classmethod
    def from_registry_snapshot(cls, registry_snapshot: dict) -> "CapabilityCatalog":
        catalog = cls()

        for name, tool_info in registry_snapshot.items():
            explicit_desc = getattr(tool_info, "descriptor", None)
            if explicit_desc is not None and isinstance(explicit_desc, CapabilityDescriptor):
                catalog.register_descriptor(explicit_desc)

        return catalog

    def get(self, wire_name: str) -> Optional[CapabilityDescriptor]:
        return self._descriptors.get(wire_name)

    def require(self, wire_name: str) -> CapabilityDescriptor:
        desc = self.get(wire_name)
        if desc is None:
            raise KeyError(f"Capability descriptor not found for '{wire_name}'")
        return desc
