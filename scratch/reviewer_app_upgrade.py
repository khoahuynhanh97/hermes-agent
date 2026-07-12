import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from telethon import TelegramClient


UPGRADE_ROOT = Path("C:/Work/Code/Upgrade_chat_bot").resolve()
APP_ROOT = UPGRADE_ROOT / "Reviewer_app"
HERMES_ROOT = Path("C:/Work/Code/Hermes_download/hermes-agent").resolve()
REPORTS_DIR = APP_ROOT / "reports"
INBOX_DIR = REPORTS_DIR / "telegram_inbox"
REVIEWS_DIR = REPORTS_DIR / "reviews"
STATE_FILE = REPORTS_DIR / "reviewer_state.json"
DEFAULT_INTERVAL_SECONDS = 180
DEFAULT_FALLBACK_SECONDS = 300
DEFAULT_MAX_HOURS = 5
REPORT_MARKERS = (
    "execution report",
    "module analysis",
    "syntax errors",
    "codex job",
    "worker report",
    "verification",
    "target component",
    "telegram_job_",
    "job_",
)

sys.path.append(str(HERMES_ROOT))

try:
    from core.ai_router import chat as ai_chat
except ImportError as exc:
    print(f"[reviewer] Error importing ai_router: {exc}")
    sys.exit(1)


def load_env():
    env_path = UPGRADE_ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv(dotenv_path=HERMES_ROOT / ".env")


def ensure_dirs():
    for path in (REPORTS_DIR, INBOX_DIR, REVIEWS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def get_required_env():
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    review_chat_id = os.getenv("TELEGRAM_REVIEW_CHAT_ID")
    source_chat = os.getenv("TELEGRAM_REVIEW_SOURCE_CHAT") or os.getenv("TELEGRAM_BOT_USERNAME", "khoaha_bot")
    if not api_id or not api_hash:
        raise RuntimeError("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env")
    if not bot_token or not review_chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_REVIEW_CHAT_ID in .env")
    return int(api_id), api_hash, bot_token.strip(), int(str(review_chat_id).strip()), source_chat.strip()


def load_state():
    if not STATE_FILE.exists():
        return {"processed_message_keys": [], "source_baselines": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"processed_message_keys": [], "source_baselines": {}}


def save_state(state):
    state["processed_message_keys"] = sorted(set(state.get("processed_message_keys", [])))[-2000:]
    state["source_baselines"] = state.get("source_baselines", {})
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def message_state_key(source_chat, message_id):
    return f"{source_chat}:{message_id}"


def message_text(message):
    return (getattr(message, "message", None) or getattr(message, "text", None) or "").strip()


def message_document_name(message):
    file_obj = getattr(message, "file", None)
    name = getattr(file_obj, "name", None) if file_obj else None
    if name:
        return Path(name).name
    return f"telegram_report_{message.id}.bin"


async def load_message_payload(client, message):
    caption = message_text(message)
    file_obj = getattr(message, "file", None)
    if not file_obj and not getattr(message, "document", None):
        return {"text": caption, "source_kind": "text" if caption else "", "source_path": "", "source_name": ""}

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_name = message_document_name(message)
    download_path = INBOX_DIR / f"{stamp}_msg_{message.id}_{source_name}"
    downloaded = await client.download_media(message, file=str(download_path))
    source_path = Path(downloaded) if downloaded else download_path
    extracted_text = ""
    if source_path.exists():
        try:
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


def is_report_payload(payload, relaxed=False):
    text = (payload.get("text", "") or "").lower()
    source_name = (payload.get("source_name", "") or "").lower()
    source_kind = (payload.get("source_kind", "") or "").lower()
    if any(marker in text for marker in REPORT_MARKERS):
        return True
    if any(name in source_name for name in ("report", "analysis", "job_", "worker", "codex")):
        return True
    if relaxed and source_kind == "document":
        return True
    return False


def classify_report(text):
    lowered = text.lower()
    if "codex job" in lowered or "job_" in lowered:
        return "worker_job"
    if any(word in lowered for word in ("error", "exception", "failed", "traceback", "bug")):
        return "bug"
    if any(word in lowered for word in ("architecture", "workflow", "refactor", "nang cap")):
        return "architecture"
    if any(word in lowered for word in ("done", "completed", "report", "verification")):
        return "delivery"
    return "general"


def build_ai_review(report_text, category):
    system_prompt = (
        "You are a senior technical reviewer for a local worker automation loop. "
        "Read the worker report and produce a concise markdown review in Vietnamese with these sections only: "
        "'## Nhan dinh', '## Van de / Rui ro', '## Prompt tiep theo'. "
        "If the report shows the task is already complete, say so clearly and do not ask to redo it. "
        "The next prompt must be actionable for a local coding worker."
    )
    prompt = (
        f"Category: {category}\n\n"
        f"Worker report:\n{report_text}\n\n"
        "Write the review now."
    )
    try:
        return ai_chat(prompt, system=system_prompt, task_type="analysis").strip()
    except Exception as exc:
        return (
            "## Nhan dinh\n"
            "Khong the goi AI reviewer, nen tam thoi fallback sang review co ban.\n\n"
            "## Van de / Rui ro\n"
            f"- Loi khi goi AI reviewer: {exc}\n\n"
            "## Prompt tiep theo\n"
            "- Doc lai worker report, xac dinh scope thay doi, va gui lai mot prompt sua doi ngan gon cho worker local."
        )


def write_review_file(source_chat, message, category, payload, review_body):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REVIEWS_DIR / f"{stamp}_review_msg_{message.id}_{category}.md"
    content = (
        f"# Reviewer App Result\n\n"
        f"- Source chat: @{source_chat}\n"
        f"- Message id: {message.id}\n"
        f"- Category: {category}\n"
        f"- Source kind: {payload.get('source_kind', 'text')}\n"
        f"- Source file: {payload.get('source_name', 'n/a')}\n"
        f"- Downloaded path: {payload.get('source_path', 'n/a')}\n"
        f"- Reviewed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{review_body}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def send_review_document(bot_token, chat_id, review_path, message_id, category):
    caption = f"Reviewer_app ready. msg={message_id} category={category} file={review_path.name}"
    with review_path.open("rb") as doc:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (review_path.name, doc, "text/markdown")},
            timeout=30,
        )
    resp.raise_for_status()


