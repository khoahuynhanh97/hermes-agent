# Hermes Gateway Rearchitecture Gate 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a traceable clean upstream baseline and freeze the channel-neutral orchestration contracts that every later Hermes Personal capability will use.

**Architecture:** Start a new isolated branch from pinned NousResearch Hermes Agent commit `0012dd1e0c7efc7e86fa75b89567a492057f0c02`; do not merge the unrelated legacy history. Keep upstream packages unchanged and add project-owned contracts under `hermes_personal`, with compatibility tests guarding the upstream AIAgent, Gateway session, tool registry, and MCP discovery surfaces.

**Tech Stack:** Python 3.11-3.13, frozen dataclasses, stdlib JSON, pytest, Git worktrees, NousResearch Hermes Agent 0.20.5.

## Global Constraints

- Execute this plan in an isolated worktree created with `superpowers:using-git-worktrees` from upstream commit `0012dd1e0c7efc7e86fa75b89567a492057f0c02`.
- Use target branch `codex/hermes-upstream-rearchitecture`; never use `git merge --allow-unrelated-histories`.
- Preserve the legacy checkout and all runtime data; no legacy database, artifact, media, or user file is modified.
- Keep upstream core files unchanged except `pyproject.toml` packaging metadata; all project-owned Python code belongs under `hermes_personal`.
- Authenticated adapters, never model-generated fields, supply principal identity.
- Contracts are provider-neutral, channel-neutral, immutable, and serializable without importing FastAPI, Telegram, Product Intelligence, or Video Factory.
- Use fake objects only; no network or paid provider call is permitted in tests.
- Run commands with native PowerShell syntax from the target worktree root.

## Program Position

This is Gate 1 of the seven-gate delivery program in the approved design. Gate 1 does not port business capabilities. Its contracts are the required input for the later Gateway/session, capability/MCP, workflow/approval, Product-to-Video, learning, and supervisor plans.

## Target File Map

| File | Responsibility |
| --- | --- |
| `hermes_personal/provenance.py` | Load and validate the pinned source-lineage record. |
| `hermes_personal/data/upstream-baseline.json` | Canonical upstream and legacy baseline identifiers. |
| `hermes_personal/contracts/principal.py` | Authenticated principal value object. |
| `hermes_personal/contracts/turn.py` | Channel-neutral turn, attachment, and channel feature contracts. |
| `hermes_personal/contracts/operator.py` | Deterministic operator command contract. |
| `hermes_personal/contracts/events.py` | Shared event envelope for all output channels. |
| `hermes_personal/contracts/capability.py` | Stable capability descriptor and in-memory catalog. |
| `docs/architecture-decisions/011-upstream-gateway-rearchitecture.md` | Records unrelated histories and clean-target branch policy. |
| `tests/hermes_personal/` | Provenance, contract, catalog, boundary, and upstream compatibility tests. |

---

### Task 1: Establish The Clean Upstream Baseline

**Files:**
- Create: `hermes_personal/__init__.py`
- Create: `hermes_personal/provenance.py`
- Create: `hermes_personal/data/upstream-baseline.json`
- Create: `docs/architecture-decisions/011-upstream-gateway-rearchitecture.md`
- Modify: `pyproject.toml` package discovery and package data
- Test: `tests/hermes_personal/test_provenance.py`

**Interfaces:**
- Consumes: Git branch `upstream/main` pinned to `0012dd1e0c7efc7e86fa75b89567a492057f0c02`.
- Produces: `load_upstream_baseline() -> UpstreamBaseline` for startup diagnostics and migration tooling.

- [ ] **Step 1: Verify the isolated target starts from the pinned upstream commit**

Run:

```powershell
git branch --show-current
git rev-parse HEAD
git merge-base 'codex/hermes-orchestrator-unification' HEAD
uv sync --extra dev
```

Expected: branch is `codex/hermes-upstream-rearchitecture`, `HEAD` is `0012dd1e0c7efc7e86fa75b89567a492057f0c02`, `git merge-base` exits `1` with no SHA, and `uv sync` exits `0`. Stop if a merge base is printed.

- [ ] **Step 2: Bring the approved design and this plan into the clean branch without joining histories**

Run:

