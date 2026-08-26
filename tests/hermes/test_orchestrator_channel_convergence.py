from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from hermes.channels.cli import main as cli_main
from hermes.channels.gateway.platforms.telegram import bot


def _update(text: str = "hello Hermes") -> SimpleNamespace:
    message = SimpleNamespace(
        text=text,
        reply_chat_action=AsyncMock(),
        reply_text=AsyncMock(),
    )
    return SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=42, username="owner"),
        effective_chat=SimpleNamespace(id=100, type="private", title=None),
    )


def test_telegram_turn_request_binds_authenticated_identity():
    history = ({"role": "user", "content": "previous request"},)
    request = bot.build_telegram_turn_request(
        _update(),
        "research three products",
        conversation_history=history,
    )

    assert request.message == "research three products"
    assert request.platform == "telegram"
    assert request.principal.actor_id == "42"
    assert request.principal.owner_user_id == "42"
    assert request.principal.session_id == "telegram:100"
    assert request.conversation_history == history


@pytest.mark.asyncio
async def test_default_free_text_uses_hermes_orchestrator_only():
    update = _update("create a TikTok product video")
    context = SimpleNamespace()

    with (
        patch.object(bot, "run_orchestrator_turn", new=AsyncMock(return_value="planned")) as run_turn,
        patch.object(bot, "send_response", new=AsyncMock()) as send,
        patch.object(bot, "ask_gemini", side_effect=AssertionError("legacy LLM router must not run")),
        patch.object(bot, "resolve_route", side_effect=AssertionError("channel semantic router must not run")),
    ):
        await bot.default_chat_handler(update, context)

    run_turn.assert_awaited_once_with(update, "create a TikTok product video")
    send.assert_awaited_once_with(update, "planned")


@pytest.mark.asyncio
async def test_tiktok_shop_product_url_reaches_orchestrator_unchanged():
    url = (
        "https://shop.tiktok.com/vn/pdp/chuot-khong-day-dareu-lm115g-multi-color-"
        "sensor-paw3512-dpi-800-1200-1600/1733129100613093024"
    )
    update = _update(url)

    with (
        patch.object(bot, "run_orchestrator_turn", new=AsyncMock(return_value="product research ready")) as run_turn,
        patch.object(bot, "send_response", new=AsyncMock()) as send,
        patch.object(bot, "ask_video_intent", new=AsyncMock()) as video_intent,
        patch.object(bot, "ask_gemini", side_effect=AssertionError("legacy LLM router must not run")),
    ):
        await bot.default_chat_handler(update, SimpleNamespace())

    run_turn.assert_awaited_once_with(update, url)
    video_intent.assert_not_awaited()
    send.assert_awaited_once_with(update, "product research ready")


@pytest.mark.asyncio
async def test_assistant_command_uses_same_orchestrator_turn():
    update = _update("/assistant analyze the knowledge base")
    context = SimpleNamespace()

    with (
        patch.object(bot, "run_orchestrator_turn", new=AsyncMock(return_value="analysis")) as run_turn,
        patch.object(bot, "send_response", new=AsyncMock()) as send,
    ):
        await bot.assistant_command(update, context)

    run_turn.assert_awaited_once_with(update, "analyze the knowledge base")
    send.assert_awaited_once_with(update, "analysis")


def test_cli_turn_request_uses_same_channel_neutral_contract():
    request = cli_main.build_cli_turn_request("research products", session_id="cli:test")

    assert request.message == "research products"
    assert request.platform == "cli"
    assert request.principal.platform == "cli"
    assert request.principal.session_id == "cli:test"


def test_cli_video_alias_routes_to_orchestrator(monkeypatch):
    run_turn = Mock()
    monkeypatch.setattr(cli_main, "run_agent_turn", run_turn)
    monkeypatch.setattr(
        cli_main,
        "run_product_to_video_command",
        lambda *_: (_ for _ in ()).throw(AssertionError("registry shortcut must not run")),
    )
    monkeypatch.setattr(cli_main.sys, "argv", ["hermes", "video", "review", "keyboard"])

    cli_main.main()

    run_turn.assert_called_once()
    prompt = run_turn.call_args.args[0]
    assert "review keyboard" in prompt


def test_cli_interactive_video_command_routes_to_orchestrator(monkeypatch):
    run_turn = Mock()
    monkeypatch.setattr(cli_main, "run_agent_turn", run_turn)

    cli_main.run_product_to_video_command("review keyboard")

    run_turn.assert_called_once()
    assert "review keyboard" in run_turn.call_args.args[0]


@pytest.mark.asyncio
async def test_video_factory_approval_command_uses_authenticated_owner(monkeypatch):
    update = _update("/vf_approve project-1 creative_brief")
    service = Mock()
    monkeypatch.setattr(bot, "_video_factory_service_factory", lambda: service)

    await bot.video_factory_approve_command(
        update,
        SimpleNamespace(args=["project-1", "creative_brief"]),
    )

    service.approve_creative_brief.assert_called_once_with("42", "project-1")
    reply = update.message.reply_text.await_args.args[0]
    assert "project-1" in reply
    assert "tiếp tục" in reply
