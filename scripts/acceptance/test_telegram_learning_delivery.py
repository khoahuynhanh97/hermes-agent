"""Focused checks for Telegram learning result delivery and approval callbacks."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from hermes.application.core import knowledge_store
from hermes.channels.gateway.platforms.telegram import bot as telegram_bot


class FakeBot:
    def __init__(self):
        self.messages = []
        self.documents = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)

    async def send_document(self, **kwargs):
        document = kwargs.get("document")
        self.documents.append({
            "chat_id": kwargs.get("chat_id"),
            "filename": kwargs.get("filename"),
            "content": document.read().decode("utf-8") if document else "",
        })


class FakeManager:
    def __init__(self, result):
        self.result = result
        self.archived = []

    def get_outbox_results(self):
        return [self.result] if not self.archived else []

    def archive_done_job(self, job_id):
        self.archived.append(job_id)
        telegram_bot._stop_event.set()


class FakeRecoveryManager:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def get_completed_job(self, job_id, owner_user_id=None):
        self.calls.append((job_id, owner_user_id))
        return self.result


class FakeQuery:
    def __init__(self, data: str, user_id: int):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.edits = []
        self.message = SimpleNamespace(chat_id=999)

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text=None, **kwargs):
        self.edits.append({"text": text, **kwargs})


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.reply_kwargs = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        self.reply_kwargs.append(kwargs)


class HtmlFailingMessage(FakeMessage):
    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        self.reply_kwargs.append(kwargs)
        if kwargs.get("parse_mode") == "HTML":
            raise RuntimeError("Telegram rejected malformed HTML")


async def run_delivery_check(tmp: Path, entry_id: str) -> None:
    output_dir = tmp / "output"
    output_dir.mkdir()
    (output_dir / "summary_analysis.md").write_text("# Summary\n\nUseful result", encoding="utf-8")
    (output_dir / "analysis.md").write_text("# Extra\n\nShould not be sent", encoding="utf-8")

    result = {
        "job_id": "job_delivery_fixture",
        "job_type": "knowledge_learning",
        "summary": "**Summary:**\nUseful result",
        "files_created": [
            "summary_analysis.md",
            "analysis.md",
            f"__KNOWLEDGE_ENTRY__:{entry_id}",
        ],
        "telegram": {"chat_id": 999, "user_id": 123},
        "target": {"project_slug": "delivery-fixture", "output_dir": str(output_dir)},
    }

    fake_manager = FakeManager(result)
    fake_bot = FakeBot()
    app = SimpleNamespace(bot=fake_bot)
    telegram_bot._stop_event.clear()

    with patch.object(telegram_bot, "AgentJobManager", return_value=fake_manager):
        await telegram_bot.poll_outbox_loop(app)

    assert fake_manager.archived == ["job_delivery_fixture"]
    assert len(fake_bot.messages) == 1
    assert "Lesson" in fake_bot.messages[0]["text"]
    assert fake_bot.messages[0]["parse_mode"] == "HTML"
    assert fake_bot.messages[0]["reply_markup"] is None
    assert f"/approve {entry_id}" in fake_bot.messages[0]["text"]
    assert f"/reject {entry_id}" in fake_bot.messages[0]["text"]
    assert [doc["filename"] for doc in fake_bot.documents] == ["summary_analysis.md"]
    assert "Useful result" in fake_bot.documents[0]["content"]


async def run_recovery_delivery_check(tmp: Path) -> None:
    output_dir = tmp / "recovery-delivery"
    output_dir.mkdir()
    (output_dir / "summary_analysis.md").write_text("# Raw Analysis", encoding="utf-8")
    job_id = "job_20260713_010203_abcdef"
    result = {
        "job_id": job_id,
        "job_type": "knowledge_learning",
        "summary": "Raw analysis is available.",
        "files_created": ["summary_analysis.md", f"__KNOWLEDGE_RECOVERY__:{job_id}"],
        "telegram": {"chat_id": 999, "user_id": 123},
        "target": {"project_slug": "recovery", "output_dir": str(output_dir)},
    }
    fake_manager = FakeManager(result)
    fake_bot = FakeBot()
    telegram_bot._stop_event.clear()
    with patch.object(telegram_bot, "AgentJobManager", return_value=fake_manager):
        await telegram_bot.poll_outbox_loop(SimpleNamespace(bot=fake_bot))

    assert fake_manager.archived == [job_id]
    assert f"/recover {job_id}" in fake_bot.messages[0]["text"]
    assert fake_bot.messages[0]["parse_mode"] == "HTML"
    assert [doc["filename"] for doc in fake_bot.documents] == ["summary_analysis.md"]


async def run_callback_check(entry_id: str) -> None:
    previous = os.environ.get("TELEGRAM_ALLOWED_USER_IDS")
    os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "123"
    try:
        query = FakeQuery(f"knowledge_approve:{entry_id}", 123)
        update = SimpleNamespace(callback_query=query)
        with patch.object(knowledge_store.UnifiedKnowledgeStore, "_rebuild_style_profile"):
            await telegram_bot.handle_callback(update, SimpleNamespace())
        assert query.edits
        assert "approved" in query.edits[-1]["text"].lower() or "approve" in query.edits[-1]["text"].lower()
        updated = knowledge_store.UnifiedKnowledgeStore().get_entry(entry_id)
        assert updated["status"] == "approved"
        assert updated["approval_history"][-1]["status"] == "approved"
    finally:
        if previous is None:
            os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)
        else:
            os.environ["TELEGRAM_ALLOWED_USER_IDS"] = previous


async def run_unauthorized_callback_check(entry_id: str) -> None:
    previous = os.environ.get("TELEGRAM_ALLOWED_USER_IDS")
    os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "999"
    try:
        query = FakeQuery(f"knowledge_approve:{entry_id}", 123)
        update = SimpleNamespace(callback_query=query)
        await telegram_bot.handle_callback(update, SimpleNamespace())
        assert query.answers
        assert query.answers[-1][0][0] == "Unauthorized"
        assert not query.edits
    finally:
        if previous is None:
            os.environ.pop("TELEGRAM_ALLOWED_USER_IDS", None)
        else:
            os.environ["TELEGRAM_ALLOWED_USER_IDS"] = previous


async def run_command_check(entry_id: str, action: str) -> None:
    message = FakeMessage()
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(args=[entry_id])
    handler = telegram_bot.approve_command if action == "approve" else telegram_bot.reject_command
    await handler(update, context)
    assert message.replies
    assert action in message.replies[-1].lower()


async def run_numbered_pending_actions_check() -> None:
    store = knowledge_store.UnifiedKnowledgeStore()
    first = store.add_entry(title="First pending", owner_user_id=123)
    second = store.add_entry(title="Second pending", owner_user_id=123)
    other_user = store.add_entry(title="Other user pending", owner_user_id=456)

    approve_message = FakeMessage()
    update = SimpleNamespace(message=approve_message, effective_user=SimpleNamespace(id=123))
    await telegram_bot.approve_command(update, SimpleNamespace(args=["1"]))
    assert store.get_entry(second["id"])["status"] == "approved"
    assert store.get_entry(first["id"])["status"] == "pending"
    assert store.get_entry(other_user["id"])["status"] == "pending"

    reject_message = FakeMessage()
    update = SimpleNamespace(message=reject_message, effective_user=SimpleNamespace(id=123))
    await telegram_bot.reject_command(update, SimpleNamespace(args=["1"]))
    assert store.get_entry(first["id"])["status"] == "rejected"

    third = store.add_entry(title="Third pending", owner_user_id=123)
    fourth = store.add_entry(title="Fourth pending", owner_user_id=123)
    bulk_message = FakeMessage()
    update = SimpleNamespace(message=bulk_message, effective_user=SimpleNamespace(id=123))
    await telegram_bot.approve_all_command(update, SimpleNamespace(args=[]))
    assert store.get_entry(third["id"])["status"] == "approved"
    assert store.get_entry(fourth["id"])["status"] == "approved"
    assert store.get_entry(other_user["id"])["status"] == "pending"
    assert "2" in bulk_message.replies[-1]


async def run_recover_command_check(tmp: Path) -> None:
    output_dir = tmp / "recovery-output"
    output_dir.mkdir()
    (output_dir / "proposal_meta.json").write_text(
        """{
  "analysis_source": "video_only",
  "confidence": "high",
  "raw_analysis": "## Summary\\n\\nRaw source summary.\\n\\n- Preserve source evidence.\\n- Review before approval."
}""",
        encoding="utf-8",
    )
    job = {
        "job_id": "job_20260713_010203_abcdef",
        "files_created": ["__KNOWLEDGE_RECOVERY__:job_20260713_010203_abcdef"],
        "source": {"value": "https://www.youtube.com/watch?v=recovery"},
        "target": {"project_slug": "recovery-video", "output_dir": str(output_dir)},
    }
    manager = FakeRecoveryManager({"ok": True, "job": job})
    message = FakeMessage()
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(args=[job["job_id"]])
    with patch.object(telegram_bot, "AgentJobManager", return_value=manager):
        await telegram_bot.recover_command(update, context)

    assert manager.calls == [(job["job_id"], 123)]
    assert message.replies and "needs_review" in message.replies[-1].lower()
    entries = knowledge_store.UnifiedKnowledgeStore().list_entries(status="pending")
    recovered = [entry for entry in entries if entry["source_url"].endswith("recovery")]
    assert len(recovered) == 1
    detail_path = knowledge_store.KB_DIR / recovered[0]["detail_file"]
    detail = __import__("json").loads(detail_path.read_text(encoding="utf-8"))["detail"]
    assert detail["needs_review"] is True
    assert detail["recovery_mode"] == "raw_analysis"


async def run_recover_not_owner_check() -> None:
    message = FakeMessage()
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(args=["job_20260713_010203_abcdef"])
    manager = FakeRecoveryManager({"ok": False, "reason": "not_owner"})
    with patch.object(telegram_bot, "AgentJobManager", return_value=manager):
        await telegram_bot.recover_command(update, context)
    assert message.replies and "không sở hữu" in message.replies[-1].lower()


async def run_reanalysis_command_check() -> None:
    store = knowledge_store.UnifiedKnowledgeStore()
    malformed = store.add_entry(
        title="Malformed lesson",
        source_url="https://www.tiktok.com/@user/video/reanalyse",
        owner_user_id=123,
        detail_data={"raw_analysis": "Saved source analysis."},
    )
    store.mark_needs_reanalysis(
        malformed["id"],
        "invalid JSON",
        {"raw_analysis": "Saved source analysis.", "original_job_id": "job_original"},
    )
    message = FakeMessage()
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=123))
    with patch.object(telegram_bot, "build_video_job", return_value={"job_id": "job_reanalysis"}) as builder:
        await telegram_bot.re_analysis_command(update, SimpleNamespace(args=[malformed["id"]]))
    assert builder.call_count == 1
    assert builder.call_args.kwargs["bypass_dedup"] is True
    assert builder.call_args.kwargs["reanalysis_target_id"] == malformed["id"]
    assert "job_reanalysis" in message.replies[-1]

    valid = store.add_entry(title="Valid lesson", owner_user_id=123)
    valid_message = FakeMessage()
    valid_update = SimpleNamespace(message=valid_message, effective_user=SimpleNamespace(id=123))
    with patch.object(telegram_bot, "build_video_job") as builder:
        await telegram_bot.re_analysis_command(valid_update, SimpleNamespace(args=[valid["id"]]))
    assert builder.call_count == 0
    assert "không cần" in valid_message.replies[-1].lower()

    other_message = FakeMessage()
    other_update = SimpleNamespace(message=other_message, effective_user=SimpleNamespace(id=456))
    with patch.object(telegram_bot, "build_video_job") as builder:
        await telegram_bot.re_analysis_command(other_update, SimpleNamespace(args=[malformed["id"]]))
    assert builder.call_count == 0
    assert "không sở hữu" in other_message.replies[-1].lower()


def run_knowledge_display_check() -> None:
    entries = [
        {
            "status": "approved",
            "category": "cong-nghe",
            "title": "CodeGraph: tối ưu token",
            "key_lessons": ["Tạo context có cấu trúc cho codebase."],
        },
        {
            "status": "approved",
            "category": "workflow",
            "title": "Superpowers Workflow",
            "key_lessons": ["Hỏi, chốt spec, duyệt rồi build."],
        },
    ]
    text = telegram_bot.format_knowledge_listing(entries, "approved", pending_count=2)
    assert text.startswith("Knowledge đã duyệt · 2 bài")
    assert "Công nghệ" in text
    assert "Workflow" in text
    assert "CodeGraph: tối ưu token" in text
    assert "Tạo context có cấu trúc cho codebase." in text
    assert "Cần xử lý: 2 bài chờ duyệt" in text
    assert "/knowledge pending" in text

    pending_text = telegram_bot.format_knowledge_listing(
        [
            {
                "status": "pending",
                "category": "technology",
                "title": "Workflow Phát Triển Phần Mềm",
                "key_lessons": ["Tóm tắt bài học."],
            },
            {
                "status": "pending",
                "category": "workflow",
                "title": "CodeGraph",
                "key_lessons": ["Tóm tắt thứ hai."],
            },
        ],
        "pending",
    )
    assert "1. 🟦 **Workflow Phát Triển Phần Mềm**" in pending_text
    assert "2. 🟩 **CodeGraph**" in pending_text
    assert "/approve 1" in pending_text
    assert "/reject 2" in pending_text
    assert "/approve_all" in pending_text

    unsafe_text = telegram_bot.format_knowledge_listing(
        [{
            "status": "pending",
            "category": "[unsafe-category",
            "title": "Unsafe [title",
            "key_lessons": ["Unsafe [takeaway"],
        }],
        "pending",
    )
    assert "Unsafe \\[takeaway" in unsafe_text
    assert "\\[unsafe-category" in unsafe_text.lower()


def run_html_renderer_check() -> None:
    rendered = telegram_bot.render_telegram_html(
        "**Bold** and *italic* with `code`.\n> quoted\nhttps://example.com/a?x=1\n<script>alert(1)</script>"
    )
    assert "<b>Bold</b>" in rendered
    assert "<i>italic</i>" in rendered
    assert "<code>code</code>" in rendered
    assert "<blockquote>quoted</blockquote>" in rendered
    assert '<a href="https://example.com/a?x=1">https://example.com/a?x=1</a>' in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>" not in rendered


def run_html_knowledge_listing_check() -> None:
    rendered = telegram_bot.format_knowledge_listing_html(
        [
            {
                "id": "kb_valid",
                "status": "pending",
                "category": "technology",
                "title": "<unsafe title>",
                "key_lessons": ["Use <review> before approval."],
            },
            {
                "id": "kb_bad",
                "status": "pending",
                "category": "technology",
                "title": "Malformed JSON",
                "key_lessons": ["Needs explicit re-analysis."],
                "needs_reanalysis": True,
            },
        ],
        "pending",
    )
    assert rendered.startswith("\U0001f4da <b>Knowledge ch")
    assert "\u2501" * 20 in rendered
    assert "\U0001f7e2 <b>1. &lt;unsafe title&gt;</b>" in rendered
    assert "Use &lt;review&gt; before approval." in rendered
    assert "<code>/approve 1</code>" in rendered
    assert "<code>/reject 1</code>" in rendered
    assert "<code>/approve_all</code>" in rendered
    assert "<code>/re_analysis kb_bad</code>" in rendered
    valid_block = rendered.split("Malformed JSON", 1)[0]
    assert "/re_analysis kb_valid" not in valid_block


async def run_html_delivery_check() -> None:
    message = FakeMessage()
    await telegram_bot.reply_html(message, "**Readable** response")
    assert message.replies == ["<b>Readable</b> response"]
    assert message.reply_kwargs == [{"parse_mode": "HTML"}]

    failing_message = HtmlFailingMessage()
    await telegram_bot.reply_html(failing_message, "<unsafe>")
    assert failing_message.reply_kwargs[0]["parse_mode"] == "HTML"
    assert failing_message.reply_kwargs[1] == {}
    assert failing_message.replies[1] == "<unsafe>"


def run_learning_intake_location_check(root: Path) -> None:
    output_dir = root / "projects" / "job_photo"
    job = {
        "job_id": "job_photo",
        "target": {"output_dir": str(output_dir)},
        "paths": {},
    }
    path = Path(telegram_bot.create_learning_intake_note(
        job=job,
        source_value="https://vt.tiktok.com/example",
        source_kind="tiktok_url",
        extra_note="",
        local_video_path=None,
        telegram_info={},
    ))
    assert path == output_dir / "learning_intake.md"
    assert path.exists()


def run_tiktok_ingestion_deferral_check() -> None:
    assert telegram_bot.should_defer_source_fetch("https://vt.tiktok.com/ZSXM7H89N/", "tiktok_url")
    assert telegram_bot.should_defer_source_fetch("https://www.tiktok.com/@author/video/123", "tiktok_url")
    assert not telegram_bot.should_defer_source_fetch("https://www.youtube.com/watch?v=123", "youtube_url")


def run_tests() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old_values = knowledge_store.KB_DIR, knowledge_store.UNIFIED_INDEX_FILE, knowledge_store.ENTRIES_DIR
        knowledge_store.KB_DIR = root / "knowledge_base"
        knowledge_store.UNIFIED_INDEX_FILE = knowledge_store.KB_DIR / "unified_index.json"
        knowledge_store.ENTRIES_DIR = knowledge_store.KB_DIR / "entries"
        try:
            entry = knowledge_store.UnifiedKnowledgeStore().add_entry(
                title="Delivery lesson",
                source_url="https://www.youtube.com/watch?v=delivery",
                key_lessons=["Send only one markdown artifact"],
                owner_user_id=123,
            )
            asyncio.run(run_delivery_check(root, entry["id"]))
            asyncio.run(run_recovery_delivery_check(root))
            asyncio.run(run_callback_check(entry["id"]))
            asyncio.run(run_unauthorized_callback_check(entry["id"]))
            command_approve = knowledge_store.UnifiedKnowledgeStore().add_entry(
                title="Command approve lesson", owner_user_id=123
            )
            asyncio.run(run_command_check(command_approve["id"], "approve"))
            command_reject = knowledge_store.UnifiedKnowledgeStore().add_entry(
                title="Command reject lesson", owner_user_id=123
            )
            asyncio.run(run_command_check(command_reject["id"], "reject"))
            asyncio.run(run_numbered_pending_actions_check())
            asyncio.run(run_recover_command_check(root))
            asyncio.run(run_recover_not_owner_check())
            asyncio.run(run_reanalysis_command_check())
            run_knowledge_display_check()
            run_html_renderer_check()
            run_html_knowledge_listing_check()
            asyncio.run(run_html_delivery_check())
            run_learning_intake_location_check(root)
            run_tiktok_ingestion_deferral_check()
        finally:
            knowledge_store.KB_DIR, knowledge_store.UNIFIED_INDEX_FILE, knowledge_store.ENTRIES_DIR = old_values

    print("telegram learning delivery checks: PASS")


if __name__ == "__main__":
    run_tests()
