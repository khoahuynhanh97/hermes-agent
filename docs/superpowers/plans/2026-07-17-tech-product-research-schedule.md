# Scheduled Tech Product Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create one finite automation that runs every 15 minutes for five occurrences, researches three non-duplicate technology accessories per occurrence, and sends each result to Hermes Telegram.

**Architecture:** Use a Codex heartbeat attached to the current task instead of adding a scheduler to Hermes. Each occurrence browses current public sources, persists minimal deduplication state under `D:\HermesData`, and sends one HTML-formatted message through the configured Telegram bot.

**Tech Stack:** Codex heartbeat automation, web research, Python, `python-telegram-bot`, Hermes `.env` configuration, local JSON state.

## Global Constraints

- Run every 15 minutes for exactly five occurrences.
- Find up to three reliable, non-duplicate consumer technology accessories per occurrence.
- Telegram is the only user-facing destination.
- Never persist or print Telegram credentials.
- Do not generate videos, publish content, or purchase products.
- Metadata without reliable public evidence must not be presented as fact.
- A failed occurrence still counts toward the five-occurrence limit.

---

### Task 1: Resolve Automation Target And Existing Schedules

**Files:**
- Read: `C:\Users\ninak\.codex\automations\*\automation.toml`
- Read: `D:\work\hermes-agent\.env`

**Interfaces:**
- Consumes: Current Codex task, Hermes project registration, existing automation metadata.
- Produces: Hermes project identifier and confirmation that no equivalent active schedule already exists.

- [ ] **Step 1: List registered Codex projects**

Use the Codex project-listing tool and select the project whose local root is exactly `D:\work\hermes-agent`.

- [ ] **Step 2: Inspect existing automation metadata**

Search automation files for an active schedule named `Hermes Tech Product Research`. If one exists, update it instead of creating a duplicate.

- [ ] **Step 3: Validate Telegram configuration without exposing secrets**

Run:

```powershell
cd D:\work\hermes-agent
.\.venv\Scripts\python.exe -c "import config; assert config.TELEGRAM_BOT_TOKEN; assert config.TELEGRAM_REVIEW_CHAT_ID; print('telegram-config-ok')"
```

Expected: `telegram-config-ok` and no credential values in output.

### Task 2: Create The Finite Heartbeat

**Files:**
- Runtime state: `D:\HermesData\scheduled_product_research.json`

**Interfaces:**
- Consumes: Hermes project identifier, current task identifier, Telegram configuration.
- Produces: One active heartbeat named `Hermes Tech Product Research` with five 15-minute occurrences.

- [ ] **Step 1: Build the automation prompt**

The prompt must require each occurrence to:

1. Read `D:\HermesData\scheduled_product_research.json`, creating it atomically when absent.
2. Determine the current occurrence number from stored successful and failed delivery records.
3. Browse current manufacturer or reputable retailer sources.
4. Select up to three product models not already present in state.
5. Prefer chargers, power banks, speakers, headphones, keyboards, hubs, stands, cables, smart-home accessories, and similar practical technology products.
6. Record product name, category, direct source link, indicative price with currency and timestamp, three verified highlights, one short-video angle, and selection rationale.
7. Escape all dynamic values before inserting them into Telegram HTML.
8. Send one Telegram message titled `Nghiên cứu sản phẩm · Lượt N/5` through `python-telegram-bot`, reading token and chat ID from `config` without printing either value.
9. Atomically persist selected product identifiers and delivery status using a temporary file followed by `Path.replace()`.
10. Avoid unbounded retries and never invent unavailable facts.

- [ ] **Step 2: Create or update the automation**

Use the Codex automation tool with:

- Name: `Hermes Tech Product Research`
- Kind: heartbeat attached to the current task
- Status: active
- Destination: local
- Recurrence: every 15 minutes, exactly five occurrences
- Prompt: the requirements from Step 1

- [ ] **Step 3: Verify the saved automation**

View the created automation by ID and verify:

- It is active.
- It targets the current task.
- It has a 15-minute interval and a finite count of five.
- Its prompt references Telegram delivery and the deduplication state file.
- It contains no token, API key, chat ID value, or product placeholder presented as real data.

### Task 3: Operational Verification

**Files:**
- Read after first occurrence: `D:\HermesData\scheduled_product_research.json`

**Interfaces:**
- Consumes: Active heartbeat from Task 2.
- Produces: Evidence that the schedule is registered and ready for its first occurrence.

- [ ] **Step 1: Confirm Telegram bot availability**

Run a redacted `get_me()` call using the configured token.

Expected: Telegram returns the bot username without printing the token.

- [ ] **Step 2: Report schedule timing**

Report the automation name, active status, first scheduled occurrence, 15-minute interval, and five-occurrence limit to the user. Do not expose the raw recurrence representation.

- [ ] **Step 3: Verify the first occurrence after it runs**

Confirm that Telegram received one message containing up to three products and that the state file records occurrence `1`, unique product identifiers, timestamp, source links, and delivery status. If delivery fails, report the failure without manually extending the five-occurrence limit.