```powershell
$paths = @(
  'docs/superpowers/specs/2026-08-22-hermes-upstream-gateway-rearchitecture-design.md',
  'docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-1.md'
)
$docCommits = git log --reverse --format='%H' 'codex/hermes-orchestrator-unification' -- $paths
git cherry-pick $docCommits
```

Expected: both approved documents exist in the clean worktree and no legacy source tree is introduced.

- [ ] **Step 3: Write the failing provenance test**

Create `tests/hermes_personal/test_provenance.py`:

```python
from hermes_personal.provenance import load_upstream_baseline


def test_pinned_upstream_baseline_is_traceable_and_unrelated():
    baseline = load_upstream_baseline()

    assert baseline.schema_version == 1
    assert baseline.upstream_repository == "https://github.com/NousResearch/hermes-agent.git"
    assert baseline.upstream_branch == "main"
    assert baseline.upstream_sha == "0012dd1e0c7efc7e86fa75b89567a492057f0c02"
    assert baseline.legacy_repository == "https://github.com/khoahuynhanh97/hermes-agent.git"
    assert baseline.legacy_branch == "codex/hermes-orchestrator-unification"
    assert baseline.legacy_head == "9d63f406f264b3513af9e369bb8d8638f4c02261"
    assert baseline.history_relation == "unrelated"
```

- [ ] **Step 4: Run the provenance test and verify it fails**

Run:

```powershell
uv run pytest tests/hermes_personal/test_provenance.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'hermes_personal'`.

- [ ] **Step 5: Add the package, immutable baseline data, and loader**

Create `hermes_personal/__init__.py`:

```python
"""Project-owned extensions for the Hermes Personal orchestrator."""
```

Create `hermes_personal/data/upstream-baseline.json`:

```json
{
  "schema_version": 1,
  "upstream_repository": "https://github.com/NousResearch/hermes-agent.git",
  "upstream_branch": "main",
  "upstream_sha": "0012dd1e0c7efc7e86fa75b89567a492057f0c02",
  "observed_at": "2026-08-22T06:34:02Z",
  "legacy_repository": "https://github.com/khoahuynhanh97/hermes-agent.git",
  "legacy_branch": "codex/hermes-orchestrator-unification",
  "legacy_head": "9d63f406f264b3513af9e369bb8d8638f4c02261",
  "history_relation": "unrelated"
}
```

Create `hermes_personal/provenance.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal


@dataclass(frozen=True)
class UpstreamBaseline:
    schema_version: int
    upstream_repository: str
    upstream_branch: str
    upstream_sha: str
    observed_at: str
    legacy_repository: str
    legacy_branch: str
    legacy_head: str
    history_relation: Literal["unrelated"]


def load_upstream_baseline() -> UpstreamBaseline:
    resource = files("hermes_personal").joinpath("data", "upstream-baseline.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    baseline = UpstreamBaseline(**payload)
    if baseline.schema_version != 1:
        raise ValueError(f"Unsupported upstream baseline schema: {baseline.schema_version}")
    if baseline.history_relation != "unrelated":
        raise ValueError(f"Unsupported history relation: {baseline.history_relation}")
    for field_name in ("upstream_sha", "legacy_head"):
        value = getattr(baseline, field_name)
        if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError(f"Invalid {field_name}: {value!r}")
    return baseline
```

Modify the existing `[tool.setuptools.packages.find]` include list in `pyproject.toml` to add:

```toml
"hermes_personal", "hermes_personal.*"
```

Add under `[tool.setuptools.package-data]`:

```toml
hermes_personal = ["data/*.json"]
```

- [ ] **Step 6: Record ADR-011**

Create `docs/architecture-decisions/011-upstream-gateway-rearchitecture.md`:

