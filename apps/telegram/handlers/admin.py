"""apps/telegram/handlers/admin.py — Admin & System Control Handlers.

Handles system status checks, help menus, start commands, and task cancellations.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from apps.telegram.utils import reply_html
import config

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    msg = (
        "🤖 **Chào mừng bạn đến với Hermes Agent!**\n\n"
        "Tôi là Trợ lý AI cá nhân chuyên về **Học Kiến Thức & Truy Vấn Trí Thức**.\n\n"
        "📌 **Các lệnh chính:**\n"
        "• `/knowledge [all|approved|pending]` - Xem danh sách bài học đã nạp\n"
        "• `/assistant <câu hỏi>` - Hỏi đáp với AI kết hợp tri thức đã học\n"
        "• `/status` - Kiểm tra trạng thái hệ thống & kết nối DB\n"
        "• `/help` - Hiển thị hướng dẫn chi tiết\n\n"
        "💡 *Gửi cho tôi bất kỳ link video/bài viết nào để tôi học bài học mới!*"
    )
    await reply_html(update.message, msg)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    msg = (
        "📖 **HƯỚNG DẪN SỬ DỤNG HERMES AGENT**\n\n"
        "**1. Quản lý Kiến thức (Knowledge Management):**\n"
        "• `/knowledge` : Xem các bài học đã duyệt\n"
        "• `/knowledge pending` : Xem bài học đang chờ duyệt\n"
        "• `/approve <id>` : Phê duyệt bài học mới vào hệ thống\n"
        "• `/reject <id>` : Từ chối bài học\n\n"
        "**2. Hỏi đáp AI (AI Assistance & RAG):**\n"
        "• `/assistant <nội dung>` : Truy vấn trợ lý AI cá nhân\n"
        "• `/tech <câu hỏi>` : Hỏi đáp kỹ thuật lập trình / kiến trúc\n"
        "• `/story <chủ đề>` : Sáng tạo kịch bản / câu chuyện\n\n"
        "**3. Hệ thống:**\n"
        "• `/status` : Báo cáo trạng thái hệ thống & bộ nhớ RAM\n"
        "• `/cancel` : Hủy tác vụ đang xử lý"
    )
    await reply_html(update.message, msg)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command: Show memory usage & system status."""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / (1024 * 1024)
    
    from core.knowledge_store import get_store
    store = get_store()
    entries = store.list_entries()
    approved = sum(1 for e in entries if e.get("status") == "approved")
    pending = sum(1 for e in entries if e.get("status") == "pending")

    msg = (
        "⚡ **BÁO CÁO TRẠNG THÁI HERMES AGENT**\n\n"
        f"• **RAM Tiến trình Bot:** `{mem_mb:.1f} MB`\n"
        f"• **Trạng thái Database:** ✅ Connected (`{config.HERMES_STORAGE_BACKEND}`)\n"
        f"• **Tổng số Bài học:** `{len(entries)}` (Approved: `{approved}`, Pending: `{pending}`)\n"
        f"• **LLM Model mặc định:** `{getattr(config, 'LLM_DEFAULT_MODEL', 'fast')}`\n"
    )
    await reply_html(update.message, msg)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command."""
    await reply_html(update.message, "🛑 Đã gửi yêu cầu hủy các tác vụ đang chạy.")
