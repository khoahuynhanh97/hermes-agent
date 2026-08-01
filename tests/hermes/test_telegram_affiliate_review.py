from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hermes.domain.affiliate_research import ContentPackage, PackageStatus


def package(package_id: str = "pkg-1", *, status: PackageStatus = PackageStatus.PENDING_REVIEW):
    return ContentPackage(
        id=package_id,
        owner_user_id="42",
        product_id="product-1",
        run_id="run-1",
        revision=1,
        status=status,
        audience="Office <workers>",
        angle="Desk setup",
        angle_reason="Strong <score> reason",
        hook="A <hook>",
        script="A short <script>",
        duration_seconds=45,
        storyboard=({"visual": "Mouse <close-up>"},),
        ai_prompts=("prompt",),
        voiceover_plan="neutral",
        text_overlays=("overlay",),
        claims=(),
        warnings=("Avoid <claims>",),
        asset_rights={},
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )


class FakeRepository:
    def __init__(self):
        self.packages = {"pkg-1": package()}
        self.events: list[tuple[str, str, str]] = []

    def get_package(self, package_id, owner_user_id):
        item = self.packages.get(package_id)
        return item if item and item.owner_user_id == owner_user_id else None

    def transition_package(self, package_id, owner_user_id, action, reason):
        item = self.get_package(package_id, owner_user_id)
        if item is None:
            raise LookupError(package_id)
        statuses = {
            "approve": PackageStatus.APPROVED,
            "revise": PackageStatus.REVISION_REQUESTED,
            "reject": PackageStatus.REJECTED,
        }
        target = statuses[action]
        if item.status is target:
            return item
        if item.status is not PackageStatus.PENDING_REVIEW:
            raise ValueError("invalid transition")
        item = replace(item, status=target)
        self.packages[package_id] = item
        self.events.append((package_id, action, reason))
        return item

    def list_packages(self, owner_user_id):
        return [item for item in self.packages.values() if item.owner_user_id == owner_user_id]

    def list_products(self, _owner_user_id):
        return [
            SimpleNamespace(
                id="product-1",
                name="Mouse Pro",
                image_urls=("https://example.test/mouse.jpg",),
                score=87.5,
                score_reason="sales=40; visual=25",
            )
        ]

    def count_approval_events(self, package_id, action):
        return sum(event[:2] == (package_id, action) for event in self.events)


class FakeMessage:
    def __init__(self):
        self.replies: list[str] = []

    async def reply_text(self, text, **_kwargs):
        self.replies.append(text)


class FakeQuery:
    def __init__(self, data="affiliate_approve:pkg-1"):
        self.data = data
        self.from_user = SimpleNamespace(id=42)
        self.message = SimpleNamespace(chat_id=42)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **_kwargs):
        self.edits.append(text)


class FakeContentService:
    def __init__(self, repository=None):
        self.calls = []
        self.repository = repository

    def revise_package(self, package_id, owner_user_id, feedback):
        self.calls.append((package_id, owner_user_id, feedback))
        if self.repository is not None:
            self.repository.transition_package(
                package_id, owner_user_id, "revise", feedback
            )
        return package(package_id + ":r2")


class FakeBot:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.messages = []

    def send_message(self, **kwargs):
        if self.error:
            raise self.error
        self.messages.append(kwargs)

    def send_photo(self, **kwargs):
        if self.error:
            raise self.error
        self.messages.append(kwargs)


class NoopPath:
    def __truediv__(self, _part):
        return self

    def mkdir(self, **_kwargs):
        return None


class FakeLearningStore:
    root = NoopPath()


def test_approve_is_owner_scoped_and_idempotent():
    from hermes.application.affiliate_review_service import AffiliateReviewService, PackageNotFound

    repository = FakeRepository()
    service = AffiliateReviewService(repository)
    first = service.apply("pkg-1", "42", "approve")
    second = service.apply("pkg-1", "42", "approve")

    assert first.status.value == "approved"
    assert second.status.value == "approved"
    assert repository.count_approval_events("pkg-1", "approve") == 1
    with pytest.raises(PackageNotFound):
        service.apply("pkg-1", "99", "reject")


def test_renderer_escapes_html_and_callback_data_is_compact():
    from hermes.adapters.telegram.affiliate_review import build_review_keyboard, render_package_html

    rendered = render_package_html(package(), product_name="Mouse <Pro>", score_reason="Good <score>")
    keyboard = build_review_keyboard("pkg-1", button_factory=lambda text, callback_data: (text, callback_data))

    assert "Mouse &lt;Pro&gt;" in rendered
    assert "<script>" not in rendered
    assert all(len(callback_data.encode("utf-8")) < 64 for row in keyboard for _, callback_data in row)


