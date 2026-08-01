import sqlite3

SCHEMA_V6 = """
CREATE TABLE IF NOT EXISTS web_documents (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    requested_url TEXT NOT NULL,
    final_url TEXT NOT NULL,
    title TEXT NOT NULL,
    markdown TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    acquisition_method TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    rights_status TEXT NOT NULL CHECK(rights_status = 'reference_only'),
    warnings_json TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    UNIQUE(owner_user_id, final_url, content_hash)
);

CREATE TABLE IF NOT EXISTS affiliate_run_web_documents (
    run_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, product_id, document_id),
    FOREIGN KEY(run_id) REFERENCES affiliate_research_runs(id) ON DELETE CASCADE,
    FOREIGN KEY(product_id) REFERENCES affiliate_products(id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES web_documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_web_documents_owner_url_hash ON web_documents(owner_user_id, final_url, content_hash);
CREATE INDEX IF NOT EXISTS idx_affiliate_run_web_documents_run_prod ON affiliate_run_web_documents(run_id, product_id);
"""


def apply_schema_v6(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_V6)
