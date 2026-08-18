import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes.runtime import config
from hermes.application.core.learning_review import LearningReviewStore


REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "reports" / "telegram_review_state.json"
RAW_REPORT_DIR = REPO_ROOT / "reports" / "telegram_reviews"
DEFAULT_INTERVAL_SECONDS = 180
DEFAULT_MAX_HOURS = 5
REPORT_TEXT_EXTENSIONS = {".md", ".txt", ".log", ".json", ".csv"}
REPORT_MARKERS = [
    "execution report",
    "module analysis",
    "syntax errors",
    "codex job",
    "antigravity",
    "worker report",
    "hermes execution",
    "recommendations",
    "verification",
    "target component",
]


REVIEW_KEYWORDS = {
    "bug": [
        "error",
        "exception",
        "traceback",
        "failed",
        "fail",
        "bug",
        "lỗi",
        "loi",
        "không chạy",
        "khong chay",
        "crash",
    ],
    "delivery": [
        "done",
        "completed",
        "created",
        "generated",
        "report",
        "xong",
        "đã tạo",
        "da tao",
        "hoàn tất",
        "hoan tat",
    ],
    "architecture": [
        "workflow",
        "flow",
        "architecture",
        "kiến trúc",
        "kien truc",
        "nâng cấp",
        "nang cap",
        "refactor",
        "review",
    ],
}


def load_env():
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv()


def get_required_env():
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    bot_username = os.environ.get("TELEGRAM_BOT_USERNAME", "khoaha_bot")
    source_chat = os.environ.get("TELEGRAM_REVIEW_SOURCE_CHAT", "") or bot_username
    if not api_id or not api_hash:
        raise RuntimeError(
            "Missing TELEGRAM_API_ID or TELEGRAM_API_HASH. "
            "Run `python scripts/telegram_userbot.py login` after adding them to .env."
        )
    return int(api_id), api_hash, source_chat


def get_bot_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "") or getattr(config, "TELEGRAM_BOT_TOKEN", "")
    token = (token or "").strip()
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        return ""
    return token


def get_review_chat_id():
    raw = os.environ.get("TELEGRAM_REVIEW_CHAT_ID", "")
    if not raw:
        raw = getattr(config, "TELEGRAM_REVIEW_CHAT_ID", "")
    raw = str(raw).strip()
    if not raw:
        raise RuntimeError(
            "Missing TELEGRAM_REVIEW_CHAT_ID. "
            "Set it in .env so the watcher can send review proposals to the fixed chat."
        )
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid TELEGRAM_REVIEW_CHAT_ID: {raw}") from exc


def load_state():
    if not STATE_FILE.exists():
        return {"processed_message_ids": [], "processed_message_keys": [], "source_baselines": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"processed_message_ids": [], "processed_message_keys": [], "source_baselines": {}}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    processed = state.get("processed_message_ids", [])
    state["processed_message_ids"] = sorted(set(processed))[-2000:]
    processed_keys = state.get("processed_message_keys", [])
    state["processed_message_keys"] = sorted(set(processed_keys))[-2000:]
    state["source_baselines"] = state.get("source_baselines", {})
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def message_state_key(source_chat, message_id):
    return f"{source_chat}:{message_id}"


def is_message_allowed(message, direction):
    if direction == "all":
        return True
    if direction == "incoming":
        return not bool(message.out)
    if direction == "outgoing":
        return bool(message.out)
    return True


def message_text(message):
    return (getattr(message, "message", None) or getattr(message, "text", None) or "").strip()


def message_document_name(message):
    file_obj = getattr(message, "file", None)
    name = getattr(file_obj, "name", None) if file_obj else None
    if name:
        return Path(name).name
    ext = ""
    if file_obj:
        mime_type = (getattr(file_obj, "mime_type", "") or "").lower()
        if mime_type == "text/markdown":
            ext = ".md"
        elif mime_type == "text/plain":
            ext = ".txt"
        elif mime_type == "application/json":
            ext = ".json"
    return f"telegram_report_{message.id}{ext or '.bin'}"


