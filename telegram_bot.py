import os
import sys
import logging
import asyncio
import re
import json
from pathlib import Path
from dotenv import load_dotenv

# Thêm thư mục hiện tại vào Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Force stdout/stderr to use UTF-8 encoding on Windows to prevent UnicodeEncodeError
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import config
import google.generativeai as genai
from core.agent_jobs import AgentJobManager
from core.assistant_runtime import HermesAssistantRuntime
from core.coding_agent import CodingAgentPlanner
from core.job_dedup import JobDedup
from core.learning_review import LearningReviewStore
from core.pending_store import PendingStore
from tools.script_generator import check_ollama, get_ollama_client
from core.router import resolve_route, get_mode, get_engine, MODE_LEARN_KNOWLEDGE, MODE_LEARN_VIDEO, MODE_LEARN_HOOK_CTA, MODE_SCRIPT_FROM_VIDEO

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

PENDING_STORE = PendingStore()
JOB_DEDUP = JobDedup()
USER_EDIT_STATE = {} # user_id -> {'proposal': name, 'field': field}
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
REPORT_PRIORITY = [
    "knowledge_proposal.md",
    "learning_proposal.md",
    "analysis.md",
    "worker_notes.md",
    "hook_body_cta.md",
    "workflow_steps.md",
]
LEARNING_STORE = LearningReviewStore()
VIDEO_SOURCE_DIR = LEARNING_STORE.root / "video_sources"
VIDEO_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

# Life-cycle and configuration flags (CODEX JOB #001)
_stop_event = asyncio.Event()
_outbox_task = None
_GEMINI_INITIALIZED = False

# Import python-telegram-bot
try:
    from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
except ImportError:
    print("[!] Thư viện python-telegram-bot chưa được cài đặt. Đang chạy cài đặt tự động...")
    # Sẽ được cài đặt thông qua requirements.txt

# Định nghĩa các System Instruction cho từng Trợ lý AI
STORY_INSTRUCTION = (
    "Bạn là một nhà văn sáng tạo lỗi lạc và là biên kịch chuyên nghiệp. "
    "Nhiệm vụ của bạn là sáng tác các câu chuyện hoặc kịch bản dựa trên chủ đề yêu cầu. "
    "Câu chuyện cần có chiều sâu, giàu cảm xúc, văn phong bay bổng lôi cuốn và sử dụng tiếng Việt tự nhiên chuẩn xác."
)

CODEREVIEW_INSTRUCTION = (
    "Bạn là một Senior Software Engineer và chuyên gia đánh giá mã nguồn (Code Reviewer). "
    "Nhiệm vụ của bạn là phân tích đoạn code được gửi, chỉ ra các lỗi logic, lỗ hổng bảo mật, "
    "vấn đề về hiệu năng và định dạng chuẩn (coding standards). "
    "Sau đó, hãy đề xuất giải pháp refactor code chi tiết kèm ví dụ minh họa cụ thể. "
    "Câu trả lời cần ngắn gọn, rõ ràng, đi thẳng vào vấn đề kỹ thuật."
)

TECH_INSTRUCTION = (
    "Bạn là một chuyên gia công nghệ thông tin và kiến trúc sư hệ thống. "
    "Nhiệm vụ của bạn là giải đáp các câu hỏi kỹ thuật, giải thuật, hướng dẫn lập trình "
    "hoặc thiết kế hệ thống một cách tối ưu, chính xác và có chiều sâu cấu trúc."
)

CHAT_INSTRUCTION = (
    "Bạn là một trợ lý ảo cá nhân đa năng thân thiện, lịch sự và hữu ích của người dùng."
)

def init_gemini():
    """Khởi tạo Google Gemini API"""
    global _GEMINI_INITIALIZED
    if _GEMINI_INITIALIZED:
        return True
        
    api_key = config.GEMINI_API_KEY
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        api_key = os.environ.get("GEMINI_API_KEY", "")
    
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        logger.warning("Chưa cấu hình GEMINI_API_KEY trong .env")
        return False
        
    genai.configure(api_key=api_key)
    _GEMINI_INITIALIZED = True
    return True

def ask_gemini(prompt: str, instruction: str) -> str:
    """Gọi Gemini API để tạo nội dung với System Instruction tương ứng"""
    if not _GEMINI_INITIALIZED:
        return "❌ Lỗi: Chưa cấu hình hoặc khởi tạo GEMINI_API_KEY trong file `.env`."
    
    try:
        model_name = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=instruction
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Lỗi kết nối Gemini API: {e}")
        return f"❌ Có lỗi xảy ra khi kết nối với Gemini AI: {str(e)}"

def ask_local_ollama(prompt: str, system_prompt: str) -> str:
    """Gọi Ollama Local Model chạy ngoại tuyến (offline)"""
    is_running, model_installed, installed_models = check_ollama()
    model_name = getattr(config, "DEFAULT_LOCAL_MODEL", "llama3.2:3b")
    
    if not is_running:
        return (
            "❌ Lỗi: Không thể kết nối tới ứng dụng Ollama trên máy tính.\n"
            "Hãy đảm bảo phần mềm Ollama đang chạy ở nền."
        )
    if not model_installed:
        return (
            f"❌ Lỗi: Mô hình cục bộ '{model_name}' chưa được cài đặt.\n"
            f"Vui lòng chạy lệnh: `ollama pull {model_name}` trong terminal của bạn."
        )
        
    try:
        client = get_ollama_client()
        response = client.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            options={"temperature": 0.7}
        )
        return response["message"]["content"]
    except Exception as e:
        logger.error(f"Lỗi Ollama: {e}")
        return f"❌ Lỗi khi truy vấn mô hình cục bộ Ollama: {str(e)}"

def split_message(text: str, limit: int = 4000) -> list[str]:
    """Cắt nhỏ tin nhắn dài hơn giới hạn của Telegram (4096 ký tự)"""
    if len(text) <= limit:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        
        # Thử cắt ở dòng mới hoặc khoảng trắng
        split_pos = text.rfind('\n', 0, limit)
        if split_pos == -1:
            split_pos = text.rfind(' ', 0, limit)
        if split_pos == -1:
            split_pos = limit
            
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    return chunks

