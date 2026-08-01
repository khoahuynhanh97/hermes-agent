import pytest
from hermes.db import Database
from hermes.domain.web_document import WebDocument
from hermes.adapters.sqlite.web_document_repository import SQLiteWebDocumentRepository


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_v6.db"
    db = Database(path=db_path)
    db.initialize()
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO affiliate_products (
                id, owner_user_id, platform, external_product_id, name, category,
                price_vnd, source_type, authorization_scope, rights_status, content_hash,
                created_at, updated_at
            ) VALUES ('prod-1', '42', 'shopee', 'sku1', 'Desk Lamp', 'lamp',
                      100000, 'csv', 'scope', 'status', 'hash', '2026-08-01', '2026-08-01')
            """
        )
        conn.execute(
            """
            INSERT INTO affiliate_research_runs (
                id, owner_user_id, idempotency_key, status, created_at, updated_at
            ) VALUES ('run-1', '42', 'key-1', 'running', '2026-08-01', '2026-08-01')
            """
        )
    return db


def sample_doc(owner_user_id="42", doc_id="doc-1", url="https://example.com/lamp"):
    return WebDocument(
        id=doc_id,
        owner_user_id=owner_user_id,
        run_id="run-1",
        product_id="prod-1",
        requested_url=url,
        final_url=url,
        title="Desk Lamp Specs",
        markdown="# Desk Lamp Specs\n\nHigh quality LED panel.",
        metadata={"author": "Reviewer"},
        acquisition_method="static_http",
        content_hash="hash123abc",
        rights_status="reference_only",
        warnings=(),
        acquired_at="2026-08-01T00:00:00Z",
    )


def test_save_find_and_attach_web_document(test_db):
    repo = SQLiteWebDocumentRepository(test_db)
    doc = sample_doc()

    saved = repo.save(doc)
    assert saved.id == "doc-1"

    found = repo.find_reusable("42", "https://example.com/lamp")
    assert found is not None
    assert found.id == "doc-1"
    assert found.title == "Desk Lamp Specs"

    # Attach to run and product
    repo.attach(run_id="run-1", product_id="prod-1", document_id="doc-1", source_kind="manufacturer")

    docs = repo.list_for_product("42", "run-1", "prod-1")
    assert len(docs) == 1
    assert docs[0].id == "doc-1"
    assert docs[0].run_id == "run-1"
    assert docs[0].product_id == "prod-1"


def test_idempotent_save_same_content(test_db):
    repo = SQLiteWebDocumentRepository(test_db)
    doc1 = sample_doc(doc_id="doc-1")
    doc2 = sample_doc(doc_id="doc-2")  # Same owner, url, content_hash

    repo.save(doc1)
    saved2 = repo.save(doc2)

    # Saved document should return original doc-1 due to UNIQUE conflict handling
    assert saved2.id == "doc-1"


def test_owner_isolation(test_db):
    repo = SQLiteWebDocumentRepository(test_db)
    doc_user1 = sample_doc(owner_user_id="42", doc_id="doc-1")
    repo.save(doc_user1)

    found = repo.find_reusable("99", "https://example.com/lamp")
    assert found is None