async def load_message_payload(client, message):
    caption = message_text(message)
    file_obj = getattr(message, "file", None)
    if not file_obj and not getattr(message, "document", None):
        return {
            "text": caption,
            "source_kind": "text" if caption else "",
            "source_path": "",
            "source_name": "",
        }

    RAW_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    inbox_dir = RAW_REPORT_DIR / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_name = message_document_name(message)
    download_path = inbox_dir / f"{stamp}_msg_{message.id}_{source_name}"

    try:
        downloaded = await client.download_media(message, file=str(download_path))
    except Exception as exc:
        return {
            "text": "",
            "source_kind": "document",
            "source_path": "",
            "source_name": source_name,
            "download_error": str(exc),
        }

    source_path = Path(downloaded) if downloaded else download_path
    extracted_text = ""
    if source_path.exists():
        suffix = source_path.suffix.lower()
        try:
            if suffix in REPORT_TEXT_EXTENSIONS or source_path.stat().st_size <= 1_000_000:
                extracted_text = source_path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            extracted_text = ""

    if caption and extracted_text:
        extracted_text = f"{caption}\n\n{extracted_text}"
    elif caption:
        extracted_text = caption
    elif not extracted_text:
        extracted_text = f"Attached report file: {source_name}"

    return {
        "text": extracted_text,
        "source_kind": "document",
        "source_path": str(source_path),
        "source_name": source_name,
    }


def classify_report(text):
    lowered = text.lower()
    scores = {
        category: sum(1 for keyword in keywords if keyword in lowered)
        for category, keywords in REVIEW_KEYWORDS.items()
    }
    category, score = max(scores.items(), key=lambda item: item[1])
    if score == 0:
        category = "general"
    if "codex job" in lowered:
        category = "worker_job"
    return category


def is_report_payload(payload):
    text = (payload.get("text", "") or "").lower()
    source_name = (payload.get("source_name", "") or "").lower()
    source_path = (payload.get("source_path", "") or "").lower()
    if any(marker in text for marker in REPORT_MARKERS):
        return True
    if any(name in source_name for name in ("report", "analysis", "job_", "codex", "worker")):
        return True
    if any(name in source_path for name in ("report", "analysis", "job_", "codex", "worker")):
        return True
    return False


def extract_target_hint(text):
    file_match = re.search(r"(?:file|path|target)\s*[:：]\s*`?([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)`?", text, re.I)
    if file_match:
        return file_match.group(1).strip()
    path_match = re.search(r"`([^`]+\.(?:py|md|json|txt|js|ts|tsx|html|css))`", text, re.I)
    if path_match:
        return path_match.group(1).strip()
    return ""


def resolve_target_path(target_hint):
    if not target_hint:
        return None
    candidate = (REPO_ROOT / target_hint).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except Exception:
        return None
    return candidate if candidate.exists() else None