async def send_response(update: Update, text: str):
    """Gửi câu trả lời cho người dùng, tự động chia nhỏ nếu quá dài"""
    chunks = split_message(text)
    for chunk in chunks:
        # Sử dụng Markdown nếu cấu trúc chuẩn, hoặc gửi text thường nếu bị lỗi cú pháp Markdown
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            # Gửi dự phòng dưới dạng plain text nếu Markdown bị lỗi cú pháp
            await update.message.reply_text(chunk)


def extract_first_url(text: str) -> str:
    match = URL_PATTERN.search(text or "")
    if not match:
        return ""
    return match.group(0).strip().rstrip(".,)")


def get_message_text(update: Update) -> str:
    message = update.message
    if not message:
        return ""
    return message.text or message.caption or ""


def command_tail(text: str, commands: list[str]) -> str:
    cleaned = (text or "").strip()
    lowered = cleaned.lower()
    for command in commands:
        if lowered.startswith(command.lower()):
            return cleaned[len(command):].strip()
    return cleaned


def extract_video_attachment(message):
    if not message:
        return None
    if getattr(message, "video", None):
        video = message.video
        return {
            "file_id": video.file_id,
            "file_unique_id": getattr(video, "file_unique_id", ""),
            "file_name": getattr(video, "file_name", "") or "telegram_video.mp4",
            "mime_type": getattr(video, "mime_type", "") or "video/mp4",
            "source": "video",
        }
    document = getattr(message, "document", None)
    if document:
        mime_type = (getattr(document, "mime_type", "") or "").lower()
        file_name = getattr(document, "file_name", "") or "telegram_document"
        if mime_type.startswith("video/") or file_name.lower().endswith((".mp4", ".mov", ".m4v", ".webm")):
            return {
                "file_id": document.file_id,
                "file_unique_id": getattr(document, "file_unique_id", ""),
                "file_name": file_name,
                "mime_type": mime_type,
                "source": "document",
            }
    return None


def get_pending_video_file(update: Update):
    message = update.message
    direct = extract_video_attachment(message)
    if direct:
        return direct
    if message and getattr(message, "reply_to_message", None):
        replied = extract_video_attachment(message.reply_to_message)
        if replied:
            return replied
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is not None:
        return PENDING_STORE.get_file(chat_id)
    return None


def safe_file_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "telegram_video.mp4").strip("._")
    return stem or "telegram_video.mp4"


async def save_telegram_video_source(update: Update, context: ContextTypes.DEFAULT_TYPE, file_info: dict):
    stamp = datetime_now_slug()
    unique = safe_file_name(file_info.get("file_unique_id") or "telegram")
    file_name = safe_file_name(file_info.get("file_name") or "telegram_video.mp4")
    target_dir = VIDEO_SOURCE_DIR / f"{stamp}_{unique}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_name
    meta_path = target_dir / "source.json"
    metadata = {
        "file_id": file_info.get("file_id", ""),
        "file_unique_id": file_info.get("file_unique_id", ""),
        "file_name": file_name,
        "mime_type": file_info.get("mime_type", ""),
        "source": file_info.get("source", ""),
        "chat_id": update.effective_chat.id if update.effective_chat else None,
        "username": update.effective_user.username if update.effective_user else "",
        "saved_path": str(target_path.resolve()),
    }
    try:
        telegram_file = await context.bot.get_file(file_info["file_id"])
        await telegram_file.download_to_drive(custom_path=str(target_path))
        metadata["download_status"] = "downloaded"
    except Exception as exc:
        metadata["download_status"] = "failed"
        metadata["download_error"] = str(exc)
        target_path = None
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return target_path, metadata


def datetime_now_slug() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_pending_video_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    text = get_message_text(update)
    url = extract_first_url(text)
    if url:
        return url

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is not None:
        return PENDING_STORE.get_link(chat_id) or ""
    return ""


async def ask_video_intent(update: Update, url: str):
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is not None:
        PENDING_STORE.set_link(chat_id, url)

    text = (
        "Mình đã nhận link video:\n"
        f"{url}\n\n"
        "Bạn muốn xử lý theo hướng nào?\n\n"
        "👉 /hoc_kien_thuc - Học kiến thức chia sẻ (công cụ, quy trình, bài học cho Hermes)\n"
        "👉 /hoc_hook_CTA - Học công thức bán hàng (Hook, Body, CTA, góc quay, prompts)\n"
        "👉 /len_kich_ban - Phân tích video và viết kịch bản review bán hàng mới\n\n"
        "Bạn cũng có thể nhắn thẳng: /hoc_kien_thuc <link> hoặc /len_kich_ban <link>."
    )
    await update.message.reply_text(text)


