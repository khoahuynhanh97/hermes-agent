from __future__ import annotations

import pytest

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.capabilities.snapshots import (
    CapabilitySnapshotRepository,
    compute_snapshot_digest,
)
from hermes_personal.storage.sqlite import connect


def _create_full_bindings(
    overrides: dict[str, dict[str, str]] | None = None,
) -> list[ImplementationBinding]:
    overrides = overrides or {}
    bindings: list[ImplementationBinding] = []
    for cap_id in INITIAL_CAPABILITIES:
        ov = overrides.get(cap_id, {})
        bindings.append(
            ImplementationBinding(
                capability_id=cap_id,
                wire_name=ov.get("wire_name", f"mcp__provider__{cap_id.replace('.', '_')}"),
                source="hermes_mcp",
                provider=ov.get("provider", "test_provider"),
                implementation_version="1.0.0",
                input_schema_version="1.0",
                output_schema_version="1.0",
                schema_digest=ov.get("schema_digest", "sha256:abc123def456"),
                health=ov.get("health", "healthy"),  # type: ignore[arg-type]
            )
        )
    return bindings


@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "test_snapshots.db"
    conn = connect(db_path)
    return CapabilitySnapshotRepository(conn), db_path


def test_equal_discovery_reuses_snapshot(repo):
    repository, _ = repo
    bindings = _create_full_bindings()

    first = repository.save(bindings)
    second = repository.save(bindings)

    assert first.snapshot_id == second.snapshot_id
    assert first.digest == second.digest
    assert len(first.bindings) == 10


def test_changed_wire_binding_creates_new_snapshot(repo):
    repository, _ = repo
    first_bindings = _create_full_bindings()
    first = repository.save(first_bindings)

    second_bindings = _create_full_bindings(
        overrides={"product.research": {"wire_name": "mcp__provider_v2__research"}}
    )
    second = repository.save(second_bindings)

    assert first.snapshot_id != second.snapshot_id
    assert first.digest != second.digest

    loaded_first = repository.get(first.snapshot_id)
    assert loaded_first is not None
    assert loaded_first.digest == first.digest


def test_digest_is_order_independent():
    bindings = _create_full_bindings()
    reversed_bindings = list(reversed(bindings))

    digest1, sorted1 = compute_snapshot_digest(bindings)
    digest2, sorted2 = compute_snapshot_digest(reversed_bindings)

    assert digest1 == digest2
    assert sorted1 == sorted2


def test_singleton_active_snapshot_state_pointer(repo):
    repository, _ = repo
    assert repository.get_active() is None

    bindings_v1 = _create_full_bindings()
    active_v1 = repository.save_and_activate(bindings_v1)

    loaded_active = repository.get_active()
    assert loaded_active is not None
    assert loaded_active.snapshot_id == active_v1.snapshot_id

    bindings_v2 = _create_full_bindings(
        overrides={"video.render": {"health": "degraded"}}
    )
    active_v2 = repository.save_and_activate(bindings_v2)

    loaded_active_v2 = repository.get_active()
    assert loaded_active_v2 is not None
    assert loaded_active_v2.snapshot_id == active_v2.snapshot_id
    assert loaded_active_v2.snapshot_id != active_v1.snapshot_id


def test_incomplete_snapshot_activation_fails_and_rolls_back(repo):
    repository, _ = repo
    full_bindings = _create_full_bindings()
    active_v1 = repository.save_and_activate(full_bindings)

    incomplete_bindings = full_bindings[:5]

    with pytest.raises(ValueError, match="snapshot incomplete, missing capabilities"):
        repository.save_and_activate(incomplete_bindings)

    assert repository.get_active().snapshot_id == active_v1.snapshot_id


def test_unknown_capability_id_or_duplicate_id_rejected(repo):
    repository, _ = repo
    full_bindings = _create_full_bindings()

    duplicate_bindings = full_bindings + [full_bindings[0]]
    with pytest.raises(ValueError, match="duplicate capability_id in bindings"):
        repository.save(duplicate_bindings)

    unknown_binding = ImplementationBinding(
        capability_id="unknown.capability",
        wire_name="mcp__unknown",
        source="hermes_mcp",
        provider="unknown",
        implementation_version="1.0.0",
        input_schema_version="1.0",
        output_schema_version="1.0",
        schema_digest="sha256:111",
        health="healthy",
    )
    with pytest.raises(ValueError, match="unknown capability_id outside INITIAL_CAPABILITIES"):
        repository.save([unknown_binding])


def test_active_snapshot_survives_repository_restart(repo):
    repository, db_path = repo
    bindings = _create_full_bindings()
    saved = repository.save_and_activate(bindings)

    new_conn = connect(db_path)
    new_repo = CapabilitySnapshotRepository(new_conn)

    active = new_repo.get_active()
    assert active is not None
    assert active.snapshot_id == saved.snapshot_id
    assert active.digest == saved.digest
    assert len(active.bindings) == 10