```markdown
# ADR-011: Clean Upstream Gateway Rearchitecture

**Status:** Accepted

**Date:** 2026-08-22

## Context

The legacy Hermes Personal branch and NousResearch Hermes Agent `main` have no
Git merge base. Combining them with an unrelated-history merge would obscure
ownership, make upstream updates unsafe, and carry legacy routing into the new
runtime.

## Decision

The target branch starts from upstream commit
`0012dd1e0c7efc7e86fa75b89567a492057f0c02`. Project-owned behavior is ported
through `hermes_personal`, plugins, skills, MCP adapters, and reviewed upstream
extension points. The legacy branch is a read-only migration source until data
and behavioral parity are verified.

The team must not use `git merge --allow-unrelated-histories` between these
roots. Upstream changes are fetched and reviewed against the pinned baseline;
custom changes are replayed through contract-tested commits.

## Consequences

- Upstream history and updates remain traceable.
- Existing Hermes Personal data is preserved and migrated explicitly.
- Product Intelligence and Video Factory are ported after canonical contracts
  are stable.
- Cutover requires parity tests and a rollback window.

## References

- `docs/superpowers/specs/2026-08-22-hermes-upstream-gateway-rearchitecture-design.md`
- `hermes_personal/data/upstream-baseline.json`
```

- [ ] **Step 7: Run the focused test**

Run:

```powershell
uv run pytest tests/hermes_personal/test_provenance.py -q
```

Expected: `1 passed`.

- [ ] **Step 8: Commit the baseline**

```powershell
git add -- pyproject.toml hermes_personal docs/architecture-decisions/011-upstream-gateway-rearchitecture.md tests/hermes_personal/test_provenance.py
git commit -m "chore: pin hermes upstream baseline"
```

---

### Task 2: Define Principal And Agent Turn Contracts

**Files:**
- Create: `hermes_personal/contracts/__init__.py`
- Create: `hermes_personal/contracts/principal.py`
- Create: `hermes_personal/contracts/turn.py`
- Test: `tests/hermes_personal/contracts/test_turn.py`

**Interfaces:**
- Consumes: authenticated actor, owner, channel, and session identifiers from a future Gateway adapter.
- Produces: `PrincipalContext`, `AttachmentRef`, `ChannelCapabilities`, and `AgentTurnRequest`.

- [ ] **Step 1: Write failing turn contract tests**

Create `tests/hermes_personal/contracts/test_turn.py`:

```python
from datetime import datetime, timezone

import pytest

from hermes_personal.contracts import (
    AgentTurnRequest,
    AttachmentRef,
    ChannelCapabilities,
    PrincipalContext,
)


def test_turn_derives_ids_without_losing_authenticated_identity():
    principal = PrincipalContext(
        actor_id="telegram:42",
        owner_user_id="user:42",
        channel="telegram",
        session_id="telegram:100",
        roles=("admin",),
    )
    request = AgentTurnRequest(
        principal=principal,
        message="research this product",
        locale="vi-VN",
        channel_capabilities=ChannelCapabilities(
            streaming=True,
            interactive_controls=True,
            attachments=True,
        ),
    )

    assert request.channel == "telegram"
    assert request.session_id == "telegram:100"
    assert request.turn_id.startswith("turn_")
    assert request.idempotency_key == request.turn_id
    assert request.occurred_at.tzinfo is timezone.utc


def test_turn_carries_typed_attachment_and_explicit_workflow_handoff():
    principal = PrincipalContext("cli:nina", "user:42", "cli", "cli:work", ())
    attachment = AttachmentRef(
        attachment_id="asset_1",
        kind="document",
        media_type="application/pdf",
        uri="hermes://assets/asset_1",
        size_bytes=512,
        digest_sha256="a" * 64,
    )
    request = AgentTurnRequest(
        principal=principal,
        message="continue this workflow",
        workflow_id="wf_123",
        attachments=(attachment,),
        occurred_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    assert request.attachments == (attachment,)
    assert request.workflow_id == "wf_123"


def test_turn_rejects_blank_message_without_attachments():
    principal = PrincipalContext("web:42", "user:42", "web", "web:s1", ())
    with pytest.raises(ValueError, match="message or attachment"):
        AgentTurnRequest(principal=principal, message="   ")
```

- [ ] **Step 2: Run tests and verify collection fails**

Run:

```powershell
uv run pytest tests/hermes_personal/contracts/test_turn.py -q
```

Expected: FAIL because `hermes_personal.contracts` does not exist.

- [ ] **Step 3: Implement the immutable principal contract**