def build_video_job(mode, source_value: str, extra_note: str = "", telegram_info: dict = None, source_kind: str = "tiktok_url"):
    if isinstance(mode, dict):
        mode = mode.get("mode", MODE_LEARN_KNOWLEDGE)
    manager = AgentJobManager()
    telegram_info = telegram_info or {}
    chat_id = telegram_info.get("chat_id", 0) or 0

    if mode in [MODE_LEARN_VIDEO, MODE_LEARN_KNOWLEDGE]:
        tasks = [
            MODE_LEARN_KNOWLEDGE,
            "analyze_video",
            "extract_tools_and_concepts",
            "extract_workflow_steps",
            "extract_key_facts_and_notes",
            "apply_knowledge_to_hermes",
            "propose_knowledge_note_for_review",
        ]
        expected_outputs = [
            "analysis.md",
            "knowledge_summary.md",
            "tools_and_concepts.md",
            "workflow_steps.md",
            "hermes_applications.md",
            "knowledge_proposal.md",
            "worker_notes.md",
        ]
        notes = (
            "Telegram request: /hoc_kien_thuc. Learn the knowledge shared in the video. "
            "Extract tools, concepts, workflow steps, key facts, cautions, and how Hermes can use this knowledge. "
            "Do not default to sales hooks, CTA, storyboard, or prompt packs unless the video itself teaches those. "
            "Do not overwrite the shared knowledge base automatically; write knowledge_proposal.md for human review."
        )
        engine = MODE_LEARN_KNOWLEDGE
        job_type = "knowledge_learning"
    elif mode == MODE_LEARN_HOOK_CTA:
        tasks = [
            MODE_LEARN_HOOK_CTA,
            "analyze_video",
            "extract_hook_body_cta",
            "extract_retention_devices",
            "extract_environment_product_voice",
            "apply_lessons_to_promptA_promptB_promptC",
            "propose_new_reusable_prompt_if_needed",
        ]
        expected_outputs = [
            "analysis.md",
            "hook_body_cta.md",
            "ideas_setup.md",
            "prompt_router_mapping.md",
            "learning_proposal.md",
            "worker_notes.md",
        ]
        notes = (
            "Telegram request: /hoc_hook_CTA. Learn the content formula from the video. "
            "Extract hook-body-proof-CTA, retention devices, visual environment, product/demo mechanics if present, and reusable content patterns. "
            "Map the lessons to the local TikTok prompt router: promptA for voice sales scripts, promptB for image/background prompts, promptC for AI video prompts. "
            "Do not overwrite the shared prompt library automatically; write learning_proposal.md for human review."
        )
        engine = MODE_LEARN_HOOK_CTA
        job_type = "hook_cta_learning"
    else:
        tasks = [
            "analyze_video",
            "describe_environment_product_voice",
            "write_script",
            "write_scene_breakdown",
            "write_image_prompts",
            "write_video_prompts",
            "write_voiceover",
            "write_hook_cta_options",
        ]
        notes = (
            "Telegram request: /len_kich_ban. Analyze the TikTok/video link and create a new sales/content script inspired by it. "
            "Include: product/environment description, visual style, speaker/voice style, hook logic, CTA logic, "
            "scene-by-scene plan, voiceover, on-screen text, image prompts, video prompts, and CapCut/editing notes. "
            "Keep the output practical for TikTok Shop and vertical 9:16 production."
        )
        expected_outputs = None
        engine = "mixed"
        job_type = "tiktok_product_review"

    if extra_note:
        notes += f"\nExtra user note: {extra_note.strip()}"

    job = JOB_DEDUP.create_or_duplicate(
        source_value,
        mode,
        chat_id,
        lambda: manager.create_job(
            source_value=source_value,
            source_kind=source_kind,
            target_mode="create_new",
            tasks=tasks,
            style={
                "language": "vi",
                "video_format": "vertical_tiktok",
                "duration_seconds": 45,
                "notes": notes,
            },
            created_by="telegram_bot",
            telegram_info=telegram_info,
            engine=engine,
            job_type=job_type,
            expected_outputs=expected_outputs,
        ),
    )
    if job.get("duplicate"):
        return job

    # Tích hợp CODEX JOB #002: Lấy transcript của video từ xa không qua Gemini File API
    try:
        from core.video_fetcher import fetch_transcript
        output_dir = job["target"]["output_dir"]
        logger.info(f"[*] Bắt đầu trích xuất transcript cho {source_value} tại {output_dir}")
        res = fetch_transcript(source_value, output_dir)
        
        job["source"]["transcript"] = res["transcript"]
        job["source"]["transcript_method"] = res["method"]
        
        # Ghi đè cập nhật lại file json trên đĩa để các worker đồng bộ dữ liệu
        manager._write_json(Path(job["paths"]["job_file"]), job)
        manager._write_json(Path(output_dir) / "job.json", job)
        logger.info(f"[+] Hoàn thành lấy transcript bằng phương pháp: {res['method']}")
    except Exception as exc:
        logger.error(f"Lỗi khi trích xuất transcript trong build_video_job: {exc}")

    return job


def build_product_manifest_job(engine: str, product_name: str, extra_note: str = "", telegram_info: dict = None):
    manager = AgentJobManager()
    notes = (
        f"Telegram manifest request. Create a TikTok product review package for: {product_name}. "
        "Telegram only creates the manifest; Hermes Planner and workers handle the task queue/artifacts."
    )
    if engine == "html_video":
        notes += " Engine target: HTML video page/storyboard render workflow."
    if extra_note:
        notes += f"\nExtra user note: {extra_note.strip()}"

    return manager.create_job(
        source_value=product_name,
        source_kind="product_text",
        target_mode="create_new",
        new_project_name=product_name,
        tasks=None,
        style={
            "language": "vi",
            "video_format": "vertical_tiktok",
            "duration_seconds": 45,
            "notes": notes,
        },
        created_by="telegram_bot",
        telegram_info=telegram_info or {},
        engine=engine,
    )


def build_upgrade_audit_job(focus: str = "", telegram_info: dict = None):
    manager = AgentJobManager()
    focus = (focus or "").strip()
    source_value = focus or "Hermes upgrade audit"
    notes = (
        "Telegram request: /de_xuat_nang_cap. Create a Codex + Antigravity "
        "upgrade audit for Hermes. This job must only write analysis and proposal "
        "artifacts. Do not implement code changes before human approval."
    )
    if focus:
        notes += f"\nUpgrade focus: {focus}"

    return manager.create_job(
        source_value=source_value,
        source_kind="upgrade_request",
        target_mode="create_new",
        new_project_name="Hermes upgrade audit",
        tasks=[
            "codex_repo_upgrade_audit",
            "antigravity_cross_review",
            "consolidate_upgrade_proposal",
            "write_human_approval_checklist",
        ],
        style={
            "language": "vi",
            "video_format": "repo_upgrade",
            "duration_seconds": 0,
            "notes": notes,
        },
        created_by="telegram_bot",
        telegram_info=telegram_info or {},
        engine="upgrade_audit",
        job_type="hermes_upgrade_audit",
        expected_outputs=[
            "upgrade_audit.md",
            "antigravity_review.md",
            "upgrade_proposal.md",
            "approval_checklist.md",
            "worker_notes.md",
        ],
    )


def looks_like_code(text: str) -> bool:
    lowered = (text or "").lower()
    code_markers = [
        "def ", "class ", "import ", "function", "const ", "let ", "var ",
        "select * from", "public ", "private ", "return ", "{", "}", "</", "dockerfile",
    ]
    return any(marker in lowered for marker in code_markers) or "\n" in text