def test_callback_payload_accepts_exactly_64_bytes():
    from hermes.adapters.telegram.affiliate_review import parse_review_callback

    prefix = "affiliate_approve:"
    payload = prefix + ("x" * (64 - len(prefix)))

    assert len(payload.encode("utf-8")) == 64
    assert parse_review_callback(payload) == ("approve", payload.split(":", 1)[1])


def test_review_delivery_returns_retryable_failure_on_transport_error():
    from hermes.adapters.telegram.affiliate_review import TelegramReviewDelivery

    result = TelegramReviewDelivery(FakeRepository(), FakeBot(RuntimeError("offline")), chat_id="42").send_pending("42", ["pkg-1"])

    assert result.ok is False
    assert result.retryable is True
    assert "offline" in result.detail


def test_review_delivery_uses_product_image_score_and_bounded_caption():
    from hermes.adapters.telegram.affiliate_review import TelegramReviewDelivery

    repository = FakeRepository()
    repository.packages["pkg-1"] = replace(package(), script="long script " * 2_000)
    bot = FakeBot()

    result = TelegramReviewDelivery(repository, bot, chat_id="42").send_pending(
        "42", ["pkg-1"]
    )

    assert result.ok is True
    assert bot.messages[0]["photo"] == "https://example.test/mouse.jpg"
    assert len(bot.messages[0]["caption"]) <= 1024
    assert "87.5" in bot.messages[0]["caption"]
    assert "sales=40" in bot.messages[0]["caption"]


def test_review_delivery_falls_back_when_async_photo_delivery_fails():
    from hermes.adapters.telegram.affiliate_review import TelegramReviewDelivery

    class AsyncPhotoBot(FakeBot):
        async def send_photo(self, **_kwargs):
            raise ValueError("photo rejected")

    bot = AsyncPhotoBot()

    result = TelegramReviewDelivery(
        FakeRepository(), bot, chat_id="42"
    ).send_pending("42", ["pkg-1"])

    assert result.ok is True
    assert bot.messages[0]["text"]


def test_review_delivery_factory_is_disabled_without_telegram_configuration():
    from hermes.adapters.telegram.affiliate_review import review_delivery_from_environment
    from hermes.application.affiliate_run_service import DisabledReviewDelivery

    delivery = review_delivery_from_environment(
        FakeRepository(), environ={}, bot_factory=lambda _token: pytest.fail("bot must stay lazy")
    )

    assert isinstance(delivery, DisabledReviewDelivery)


def test_review_delivery_factory_uses_injected_bot_when_configured():
    from hermes.adapters.telegram.affiliate_review import TelegramReviewDelivery, review_delivery_from_environment

    bot = FakeBot()
    delivery = review_delivery_from_environment(
        FakeRepository(),
        environ={"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_REVIEW_CHAT_ID": "42"},
        bot_factory=lambda token: bot if token == "test-token" else pytest.fail("wrong token"),
    )

    assert isinstance(delivery, TelegramReviewDelivery)
    assert delivery._bot is bot
    assert delivery._chat_id == "42"


def test_job_handler_injects_environment_review_delivery(monkeypatch):
    import core.affiliate_research_jobs as jobs
    import hermes.adapters.model.affiliate_content_gateway as content_gateway_module
    import hermes.adapters.sqlite.affiliate_research_repository as repository_module
    import hermes.application.affiliate_catalog_service as catalog_module
    import hermes.application.affiliate_content_service as content_module
    import hermes.db as database_module
    import hermes.llm as llm_module

    repository = FakeRepository()
    delivery = object()
    captured = {}

    class CapturingRunService:
        def __init__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(jobs, "AffiliateRunService", CapturingRunService)
    monkeypatch.setattr(repository_module, "SQLiteAffiliateResearchRepository", lambda _database: repository)
    monkeypatch.setattr(database_module, "Database", lambda: object())
    monkeypatch.setattr(catalog_module, "AffiliateCatalogService", lambda _repository: object())
    monkeypatch.setattr(content_module, "AffiliateContentService", lambda *_args: object())
    monkeypatch.setattr(content_gateway_module, "AffiliateContentGateway", lambda _gateway: object())
    monkeypatch.setattr(llm_module, "HermesLLMGateway", lambda: object())

    handler = jobs.build_affiliate_research_job_handler(
        ".",
        review_delivery_factory=lambda supplied_repository: delivery
        if supplied_repository is repository
        else pytest.fail("wrong repository"),
    )

    assert isinstance(handler, jobs.AffiliateResearchJobHandler)
    assert captured["kwargs"]["review_delivery"] is delivery
    assert (
        captured["kwargs"]["reference_collector"].__class__.__name__
        == "TikTokReferenceCollector"
    )


