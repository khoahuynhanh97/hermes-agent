"""Behavior contracts for the Vietnamese ``/hoc_kien_thuc``, ``/hoc``, and ``/hoc_cta`` commands."""

from datetime import datetime
from pathlib import Path
from queue import SimpleQueue
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionEntry, SessionSource, build_session_key
from agent.knowledge_capture_prompt import (
    KnowledgeCaptureInputError,
    ProcedureContractError,
    _resolve_procedure_contract_path,
    build_knowledge_capture_prompt,
    load_procedure_contract,
)


def _make_source() -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        user_id="u1",
        chat_id="c1",
        user_name="tester",
        chat_type="dm",
    )


def _make_event(text: str) -> MessageEvent:
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=_make_source(),
        message_id="m1",
        internal=True,
    )


def _session_entry() -> SessionEntry:
    return SessionEntry(
        session_key=build_session_key(_make_source()),
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.TELEGRAM,
        chat_type="dm",
        total_tokens=0,
    )


def _make_gateway_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")}
    )
    adapter = MagicMock()
    adapter.send = AsyncMock()
    adapter._pending_messages = {}
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._voice_mode = {}
    runner.hooks = SimpleNamespace(
        emit=AsyncMock(),
        emit_collect=AsyncMock(return_value=[]),
        loaded_hooks=False,
    )
    runner.session_store = MagicMock()
    runner.session_store.get_or_create_session.return_value = _session_entry()
    runner.session_store.load_transcript.return_value = []
    runner.session_store.has_any_sessions.return_value = True
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._queued_events = {}
    runner._session_db = MagicMock()
    runner._session_db.get_session_title.return_value = None
    runner._reasoning_config = None
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._show_reasoning = False
    runner._is_user_authorized = lambda _source: True
    runner._set_session_env = lambda _context: None
    runner._should_send_voice_reply = lambda *_args, **_kwargs: False
    runner._send_voice_reply = AsyncMock()
    runner._capture_gateway_honcho_if_configured = lambda *args, **kwargs: None
    runner._emit_gateway_run_progress = AsyncMock()
    runner._update_prompt_pending = {}
    runner._busy_input_mode = "interrupt"
    runner._draining = False
    runner._session_run_generation = {}
    runner._session_sources = {}
    runner._pending_native_image_paths_by_session = {}
    runner._background_tasks = {}
    runner._background_task_counter = 0
    runner._session_model_overrides = {}
    runner._pending_model_notes = {}
    runner._service_tier = None
    runner._fast_mode_by_session = {}
    runner._goal_state_by_session = {}
    runner._goal_runs_in_progress = set()
    runner._goal_queued_by_session = set()
    runner._is_telegram_topic_root_lobby = lambda _source: False
    runner._should_send_telegram_lobby_reminder = lambda _source: False
    runner._check_slash_access = lambda _source, _command: None
    runner._begin_session_run_generation = lambda _key: 1
    runner._release_running_agent_state = lambda key: runner._running_agents.pop(key, None)
    return runner, adapter


def test_prompt_mode_branch_lock_knowledge(tmp_path: Path):
    contract_text = load_procedure_contract()
    source = "https://vt.tiktok.com/example/"
    prompt = build_knowledge_capture_prompt(source, mode="knowledge", working_directory=tmp_path)

    assert source in prompt
    assert str(tmp_path.resolve()) in prompt
    assert "[/hoc_kien_thuc]" in prompt
    assert "SELECTED MODE: knowledge" in prompt
    assert "STEP 5 BRANCH: Mode A only" in prompt
    assert "REQUIRED ANALYSIS ARTIFACT: knowledge_analysis.md" in prompt
    assert "DO NOT execute Mode B or create cta_analysis.md." in prompt
    assert contract_text in prompt


def test_prompt_mode_branch_lock_cta(tmp_path: Path):
    contract_text = load_procedure_contract()
    source = "https://vt.tiktok.com/example_cta/"
    prompt = build_knowledge_capture_prompt(source, mode="cta", working_directory=tmp_path)

    assert source in prompt
    assert str(tmp_path.resolve()) in prompt
    assert "[/hoc_cta]" in prompt
    assert "SELECTED MODE: cta" in prompt
    assert "STEP 5 BRANCH: Mode B only" in prompt
    assert "REQUIRED ANALYSIS ARTIFACT: cta_analysis.md" in prompt
    assert "DO NOT execute Mode A or create knowledge_analysis.md." in prompt
    assert contract_text in prompt