async def create_product_job_command(update: Update, context: ContextTypes.DEFAULT_TYPE, engine: str):
    raw_text = update.message.text or ""
    command = raw_text.split(maxsplit=1)[0] if raw_text.strip() else ""
    product_name = raw_text[len(command):].strip()
    if not product_name:
        await update.message.reply_text(
            "Hãy nhập tên sản phẩm sau lệnh.\n"
            "Ví dụ: /review Giá đỡ điện thoại xoay 360 màu trắng\n"
            "Hoặc: /htmlvideo Giá đỡ điện thoại xoay 360"
        )
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    username = update.effective_user.username if update.effective_user else ""
    telegram_info = {"chat_id": chat_id, "username": username}

    await update.message.reply_text("Đã nhận yêu cầu. Hermes đang tạo Job Manifest và Planner task queue...")
    try:
        job = build_product_manifest_job(engine, product_name, telegram_info=telegram_info)
        reply = (
            "Đã tạo Job Manifest.\n\n"
            f"Job ID: {job['job_id']}\n"
            f"Engine: {engine}\n"
            f"Project: {job['target']['project_slug']}\n"
            f"Manifest: {job['paths'].get('manifest_file', '')}\n"
            f"Task prompt: {job['paths'].get('manifest_worker_prompt', '')}\n\n"
            "Mở Hermes GUI tab Agent Jobs để xem checklist/progress/artifacts."
        )
        await update.message.reply_text(reply)
    except Exception as exc:
        logger.exception("Failed to create product manifest job")
        await update.message.reply_text(f"Lỗi tạo Job Manifest: {exc}")


