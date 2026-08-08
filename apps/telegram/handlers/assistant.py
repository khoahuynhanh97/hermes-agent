"""apps/telegram/handlers/assistant.py — Hermes Assistant & Chat Command Handlers.

Handles general AI assistance, chat responses, story creation,
and coding assistant commands (/assistant, /story, /tech, /code_plan).
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from apps.telegram.utils import reply_html

logger = logging.getLogger(__name__)


async def assistant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /assistant command: Run Assistant Runtime with RAG context."""
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await reply_html(update.message, "🤖 Chào bạn! Hãy nhập câu hỏi sau lệnh `/assistant <nội dung>` để tôi hỗ trợ.")
        return

    from core.assistant_runtime import HermesAssistantRuntime
    runtime = HermesAssistantRuntime()
    response = runtime.format_markdown(runtime.build_plan(user_text))
    await reply_html(update.message, response)


async def story_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /story command: Generate creative story/script."""
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await reply_html(update.message, "✍️ Vui lòng cung cấp chủ đề cho câu chuyện. Ví dụ: `/story một chú mèo du hành vũ trụ`")
        return

    from core.llm_gateway import complete
    instruction = (
        "Bạn là một nhà văn sáng tạo lỗi lạc. Hãy viết một câu chuyện ngắn hoặc kịch bản hay, "
        "giàu cảm xúc, văn phong lôi cuốn bằng tiếng Việt."
    )
    res = complete(user_text, system=instruction, task_type="chat")
    await reply_html(update.message, res)


async def tech_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tech command: Technical Q&A and architecture guidance."""
    user_text = " ".join(context.args) if context.args else ""
    if not user_text:
        await reply_html(update.message, "💻 Vui lòng đặt câu hỏi kỹ thuật. Ví dụ: `/tech Kiến trúc Monorepo là gì?`")
        return

    from core.llm_gateway import complete
    instruction = (
        "Bạn là một Senior Software Engineer và Chuyên gia Kiến trúc Hệ thống. "
        "Hãy giải đáp câu hỏi kỹ thuật một cách tối ưu, chính xác và cấu trúc rõ ràng."
    )
    res = complete(user_text, system=instruction, task_type="chat")
    await reply_html(update.message, res)
