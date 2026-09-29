from __future__ import annotations

import pytest

from hermes_personal.learning.artifacts import SourceArtifactStore
from hermes_personal.learning.models import LearningCandidate
from hermes_personal.learning.repository import LearningRepository
from hermes_personal.storage.sqlite import connect as sqlite_connect


@pytest.fixture
def db_conn(tmp_path):
    conn = sqlite_connect(tmp_path / "artifacts_test.db")
    conn.execute(
        "INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) "
        "VALUES ('user1', 'User 1', '2026-08-24T00:00:00Z')"
    )
    conn.commit()
    yield conn
    conn.close()


def test_source_artifact_store_and_link(db_conn, tmp_path):
    repo = LearningRepository(db_conn)
    store_dir = tmp_path / "sources"
    store = SourceArtifactStore(db_conn, base_dir=store_dir)

    from hermes_personal.learning.models import EvidenceRef

    ev = EvidenceRef(
        evidence_id="ev_art_1",
        source_type="turn",
        source_id="turn_1",
        digest="sha256:112233",
        excerpt="Audio trends research",
    )
    cand = LearningCandidate(
        candidate_id="cand_media_1",
        owner_user_id="user1",
        kind="knowledge",
        title="TikTok Audio Strategy",
        content="Use trending music in background",
        evidence=(ev,),
        status="draft",
    )
    repo.create_candidate(cand)

    # 2. Store sample media file (transcript)
    sample_txt = tmp_path / "transcript.txt"
    sample_txt.write_text("Detailed video transcript text...", encoding="utf-8")

    rec = store.store_file(
        candidate_id="cand_media_1",
        owner_user_id="user1",
        source_path=sample_txt,
        kind="transcript",
        mime_type="text/plain",
    )

    assert rec.artifact_id.startswith("art_")
    assert rec.candidate_id == "cand_media_1"
    assert rec.kind == "transcript"
    assert rec.size_bytes > 0
    assert len(rec.sha256) == 64

    # 3. List artifacts for candidate
    artifacts = store.list_artifacts_for_candidate("cand_media_1")
    assert len(artifacts) == 1
    assert artifacts[0].artifact_id == rec.artifact_id
    assert (store.base_dir / artifacts[0].relative_path).is_file()
