import sqlite3

import pytest

from hermes_personal.identity import (
    IdentityConflict,
    IdentityRepository,
    UnknownIdentity,
)
from hermes_personal.storage.sqlite import connect


@pytest.fixture
def identity_repository(tmp_path):
    connection = connect(tmp_path / "identity.sqlite")
    repository = IdentityRepository(connection)
    try:
        yield repository
    finally:
        connection.close()


def test_same_owner_resolves_across_linked_channels(identity_repository):
    owner = identity_repository.create_owner("Khoa")
    identity_repository.link(owner.owner_user_id, "telegram", "tg:42")
    identity_repository.link(owner.owner_user_id, "web", "oidc:khoa")

    assert identity_repository.resolve("telegram", "tg:42") == owner
    assert identity_repository.resolve("web", "oidc:khoa") == owner


def test_external_subject_cannot_be_reassigned(identity_repository):
    first = identity_repository.create_owner("first")
    second = identity_repository.create_owner("second")
    identity_repository.link(first.owner_user_id, "cli", "local:khoa")

    with pytest.raises(IdentityConflict):
        identity_repository.link(second.owner_user_id, "cli", "local:khoa")


def test_whitespace_only_external_subject_is_rejected(identity_repository):
    owner = identity_repository.create_owner("Khoa")

    with pytest.raises(ValueError, match="external_subject must not be blank"):
        identity_repository.link(owner.owner_user_id, "telegram", "   ")


def test_unlinked_channel_subject_is_unknown(identity_repository):
    with pytest.raises(UnknownIdentity):
        identity_repository.resolve("web", "oidc:unknown")


def test_unknown_owner_link_is_rolled_back(identity_repository):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        identity_repository.link("missing-owner", "cli", "local:khoa")

    row = identity_repository._connection.execute(
        "SELECT COUNT(*) AS count FROM channel_identity"
    ).fetchone()
    assert row["count"] == 0
