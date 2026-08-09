# Telegram HTML Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render every Hermes Telegram text response as safe, readable Telegram HTML.

**Architecture:** Keep message content as plain text or Markdown. Add small rendering and delivery helpers in `telegram_bot.py`; the knowledge listing produces escaped application-owned HTML directly. Existing handlers call the helpers rather than selecting Markdown independently.

**Tech Stack:** Python, python-telegram-bot, standard-library `html` and `re`.

## Global Constraints

- Do not pass raw model or source HTML to Telegram.
- Escape knowledge fields before embedding them in generated HTML.
- Preserve the current local job, approval, and Drive behavior.
- Do not add a rendering dependency for this small personal bot.

---

### Task 1: Specify and test safe rendering

**Files:**
- Modify: `scripts/test_telegram_learning_delivery.py`

**Interfaces:**
- Produces tests for `render_telegram_html(text)`, `reply_html(...)`, and HTML knowledge listings.

- [ ] Add a test that verifies Markdown emphasis, code, blockquote, and a valid URL become Telegram HTML.
- [ ] Add a test that verifies source HTML is escaped rather than executed as formatting.
- [ ] Add a test that verifies a reply uses `parse_mode="HTML"` and has a plain fallback.
- [ ] Run: `python scripts/test_telegram_learning_delivery.py`.
- [ ] Confirm it fails because the renderer and helpers do not yet exist.

### Task 2: Add the renderer and delivery helpers

**Files:**
- Modify: `telegram_bot.py`

**Interfaces:**
- `render_telegram_html(text: str) -> str`
- `reply_html(message, text: str, *, already_html: bool = False, **kwargs) -> None`
- `send_html_message(bot, chat_id, text: str, *, already_html: bool = False, **kwargs) -> None`

- [ ] Escape raw input before applying controlled Markdown substitutions.
- [ ] Split raw text at a conservative size before rendering each Telegram message.
- [ ] Send HTML first and plain text on Telegram formatting failure.
- [ ] Run: `python scripts/test_telegram_learning_delivery.py`.

### Task 3: Route existing output through the helpers

**Files:**
- Modify: `telegram_bot.py`
- Modify: `scripts/test_telegram_learning_delivery.py`

**Interfaces:**
- All regular replies, outbox results, and callback edits use HTML parse mode.

- [ ] Replace direct text send paths with the HTML helpers without changing command semantics.
- [ ] Make `format_knowledge_listing` emit the requested compact HTML layout, with escaped title and summary fields.
- [ ] Keep `/approve`, `/reject`, and `/approve_all` visible as `<code>` commands in pending listings.
- [ ] Add delivery assertions for HTML mode and catalogue formatting.
- [ ] Run focused delivery tests and the existing test suite.

### Task 4: Runtime verification

**Files:**
- No source changes expected.

- [ ] Run: `python scripts/test_telegram_learning_delivery.py`.
- [ ] Run: `python -m compileall telegram_bot.py`.
- [ ] Restart only the Telegram bot and inspect its startup log for successful polling.
- [ ] Send `/knowledge approved` to verify Telegram renders bold headings, separators, and coloured emoji markers.