def test_prompt_invalid_mode_normalizes_to_knowledge():
    prompt = build_knowledge_capture_prompt("https://vt.tiktok.com/example/", mode="unrecognized_mode")
    assert "SELECTED MODE: knowledge" in prompt
    assert "STEP 5 BRANCH: Mode A only" in prompt
    assert "REQUIRED ANALYSIS ARTIFACT: knowledge_analysis.md" in prompt


def test_prompt_builder_does_not_hardcode_procedure_steps():
    """Verify that agent/knowledge_capture_prompt.py does NOT hardcode duplicate 8-step text."""
    prompt_py = Path(__file__).resolve().parents[2] / "agent" / "knowledge_capture_prompt.py"
    source = prompt_py.read_text(encoding="utf-8")

    assert "Required procedure:" not in source
    assert "1. Acquire the actual source media" not in source
    assert "load_procedure_contract" in source


# ─────────────────────────────────────────────────────────────────────────────
# Regression Tests: Exception Separation & Path Resolution
# ─────────────────────────────────────────────────────────────────────────────

def test_prompt_empty_source_raises_knowledge_capture_input_error():
    """Empty or whitespace-only source must raise KnowledgeCaptureInputError and not ProcedureContractError."""
    with pytest.raises(KnowledgeCaptureInputError) as exc_info:
        build_knowledge_capture_prompt("   ")

    assert not isinstance(exc_info.value, ProcedureContractError)
    assert "requires a media URL or local media path" in str(exc_info.value)


def test_prompt_builder_fails_loudly_when_custom_contract_missing():
    """Custom contract path that does not exist must raise ProcedureContractError containing the path."""
    nonexistent = Path("nonexistent_contract_path_test.md")
    with pytest.raises(ProcedureContractError) as exc_info:
        build_knowledge_capture_prompt(
            "https://vt.tiktok.com/example/",
            contract_path=nonexistent,
        )

    assert "Procedure contract not found" in str(exc_info.value)
    assert str(nonexistent.resolve()) in str(exc_info.value)


def test_prompt_builder_fails_when_contract_is_empty(tmp_path: Path):
    """Empty contract file must raise ProcedureContractError and include the absolute path."""
    empty_contract = tmp_path / "empty-contract.md"
    empty_contract.write_text("   \n", encoding="utf-8")

    with pytest.raises(ProcedureContractError) as exc_info:
        build_knowledge_capture_prompt(
            "https://vt.tiktok.com/example/",
            contract_path=empty_contract,
        )

    err_msg = str(exc_info.value)
    assert "empty" in err_msg or "rỗng" in err_msg
    assert str(empty_contract.resolve()) in err_msg