Create `hermes_personal/contracts/principal.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChannelName = Literal["telegram", "cli", "web", "omni"]


@dataclass(frozen=True)
class PrincipalContext:
    actor_id: str
    owner_user_id: str
    channel: ChannelName
    session_id: str
    roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.channel not in {"telegram", "cli", "web", "omni"}:
            raise ValueError(f"unsupported channel: {self.channel}")
        for field_name in ("actor_id", "owner_user_id", "session_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be blank")
```

- [ ] **Step 4: Implement attachment, channel feature, and turn contracts**

Create `hermes_personal/contracts/turn.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping
from uuid import uuid4

from .principal import ChannelName, PrincipalContext

AttachmentKind = Literal["image", "video", "audio", "document", "other"]


@dataclass(frozen=True)
class AttachmentRef:
    attachment_id: str
    kind: AttachmentKind
    media_type: str
    uri: str
    size_bytes: int | None = None
    digest_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.attachment_id.strip() or not self.uri.strip():
            raise ValueError("attachment_id and uri must not be blank")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if self.digest_sha256 is not None:
            digest = self.digest_sha256
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("digest_sha256 must be lowercase SHA-256")


@dataclass(frozen=True)
class ChannelCapabilities:
    streaming: bool = False
    interactive_controls: bool = False
    attachments: bool = False


@dataclass(frozen=True)
class AgentTurnRequest:
    principal: PrincipalContext
    message: str
    schema_version: int = 1
    attachments: tuple[AttachmentRef, ...] = ()
    conversation_history: tuple[Mapping[str, Any], ...] = ()
    enabled_toolsets: tuple[str, ...] = ()
    workflow_id: str | None = None
    locale: str = "vi-VN"
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    turn_id: str = field(default_factory=lambda: f"turn_{uuid4().hex}")
    idempotency_key: str = ""
    channel_capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported AgentTurnRequest schema: {self.schema_version}")
        if not self.message.strip() and not self.attachments:
            raise ValueError("message or attachment is required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        object.__setattr__(
            self,
            "conversation_history",
            tuple(MappingProxyType(dict(message)) for message in self.conversation_history),
        )
        if not self.idempotency_key.strip():
            object.__setattr__(self, "idempotency_key", self.turn_id)

    @property
    def channel(self) -> ChannelName:
        return self.principal.channel

    @property
    def session_id(self) -> str:
        return self.principal.session_id
```

Create `hermes_personal/contracts/__init__.py`:

```python
from .principal import ChannelName, PrincipalContext
from .turn import AgentTurnRequest, AttachmentRef, ChannelCapabilities

__all__ = [
    "AgentTurnRequest",
    "AttachmentRef",
    "ChannelCapabilities",
    "ChannelName",
    "PrincipalContext",
]
```

- [ ] **Step 5: Run turn contract tests**

Run:

```powershell
uv run pytest tests/hermes_personal/contracts/test_turn.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Commit turn contracts**

```powershell
git add -- hermes_personal/contracts tests/hermes_personal/contracts/test_turn.py
git commit -m "feat: define canonical agent turn contract"
```

---

### Task 3: Define Operator Commands And Shared Agent Events

**Files:**
- Create: `hermes_personal/contracts/operator.py`
- Create: `hermes_personal/contracts/events.py`
- Create: `hermes_personal/contracts/serialization.py`
- Modify: `hermes_personal/contracts/__init__.py`
- Test: `tests/hermes_personal/contracts/test_operator_events.py`

**Interfaces:**
- Consumes: `PrincipalContext` and correlation IDs from the turn/workflow boundary.
- Produces: `OperatorCommand` for deterministic mutations and `AgentEvent` for channel-neutral progress/output.

- [ ] **Step 1: Write failing command and event tests**

Create `tests/hermes_personal/contracts/test_operator_events.py`:

```python
from datetime import timezone

import pytest

from hermes_personal.contracts import (
    AgentEvent,
    OperatorCommand,
    PrincipalContext,
    to_primitive,
)


def test_operator_command_is_owner_bound_and_idempotent():
    principal = PrincipalContext("telegram:42", "user:42", "telegram", "telegram:100")
    command = OperatorCommand(
        principal=principal,
        command_type="approve",
        target_id="approval_7",
        expected_version=3,
        payload={"decision": "approved"},
    )

    assert command.command_id.startswith("cmd_")
    assert command.idempotency_key == command.command_id
    assert command.owner_user_id == "user:42"
    assert command.occurred_at.tzinfo is timezone.utc
    assert to_primitive(command)["payload"] == {"decision": "approved"}