def analyze_target_context(target_hint):
    target_path = resolve_target_path(target_hint)
    if not target_path:
        return (
            "Target file not explicit. Treat this as a repo-level review and keep the next change request "
            "focused on the Hermes control center, review queue, and Telegram handoff."
        )

    try:
        content = target_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Target file `{target_hint}` exists, but could not be read cleanly: {exc}"

    lines = content.splitlines()
    line_count = len(lines)
    byte_size = target_path.stat().st_size

    if target_path.suffix.lower() == ".py":
        defs = []
        for line in lines:
            m = re.match(r"\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if m:
                defs.append(m.group(1))
        defs = defs[:8]
        if defs:
            return (
                f"Target file `{target_hint}` is a Python module ({line_count} lines, {byte_size} bytes). "
                f"Main entry points seen: {', '.join(defs)}. "
                "The next request should stay local to this module and its immediate call chain."
            )
        return (
            f"Target file `{target_hint}` is a Python module ({line_count} lines, {byte_size} bytes). "
            "No obvious top-level entry points were extracted, so keep the change request narrow and verify the call chain."
        )

    return (
        f"Target file `{target_hint}` exists ({line_count} lines, {byte_size} bytes). "
        "Use the report to derive a narrow request against the related module boundary, not a broad repo rewrite."
    )


def build_change_request(category, target_hint, report_text, system_notes):
    report_preview = report_text[:260].replace("\n", " ")
    target_text = target_hint or "the relevant Hermes module"
    focus = {
        "bug": "fix the failing branch, preserve behavior, and verify with the smallest meaningful check",
        "delivery": "confirm the artifact flow and make the output/report path explicit",
        "architecture": "keep the control-center flow intact and tighten the module boundary",
        "worker_job": "convert the incoming job into a precise implementation task with clear verify steps",
        "general": "turn the report into a narrow change request with a concrete verify plan",
    }.get(category, "turn the report into a narrow change request with a concrete verify plan")

    return (
        f"**New request:** update `{target_text}` based on this report.\n"
        f"**Why:** {focus}.\n"
        f"**Report signal:** `{report_preview}`\n"
        f"**System note:** {system_notes}\n"
        f"**Deliverable:** patch + brief diff summary + verify notes.\n"
        f"**Constraint:** do not touch unrelated watchers or widen scope."
    )


def build_review_markdown(message, bot_username, category, payload):
    text = payload.get("text", "")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg_time = getattr(message, "date", None)
    msg_time_text = msg_time.isoformat() if msg_time else ""
    target_hint = extract_target_hint(text)
    preview = text[:500].replace("\n", " ")
    system_notes = analyze_target_context(target_hint)
    generated_prompt = build_change_request(category, target_hint, text, system_notes)
    source_kind = payload.get("source_kind", "") or "text"
    source_path = payload.get("source_path", "")
    source_name = payload.get("source_name", "")

    return f"""# Telegram Review

- Created at: {created_at}
- Telegram chat: @{bot_username}
- Message id: {message.id}
- Message time: {msg_time_text}
- Category: {category}
- Source kind: {source_kind}
{f'- Source file: `{source_name}`' if source_name else '- Source file: not detected'}
{f'- Downloaded path: `{source_path}`' if source_path else '- Downloaded path: n/a'}
{f'- Target hint: `{target_hint}`' if target_hint else '- Target hint: not detected from message'}

## Tóm tắt nhanh

{preview or "(Message không có text rõ ràng.)"}

## Phân tích hệ thống

{system_notes}

## Yêu cầu mới đề xuất

{generated_prompt}
"""


def build_telegram_caption(message, category, proposal_path):
    preview = message_text(message)[:180].replace("\n", " ")
    parts = [
        "Hermes review ready.",
        f"msg={message.id}",
        f"category={category}",
        f"proposal={Path(proposal_path).name if proposal_path else 'n/a'}",
    ]
    if preview:
        parts.append(f"preview={preview}")
    return "\n".join(parts)


def build_prompt_suggestion(text, category, target_hint):
    target_text = target_hint or "phạm vi liên quan trong repo"
    base_actions = {
        "bug": [
            "trace file/log liên quan",
            "xác định nguyên nhân gốc",
            "sửa đúng chỗ nhỏ nhất",
            "chạy kiểm tra cú pháp/biên dịch phù hợp",
        ],
        "architecture": [
            "giữ đúng kiến trúc control center hiện tại",
            "thiết kế theo hướng manifest -> task queue -> worker -> artifact",
            "thêm review gate trước khi tự động học/sửa",
            "xác minh tác động chéo module",
        ],
        "delivery": [
            "đối chiếu report với artifact thực tế",
            "xác minh output đã sinh đủ",
            "nếu thiếu thì bổ sung bước tạo hoặc đồng bộ",
            "ghi rõ kết quả vào .md review report",
        ],
        "worker_job": [
            "xác định rõ scope job",
            "tách nhiệm vụ thành bước nhỏ để Antigravity thực thi",
            "ghi kết quả chạy thử và file đã sửa",
            "đính kèm report để Codex review tiếp",
        ],
        "general": [
            "đọc report và map sang mục tiêu kỹ thuật rõ ràng",
            "không tự sửa ngoài scope",
            "đề xuất bước tiếp theo ngắn gọn",
            "đưa ra tiêu chí verify",
        ],
    }.get(category, [
        "đọc report",
        "xác định phạm vi sửa đổi",
        "thực thi thay đổi cần thiết",
        "ghi báo cáo kết quả",
    ])

    bullet_lines = "\n".join(f"- {action}" for action in base_actions)
    preview = text[:280].replace("\n", " ")
    return (
        f"**Mục tiêu:** tạo thay đổi có kiểm soát cho `{target_text}`.\n"
        f"**Tín hiệu đầu vào:** `{preview}`\n"
        f"**Bước cần làm:**\n{bullet_lines}\n"
        f"**Ràng buộc:** không đụng watcher khác, chỉ sửa trong phạm vi liên quan, và luôn ghi kết quả ra .md."
    )


def write_raw_report(message, bot_username, category, payload):
    RAW_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RAW_REPORT_DIR / f"{stamp}_msg_{message.id}_{category}.json"
    payload = {
        "bot_username": bot_username,
        "message_id": message.id,
        "message_time": getattr(message, "date", None).isoformat() if getattr(message, "date", None) else "",
        "direction": "outgoing" if getattr(message, "out", False) else "incoming",
        "category": category,
        "text": payload.get("text", ""),
        "source_kind": payload.get("source_kind", ""),
        "source_path": payload.get("source_path", ""),
        "source_name": payload.get("source_name", ""),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def send_review_to_telegram(markdown_path, message, category):
    token = get_bot_token()
    if not token:
        return False
    chat_id = get_review_chat_id()

    try:
        import requests
    except Exception:
        return False

    caption = build_telegram_caption(message, category, markdown_path)
    try:
        with open(markdown_path, "rb") as doc:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                },
                files={
                    "document": (Path(markdown_path).name, doc, "text/markdown"),
                },
                timeout=20,
            )
        resp.raise_for_status()
        return True
    except Exception as exc:
        print(f"[telegram-review] Telegram sendDocument failed: {exc}", file=sys.stderr)
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"Review proposal created: {Path(markdown_path).name}\\ncategory={category}",
                },
                timeout=10,
            )
        except Exception:
            pass
        return False