async def create_video_job_command(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    url = get_pending_video_url(update, context)
    pending_file = None if url else get_pending_video_file(update)
    source_value = url
    
    source_kind = "url"
    if url:
        if "tiktok" in url.lower():
            source_kind = "tiktok_url"
        elif "youtube" in url.lower() or "youtu.be" in url.lower():
            source_kind = "youtube_url"
            
    local_video_path = None
    source_metadata = {}

    if not source_value and pending_file:
        await update.message.reply_text("Da nhan video. Minh dang luu file vao kho hoc hoi...")
        local_video_path, source_metadata = await save_telegram_video_source(update, context, pending_file)
        source_value = str(local_video_path.resolve()) if local_video_path else f"telegram_file:{pending_file.get('file_id', '')}"
        source_kind = "local_video" if local_video_path else "telegram_video"

    if not source_value:
        await update.message.reply_text(
            "Mình chưa nhận được link hoặc file video nào. Hãy gửi link TikTok/YouTube hoặc gửi file video kèm caption:\n"
            "/hoc_kien_thuc <link>\n"
            "/hoc_hook_CTA <link>\n"
            "/len_kich_ban <link>\n"
            "/hoc_video"
        )
        return

    await update.message.reply_text("Da nhan yeu cau. Minh dang tao job de worker phan tich video...")
    try:
        raw_text = get_message_text(update)
        extra_note = raw_text.replace("/hoc_video", "").replace("/hoc_kien_thuc", "").replace("/hoc_hook_CTA", "").replace("/hoc_hook_cta", "").replace("/len_kich_ban", "")
        extra_note = extra_note.replace("/học video", "").replace("/lên kịch bản", "")
        extra_note = extra_note.replace(source_value, "").replace(url or "", "").strip()
        
        chat_id = update.effective_chat.id if update.effective_chat else None
        username = update.effective_user.username if update.effective_user else ""
        telegram_info = {
            "chat_id": chat_id,
            "username": username,
            "source_metadata": source_metadata,
        }

        job = build_video_job(
            mode,
            source_value,
            extra_note=extra_note,
            telegram_info=telegram_info,
            source_kind=source_kind,
        )
        if job.get("duplicate"):
            if chat_id is not None:
                if url and PENDING_STORE.get_link(chat_id) == url:
                    PENDING_STORE.clear_link(chat_id)
                if pending_file:
                    PENDING_STORE.clear_file(chat_id)
            await update.message.reply_text(
                "Video nay da duoc xu ly roi.\n"
                f"Job ID cu: {job['existing_job_id']}\n"
                f"Dung /report {job['existing_job_id']} de xem ket qua."
            )
            return

        intake_path = ""
        if mode in [MODE_LEARN_VIDEO, MODE_LEARN_KNOWLEDGE, MODE_LEARN_HOOK_CTA]:
            intake_path = create_learning_intake_note(
                job=job,
                source_value=source_value,
                source_kind=source_kind,
                extra_note=extra_note,
                local_video_path=local_video_path,
                telegram_info=telegram_info,
            )

        if chat_id is not None and url and PENDING_STORE.get_link(chat_id) == url:
            PENDING_STORE.clear_link(chat_id)
        if chat_id is not None and pending_file:
            PENDING_STORE.clear_file(chat_id)

        reply = (
            "Da tao job phan tich video.\n\n"
            f"Job ID: {job['job_id']}\n"
            f"Project: {job['target']['project_slug']}\n"
            f"Output: {job['target']['output_dir']}\n"
            f"Worker prompt: {job['paths']['worker_prompt']}\n\n"
            f"Intake note: {intake_path or 'N/A'}\n\n"
            "Bot se tu dong gui ket qua va tep tin vao day ngay khi Worker/AI xu ly xong."
        )
        await update.message.reply_text(reply)
    except Exception as exc:

        logger.exception("Failed to create video job")
        await update.message.reply_text(f"Lỗi tạo job video: {exc}")


def create_learning_intake_note(job: dict, source_value: str, source_kind: str, extra_note: str, local_video_path, telegram_info: dict):
    output_dir = job.get("target", {}).get("output_dir", "")
    worker_prompt = job.get("paths", {}).get("worker_prompt", "")
    manifest_prompt = job.get("paths", {}).get("manifest_worker_prompt", "")
    body = f"""# Video Learning Intake

Status: pending_review
Job ID: {job.get('job_id', '')}
Source kind: {source_kind}
Source: {source_value}
Local video: {str(local_video_path) if local_video_path else ''}
Telegram user: {telegram_info.get('username', '')}
Extra note: {extra_note}

## What to learn

- Neu dung /hoc_kien_thuc: cong cu, khai niem, quy trinh, buoc lam, luu y, cach ap dung vao Hermes.
- Neu dung /hoc_hook_CTA: hook, body, proof, CTA, retention, goc quay, prompt/phong cach noi dung.
- Khong duoc bia noi dung neu worker chua doc duoc video/transcript.

## Worker files

- Output folder: {output_dir}
- Legacy worker prompt: {worker_prompt}
- Manifest worker prompt: {manifest_prompt}

## Human approval rule

File nay chi la phieu nhan job. Ket qua hoc that se duoc worker ghi vao `learning_proposal.md` va day sang `knowledge_base/review_queue/` de anh duyet.
"""
    intake_dir = LEARNING_STORE.root / "video_intake"
    intake_dir.mkdir(parents=True, exist_ok=True)
    safe_job_id = re.sub(r"[^A-Za-z0-9_-]+", "-", job.get("job_id", "job")).strip("-")
    path = intake_dir / f"{datetime_now_slug()}_{safe_job_id}.md"
    path.write_text(body.strip() + "\n", encoding="utf-8")
    return str(path.resolve())


async def hoc_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = get_mode(update.message.text or "/hoc_video")
    await create_video_job_command(update, context, mode=mode)


async def hoc_kien_thuc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = get_mode(update.message.text or "/hoc_kien_thuc")
    await create_video_job_command(update, context, mode=mode)


async def hoc_hook_cta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = get_mode(update.message.text or "/hoc_hook_cta")
    await create_video_job_command(update, context, mode=mode)


async def len_kich_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = get_mode(update.message.text or "/len_kich_ban")
    await create_video_job_command(update, context, mode=mode)


async def luu_prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = get_message_text(update)
    body = command_tail(raw_text, ["/luu_prompt", "/save_prompt"])
    if not body and update.message and getattr(update.message, "reply_to_message", None):
        body = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""

    if not body.strip():
        await update.message.reply_text(
            "Gui prompt sau lenh, hoac reply vao mot tin nhan prompt:\n"
            "/luu_prompt Ten prompt | noi dung prompt"
        )
        return

    title = "Prompt tu Telegram"
    prompt_text = body.strip()
    if "|" in prompt_text:
        title_part, prompt_part = prompt_text.split("|", 1)
        if title_part.strip() and prompt_part.strip():
            title = title_part.strip()
            prompt_text = prompt_part.strip()

    username = update.effective_user.username if update.effective_user else ""
    proposal = f"""# Prompt Proposal

Status: pending_review
Title: {title}
Source: Telegram
Telegram user: {username}

## Prompt

```text
{prompt_text}
```

## Suggested use

- Neu la voice/script ban hang, dua vao promptA hoac tao template voice moi.
- Neu la prompt hinh/background, dua vao promptB.
- Neu la prompt video AI, dua vao promptC.

## Review checklist

- Co trung template hien co khong?
- Bien dau vao can co la gi?
- Khi nao nen ap dung?
- Khi nao khong nen ap dung?
"""
    path = LEARNING_STORE.create_proposal(title, proposal, prefix="prompt")
    await update.message.reply_text(
        "Da luu prompt vao hang cho duyet.\n"
        f"Proposal: {path}\n\n"
        "Mo GUI tab Duyet hoc hoi de approve hoac reject."
    )


async def de_xuat_nang_cap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = get_message_text(update)
    focus = command_tail(raw_text, ["/de_xuat_nang_cap", "/upgrade_audit", "/audit_upgrade"])
    telegram_info = {
        "chat_id": update.effective_chat.id if update.effective_chat else None,
        "username": update.effective_user.username if update.effective_user else "",
    }
    try:
        job = build_upgrade_audit_job(focus=focus, telegram_info=telegram_info)
        reply = (
            "Da tao job de xuat nang cap Hermes.\n\n"
            f"Job ID: {job['job_id']}\n"
            f"Project: {job['target']['project_slug']}\n"
            f"Output: {job['target']['output_dir']}\n"
            f"Worker prompt: {job['paths']['worker_prompt']}\n"
            f"Manifest prompt: {job['paths']['manifest_worker_prompt']}\n\n"
            "Quy trinh: Codex audit -> Antigravity review -> Codex gom proposal -> anh approve roi moi implement."
        )
        await update.message.reply_text(reply)
    except Exception as exc:
        logger.exception("Failed to create upgrade audit job")
        await update.message.reply_text(f"Loi tao job de xuat nang cap: {exc}")


async def assistant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = get_message_text(update)
    request = command_tail(raw_text, ["/assistant"])
    if not request:
        await update.message.reply_text(
            "Usage: /assistant <request>\n"
            "Example: /assistant learn from telegram report and fix duplicate jobs"
        )
        return

    runtime = HermesAssistantRuntime(Path(__file__).resolve().parent)
    plan = runtime.build_plan(request)
    await send_response(update, runtime.format_markdown(plan))


async def code_plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = get_message_text(update)
    request = command_tail(raw_text, ["/code_plan"])
    if not request:
        await update.message.reply_text(
            "Usage: /code_plan <coding request>\n"
            "Example: /code_plan fix telegram duplicate reports"
        )
        return

    planner = CodingAgentPlanner(Path(__file__).resolve().parent)
    plan = planner.build_plan(request)
    report_path = planner.write_report(plan)
    await send_response(update, planner.format_markdown(plan)[:3500])
    try:
        with report_path.open("rb") as doc:
            await update.message.reply_document(document=doc, filename=report_path.name)
    except Exception as exc:
        logger.warning("Could not send code plan report %s: %s", report_path, exc)
        await update.message.reply_text(f"Report written locally: {report_path}")


# Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤖 **Xin chào! Tôi là Trợ lý AI Đa Năng của bạn (Hermes Agent).**\n\n"
        "Tôi có thể hỗ trợ bạn thực hiện các tác vụ công nghệ và sáng tạo bằng các lệnh dưới đây:\n\n"
        "📝 **Sáng tác truyện**: `/story [chủ đề]` (Ví dụ: `/story Một thành phố trên mây`)\n"
        "🛍️ **Tạo Job Manifest review sản phẩm**: `/review [tên sản phẩm]`\n"
        "🌐 **Tạo Job Manifest HTML video**: `/htmlvideo [tên sản phẩm]`\n"
        "💻 **Review Code**: `/review [đoạn code]` nếu nội dung có dấu hiệu code\n"
        "💡 **Hỏi đáp Công nghệ**: `/tech [câu hỏi]` (Ví dụ: `/tech Docker là gì`)\n"
        "🏠 **Chat Offline (Ollama)**: `/local [câu hỏi]` (Sử dụng AI chạy cục bộ trên máy tính của bạn)\n\n"
        "🎬 **Học từ video TikTok**: gửi link/video rồi chọn hướng học\n"
        "   • `/hoc_kien_thuc` = học kiến thức bài chia sẻ: công cụ, khái niệm, quy trình, bước làm, lưu ý\n"
        "   • `/hoc_hook_CTA` = học công thức nội dung: hook, body, proof, CTA, góc quay, prompt/phân cảnh\n"
        "   • `/hoc_video` = alias của `/hoc_kien_thuc`\n"
        "   • `/len_kich_ban` = phân tích và lên kịch bản mới\n\n"
        "🧠 **Lưu prompt học hỏi**: `/luu_prompt Tên prompt | nội dung prompt`\n\n"
        "💬 Ngoài ra, bạn có thể **chat trực tiếp** không cần lệnh, tôi sẽ trả lời như một người bạn ảo!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)

async def story_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip()
    if not topic:
        await update.message.reply_text("⚠️ Vui lòng nhập chủ đề câu chuyện sau lệnh `/story`. Ví dụ: `/story Con mèo bay`")
        return
        
    await update.message.reply_text("📝 *Đang sáng tác truyện cho bạn, vui lòng chờ chút...*", parse_mode="Markdown")
    await update.message.reply_chat_action("typing")
    
    result = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, topic, STORY_INSTRUCTION)
    await send_response(update, result)