def test_prompt_builder_fails_when_contract_read_raises_io_error(tmp_path: Path):
    """Unreadable contract file (e.g. PermissionError/OSError) must raise ProcedureContractError chaining the cause."""
    dummy_contract = tmp_path / "unreadable-contract.md"
    dummy_contract.write_text("# Contract", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
        with pytest.raises(ProcedureContractError) as exc_info:
            build_knowledge_capture_prompt(
                "https://vt.tiktok.com/example/",
                contract_path=dummy_contract,
            )

        assert isinstance(exc_info.value.__cause__, PermissionError)
        assert "Failed to read procedure contract" in str(exc_info.value)


def test_resolve_procedure_contract_path_fails_when_skills_dir_resolution_raises(monkeypatch):
    """When get_skills_dir() raises an exception, _resolve_procedure_contract_path must fail
    with ProcedureContractError and MUST NOT silently fallback to repo/cwd."""
    import agent.knowledge_capture_prompt as prompt_mod

    def faulty_get_skills_dir():
        raise RuntimeError("Profile database corrupt")

    monkeypatch.setattr(prompt_mod, "get_skills_dir", faulty_get_skills_dir)

    with pytest.raises(ProcedureContractError) as exc_info:
        _resolve_procedure_contract_path()

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "Unable to resolve active Hermes skills directory" in str(exc_info.value)


def test_prompt_conditional_audio_contract(tmp_path: Path):
    prompt = build_knowledge_capture_prompt(
        "https://vt.tiktok.com/example/", mode="knowledge", working_directory=tmp_path
    ).lower()

    assert "has_audio: false" in prompt or "silent" in prompt
    assert "audio.wav" in prompt


def test_command_is_registered_for_cli_and_gateway():
    from hermes_cli.commands import resolve_command

    cmd_knowledge = resolve_command("hoc_kien_thuc")
    assert cmd_knowledge is not None
    assert cmd_knowledge.name == "hoc_kien_thuc"
    assert not cmd_knowledge.cli_only
    assert "hoc" in cmd_knowledge.aliases

    cmd_hoc_alias = resolve_command("hoc")
    assert cmd_hoc_alias is not None
    assert cmd_hoc_alias.name == "hoc_kien_thuc"

    cmd_cta = resolve_command("hoc_cta")
    assert cmd_cta is not None
    assert cmd_cta.name == "hoc_cta"
    assert not cmd_cta.cli_only

    # Case-insensitive resolution
    cmd_cta_upper = resolve_command("hoc_CTA")
    assert cmd_cta_upper is not None
    assert cmd_cta_upper.name == "hoc_cta"

    cmd_cta_slash = resolve_command("/hoc_CTA")
    assert cmd_cta_slash is not None
    assert cmd_cta_slash.name == "hoc_cta"


def test_slack_parity_includes_hoc_commands():
    from hermes_cli.commands import _SLACK_VIA_HERMES_ONLY

    assert "hoc_kien_thuc" in _SLACK_VIA_HERMES_ONLY
    assert "hoc_cta" in _SLACK_VIA_HERMES_ONLY
    assert "hoc" in _SLACK_VIA_HERMES_ONLY


def test_cli_handler_queues_knowledge_and_cta_prompts(tmp_path: Path, monkeypatch):
    from hermes_cli.cli_commands_mixin import CLICommandsMixin

    class _CLI(CLICommandsMixin):
        pass

    monkeypatch.chdir(tmp_path)
    cli = _CLI()
    cli._pending_input = SimpleQueue()

    # 1. /hoc_kien_thuc
    cli._handle_knowledge_capture_command("/hoc_kien_thuc https://vt.tiktok.com/example_knowledge/")
    queued = cli._pending_input.get_nowait()
    assert queued.startswith("[/hoc_kien_thuc]")
    assert "https://vt.tiktok.com/example_knowledge/" in queued

    # 2. /hoc alias
    cli._handle_knowledge_capture_command("/hoc https://vt.tiktok.com/example_hoc/")
    queued_alias = cli._pending_input.get_nowait()
    assert queued_alias.startswith("[/hoc_kien_thuc]")
    assert "https://vt.tiktok.com/example_hoc/" in queued_alias

    # 3. /hoc_cta
    cli._handle_knowledge_capture_command("/hoc_cta https://vt.tiktok.com/example_cta/")
    queued_cta = cli._pending_input.get_nowait()
    assert queued_cta.startswith("[/hoc_cta]")
    assert "https://vt.tiktok.com/example_cta/" in queued_cta

    # 4. /hoc_CTA
    cli._handle_knowledge_capture_command("/hoc_CTA https://vt.tiktok.com/example_cta_upper/")
    queued_cta_upper = cli._pending_input.get_nowait()
    assert queued_cta_upper.startswith("[/hoc_cta]")
    assert "https://vt.tiktok.com/example_cta_upper/" in queued_cta_upper


def test_cli_contract_error_handles_cleanly_without_enqueue(capsys, monkeypatch):
    """When procedure contract error occurs, CLI does not raise, does not enqueue,
    and output clearly indicates contract error without claiming missing URL."""
    from hermes_cli.cli_commands_mixin import CLICommandsMixin
    import agent.knowledge_capture_prompt as prompt_mod

    class _CLI(CLICommandsMixin):
        pass

    cli = _CLI()
    cli._pending_input = SimpleQueue()

    def fake_build(*args, **kwargs):
        raise ProcedureContractError("contract corrupted on disk")

    monkeypatch.setattr(prompt_mod, "build_knowledge_capture_prompt", fake_build)

    # Should not raise exception
    cli._handle_knowledge_capture_command("/hoc https://vt.tiktok.com/example/")

    # Should not enqueue
    assert cli._pending_input.empty()

    captured = capsys.readouterr().out
    assert "procedure contract bị thiếu, rỗng hoặc không đọc được" in captured
    assert "requires a media URL" not in captured


def test_cli_empty_source_shows_usage(capsys):
    from hermes_cli.cli_commands_mixin import CLICommandsMixin

    class _CLI(CLICommandsMixin):
        pass

    cli = _CLI()
    cli._pending_input = SimpleQueue()

    cli._handle_knowledge_capture_command("/hoc")
    assert cli._pending_input.empty()
    captured = capsys.readouterr().out
    assert "requires a media URL" in captured or "media path" in captured


@pytest.mark.asyncio
async def test_gateway_runtime_hoc_command_handling():
    runner, adapter = _make_gateway_runner()
    captured = {}

    async def fake_handle_message_with_agent(event, source, key, generation):
        captured["text"] = event.text
        captured["command"] = event.get_command()
        captured["source"] = source
        return {"final_response": "done", "messages": []}

    runner._handle_message_with_agent = fake_handle_message_with_agent

    # Test /hoc with alias
    event = _make_event("/hoc https://vt.tiktok.com/test_hoc/")
    result = await runner._handle_message(event)

    assert result == {"final_response": "done", "messages": []}
    assert captured["text"].startswith("[/hoc_kien_thuc]")
    assert "https://vt.tiktok.com/test_hoc/" in captured["text"]
    assert adapter.send.await_count == 1
    assert "Đang tải media" in adapter.send.await_args[0][1]


@pytest.mark.asyncio
async def test_gateway_runtime_hoc_cta_command_handling():
    runner, adapter = _make_gateway_runner()
    captured = {}

    async def fake_handle_message_with_agent(event, source, key, generation):
        captured["text"] = event.text
        captured["command"] = event.get_command()
        captured["source"] = source
        return {"final_response": "done", "messages": []}

    runner._handle_message_with_agent = fake_handle_message_with_agent

    # Test /hoc_CTA with uppercase
    event = _make_event("/hoc_CTA https://vt.tiktok.com/test_cta/")
    result = await runner._handle_message(event)

    assert result == {"final_response": "done", "messages": []}
    assert captured["text"].startswith("[/hoc_cta]")
    assert "https://vt.tiktok.com/test_cta/" in captured["text"]
    assert adapter.send.await_count == 1
    assert "Hook/CTA" in adapter.send.await_args[0][1]


@pytest.mark.asyncio
async def test_gateway_runtime_missing_url_returns_usage_and_preserves_role_alternation():
    runner, adapter = _make_gateway_runner()
    agent_called = False

    async def fake_handle_message_with_agent(event, source, key, generation):
        nonlocal agent_called
        agent_called = True
        return {"final_response": "should_not_run", "messages": []}

    runner._handle_message_with_agent = fake_handle_message_with_agent

    # Missing URL on /hoc
    event = _make_event("/hoc")
    result = await runner._handle_message(event)

    assert "Cách dùng:" in result
    assert "/hoc_kien_thuc" in result
    assert agent_called is False
    assert adapter.send.await_count == 0


@pytest.mark.asyncio
async def test_gateway_runtime_contract_error_returns_contract_notice_and_preserves_role_alternation(monkeypatch):
    import agent.knowledge_capture_prompt as prompt_mod

    runner, adapter = _make_gateway_runner()
    agent_called = False

    async def fake_handle_message_with_agent(event, source, key, generation):
        nonlocal agent_called
        agent_called = True
        return {"final_response": "should_not_run", "messages": []}

    runner._handle_message_with_agent = fake_handle_message_with_agent

    def fake_build(*args, **kwargs):
        raise ProcedureContractError("procedure contract file is empty")

    monkeypatch.setattr(prompt_mod, "build_knowledge_capture_prompt", fake_build)

    event = _make_event("/hoc https://vt.tiktok.com/example/")
    result = await runner._handle_message(event)

    assert "procedure contract bị thiếu, rỗng hoặc không đọc được" in result
    assert "Cách dùng:" not in result
    assert agent_called is False
    assert adapter.send.await_count == 0