def test_agent_event_keeps_cross_channel_correlation():
    event = AgentEvent(
        event_type="workflow_state",
        principal_id="user:42",
        session_id="web:s1",
        turn_id="turn_1",
        workflow_id="wf_1",
        job_id="job_1",
        approval_id="approval_1",
        tool_call_id="tool_1",
        sequence=4,
        data={"state": "AwaitingBriefApproval"},
    )

    assert event.event_id.startswith("evt_")
    assert event.data["state"] == "AwaitingBriefApproval"


def test_agent_event_rejects_negative_sequence():
    with pytest.raises(ValueError, match="sequence"):
        AgentEvent(
            event_type="warning",
            principal_id="user:42",
            session_id="cli:s1",
            turn_id="turn_1",
            sequence=-1,
        )
```

- [ ] **Step 2: Run tests and verify imports fail**

Run:

```powershell
uv run pytest tests/hermes_personal/contracts/test_operator_events.py -q
```

Expected: FAIL because `OperatorCommand` and `AgentEvent` are not exported.

- [ ] **Step 3: Implement deterministic operator commands**

Create `hermes_personal/contracts/operator.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping
from uuid import uuid4

from .principal import PrincipalContext

OperatorCommandType = Literal[
    "approve", "reject", "retry", "cancel", "upload", "form_update"
]