async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lấy toàn bộ nội dung sau lệnh `/review `
    message_text = update.message.text
    code = message_text[len("/review"):].strip()
    
    if not code:
        await update.message.reply_text(
            "Vui lòng nhập tên sản phẩm sau `/review`, ví dụ:\n"
            "`/review Giá đỡ điện thoại xoay 360 màu trắng`\n\n"
            "Nếu muốn review code, gửi đoạn code sau `/review` như trước."
        )
        return

    if not looks_like_code(code):
        await create_product_job_command(update, context, engine="ai_studio")
        return
        
    await update.message.reply_text("🔍 *Đang phân tích cấu trúc và đánh giá code của bạn...*", parse_mode="Markdown")
    await update.message.reply_chat_action("typing")
    
    result = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, code, CODEREVIEW_INSTRUCTION)
    await send_response(update, result)


async def htmlvideo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await create_product_job_command(update, context, engine="html_video")

async def tech_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args).strip()
    if not question:
        await update.message.reply_text("⚠️ Vui lòng nhập câu hỏi công nghệ sau lệnh `/tech`. Ví dụ: `/tech RESTful API là gì`")
        return
        
    await update.message.reply_text("💡 *Đang tra cứu và tổng hợp kiến thức công nghệ...*", parse_mode="Markdown")
    await update.message.reply_chat_action("typing")
    
    result = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, question, TECH_INSTRUCTION)
    await send_response(update, result)

async def local_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args).strip()
    if not question:
        await update.message.reply_text("⚠️ Vui lòng nhập câu hỏi sau lệnh `/local`. Ví dụ: `/local Viết một bài thơ về biển`")
        return
        
    model_name = getattr(config, "DEFAULT_LOCAL_MODEL", "llama3.2:3b")
    await update.message.reply_text(f"🏠 *Đang xử lý cục bộ trên máy tính của bạn (Ollama - {model_name})...*", parse_mode="Markdown")
    await update.message.reply_chat_action("typing")
    
    # Chạy đồng bộ trong Threadpool của asyncio để không làm đơ bot khi Ollama chạy lâu
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, 
        ask_local_ollama, 
        question, 
        "Bạn là một trợ lý AI hữu ích hoạt động cục bộ trên máy tính của người dùng. Hãy trả lời ngắn gọn bằng tiếng Việt."
    )
    await send_response(update, result)


async def video_attachment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_info = extract_video_attachment(update.message)
    if not file_info:
        return
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is not None:
        PENDING_STORE.set_file(chat_id, file_info)

    caption = (update.message.caption or "").strip()
    route = resolve_route(caption)
    if route:
        await create_video_job_command(update, context, mode=route["mode"])
        return

    await update.message.reply_text(
        "Minh da nhan video.\n"
        "Gui /hoc_kien_thuc de hoc noi dung/kien thuc trong video.\n"
        "Gui /hoc_hook_CTA de hoc hook, CTA, prompt/phong cach noi dung.\n"
        "Hoac gui /len_kich_ban de tao kich ban moi dua tren video."
    )


async def default_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lắng nghe các tin nhắn thường không dùng slash command
    user_text = update.message.text
    await update.message.reply_chat_action("typing")

    route = resolve_route(user_text)
    if route:
        await create_video_job_command(update, context, mode=route["mode"])
        return

    url = extract_first_url(user_text)
    if url and any(domain in url.lower() for domain in ["tiktok.com", "vt.tiktok.com", "douyin.com", "youtube.com", "youtu.be", "instagram.com", "facebook.com"]):
        await ask_video_intent(update, url)
        return
    
    # Định tuyến ngầm: Nếu tin nhắn chứa code nhiều dòng hoặc từ khóa lập trình, dùng CODEREVIEW/TECH
    contains_code_patterns = any(
        kw in user_text for kw in [
            "def ", "class ", "import ", "function", "const ", "let ", "var ", 
            "select * from", "html", "css", "dockerfile", "git commit"
        ]
    ) or "\n" in user_text and ("{" in user_text or ":" in user_text)
    
    if contains_code_patterns:
        instruction = CODEREVIEW_INSTRUCTION
    else:
        instruction = CHAT_INSTRUCTION

    result = await asyncio.get_event_loop().run_in_executor(None, ask_gemini, user_text, instruction)
    await send_response(update, result)