def test_callback_rejects_unauthorized_user(monkeypatch):
    import core.learning_review
    import importlib

    monkeypatch.setattr(core.learning_review, "LearningReviewStore", FakeLearningStore)
    telegram_bot = importlib.import_module("telegram_bot")
    telegram_bot = importlib.reload(telegram_bot)
    repository = FakeRepository()
    query = FakeQuery()
    update = SimpleNamespace(callback_query=query)
    with patch("telegram_bot.is_authorized_user_id", return_value=False), patch.object(
        telegram_bot, "_affiliate_review_repository_factory", return_value=repository
    ):
        asyncio.run(telegram_bot.handle_callback(update, SimpleNamespace(bot=FakeBot())))

    assert repository.get_package("pkg-1", "42").status.value == "pending_review"
    assert query.answers[0][0] == ("Unauthorized",)


def test_revision_callback_only_instructs_and_does_not_transition(monkeypatch):
    import core.learning_review
    import importlib

    monkeypatch.setattr(core.learning_review, "LearningReviewStore", FakeLearningStore)
    telegram_bot = importlib.import_module("telegram_bot")
    telegram_bot = importlib.reload(telegram_bot)
    repository = FakeRepository()
    query = FakeQuery("affiliate_revise:pkg-1")
    update = SimpleNamespace(callback_query=query)
    with patch("telegram_bot.is_authorized_user_id", return_value=True), patch.object(
        telegram_bot, "_affiliate_review_repository_factory", return_value=repository
    ):
        asyncio.run(telegram_bot.handle_callback(update, SimpleNamespace(bot=FakeBot())))

    assert repository.get_package("pkg-1", "42").status is PackageStatus.PENDING_REVIEW
    assert repository.events == []
    assert "/affiliate_revise" in query.edits[-1]


def test_revision_command_requires_feedback_and_invokes_content_service(monkeypatch):
    import core.learning_review
    import importlib

    monkeypatch.setattr(core.learning_review, "LearningReviewStore", FakeLearningStore)
    telegram_bot = importlib.import_module("telegram_bot")
    telegram_bot = importlib.reload(telegram_bot)
    repository = FakeRepository()
    message = FakeMessage()
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=42))
    content = FakeContentService(repository)
    with patch.object(telegram_bot, "_affiliate_review_repository_factory", return_value=repository), patch.object(
        telegram_bot, "_affiliate_content_service_factory", return_value=content
    ):
        asyncio.run(telegram_bot.affiliate_revise_command(update, SimpleNamespace(args=["pkg-1"])))
        assert "feedback" in message.replies[-1].lower()

        asyncio.run(
            telegram_bot.affiliate_revise_command(
                update, SimpleNamespace(args=["pkg-1", "Make", "the", "hook", "shorter"])
            )
        )

    assert repository.get_package("pkg-1", "42").status is PackageStatus.REVISION_REQUESTED
    assert content.calls == [("pkg-1", "42", "Make the hook shorter")]


def test_revision_command_failure_leaves_parent_unchanged(monkeypatch):
    import core.learning_review
    import importlib

    monkeypatch.setattr(core.learning_review, "LearningReviewStore", FakeLearningStore)
    telegram_bot = importlib.import_module("telegram_bot")
    telegram_bot = importlib.reload(telegram_bot)
    repository = FakeRepository()
    message = FakeMessage()
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=42))

    class FailingContentService:
        def revise_package(self, *_args):
            raise ValueError("validation failed")

    with patch.object(
        telegram_bot, "_affiliate_review_repository_factory", return_value=repository
    ), patch.object(
        telegram_bot,
        "_affiliate_content_service_factory",
        return_value=FailingContentService(),
    ):
        asyncio.run(
            telegram_bot.affiliate_revise_command(
                update, SimpleNamespace(args=["pkg-1", "shorter"])
            )
        )

    assert repository.get_package("pkg-1", "42").status is PackageStatus.PENDING_REVIEW
    assert repository.events == []