async def review_once(limit, direction, skip_history_on_first_run=False, relaxed_report_check=False):
    ensure_dirs()
    load_env()
    api_id, api_hash, bot_token, review_chat_id, source_chat = get_required_env()
    session_path = HERMES_ROOT / "userbot"
    client = TelegramClient(str(session_path), api_id, api_hash)
    state = load_state()
    processed_keys = set(state.get("processed_message_keys", []))
    created = []

    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Reviewer app userbot is not authorized.")

        baselines = state.setdefault("source_baselines", {})
        if skip_history_on_first_run and source_chat not in baselines:
            latest = await client.get_messages(source_chat, limit=1)
            baselines[source_chat] = latest[0].id if latest else 0
            state["last_run_at"] = datetime.now().isoformat()
            save_state(state)
            print(f"[reviewer] Baseline set for {source_chat} at message {baselines[source_chat]}")
            return []

        messages = []
        async for message in client.iter_messages(source_chat, limit=limit):
            baseline_id = int(state.get("source_baselines", {}).get(source_chat, 0) or 0)
            if baseline_id and message.id <= baseline_id:
                continue
            state_key = message_state_key(source_chat, message.id)
            if state_key in processed_keys:
                continue
            if direction == "incoming" and bool(message.out):
                continue
            if direction == "outgoing" and not bool(message.out):
                continue
            payload = await load_message_payload(client, message)
            if not payload.get("text", "").strip():
                processed_keys.add(state_key)
                continue
            if not is_report_payload(payload, relaxed=relaxed_report_check):
                processed_keys.add(state_key)
                continue
            lowered = payload["text"].lower()
            if "reviewer_app ready" in lowered or "reviewer app result" in lowered:
                processed_keys.add(state_key)
                continue
            messages.append((message, payload))

        for message, payload in reversed(messages):
            category = classify_report(payload["text"])
            review_body = build_ai_review(payload["text"], category)
            review_path = write_review_file(source_chat, message, category, payload, review_body)
            send_review_document(bot_token, review_chat_id, review_path, message.id, category)
            processed_keys.add(message_state_key(source_chat, message.id))
            created.append({"message_id": message.id, "category": category, "review_path": str(review_path)})

        state["processed_message_keys"] = list(processed_keys)
        state["last_run_at"] = datetime.now().isoformat()
        save_state(state)
    finally:
        await client.disconnect()

    return created


async def main():
    ensure_dirs()
    load_env()
    _, _, _, _, source_chat = get_required_env()
    started_at = datetime.now()
    deadline = started_at.timestamp() + (DEFAULT_MAX_HOURS * 3600)
    last_fallback_at = 0.0
    print(f"[reviewer] Reviewer_app started. Source chat=@{source_chat}, interval=180s, fallback=300s, max_hours=5")
    while True:
        created = await review_once(limit=20, direction="all", skip_history_on_first_run=True)
        if created:
            print(f"[reviewer] Created {len(created)} review file(s).")
        else:
            print("[reviewer] Main scan found no new report.")
            now_ts = datetime.now().timestamp()
            if now_ts - last_fallback_at >= DEFAULT_FALLBACK_SECONDS:
                recovered = await review_once(limit=50, direction="all", skip_history_on_first_run=False, relaxed_report_check=True)
                last_fallback_at = now_ts
                if recovered:
                    print(f"[reviewer] Fallback recovered {len(recovered)} report(s).")
                else:
                    print("[reviewer] Fallback found no new report.")
        remaining = deadline - datetime.now().timestamp()
        if remaining <= 0:
            print("[reviewer] Max runtime reached (5h). Stopping reviewer_app.")
            break
        await asyncio.sleep(min(DEFAULT_INTERVAL_SECONDS, max(1, int(remaining))))


if __name__ == "__main__":
    asyncio.run(main())
