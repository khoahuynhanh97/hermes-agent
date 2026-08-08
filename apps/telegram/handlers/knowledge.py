"""apps/telegram/handlers/knowledge.py — Knowledge & Learning Command Handlers.

Handles all Telegram commands related to Knowledge Acquisition, Review,
Approval/Rejection, and Querying (/knowledge, /learn, /approve, /reject, /review).
"""

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from apps.telegram.utils import reply_html

logger = logging.getLogger(__name__)


async def knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /knowledge command: List stored knowledge entries."""
    from core.knowledge_store import get_store
    
    args = context.args or []
    filter_status = "approved"
    if args:
        sub = args[0].lower()
        if sub in ("all", "pending", "approved", "rejected"):
            filter_status = None if sub == "all" else sub

    store = get_store()
    entries = store.list_entries(status=filter_status)
    
    if not entries:
        msg = f"📚 Chưa có bài học nào trong hệ thống (filter: {filter_status or 'all'})."
        await reply_html(update.message, msg)
        return

    msg = f"📚 **Danh sách Bài học Hermes ({len(entries)} bài - {filter_status or 'tất cả'}):**\n\n"
    for i, e in enumerate(entries[:15], 1):
        status_icon = "✅" if e.get("status") == "approved" else ("⏳" if e.get("status") == "pending" else "❌")
        msg += f"{i}. {status_icon} **{e.get('title', 'Untitled')}** (`{e.get('id')}`)\n"
        if e.get("key_lessons"):
            msg += f"   - {e['key_lessons'][0]}\n"

    if len(entries) > 15:
        msg += f"\n*...và {len(entries) - 15} bài học khác.*"

    await reply_html(update.message, msg)


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /approve <id> command."""
    args = context.args or []
    if not args:
        await reply_html(update.message, "⚠️ Vui lòng nhập ID bài học cần duyệt. Ví dụ: `/approve kb_12345`")
        return

    entry_id = args[0].strip()
    from core.knowledge_store import approve_entry
    result = approve_entry(entry_id, approved_by=str(update.effective_user.id))
    
    if result:
        await reply_html(update.message, f"✅ Đã duyệt thành công bài học **{result.get('title')}** (`{entry_id}`).")
    else:
        await reply_html(update.message, f"❌ Không tìm thấy bài học có ID/slug: `{entry_id}`.")


async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reject <id> command."""
    args = context.args or []
    if not args:
        await reply_html(update.message, "⚠️ Vui lòng nhập ID bài học cần từ chối. Ví dụ: `/reject kb_12345`")
        return

    entry_id = args[0].strip()
    from core.knowledge_store import reject_entry
    result = reject_entry(entry_id, rejected_by=str(update.effective_user.id))
    
    if result:
        await reply_html(update.message, f"❌ Đã từ chối bài học **{result.get('title')}** (`{entry_id}`).")
    else:
        await reply_html(update.message, f"❌ Không tìm thấy bài học có ID/slug: `{entry_id}`.")
