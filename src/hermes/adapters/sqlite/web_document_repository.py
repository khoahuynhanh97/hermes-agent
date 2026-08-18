import json
from datetime import datetime, timezone
from typing import Optional, List
from hermes.db import Database
from hermes.domain.web_document import WebDocument
from hermes.ports.web_document_repository import WebDocumentRepository


class SQLiteWebDocumentRepository(WebDocumentRepository):
    def __init__(self, db: Database):
        self.db = db

    def _row_to_document(self, row) -> WebDocument:
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        warnings = tuple(json.loads(row["warnings_json"])) if row["warnings_json"] else ()
        return WebDocument(
            id=row["id"],
            owner_user_id=row["owner_user_id"],
            run_id="",  # owner-scoped doc, run association is via attachment table
            product_id="",
            requested_url=row["requested_url"],
            final_url=row["final_url"],
            title=row["title"],
            markdown=row["markdown"],
            metadata=metadata,
            acquisition_method=row["acquisition_method"],
            content_hash=row["content_hash"],
            rights_status=row["rights_status"],
            warnings=warnings,
            acquired_at=row["acquired_at"],
        )

    def find_reusable(
        self, owner_user_id: str, normalized_url: str
    ) -> Optional[WebDocument]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM web_documents
                WHERE owner_user_id = ? AND (requested_url = ? OR final_url = ?)
                ORDER BY acquired_at DESC LIMIT 1
                """,
                (owner_user_id, normalized_url, normalized_url),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_document(row)
            return None

    def save(self, document: WebDocument) -> WebDocument:
        metadata_json = json.dumps(document.metadata)
        warnings_json = json.dumps(list(document.warnings))

        with self.db.transaction(immediate=True) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO web_documents (
                    id, owner_user_id, requested_url, final_url, title, markdown,
                    metadata_json, acquisition_method, content_hash, rights_status,
                    warnings_json, acquired_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_user_id, final_url, content_hash) DO NOTHING
                """,
                (
                    document.id,
                    document.owner_user_id,
                    document.requested_url,
                    document.final_url,
                    document.title,
                    document.markdown,
                    metadata_json,
                    document.acquisition_method,
                    document.content_hash,
                    document.rights_status,
                    warnings_json,
                    document.acquired_at,
                ),
            )
            if cursor.rowcount == 0:
                # Existing document matched UNIQUE(owner_user_id, final_url, content_hash)
                cursor.execute(
                    """
                    SELECT * FROM web_documents
                    WHERE owner_user_id = ? AND final_url = ? AND content_hash = ?
                    """,
                    (document.owner_user_id, document.final_url, document.content_hash),
                )
                row = cursor.fetchone()
                if row:
                    return self._row_to_document(row)

            return document

    def attach(
        self, run_id: str, product_id: str, document_id: str, source_kind: str
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO affiliate_run_web_documents (
                    run_id, product_id, document_id, source_kind, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, product_id, document_id, source_kind, created_at),
            )

    def list_for_product(
        self, owner_user_id: str, run_id: str, product_id: str
    ) -> List[WebDocument]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT d.*, arwd.run_id as attached_run_id, arwd.product_id as attached_product_id
                FROM web_documents d
                JOIN affiliate_run_web_documents arwd ON arwd.document_id = d.id
                WHERE d.owner_user_id = ? AND arwd.run_id = ? AND arwd.product_id = ?
                ORDER BY d.acquired_at ASC
                """,
                (owner_user_id, run_id, product_id),
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                doc = self._row_to_document(row)
                # Attach run_id and product_id context
                doc_with_context = WebDocument(
                    id=doc.id,
                    owner_user_id=doc.owner_user_id,
                    run_id=row["attached_run_id"],
                    product_id=row["attached_product_id"],
                    requested_url=doc.requested_url,
                    final_url=doc.final_url,
                    title=doc.title,
                    markdown=doc.markdown,
                    metadata=doc.metadata,
                    acquisition_method=doc.acquisition_method,
                    content_hash=doc.content_hash,
                    rights_status=doc.rights_status,
                    warnings=doc.warnings,
                    acquired_at=doc.acquired_at,
                )
                result.append(doc_with_context)
            return result
