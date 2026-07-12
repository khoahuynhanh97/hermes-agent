import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv


UPGRADE_ROOT = Path("C:/Work/Code/Upgrade_chat_bot").resolve()
APP_ROOT = UPGRADE_ROOT / "Reviewer_app"
HERMES_AGENT_ROOT = Path("C:/Work/Code/Hermes_download/hermes-agent").resolve()
REPORTS_DIR = APP_ROOT / "reports"
INBOX_DIR = REPORTS_DIR / "telegram_inbox"
REVIEWS_DIR = REPORTS_DIR / "reviews"
STATE_FILE = REPORTS_DIR / "reviewer_state.json"
DEFAULT_INTERVAL_SECONDS = 180
DEFAULT_MAX_HOURS = 5
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_IDLE_NO_REPORT_SCANS = 3

SELF_MESSAGE_MARKERS = (
    "reviewer_app ready",
    "reviewer app result",
    "codex review wakeup",
    "reviewer app wakeup",
    "prompt cho codex reviewer",
)
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
    "report",
    "analysis",
)


def load_env():
    env_path = UPGRADE_ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()


def ensure_dirs():
    for path in (REPORTS_DIR, INBOX_DIR, REVIEWS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def get_required_env():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    review_chat_id = os.getenv("TELEGRAM_REVIEW_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in .env")
    if not review_chat_id:
        raise RuntimeError("Missing TELEGRAM_REVIEW_CHAT_ID or TELEGRAM_CHAT_ID in .env")
    return bot_token.strip(), str(review_chat_id).strip()


def get_idle_config():
    raw_threshold = (
        os.getenv("REVIEWER_IDLE_NO_REPORT_SCANS")
        or os.getenv("REVIEWER_IDLE_NO_MESSAGE_SCANS")
        or str(DEFAULT_IDLE_NO_REPORT_SCANS)
    ).strip()
    try:
        threshold = int(raw_threshold)
    except ValueError:
        threshold = DEFAULT_IDLE_NO_REPORT_SCANS
    target = os.getenv("REVIEWER_IDLE_AUDIT_TARGET", str(HERMES_AGENT_ROOT)).strip()
    return max(0, threshold), target


def load_state():
    if not STATE_FILE.exists():
        return {"processed_message_keys": [], "last_update_id": 0}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    state.setdefault("processed_message_keys", [])
    state.setdefault("last_update_id", 0)
    state.setdefault("no_report_scan_count", state.get("no_message_scan_count", 0))
    state.setdefault("idle_audit_pending", False)
    return state


def save_state(state):
    state["processed_message_keys"] = sorted(set(state.get("processed_message_keys", [])))[-2000:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def bot_api_url(bot_token, method):
    return f"https://api.telegram.org/bot{bot_token}/{method}"


def bot_file_url(bot_token, file_path):
    return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"


def telegram_get(bot_token, method, params=None):
    response = requests.get(
        bot_api_url(bot_token, method),
        params=params or {},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API {method} failed: {data}")
    return data.get("result")


def telegram_post(bot_token, method, data=None, files=None):
    response = requests.post(
        bot_api_url(bot_token, method),
        data=data or {},
        files=files,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API {method} failed: {payload}")
    return payload.get("result")


def get_updates(bot_token, offset):
    params = {
        "timeout": 0,
        "limit": 100,
        "allowed_updates": json.dumps(["message", "channel_post"]),
    }
    if offset:
        params["offset"] = offset
    return telegram_get(bot_token, "getUpdates", params=params) or []


def update_message(update):
    return update.get("message") or update.get("channel_post")


def message_chat_id(message):
    chat = message.get("chat") or {}
    return str(chat.get("id", "")).strip()


def message_state_key(message):
    return f"{message_chat_id(message)}:{message.get('message_id')}"


def message_text(message):
    return (message.get("text") or message.get("caption") or "").strip()


def document_name(document, message_id):
    name = document.get("file_name") if document else None
    if name:
        return Path(name).name
    return f"telegram_report_{message_id}.bin"


def download_document(bot_token, message, document):
    message_id = message.get("message_id")
    source_name = document_name(document, message_id)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_path = INBOX_DIR / f"{stamp}_msg_{message_id}_{source_name}"

    file_info = telegram_get(bot_token, "getFile", params={"file_id": document["file_id"]})
    file_path = file_info.get("file_path")
    if not file_path:
        raise RuntimeError(f"Telegram getFile returned no file_path for message {message_id}")

    response = requests.get(bot_file_url(bot_token, file_path), timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    target_path.write_bytes(response.content)
    return target_path, source_name


def load_message_payload(bot_token, message):
    caption = message_text(message)
    document = message.get("document")
    if not document:
        return {
            "text": caption,
            "source_kind": "text" if caption else "",
            "source_path": "",
            "source_name": "",
        }

    source_path, source_name = download_document(bot_token, message, document)
    extracted_text = ""
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


def is_report_payload(payload):
    text = (payload.get("text", "") or "").lower()
    source_name = (payload.get("source_name", "") or "").lower()
    if any(marker in text for marker in REPORT_MARKERS):
        return True
    if any(name in source_name for name in ("report", "analysis", "job_", "worker", "codex")):
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


def build_codex_wakeup_prompt(chat_id, message, category, payload):
    report_text = payload.get("text", "").strip()
    source_file = payload.get("source_name", "n/a") or "n/a"
    downloaded_path = payload.get("source_path", "n/a") or "n/a"
    return (
        "# Codex Review Wakeup\n\n"
        "This is a wakeup prompt for Codex reviewer. Reviewer_app only forwards the report and the request; "
        "it does not review by itself and does not edit code.\n\n"
        "## Context\n\n"
        f"- Source chat id: {chat_id}\n"
        f"- Message id: {message.get('message_id')}\n"
        f"- Category: {category}\n"
        f"- Source kind: {payload.get('source_kind', 'text')}\n"
        f"- Source file: {source_file}\n"
        f"- Downloaded path: {downloaded_path}\n"
        f"- Created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "## Codex Role\n\n"
        "You are Codex acting as a senior technical reviewer and project architect. Read the worker report below, "
        "review it technically, identify risks, and create the next actionable prompt for the local worker.\n\n"
        "## Required Work\n\n"
        "1. Briefly summarize what the worker did and the current result.\n"
        "2. If the report proves the task is complete, clearly say it is complete and do not ask the worker to redo it.\n"
        "3. If there are remaining bugs, risks, or missing verification steps, state their priority.\n"
        "4. Write a concrete next prompt for the local worker, including files/modules to inspect, work to perform, and verification steps.\n"
        "5. Send the review/prompt back to the Telegram chat so the worker can continue the loop.\n\n"
        "## Expected Output\n\n"
        "Write in English with these sections:\n\n"
        "- `## Assessment`\n"
        "- `## Issues / Risks`\n"
        "- `## Worker Prompt`\n\n"
        "## Worker Report\n\n"
        f"{report_text}\n"
    )


def build_idle_audit_wakeup_prompt(chat_id, audit_target, no_report_scan_count):
    return (
        "# Codex Idle Audit Wakeup\n\n"
        "Reviewer_app has checked Telegram several times in a row without finding a valid new report. "
        "This prompt wakes Codex up to proactively review the source code and produce a fix/upgrade prompt for the worker.\n\n"
        "## Context\n\n"
        f"- Chat id: {chat_id}\n"
        f"- Consecutive scans without report: {no_report_scan_count}\n"
        f"- Audit target: {audit_target}\n"
        f"- Created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "## Codex Role\n\n"
        "You are Codex acting as a senior technical reviewer and project architect. Review the source code at the audit target, "
        "prioritizing modules related to the Telegram worker/reviewer loop, workflow automation, state/log handling, "
        "and recent reports if available. Then propose a valuable fix or upgrade prompt for the local worker.\n\n"
        "## Required Work\n\n"
        "1. Inspect the current source code and workflow for real bugs or operational risks.\n"
        "2. If the system looks healthy, propose a small useful upgrade instead of creating busywork.\n"
        "3. If you find a bug or risk, state the affected file/module and priority.\n"
        "4. Write a clear local-worker prompt with scope, tasks, and verification steps.\n"
        "5. Send the result to the Telegram chat so the worker can continue.\n\n"
        "## Expected Output\n\n"
        "Write in English with these sections:\n\n"
        "- `## Assessment`\n"
        "- `## Fix / Upgrade Proposal`\n"
        "- `## Worker Prompt`\n"
    )


def write_wakeup_file(chat_id, message, category, payload, wakeup_body):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    message_id = message.get("message_id")
    path = REVIEWS_DIR / f"{stamp}_codex_wakeup_msg_{message_id}_{category}.md"
    content = (
        "# Reviewer App Wakeup Result\n\n"
        f"- Source chat id: {chat_id}\n"
        f"- Message id: {message_id}\n"
        f"- Category: {category}\n"
        f"- Source kind: {payload.get('source_kind', 'text')}\n"
        f"- Source file: {payload.get('source_name', 'n/a')}\n"
        f"- Downloaded path: {payload.get('source_path', 'n/a')}\n"
        f"- Wakeup prompt created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{wakeup_body}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def write_idle_wakeup_file(chat_id, audit_target, no_report_scan_count, wakeup_body):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REVIEWS_DIR / f"{stamp}_codex_idle_audit_no_report_{no_report_scan_count}.md"
    content = (
        "# Reviewer App Idle Audit Wakeup\n\n"
        f"- Source chat id: {chat_id}\n"
        f"- Consecutive scans without report: {no_report_scan_count}\n"
        f"- Audit target: {audit_target}\n"
        f"- Wakeup prompt created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{wakeup_body}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def send_wakeup_document(bot_token, chat_id, wakeup_path, message_id, category):
    if message_id is None:
        caption = f"Codex idle audit wakeup. category={category} file={wakeup_path.name}"
    else:
        caption = f"Codex review wakeup. msg={message_id} category={category} file={wakeup_path.name}"
    with wakeup_path.open("rb") as doc:
        telegram_post(
            bot_token,
            "sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (wakeup_path.name, doc, "text/markdown")},
        )


def review_once():
    ensure_dirs()
    load_env()
    bot_token, review_chat_id = get_required_env()
    idle_threshold, audit_target = get_idle_config()
    state = load_state()
    processed_keys = set(state.get("processed_message_keys", []))
    last_update_id = int(state.get("last_update_id", 0) or 0)
    created = []

    updates = get_updates(bot_token, last_update_id + 1 if last_update_id else None)
    for update in updates:
        update_id = int(update.get("update_id", 0) or 0)
        if update_id:
            state["last_update_id"] = max(int(state.get("last_update_id", 0) or 0), update_id)

        message = update_message(update)
        if not message:
            continue
        chat_id = message_chat_id(message)
        if chat_id != str(review_chat_id):
            continue

        state_key = message_state_key(message)
        if state_key in processed_keys:
            continue

        payload = load_message_payload(bot_token, message)
        if not payload.get("text", "").strip():
            processed_keys.add(state_key)
            continue

        lowered = payload["text"].lower()
        if any(marker in lowered for marker in SELF_MESSAGE_MARKERS):
            processed_keys.add(state_key)
            continue

        if not is_report_payload(payload):
            processed_keys.add(state_key)
            continue

        category = classify_report(payload["text"])
        wakeup_body = build_codex_wakeup_prompt(chat_id, message, category, payload)
        wakeup_path = write_wakeup_file(chat_id, message, category, payload, wakeup_body)
        send_wakeup_document(bot_token, review_chat_id, wakeup_path, message.get("message_id"), category)
        processed_keys.add(state_key)
        state["idle_audit_pending"] = False
        created.append({"message_id": message.get("message_id"), "category": category, "wakeup_path": str(wakeup_path)})

    if not created:
        no_report_scan_count = int(state.get("no_report_scan_count", 0) or 0) + 1
        state["no_report_scan_count"] = no_report_scan_count
        if state.get("idle_audit_pending"):
            state["no_report_scan_count"] = min(no_report_scan_count, idle_threshold or no_report_scan_count)
        elif idle_threshold and no_report_scan_count >= idle_threshold:
            wakeup_body = build_idle_audit_wakeup_prompt(review_chat_id, audit_target, no_report_scan_count)
            wakeup_path = write_idle_wakeup_file(review_chat_id, audit_target, no_report_scan_count, wakeup_body)
            send_wakeup_document(bot_token, review_chat_id, wakeup_path, None, "idle_audit")
            state["no_report_scan_count"] = 0
            state["idle_audit_pending"] = True
            state["last_idle_audit_at"] = datetime.now().isoformat()
            created.append({"message_id": None, "category": "idle_audit", "wakeup_path": str(wakeup_path)})
    else:
        state["no_report_scan_count"] = 0

    state["processed_message_keys"] = list(processed_keys)
    state["last_run_at"] = datetime.now().isoformat()
    save_state(state)
    return created


def main():
    ensure_dirs()
    load_env()
    _, review_chat_id = get_required_env()
    idle_threshold, _ = get_idle_config()
    deadline = time.time() + (DEFAULT_MAX_HOURS * 3600)
    print(
        f"[reviewer] Reviewer_app started. chat_id={review_chat_id}, interval=180s, "
        f"max_hours=5, idle_no_report_scans={idle_threshold}",
        flush=True,
    )

    while True:
        try:
            created = review_once()
            if created:
                print(f"[reviewer] Created {len(created)} Codex wakeup file(s).", flush=True)
            else:
                state = load_state()
                count = int(state.get("no_report_scan_count", 0) or 0)
                print(f"[reviewer] Scan found no new report. no_report_scan_count={count}/{idle_threshold}", flush=True)
        except Exception as exc:
            print(f"[reviewer] ERROR: {exc}", flush=True)

        remaining = deadline - time.time()
        if remaining <= 0:
            print("[reviewer] Max runtime reached (5h). Stopping reviewer_app.", flush=True)
            break
        time.sleep(min(DEFAULT_INTERVAL_SECONDS, max(1, int(remaining))))


if __name__ == "__main__":
    main()