def sort_report_files(paths: list[Path]) -> list[Path]:
    priority = {name: index for index, name in enumerate(REPORT_PRIORITY)}
    original_order = {str(path.resolve()): index for index, path in enumerate(paths)}
    return sorted(
        paths,
        key=lambda path: (
            priority.get(path.name, len(REPORT_PRIORITY)),
            original_order.get(str(path.resolve()), 0),
        ),
    )


def find_report_files(job_id: str) -> list[Path]:
    job_id = (job_id or "").strip()
    if not job_id:
        return []

    repo_root = Path(__file__).resolve().parent
    manager = AgentJobManager()
    output_dirs = []

    for row in manager.list_jobs(limit=500):
        if row.get("job_id") != job_id:
            continue
        try:
            data = manager.load_manifest_job(job_id, sync=True)
            output_dirs.append(Path(data["job_dir"]) / "artifacts")
            legacy_output = data.get("metadata", {}).get("legacy_output_dir")
            if legacy_output:
                output_dirs.append(Path(legacy_output))
        except Exception:
            path = row.get("path")
            if path:
                output_dirs.append(Path(path) / "artifacts")

    for folder in [
        manager.inbox_dir,
        manager.processing_dir,
        manager.outbox_dir,
        manager.failed_dir,
        manager.jobs_root / "done_archived",
    ]:
        for json_path in folder.glob("*.json"):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("job_id") != job_id:
                continue
            output_dir = data.get("target", {}).get("output_dir") or data.get("output_dir")
            if output_dir:
                output_dirs.append(Path(output_dir))

    found = []
    seen = set()
    for output_dir in output_dirs:
        if not output_dir.exists():
            continue
        for path in sorted(output_dir.rglob("*.md")):
            resolved = str(path.resolve())
            if resolved not in seen:
                seen.add(resolved)
                found.append(path)

    lowered = job_id.lower()
    for path in repo_root.rglob("*.md"):
        path_text = str(path).lower()
        if lowered not in path_text:
            continue
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            found.append(path)
    return sort_report_files(found)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = " ".join(context.args).strip()
    if not job_id:
        await update.message.reply_text("Hay nhap Job ID. Vi du: /report job_20260703_123456_abcd")
        return

    reports = find_report_files(job_id)
    if not reports:
        await update.message.reply_text(f"Chua co report cho job nay: {job_id}")
        return

    selected = reports[:3]
    await update.message.reply_text(
        f"Tim thay {len(reports)} files, dang gui {len(selected)} file quan trong nhat."
    )
    for path in selected:
        try:
            with path.open("rb") as doc:
                await update.message.reply_document(document=doc, filename=path.name)
        except Exception as exc:
            logger.warning("Could not send report %s: %s", path, exc)
            text = path.read_text(encoding="utf-8", errors="replace")
            await update.message.reply_text(text[:3500])


async def poll_outbox_loop(application):
    manager = AgentJobManager()
    while not _stop_event.is_set():
        try:
            results = manager.get_outbox_results()
            for res in results:
                telegram_info = res.get("telegram", {})
                chat_id = telegram_info.get("chat_id")
                job_id = res.get("job_id")
                project_slug = res.get("target", {}).get("project_slug", "")
                summary = res.get("summary", "Đã xử lý xong tác vụ.")
                output_dir = res.get("target", {}).get("output_dir", "")
                files_created = res.get("files_created", [])

                if chat_id:
                    msg = (
                        f"🎉 **JOB HOÀN THÀNH!** [`{job_id}`]\n\n"
                        f"📁 **Dự án**: `{project_slug}`\n"
                        f"📝 **Tóm tắt**: {summary}\n"
                    )
                    proposal_name = None
                    real_files = []
                    for fname in files_created:
                        if fname.startswith("__PROPOSAL__:"):
                            proposal_name = fname.split(":", 1)[1]
                        else:
                            real_files.append(fname)
                    
                    if proposal_name:
                        msg += f"\n📌 **Hàng đợi duyệt**: `{proposal_name}`\n*(Vui lòng mở GUI tab Duyệt học hỏi để xem chi tiết và phê duyệt)*"

                    try:
                        await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    except Exception:
                        await application.bot.send_message(chat_id=chat_id, text=msg)

                    if output_dir and os.path.exists(output_dir):
                        for fname in real_files:
                            fpath = os.path.join(output_dir, fname)
                            if os.path.exists(fpath):
                                try:
                                    with open(fpath, "rb") as doc:
                                        await application.bot.send_document(chat_id=chat_id, document=doc, filename=fname)
                                except Exception as e:
                                    logger.error(f"Failed to send document {fname}: {e}")

                manager.archive_done_job(job_id)
        except Exception as e:
            logger.error(f"Error in poll_outbox_loop: {e}")
        
        try:
            await asyncio.sleep(4)
        except asyncio.CancelledError:
            break


async def post_init(application):
    global _outbox_task
    removed_pending = PENDING_STORE.cleanup_expired()
    removed_dedup = JOB_DEDUP.cleanup_expired()
    logger.info("Startup cleanup removed %s pending entries and %s dedup entries.", removed_pending, removed_dedup)
    _outbox_task = asyncio.create_task(poll_outbox_loop(application))


async def post_stop(application):
    global _outbox_task
    logger.info("Đang dừng Telegram Bot và dọn dẹp tài nguyên...")
    _stop_event.set()
    if _outbox_task:
        _outbox_task.cancel()
        try:
            await _outbox_task
        except asyncio.CancelledError:
            pass
    logger.info("Vòng lặp outbox đã được đóng an toàn.")



