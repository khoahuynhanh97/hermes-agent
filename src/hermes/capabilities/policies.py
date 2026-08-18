from dataclasses import dataclass
from typing import Optional, Literal
from hermes.capabilities.models import CapabilityDescriptor


@dataclass(frozen=True)
class CapabilityPolicy:
    owner: str
    source: str
    trust: str
    side_effects: str
    principal_mode: str
    idempotency: str
    approval_policy: str
    data_classification: str


_NATIVE_TOOLSET_DEFAULTS = {
    # Default for all hermes built-in toolsets is session mode + write side effects
    "default": CapabilityPolicy(
        owner="hermes",
        source="native",
        trust="first_party",
        side_effects="write",
        principal_mode="session",
        idempotency="supported",
        approval_policy="default",
        data_classification="internal",
    ),
    # Some test toolsets
    "test": CapabilityPolicy(
        owner="test",
        source="native",
        trust="first_party",
        side_effects="read",
        principal_mode="none",
        idempotency="supported",
        approval_policy="default",
        data_classification="internal",
    ),
    "test_ts": CapabilityPolicy(
        owner="test",
        source="native",
        trust="first_party",
        side_effects="read",
        principal_mode="session",
        idempotency="supported",
        approval_policy="default",
        data_classification="internal",
    ),
}


# The list of all known production native toolsets
_KNOWN_NATIVE_TOOLSETS = {
    "bfl", "browser", "browser-cdp", "clarify", "code_execution", "computer_use",
    "cronjob", "delegation", "discord", "discord_admin", "feishu_doc", "feishu_drive",
    "file", "hermes-yuanbao", "homeassistant", "image_gen", "kanban", "memory", "project",
    "session_search", "skills", "terminal", "todo", "tts", "video", "video_factory", "video_gen", "vision",
    "web", "x_search"
}

for _ts in _KNOWN_NATIVE_TOOLSETS:
    _NATIVE_TOOLSET_DEFAULTS[_ts] = _NATIVE_TOOLSET_DEFAULTS["default"]


class CapabilityPolicyResolver:
    def resolve_native(self, name: str, toolset: str) -> Optional[CapabilityDescriptor]:
        policy = _NATIVE_TOOLSET_DEFAULTS.get(toolset)
        if policy is None:
            return None
        
        return CapabilityDescriptor(
            capability_id=f"cap_{name}",
            wire_name=name,
            owner=policy.owner,
            source=policy.source,
            trust=policy.trust,
            version="1.0",
            toolset=toolset,
            side_effects=policy.side_effects,
            principal_mode=policy.principal_mode,
            idempotency=policy.idempotency,
            approval_policy=policy.approval_policy,
            data_classification=policy.data_classification,
        )

    def resolve_mcp(
        self,
        server_name: str,
        server_config: dict,
        wire_name: str,
    ) -> CapabilityDescriptor:
        # Check if the server config explicitly declares a capability block
        cap_config = server_config.get("capability", {})
        owner = cap_config.get("owner", server_name)
        source = cap_config.get("source", "external_mcp")
        trust = cap_config.get("trust", "configured_external")
        principal_mode = cap_config.get("principal_mode", "none")
        side_effects = cap_config.get("side_effects", "external")
        toolset = cap_config.get("toolset", f"mcp-{server_name}")
        
        return CapabilityDescriptor(
            capability_id=f"cap_{wire_name}",
            wire_name=wire_name,
            owner=owner,
            source=source,
            trust=trust,
            version="1.0",
            toolset=toolset,
            side_effects=side_effects,
            principal_mode=principal_mode,
            idempotency="supported",
            approval_policy="default",
            data_classification="internal",
        )

