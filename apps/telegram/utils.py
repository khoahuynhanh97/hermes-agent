"""apps/telegram/utils.py — Shared Telegram utility functions.

Extracted from the original telegram_bot.py to enable handler modules
to reuse message splitting, HTML rendering, and safe reply functions.
"""

import re
from html import escape as html_escape, unescape as html_unescape
from urllib.parse import urlparse

from telegram import Update
from telegram.constants import ParseMode


# ----------------------------------------------------------------
# Message splitting
# ----------------------------------------------------------------

def split_message(text: str, limit: int = 4000) -> list[str]:
    """Cắt nhỏ tin nhắn dài hơn giới hạn của Telegram (4096 ký tự)"""
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        split_pos = text.rfind('\n', 0, limit)
        if split_pos == -1:
            split_pos = text.rfind(' ', 0, limit)
        if split_pos == -1:
            split_pos = limit

        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    return chunks


# ----------------------------------------------------------------
# HTML rendering for Telegram
# ----------------------------------------------------------------

_CODE_BLOCK_PATTERN = re.compile(r"```[^\n`]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+)`")
_URL_RENDER_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def _telegram_safe_url(value: str) -> bool:
    parsed = urlparse(html_unescape(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def render_telegram_html(text: str) -> str:
    """Escape untrusted text and render a small Telegram-safe Markdown subset."""
    placeholders: list[str] = []

    def protect(rendered: str) -> str:
        token = f"\ue000{len(placeholders)}\ue001"
        placeholders.append(rendered)
        return token

    raw = str(text or "").replace("\r\n", "\n")
    raw = _CODE_BLOCK_PATTERN.sub(
        lambda match: protect(f"<pre>{html_escape(match.group(1).strip(chr(10)))}</pre>"),
        raw,
    )
    raw = _INLINE_CODE_PATTERN.sub(
        lambda match: protect(f"<code>{html_escape(match.group(1))}</code>"),
        raw,
    )
    rendered = html_escape(raw, quote=True)

    def render_url(match: re.Match) -> str:
        original = match.group(0)
        url = original.rstrip(".,!?:;)")
        suffix = original[len(url):]
        if not _telegram_safe_url(url):
            return original
        return f'<a href="{url}">{url}</a>{suffix}'

    rendered = _URL_RENDER_PATTERN.sub(render_url, rendered)
    rendered = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", rendered)
    rendered = re.sub(r"~~(.+?)~~", r"<s>\1</s>", rendered)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", rendered)
    rendered = re.sub(r"(?m)^&gt;\s?(.*)$", r"<blockquote>\1</blockquote>", rendered)
    rendered = re.sub(r"(?m)^#{1,3}\s+(.+)$", r"<b>\1</b>", rendered)

    for index, replacement in enumerate(placeholders):
        rendered = rendered.replace(f"\ue000{index}\ue001", replacement)
    return rendered


def telegram_html_to_plain_text(value: str) -> str:
    """Produce a readable fallback after Telegram rejects an HTML response."""
    return html_unescape(_HTML_TAG_PATTERN.sub("", value))


# ----------------------------------------------------------------
# Safe reply helpers
# ----------------------------------------------------------------

async def reply_html(message, text: str, *, already_html: bool = False, **kwargs) -> None:
    """Send one Telegram reply as controlled HTML, with a plain-text fallback."""
    html_body = text if already_html else render_telegram_html(text)
    for chunk in split_message(html_body):
        try:
            await message.reply_text(chunk, parse_mode=ParseMode.HTML, **kwargs)
        except Exception:
            plain = telegram_html_to_plain_text(chunk)
            try:
                await message.reply_text(plain, **kwargs)
            except Exception:
                pass


async def send_html_message(bot, chat_id, text: str, *, already_html: bool = False, **kwargs) -> None:
    """Send a standalone message (not a reply) as controlled HTML."""
    html_body = text if already_html else render_telegram_html(text)
    for chunk in split_message(html_body):
        try:
            await bot.send_message(chat_id, chunk, parse_mode=ParseMode.HTML, **kwargs)
        except Exception:
            plain = telegram_html_to_plain_text(chunk)
            try:
                await bot.send_message(chat_id, plain, **kwargs)
            except Exception:
                pass


async def edit_html_message(query, text: str, *, already_html: bool = False, **kwargs) -> None:
    """Edit an existing inline-keyboard message with controlled HTML."""
    html_body = text if already_html else render_telegram_html(text)
    try:
        await query.edit_message_text(html_body, parse_mode=ParseMode.HTML, **kwargs)
    except Exception:
        plain = telegram_html_to_plain_text(html_body)
        try:
            await query.edit_message_text(plain, **kwargs)
        except Exception:
            pass