@dataclass(frozen=True)
class OperatorCommand:
    principal: PrincipalContext
    command_type: OperatorCommandType
    target_id: str
    expected_version: int
    schema_version: int = 1
    payload: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    command_id: str = field(default_factory=lambda: f"cmd_{uuid4().hex}")
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported OperatorCommand schema: {self.schema_version}")
        if not self.target_id.strip():
            raise ValueError("target_id must not be blank")
        if self.expected_version < 0:
            raise ValueError("expected_version must be non-negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        if not self.idempotency_key.strip():
            object.__setattr__(self, "idempotency_key", self.command_id)

    @property
    def owner_user_id(self) -> str:
        return self.principal.owner_user_id
```

- [ ] **Step 4: Implement the shared event envelope**

Create `hermes_personal/contracts/events.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping
from uuid import uuid4

AgentEventType = Literal[
    "text_delta",
    "clarification_required",
    "tool_activity",
    "workflow_state",
    "approval_required",
    "cost_update",
    "artifact",
    "warning",
    "completed",
    "failed",
]


@dataclass(frozen=True)
class AgentEvent:
    event_type: AgentEventType
    principal_id: str
    session_id: str
    turn_id: str
    sequence: int
    schema_version: int = 1
    data: Mapping[str, Any] = field(default_factory=dict)
    workflow_id: str | None = None
    job_id: str | None = None
    approval_id: str | None = None
    tool_call_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex}")

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported AgentEvent schema: {self.schema_version}")
        for field_name in ("principal_id", "session_id", "turn_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))
```

Create `hermes_personal/contracts/serialization.py`:

```python
from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any, Mapping


def to_primitive(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_primitive(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    return value
```

Replace `hermes_personal/contracts/__init__.py` with:

```python
from .events import AgentEvent, AgentEventType
from .operator import OperatorCommand, OperatorCommandType
from .principal import ChannelName, PrincipalContext
from .serialization import to_primitive
from .turn import AgentTurnRequest, AttachmentRef, ChannelCapabilities

__all__ = [
    "AgentEvent",
    "AgentEventType",
    "AgentTurnRequest",
    "AttachmentRef",
    "ChannelCapabilities",
    "ChannelName",
    "OperatorCommand",
    "OperatorCommandType",
    "PrincipalContext",
    "to_primitive",
]
```

- [ ] **Step 5: Run command and event tests**

Run:

```powershell
uv run pytest tests/hermes_personal/contracts/test_operator_events.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Commit operator and event contracts**

```powershell
git add -- hermes_personal/contracts tests/hermes_personal/contracts/test_operator_events.py
git commit -m "feat: add operator command and agent event contracts"
```

---

### Task 4: Define Stable Capability Descriptors And Catalog Resolution

**Files:**
- Create: `hermes_personal/contracts/capability.py`
- Modify: `hermes_personal/contracts/__init__.py`
- Test: `tests/hermes_personal/contracts/test_capability.py`

**Interfaces:**
- Consumes: native, plugin, or MCP wire-tool registration metadata.
- Produces: stable `CapabilityDescriptor` records and `CapabilityCatalog.resolve(identifier)` independent of provider wire names.

- [ ] **Step 1: Write failing stable-ID catalog tests**

Create `tests/hermes_personal/contracts/test_capability.py`:

```python
import pytest

from hermes_personal.contracts import CapabilityCatalog, CapabilityDescriptor


def descriptor(wire_name: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id="product.research",
        wire_name=wire_name,
        owner="product_intelligence",
        source="external_mcp",
        trust="configured_external",
        version="1.0.0",
        toolset="product-intelligence",
        side_effects="external",
        principal_mode="session",
        idempotency="supported",
        approval_policy="none",
        data_classification="internal",
        input_schema_version="1.0",
        output_schema_version="1.0",
        risk="low",
        cost_class="free",
        provider_policy="product-intelligence-default",
        health="healthy",
        allowed_skills=("product-research",),
        allowed_workflows=("product_research", "product_to_video"),
    )


def test_catalog_resolves_stable_id_and_current_wire_name():
    catalog = CapabilityCatalog()
    item = descriptor("mcp__product_intelligence__research_product")
    catalog.register(item)

    assert catalog.resolve("product.research") is item
    assert catalog.resolve("mcp__product_intelligence__research_product") is item


def test_wire_binding_can_change_without_changing_capability_id():
    catalog = CapabilityCatalog()
    catalog.register(descriptor("mcp__pi__research_product"))

    rebound = catalog.rebind_wire(
        "product.research", "mcp__product_intelligence_v2__research"
    )

    assert rebound.capability_id == "product.research"
    assert catalog.resolve("mcp__product_intelligence_v2__research") is rebound
    with pytest.raises(KeyError):
        catalog.resolve("mcp__pi__research_product")


def test_catalog_rejects_two_capabilities_bound_to_one_wire_name():
    catalog = CapabilityCatalog()
    catalog.register(descriptor("mcp__pi__research"))
    conflict = CapabilityDescriptor(
        **{
            **descriptor("mcp__pi__research").__dict__,
            "capability_id": "product.resource_pack.build",
        }
    )

    with pytest.raises(ValueError, match="wire name"):
        catalog.register(conflict)
```

- [ ] **Step 2: Run tests and verify imports fail**

Run:

```powershell
uv run pytest tests/hermes_personal/contracts/test_capability.py -q
```

Expected: FAIL because capability contracts are not exported.

- [ ] **Step 3: Implement the descriptor and dual-index catalog**

Create `hermes_personal/contracts/capability.py`:

```python
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
```

Replace `hermes_personal/contracts/__init__.py` with:

```python
from .capability import CapabilityCatalog, CapabilityDescriptor
from .events import AgentEvent, AgentEventType
from .operator import OperatorCommand, OperatorCommandType
from .principal import ChannelName, PrincipalContext
from .serialization import to_primitive
from .turn import AgentTurnRequest, AttachmentRef, ChannelCapabilities

__all__ = [
    "AgentEvent",
    "AgentEventType",
    "AgentTurnRequest",
    "AttachmentRef",
    "CapabilityCatalog",
    "CapabilityDescriptor",
    "ChannelCapabilities",
    "ChannelName",
    "OperatorCommand",
    "OperatorCommandType",
    "PrincipalContext",
    "to_primitive",
]
```

- [ ] **Step 4: Run capability tests**

Run:

```powershell
uv run pytest tests/hermes_personal/contracts/test_capability.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit capability contracts**

```powershell
git add -- hermes_personal/contracts tests/hermes_personal/contracts/test_capability.py
git commit -m "feat: add stable capability catalog contracts"
```

---

### Task 5: Lock Contract Boundaries And Upstream Compatibility

**Files:**
- Create: `tests/hermes_personal/test_contract_architecture.py`
- Create: `tests/hermes_personal/test_upstream_compatibility.py`

**Interfaces:**
- Consumes: upstream `AIAgent`, `SessionStore`, `ToolRegistry`, and MCP discovery public surfaces.
- Produces: a fail-fast compatibility gate for every later upstream update and project-owned adapter.

- [ ] **Step 1: Write the contract dependency boundary test**

Create `tests/hermes_personal/test_contract_architecture.py`:

```python
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "hermes_personal" / "contracts"
FORBIDDEN_ROOTS = {
    "fastapi",
    "gateway",
    "telegram",
    "product_intelligence",
    "video_factory",
    "run_agent",
    "tools",
}


def test_contracts_do_not_import_transport_provider_or_upstream_runtime():
    violations = []
    for path in CONTRACT_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".", 1)[0] in FORBIDDEN_ROOTS:
                    violations.append(f"{path.name}: {name}")
    assert violations == []
```

- [ ] **Step 2: Write the upstream public-surface compatibility test**

Create `tests/hermes_personal/test_upstream_compatibility.py`:

```python
import inspect


def test_upstream_agent_turn_surface_is_available():
    from run_agent import AIAgent

    parameters = inspect.signature(AIAgent.run_conversation).parameters
    assert {"user_message", "conversation_history", "task_id"} <= set(parameters)


def test_upstream_gateway_session_surface_is_available():
    from gateway.session import SessionContext, SessionStore

    assert SessionContext is not None
    assert SessionStore is not None


def test_upstream_tool_and_mcp_discovery_surfaces_are_available():
    from tools.mcp_tool import discover_mcp_tools, refresh_agent_mcp_tools
    from tools.registry import ToolRegistry

    assert callable(discover_mcp_tools)
    assert callable(refresh_agent_mcp_tools)
    assert callable(ToolRegistry.register)
    assert callable(ToolRegistry.get_definitions)
    assert callable(ToolRegistry.dispatch)
```

- [ ] **Step 3: Run all Gate 1 project-owned tests**

Run:

```powershell
uv run pytest tests/hermes_personal -q
```

Expected: `14 passed`.

- [ ] **Step 4: Run the focused upstream regression set**

Run:

```powershell
uv run pytest tests/tools/test_registry.py tests/tools/test_mcp_capability_gating.py tests/gateway/test_session.py -q
```

Expected: exit code `0` with no failures. Record the exact test count in the execution report rather than hard-coding a count that can change with upstream.

- [ ] **Step 5: Verify package build contents**

Run:

```powershell
uv build --wheel
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run python -c "import glob,zipfile; p=glob.glob('dist/*.whl')[-1]; z=zipfile.ZipFile(p); names=set(z.namelist()); assert 'hermes_personal/data/upstream-baseline.json' in names; print(p)"
```

Expected: both commands exit `0`, and the wheel path is printed.

- [ ] **Step 6: Commit compatibility gates**

```powershell
git add -- tests/hermes_personal/test_contract_architecture.py tests/hermes_personal/test_upstream_compatibility.py
git commit -m "test: lock upstream orchestration compatibility"
```

- [ ] **Step 7: Run final Gate 1 verification**

Run:

```powershell
uv run pytest tests/hermes_personal tests/tools/test_registry.py tests/tools/test_mcp_capability_gating.py tests/gateway/test_session.py -q
git diff --check
git status --short
```

Expected: pytest exits `0`; `git diff --check` prints nothing; `git status --short` contains no tracked source changes. Build artifacts under `dist/` may be untracked and must not be committed.

## Gate 1 Exit Criteria

- The target branch descends from the pinned upstream SHA and has no unrelated-history merge.
- ADR-011 and the packaged provenance record identify both source roots exactly.
- Principal, Agent Turn, Operator Command, Agent Event, and Capability contracts are immutable and transport/provider neutral.
- Capability resolution works by stable ID and current wire name.
- Upstream AIAgent, Gateway session, registry, and MCP discovery compatibility checks pass.
- The wheel contains `hermes_personal` and its baseline JSON.
- No legacy runtime data or paid provider was touched.

After this gate passes, write the Gate 2 plan for Gateway convergence, global identity mapping, per-channel sessions, and explicit workflow handoff. Do not port Product Intelligence or Video Factory before Gate 2 is accepted.
