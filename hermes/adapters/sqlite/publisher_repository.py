"""SQLite publication store."""
from __future__ import annotations

from hermes.db import Database, utc_now
from hermes.domain.publisher import Publication, PublicationStatus
from hermes.ports.publisher import PublicationStore


class SQLitePublicationStore(PublicationStore):
    def __init__(self, database: Database):
        self._database = database
        self._database.initialize()

    def upsert(self, publication: Publication) -> Publication:
        now = utc_now()
        with self._database.transaction(immediate=True) as conn:
            existing = conn.execute(
                "SELECT publication_id FROM publications WHERE owner_user_id=? AND project_id=? AND platform=?",
                (publication.owner_user_id, publication.project_id, publication.platform),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE publications SET status=?, post_id=?, caption=?, published_at=?,
                       last_error=?, updated_at=? WHERE publication_id=?""",
                    (publication.status.value, publication.post_id, publication.caption,
                     publication.published_at, publication.last_error, now, existing["publication_id"]),
                )
                return Publication(
                    publication_id=existing["publication_id"], project_id=publication.project_id,
                    owner_user_id=publication.owner_user_id, platform=publication.platform,
                    status=publication.status, post_id=publication.post_id, caption=publication.caption,
                    published_at=publication.published_at, last_error=publication.last_error,
                    created_at=publication.created_at, updated_at=now,
                )
            conn.execute(
                """INSERT INTO publications(publication_id, project_id, owner_user_id, platform,
                   status, post_id, caption, published_at, last_error, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (publication.publication_id, publication.project_id, publication.owner_user_id,
                 publication.platform, publication.status.value, publication.post_id, publication.caption,
                 publication.published_at, publication.last_error, now, now),
            )
        return publication

    def get(self, owner_user_id: str, project_id: str, platform: str) -> Publication | None:
        with self._database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM publications WHERE owner_user_id=? AND project_id=? AND platform=?",
                (owner_user_id, project_id, platform),
            ).fetchone()
        if not row:
            return None
        return Publication(
            publication_id=row["publication_id"], project_id=row["project_id"],
            owner_user_id=row["owner_user_id"], platform=row["platform"],
            status=PublicationStatus(row["status"]), post_id=row["post_id"], caption=row["caption"],
            published_at=row["published_at"], last_error=row["last_error"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def update_status(self, owner_user_id: str, project_id: str, platform: str,
                      status: PublicationStatus, post_id: str | None = None,
                      last_error: str = "") -> Publication | None:
        pub = self.get(owner_user_id, project_id, platform)
        if pub is None:
            return None
        now = utc_now()
        with self._database.transaction(immediate=True) as conn:
            conn.execute(
                """UPDATE publications SET status=?, post_id=COALESCE(?, post_id),
                   last_error=?, published_at=COALESCE(?, published_at), updated_at=?
                   WHERE publication_id=?""",
                (status.value, post_id, last_error,
                 now if status == PublicationStatus.PUBLISHED else None, now, pub.publication_id),
            )
        return self.get(owner_user_id, project_id, platform)