def scan_project_features():
    features = []
    # Scan gui/
    gui_dir = REPO_ROOT / "gui"
    if gui_dir.exists():
        py_files = list(gui_dir.glob("*.py"))
        features.append(f"- **GUI Desktop ({len(py_files)} files):** Giao diện customtkinter điều khiển chính (app.py, components.py, theme.py).")
    
    # Scan core/
    core_dir = REPO_ROOT / "core"
    if core_dir.exists():
        core_files = list(core_dir.glob("*.py"))
        features.append(f"- **Core Engines ({len(core_files)} modules):** Điều phối tác vụ, quản lý project, lưu trữ tri thức.")
        
    # Scan tools/
    tools_dir = REPO_ROOT / "tools"
    if tools_dir.exists():
        tool_files = list(tools_dir.glob("*.py"))
        features.append(f"- **Integrations & Scrapers ({len(tool_files)} files):** Bộ tải video (video_downloader.py), phân tích video (video_analyser.py), custom parsers TMĐT.")
        
    # Scan scripts/
    scripts_dir = REPO_ROOT / "scripts"
    if scripts_dir.exists():
        script_files = list(scripts_dir.glob("*.py"))
        features.append(f"- **Scripts & Daemons ({len(script_files)} files):** Watcher Telegram, Userbot giao tiếp, agent control.")
        
    return "\n".join(features)


def run_autonomous_analysis(dry_run=False):
    analysis_file = REPO_ROOT / "reports" / "hermes_system_analysis.md"
    proposals_file = REPO_ROOT / "reports" / "proposed_upgrades.md"
    
    # 1. Sinh file phân tích hệ thống nếu chưa có
    if not analysis_file.exists():
        if dry_run:
            return False
        
        feature_text = scan_project_features()
        analysis_content = f"""# BÁO CÁO PHÂN TÍCH HỆ THỐNG (HERMES AGENT ARCHITECTURE & FEATURES)

- **Tác giả:** Antigravity Watcher
- **Mục tiêu:** Quét cấu trúc codebase tự động
- **Ngày cập nhật:** {datetime.now().strftime('%Y-%m-%d')}

## 🗺️ 1. Bản Đồ Kiến Trúc Hệ Thống (Architecture Map)
Hệ thống Hermes Agent được thiết kế theo mô hình **Control Center (Giao diện trung tâm) + Task Queue + Worker + Artifact Flow**.

## 🧩 2. Các Module Tính Năng Hiện Có
{feature_text}

## ⚠️ 3. Nợ Kỹ Thuật & Điểm Cần Cải Tiến (Technical Debt)
1. Sự Phình To Của `gui/app.py` (245KB - cần refactor).
2. Quản lý Khóa API trong `config.py` thay vì chỉ sử dụng `.env`.
3. Chưa tự động xóa video tạm sau khi chạy analyze_video.
"""
        analysis_file.parent.mkdir(parents=True, exist_ok=True)
        analysis_file.write_text(analysis_content, encoding="utf-8")
        print(f"[telegram-review] Đã tự động sinh file phân tích hệ thống tại: {analysis_file.name}")
        
    # 2. Sinh file đề xuất nâng cấp nếu chưa có
    if not proposals_file.exists():
        if dry_run:
            return False
        proposals_content = """# ĐỀ XUẤT NÂNG CẤP & TỐI ƯU HÓA HỆ THỐNG (PROPOSED UPGRADES)

- **Tác giả:** Antigravity Watcher
- **Trạng thái:** Chờ phê duyệt (Pending Approval)

---

## 🛠️ Đề xuất #002: Tái cấu trúc tách nhỏ `gui/app.py`
- Tách các tab chức năng ra thành lớp độc lập trong `gui/`.

## 🛡️ Đề xuất #003: Chuẩn hóa bảo mật cấu hình (.env)
- Nạp API keys trực tiếp qua dotenv.

## 🗑️ Đề xuất #004: Tự động xóa video tạm trong `JobWatcher`
- Thêm bước xóa file mp4 phôi trong source_video/ sau khi hoàn thành task.
"""
        proposals_file.write_text(proposals_content, encoding="utf-8")
        print(f"[telegram-review] Đã tự động sinh đề xuất nâng cấp tại: {proposals_file.name}")
        return True
        
    return False


