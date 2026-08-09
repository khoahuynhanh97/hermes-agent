# Telegram HTML Rendering Design

## Goal

Make Hermes Telegram responses easier to scan using Telegram HTML while keeping
all LLM and source content untrusted.

## Decision

Hermes will not ask models or source processors to produce Telegram HTML.
Responses remain plain text or simple Markdown. A small renderer in
`telegram_bot.py` will escape text first, then convert only a limited subset
of Markdown into Telegram-supported HTML:

- bold, italic, underline, strike-through
- inline code and fenced code blocks
- blockquotes
- validated `http` and `https` links
- spoilers

The knowledge catalogue will produce controlled HTML directly because its
layout is application-owned. Entry fields such as titles and summaries are
escaped before interpolation. Visual grouping uses emoji markers because
Telegram has no text-color API.

## Sending Rules

- All text replies from the bot use `parse_mode="HTML"` through helpers.
- Long raw responses are split before rendering so HTML tags are never split.
- If Telegram rejects a rendered message, Hermes sends a plain-text fallback.
- Documents remain documents; this change does not alter learning jobs,
  approval state, or Drive storage.

## Non-Goals

- No arbitrary HTML from model output, captions, transcripts, or web pages.
- No general Markdown parser dependency.
- No changes to Telegram inline button behavior.
