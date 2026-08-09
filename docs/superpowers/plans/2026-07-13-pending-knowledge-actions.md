# Pending Knowledge Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/knowledge pending` scannable and let its owner approve or reject lessons by displayed number, including a safe approve-all command.

**Architecture:** Keep Telegram text output as Markdown because Telegram does not offer per-title text colours. `format_knowledge_listing` renders a blue/green marker and bold title; command handlers resolve a positive ordinal against the caller's current pending ordering, while preserving ID-based commands.

**Tech Stack:** Python, python-telegram-bot, existing local JSON knowledge store, script-based regression tests.

## Global Constraints

- Do not change approved/rejected listing behavior beyond harmless Markdown title formatting.
- `/approve_all` acts only on the caller's own pending entries.
- Preserve `/approve <knowledge_id>` and `/reject <knowledge_id>`.
- Do not add `/reject_all`.

---

### Task 1: Pending Listing Contract

**Files:**
- Modify: `scripts/test_telegram_learning_delivery.py`
- Modify: `telegram_bot.py`

- [ ] Add a failing test that asserts numbered pending entries render `🟦`/`🟩`, bold titles, per-item commands, and `/approve_all`.
- [ ] Run the test and confirm the current listing lacks the commands.
- [ ] Render the pending-only controls without changing non-pending filtering.
- [ ] Re-run the display test.

### Task 2: Number And Bulk Actions

**Files:**
- Modify: `scripts/test_telegram_learning_delivery.py`
- Modify: `telegram_bot.py`

- [ ] Add failing tests for `/approve 1`, `/reject 1`, and `/approve_all` with owner-scoped pending entries.
- [ ] Resolve numeric targets against the same newest-first pending ordering used by `/knowledge pending`.
- [ ] Add `/approve_all`; report the actual approved count and leave rejected/other-user entries untouched.
- [ ] Register the command and run the Telegram delivery regression suite.

### Task 3: Verification And Restart

**Files:**
- Verify: `telegram_bot.py`, `scripts/test_telegram_learning_delivery.py`

- [ ] Run `python -m py_compile telegram_bot.py`.
- [ ] Run relevant Telegram and knowledge tests with UTF-8 console output.
- [ ] Restart only Telegram bot and verify its startup log; leave worker and GUI untouched.