async def review_once(limit, direction, dry_run=False, skip_history_on_first_run=False):
    load_env()
    api_id, api_hash, source_chat = get_required_env()
    session_path = REPO_ROOT / "userbot"
    client = TelegramClient(str(session_path), api_id, api_hash)
    store = LearningReviewStore()
    state = load_state()
    processed_ids = set(state.get("processed_message_ids", []))
    processed_keys = set(state.get("processed_message_keys", []))
    created = []

    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Userbot is not authorized. Run `python scripts/telegram_userbot.py login` first.")

        baselines = state.setdefault("source_baselines", {})
        if skip_history_on_first_run and source_chat not in baselines:
            latest = await client.get_messages(source_chat, limit=1)
            latest_id = latest[0].id if latest else 0
            baselines[source_chat] = latest_id
            state["last_run_at"] = datetime.now().isoformat()
            if not dry_run:
                save_state(state)
            print(
                f"[telegram-review] Baseline set for {source_chat} at message {latest_id}. "
                "Existing history was skipped; future messages will be reviewed."
            )
            return []

        messages = []
        async for message in client.iter_messages(source_chat, limit=limit):
            baseline_id = int(state.get("source_baselines", {}).get(source_chat, 0) or 0)
            if baseline_id and message.id <= baseline_id:
                continue
            state_key = message_state_key(source_chat, message.id)
            if state_key in processed_keys:
                continue
            if not is_message_allowed(message, direction):
                continue
            payload = await load_message_payload(client, message)
            msg_txt = payload.get("text", "").strip()
            if not msg_txt:
                processed_ids.add(message.id)
                processed_keys.add(state_key)
                continue
            if not is_report_payload(payload):
                processed_ids.add(message.id)
                processed_keys.add(state_key)
                continue

            # Tránh vòng lặp vô hạn: Bỏ qua tin nhắn thông báo tự động của watcher/bot
            txt_lower = msg_txt.lower()
            if (
                "review proposal ready" in txt_lower
                or "proposed upgrades ready" in txt_lower
                or "hermes review ready" in txt_lower
            ):
                processed_ids.add(message.id)
                processed_keys.add(state_key)
                continue
            messages.append((message, payload))

        for message, payload in reversed(messages):
            category = classify_report(payload.get("text", ""))
            markdown = build_review_markdown(message, source_chat, category, payload)
            raw_path = None if dry_run else write_raw_report(message, source_chat, category, payload)
            proposal_path = None
            sent_to_telegram = False
            if not dry_run:
                proposal_path = store.create_proposal(
                    title=f"telegram-msg-{message.id}-{category}",
                    body=markdown,
                    prefix="telegram-review",
                )
                sent_to_telegram = send_review_to_telegram(
                    proposal_path,
                    message,
                    category,
                )
            processed_ids.add(message.id)
            processed_keys.add(message_state_key(source_chat, message.id))
            created.append(
                {
                    "message_id": message.id,
                    "category": category,
                    "proposal_path": str(proposal_path) if proposal_path else "",
                    "raw_path": str(raw_path) if raw_path else "",
                    "sent_to_telegram": sent_to_telegram,
                    "source_kind": payload.get("source_kind", ""),
                    "source_path": payload.get("source_path", ""),
                }
            )

        if not dry_run:
            state["processed_message_ids"] = list(processed_ids)
            state["processed_message_keys"] = list(processed_keys)
            state["last_run_at"] = datetime.now().isoformat()
            save_state(state)
    finally:
        await client.disconnect()

    return created