async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("approve:"):
        proposal_name = data.split(":", 1)[1]
        try:
            res = LEARNING_STORE.approve(proposal_name)
            await query.edit_message_text(text=f"✅ Đã DUYỆT proposal `{proposal_name}` thành công và lưu vào Knowledge Store!", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(text=f"❌ Lỗi duyệt: {e}")
            
    elif data.startswith("reject:"):
        proposal_name = data.split(":", 1)[1]
        try:
            LEARNING_STORE.reject(proposal_name)
            await query.edit_message_text(text=f"❌ Đã TỪ CHỐI và chuyển `{proposal_name}` vào thùng rác.", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(text=f"❌ Lỗi từ chối: {e}")
            
    elif data.startswith("edit:"):
        proposal_name = data.split(":", 1)[1]
        keyboard = [
            [InlineKeyboardButton("Tiêu đề", callback_data=f"edit_field:{proposal_name}:Title")],
            [InlineKeyboardButton("Bài học", callback_data=f"edit_field:{proposal_name}:Lessons")],
            [InlineKeyboardButton("Hủy sửa", callback_data=f"cancel_edit:{proposal_name}")]
        ]
        await query.edit_message_text(text=f"✏️ Bạn muốn sửa phần nào của `{proposal_name}`?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif data.startswith("cancel_edit:"):
        proposal_name = data.split(":", 1)[1]
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve:{proposal_name}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject:{proposal_name}")],
            [InlineKeyboardButton("✏️ Sửa đổi", callback_data=f"edit:{proposal_name}")]
        ]
        await query.edit_message_text(text=f"📌 Hàng đợi duyệt: `{proposal_name}`\n\nTrạng thái: Đã hủy sửa đổi.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data.startswith("edit_field:"):
        parts = data.split(":")
        proposal_name = parts[1]
        field = parts[2]
        
        USER_EDIT_STATE[user_id] = {"proposal": proposal_name, "field": field}
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Bạn đang sửa **{field}** cho `{proposal_name}`.\nHãy nhập nội dung mới (hoặc gửi 'huy' để hủy):",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True)
        )

async def handle_force_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return False
        
    # Check if this is a reply to our ForceReply message
    if not update.message.reply_to_message:
        # Not a reply, let other handlers handle it
        return False
        
    user_id = update.effective_user.id
    if user_id not in USER_EDIT_STATE:
        return False
        
    state = USER_EDIT_STATE.pop(user_id)
    proposal_name = state["proposal"]
    field = state["field"]
    new_text = update.message.text
    
    if new_text.lower() == 'huy':
        await update.message.reply_text("Đã hủy sửa đổi.")
        return True
        
    # Apply change to file
    try:
        prop_path = LEARNING_STORE.queue_dir / proposal_name
        if prop_path.exists():
            content = prop_path.read_text(encoding="utf-8")
            content = content + f"\n\n**[SỬA ĐỔI - {field}]:**\n{new_text}"
            prop_path.write_text(content, encoding="utf-8")
            
            keyboard = [
                [InlineKeyboardButton("✅ Approve", callback_data=f"approve:{proposal_name}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject:{proposal_name}")],
                [InlineKeyboardButton("✏️ Sửa tiếp", callback_data=f"edit:{proposal_name}")]
            ]
            await update.message.reply_text(f"✅ Đã ghi nhận sửa đổi cho `{proposal_name}`.\nBạn có muốn duyệt ngay không?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Không tìm thấy proposal: {proposal_name}")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi ghi file: {e}")
        
    # We handled it, but telegram ext handlers require we don't return True to consume it if it's just a handler
    # Actually for MessageHandler, we don't need to return True.
    pass


def main():
    # Load env vars một lần nữa phòng hờ
    load_dotenv()
    
    # Kiểm tra cấu hình và cảnh báo nếu thiếu
    config.verify_config()
    
    # Khởi tạo Gemini một lần trước khi dựng app (CODEX JOB #001)
    init_gemini()
    
    token = config.TELEGRAM_BOT_TOKEN
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        
    if not token:
        print("\n❌ LỖI KHỞI CHẠY BOT:")
        print("----------------------------------------------------------------------")
        print("Không tìm thấy cấu hình TELEGRAM_BOT_TOKEN.")
        print("Vui lòng làm theo các bước:")
        print("1. Tạo bot thông qua @BotFather trên Telegram để nhận Token.")
        print("2. Thêm dòng sau vào file '.env' trong thư mục dự án:")
        print("   TELEGRAM_BOT_TOKEN=\"token_cua_ban_o_day\"")
        print("3. Khởi chạy lại script này: python telegram_bot.py")
        print("----------------------------------------------------------------------\n")
        return

    # Khởi động ứng dụng
    print(f"🤖 Đang cấu hình và kết nối Telegram Bot...")
    app = ApplicationBuilder().token(token).post_init(post_init).post_stop(post_stop).build()

    # Đăng ký các bộ lắng nghe sự kiện lệnh
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("story", story_command))
    app.add_handler(CommandHandler("review", review_command))
    app.add_handler(CommandHandler("htmlvideo", htmlvideo_command))
    app.add_handler(CommandHandler("tech", tech_command))
    app.add_handler(CommandHandler("local", local_command))
    app.add_handler(CommandHandler("hoc_video", hoc_video_command))
    app.add_handler(CommandHandler("hoc_kien_thuc", hoc_kien_thuc_command))
    app.add_handler(CommandHandler("hoc_hook_CTA", hoc_hook_cta_command))
    app.add_handler(CommandHandler("hoc_hook_cta", hoc_hook_cta_command))
    app.add_handler(CommandHandler("len_kich_ban", len_kich_ban_command))
    app.add_handler(CommandHandler("luu_prompt", luu_prompt_command))
    app.add_handler(CommandHandler("save_prompt", luu_prompt_command))
    app.add_handler(CommandHandler("de_xuat_nang_cap", de_xuat_nang_cap_command))
    app.add_handler(CommandHandler("upgrade_audit", de_xuat_nang_cap_command))
    app.add_handler(CommandHandler("audit_upgrade", de_xuat_nang_cap_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("assistant", assistant_command))
    app.add_handler(CommandHandler("code_plan", code_plan_command))
    
    # Đăng ký lắng nghe video/document trước text handler.
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.ALL, video_attachment_handler))

    # Đăng ký lắng nghe tin nhắn văn bản thường và các slash command có dấu/alias chưa đăng ký
    app.add_handler(MessageHandler(filters.TEXT, default_chat_handler))

    print("⚡ Bot Telegram đã KHỞI CHẠY và đang LẮNG NGHE tin nhắn...")
    print("👉 Hãy truy cập Telegram và chat với bot của bạn ngay bây giờ!")
    app.run_polling()

if __name__ == "__main__":
    main()
