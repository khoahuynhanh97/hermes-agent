"""Tests for the spec-compliant ``AffiliateAnalysis`` Tier-3 pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Sequence
from unittest.mock import MagicMock

import pytest

from hermes.adapters.model.affiliate_analysis_gateway import (
    AffiliateAnalysisGateway,
    validate_analysis_payload,
)
from hermes.adapters.sqlite.affiliate_analysis_repository import (
    SQLiteAffiliateAnalysisRepository,
    _content_hash,
)
from hermes.application.affiliate_analysis_service import (
    AffiliateAnalysisService,
    AffiliateAnalysisValidationError,
)
from hermes.domain.affiliate_analysis import (
    AffiliateAnalysis,
    TikTokScript,
    VisualPrompts,
)
from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ReferenceMetadata,
)


def _make_product(**overrides: Any) -> AffiliateProduct:
    base = dict(
        id="prod_1",
        owner_user_id="u1",
        platform="shopee",
        external_product_id="ext_1",
        name="Mechanical keyboard",
        category="keyboard",
        price_vnd=800_000,
        sold_count=12,
        rating=4.7,
        review_count=8,
        commission_rate=0.1,
        shop_name="Acme",
        product_url="https://example.test/keyboard",
        image_urls=("https://example.test/img.jpg",),
        visual_signals=("rgb", "tactile_interaction"),
        source_type="shopee_csv",
        source_url="https://example.test/keyboard",
        authorization_scope="public",
        rights_status="reference_only",
        content_hash="abc",
        created_at="2026-08-02T00:00:00+00:00",
        updated_at="2026-08-02T00:00:00+00:00",
    )
    base.update(overrides)
    return AffiliateProduct(**base)


def _good_payload() -> dict[str, Any]:
    return {
        "usp_list": ["Gõ phím im lặng", "Layout 75% gọn gàng"],
        "pain_points": ["Bàn phím cơ ồn ào khi làm việc đêm", "Layout fullsize chiếm nhiều diện tích"],
        "target_audience": "Dân văn phòng làm việc đêm, thích setup gọn gàng",
        "tiktok_script": {
            "hook": "Bạn có biết bàn phím cơ cũng có thể im lặng tuyệt đối?",
            "body": "Mình gõ thử trong 3 giây, không một tiếng click. Layout 75% gọn bàn, RGB đổi màu theo nhịp.",
            "cta": "Chỉ 800k, bấm giỏ hàng ngay để nhận ưu đãi hôm nay!",
        },
        "visual_prompts": {
            "image_prompt": "Vertical 9:16 product hero, photoreal mechanical keyboard on a clean desk, RGB underglow, soft warm rim light.",
            "video_prompt": "Vertical 9:16 close-up 6s shot, slow pan across tactile keys, shallow depth of field, no text.",
        },
    }


def test_validate_payload_accepts_spec_compliant_object():
    payload = _good_payload()
    out = validate_analysis_payload(payload)
    assert out is payload


@pytest.mark.parametrize(
    "mutator,message",
    [
        (lambda p: p.__setitem__("usp_list", []), "usp_list"),
        (lambda p: p.__setitem__("usp_list", ["only-one"]), "usp_list"),
        (lambda p: p.__setitem__("pain_points", "x"), "pain_points"),
        (lambda p: p.__setitem__("target_audience", "  "), "target_audience"),
        (lambda p: p["tiktok_script"].__delitem__("hook"), "tiktok_script.hook"),
        (lambda p: p["visual_prompts"].__delitem__("image_prompt"), "visual_prompts.image_prompt"),
    ],
)
def test_validate_payload_rejects_schema_drift(mutator, message):
    from hermes.llm import StructuredOutputError

    payload = _good_payload()
    mutator(payload)
    with pytest.raises(StructuredOutputError, match=message):
        validate_analysis_payload(payload)


def test_content_hash_changes_when_payload_changes():
    a = _good_payload()
    b = _good_payload()
    b["usp_list"] = ["Khác"]
    h1 = _content_hash(_payload_to_analysis(a))
    h2 = _content_hash(_payload_to_analysis(b))
    assert h1 != h2


def test_sqlite_repository_round_trips_and_dedupes(tmp_path):
    db_file = tmp_path / "hermes.db"
    db = _make_db(db_file)
    repo = SQLiteAffiliateAnalysisRepository(db)
    payload = _payload_to_analysis(_good_payload())
    first = repo.save(payload)
    second = repo.save(payload)
    assert first.analysis_id == second.analysis_id
    assert first.tiktok_script.hook == second.tiktok_script.hook

    found = repo.find_for_product(payload.owner_user_id, payload.product_id)
    assert len(found) == 1
    assert found[0].analysis_id == first.analysis_id
    assert found[0].usp_list == payload.usp_list
    assert found[0].pain_points == payload.pain_points


def test_sqlite_repository_migrates_to_schema_v7(tmp_path):
    db_file = tmp_path / "hermes.db"
    db = _make_db(db_file)
    with db.connect() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 7


def _make_db(db_file):
    from hermes.db import Database

    db = Database(db_file)
    db.initialize()
    return db


def _payload_to_analysis(payload, *, fallback_used: bool = False) -> AffiliateAnalysis:
    return AffiliateAnalysis(
        analysis_id="ana_test1234",
        owner_user_id="u1",
        product_id="prod_1",
        run_id="run_1",
        usp_list=tuple(payload["usp_list"]),
        pain_points=tuple(payload["pain_points"]),
        target_audience=payload["target_audience"],
        tiktok_script=TikTokScript(**payload["tiktok_script"]),
        visual_prompts=VisualPrompts(**payload["visual_prompts"]),
        fallback_used=fallback_used,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


# ----- service tests -----


class _StubRepository:
    def __init__(self):
        self.saved: list[AffiliateAnalysis] = []

    def save(self, analysis: AffiliateAnalysis) -> AffiliateAnalysis:
        self.saved.append(analysis)
        return analysis


class _StubGateway:
    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self._response = response or _good_payload()
        self._error = error
        self.calls: list[tuple[Any, Sequence[Any], Sequence[Any]]] = []

    def generate(self, product, references, web_documents=()) -> dict:
        self.calls.append((product, references, web_documents))
        if self._error is not None:
            raise self._error
        return self._response


def test_service_persists_analysis_for_owned_product():
    repo = _StubRepository()
    gw = _StubGateway()
    service = AffiliateAnalysisService(gw, repo)
    analysis = service.analyze_product("u1", "run_1", _make_product())
    assert analysis.analysis_id.startswith("ana_")
    assert analysis.usp_list == tuple(_good_payload()["usp_list"])
    assert repo.saved == [analysis]


def test_service_rejects_product_owned_by_other_user():
    service = AffiliateAnalysisService(_StubGateway(), _StubRepository())
    with pytest.raises(AffiliateAnalysisValidationError, match="owner mismatch"):
        service.analyze_product("u1", "run_1", _make_product(owner_user_id="other"))


def test_service_rejects_payload_failing_spec_validation():
    bad = _good_payload()
    bad["usp_list"] = ["single"]  # OK length but bad["pain_points"] removed below
    del bad["pain_points"]
    service = AffiliateAnalysisService(_StubGateway(bad), _StubRepository())
    with pytest.raises(AffiliateAnalysisValidationError):
        service.analyze_product("u1", "run_1", _make_product())


def test_service_propagates_gateway_failure_without_persisting():
    repo = _StubRepository()
    gw = _StubGateway(error=RuntimeError("9Router offline"))
    service = AffiliateAnalysisService(gw, repo)
    with pytest.raises(RuntimeError, match="9Router offline"):
        service.analyze_product("u1", "run_1", _make_product())
    assert repo.saved == []


def test_gateway_calls_underlying_llm_once_with_payload_context():
    captured = MagicMock()
    captured.structured = MagicMock(return_value=_good_payload())
    gateway = AffiliateAnalysisGateway(captured)  # type: ignore[arg-type]
    gateway.generate(_make_product())
    assert captured.structured.called
    prompt_arg = captured.structured.call_args.kwargs
    assert prompt_arg["task_type"] == "structured_extraction"


def test_sqlite_repository_list_references(tmp_path):
    from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
    
    db_file = tmp_path / "hermes.db"
    db = _make_db(db_file)
    repo = SQLiteAffiliateResearchRepository(db)
    ref = ReferenceMetadata(
        id="ref_1",
        owner_user_id="u1",
        product_id="prod_1",
        platform="shopee",
        source_url="https://example.test/source",
        title="Test reference",
        author_name="Jane Doe",
        author_url="https://example.test/jane",
        thumbnail_url="https://example.test/thumb.jpg",
        caption="Snippet text",
        embed_html="",
        authorization_scope="public_reference",
        rights_status="reference_only",
        media_local_path="",
        collected_at="2026-08-02T12:00:00Z",
        source_type="public_web_document",
        content_hash="hash123",
    )
    repo.upsert_product(_make_product())
    repo.save_reference(ref)
    
    loaded = repo.list_references("u1", "prod_1")
    assert len(loaded) == 1
    assert loaded[0].id == "ref_1"
    assert loaded[0].title == "Test reference"


def test_gateway_includes_web_documents_in_payload():
    from hermes.domain.web_document import WebDocument
    
    captured = MagicMock()
    captured.structured = MagicMock(return_value=_good_payload())
    gateway = AffiliateAnalysisGateway(captured)  # type: ignore[arg-type]
    
    doc = WebDocument(
        id="doc_1",
        owner_user_id="u1",
        run_id="run_1",
        product_id="prod_1",
        requested_url="https://example.test/doc",
        final_url="https://example.test/doc_final",
        title="Doc Title",
        markdown="# Full Article Markdown",
        metadata={},
        acquisition_method="crawl4ai",
        content_hash="doc_hash",
        rights_status="reference_only",
        warnings=(),
        acquired_at="2026-08-02T12:00:00Z",
    )
    
    gateway.generate(_make_product(), web_documents=[doc])
    assert captured.structured.called
    prompt_val = captured.structured.call_args[0][0]
    assert "web_documents" in prompt_val
    assert "Full Article Markdown" in prompt_val