class TeeStream:
    def __init__(self, file_path, original_stream):
        self.file = open(file_path, "a", encoding="utf-8", buffering=1)
        self.original_stream = None if os.environ.get("TELEGRAM_REVIEW_SUPPRESS_CONSOLE") == "1" else original_stream
    def write(self, data):
        self.file.write(data)
        if self.original_stream is None:
            return
        try:
            self.original_stream.write(data)
        except UnicodeEncodeError:
            safe_data = data.encode(self.original_stream.encoding or "utf-8", errors="replace").decode(
                self.original_stream.encoding or "utf-8",
                errors="replace",
            )
            self.original_stream.write(safe_data)
    def flush(self):
        self.file.flush()
        if self.original_stream is not None:
            self.original_stream.flush()

async def run_loop(
    interval,
    limit,
    direction,
    dry_run=False,
    skip_history_on_first_run=False,
):
    started_at = datetime.now()
    deadline = started_at.timestamp() + (DEFAULT_MAX_HOURS * 3600)
    while True:
        try:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏳ [telegram-review] Đang quét tin nhắn mới từ Telegram...")
            created = await review_once(
                limit=limit,
                direction=direction,
                dry_run=dry_run,
                skip_history_on_first_run=skip_history_on_first_run,
            )
            if created:
                action = "Would create" if dry_run else "Created"
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [telegram-review] {action} {len(created)} proposal(s):")
                for item in created:
                    sent_flag = " sent" if item.get("sent_to_telegram") else ""
                    source_flag = f" source={item.get('source_kind')}" if item.get("source_kind") else ""
                    print(f"  - msg {item['message_id']} [{item['category']}] {item['proposal_path']}{sent_flag}{source_flag}")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [telegram-review] Không phát hiện tin nhắn mới để review.")
        except Exception as exc:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [telegram-review] ERROR: {exc}", file=sys.stderr)
        remaining = deadline - datetime.now().timestamp()
        if remaining <= 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [telegram-review] Hết thời gian chạy tối đa (5h). Đang dừng watcher.")
            break
        await asyncio.sleep(min(interval, max(1, int(remaining))))


def parse_args():
    parser = argparse.ArgumentParser(description="Read Telegram bot messages and create Hermes review proposals.")
    parser.add_argument("--once", action="store_true", help="Run one sync/review pass and exit.")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS, help="Polling interval in seconds.")
    parser.add_argument("--max-hours", type=float, default=DEFAULT_MAX_HOURS, help="Stop after this many hours.")
    parser.add_argument("--fallback-seconds", type=int, default=DEFAULT_FALLBACK_SECONDS, help="Run a deeper fallback scan every N seconds when the main loop finds nothing.")
    parser.add_argument("--limit", type=int, default=20, help="How many recent Telegram messages to scan per pass.")
    parser.add_argument(
        "--direction",
        choices=["incoming", "outgoing", "all"],
        default=os.environ.get("TELEGRAM_REVIEW_DIRECTION", "all"),
        help="Which chat messages to review. Default: all messages.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Read messages without writing proposals/state.")
    parser.add_argument(
        "--skip-history-on-first-run",
        action="store_true",
        help="When a source chat has no baseline, mark current latest message as baseline and review only future messages.",
    )
    parser.add_argument("--log-file", default="", help="Append stdout logs to this file.")
    parser.add_argument("--error-log-file", default="", help="Append stderr logs to this file.")
    return parser.parse_args()


def redirect_logs(args):
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = TeeStream(log_path, sys.stdout)
    if args.error_log_file:
        error_path = Path(args.error_log_file)
        error_path.parent.mkdir(parents=True, exist_ok=True)
        sys.stderr = TeeStream(error_path, sys.stderr)


def main():
    args = parse_args()
    redirect_logs(args)
    global DEFAULT_MAX_HOURS
    DEFAULT_MAX_HOURS = args.max_hours
    if args.once:
        created = asyncio.run(
            review_once(
                args.limit,
                args.direction,
                args.dry_run,
                args.skip_history_on_first_run,
                False,
            )
        )
        if not created:
            print("[telegram-review] No new Telegram messages to review.")
        else:
            action = "Would create" if args.dry_run else "Created"
            print(f"[telegram-review] {action} {len(created)} proposal(s).")
            for item in created:
                sent_flag = " sent" if item.get("sent_to_telegram") else ""
                source_flag = f" source={item.get('source_kind')}" if item.get("source_kind") else ""
                print(f"  - msg {item['message_id']} [{item['category']}] {item['proposal_path']}{sent_flag}{source_flag}")
        return
    asyncio.run(
        run_loop_with_fallback(
            args.interval,
            args.limit,
            args.direction,
            args.dry_run,
            args.skip_history_on_first_run,
            args.fallback_seconds,
        )
    )


if __name__ == "__main__":
    main()
