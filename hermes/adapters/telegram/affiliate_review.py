from __future__ import annotations

import asyncio
import inspect
from html import escape
from typing import Any, Callable, Sequence

from hermes.domain.affiliate_research import ContentPackage, ProjectionResult
from hermes.ports.affiliate_research import AffiliateResearchRepository


_CALLBACK_PREFIXES = {
    "approve": "affiliate_approve",
    "revise": "affiliate_revise",
    "reject": "affiliate_reject",
}


def parse_review_callback(data: str) -> tuple[str, str] | None:
    """Parse only compact affiliate review callback payloads."""
    if not isinstance(data, str) or len(data.encode("utf-8")) >= 64:
        return None
    prefix, separator, package_id = data.partition(":")
    action = next((name for name, value in _CALLBACK_PREFIXES.items() if value == prefix), None)
    if not separator or not action or not package_id:
        return None
    return action, package_id


def build_review_keyboard(
    package_id: str,
    *,
    button_factory: Callable[[str, str], Any] | None = None,
) -> tuple[tuple[Any, ...], ...]:
    if button_factory is None:
        from telegram import InlineKeyboardButton

        button_factory = InlineKeyboardButton
    buttons = []
    for action, label in (("approve", "Approve"), ("revise", "Revise"), ("reject", "Reject")):
        callback_data = f"{_CALLBACK_PREFIXES[action]}:{package_id}"
        if len(callback_data.encode("utf-8")) >= 64:
            raise ValueError("affiliate package id is too long for Telegram callback data")
        buttons.append(button_factory(label, callback_data=callback_data))
    return (tuple(buttons),)


def render_package_html(
    package: ContentPackage,
    *,
    product_name: str = "",
    score_reason: str = "",
) -> str:
    """Render untrusted package data as Telegram-safe HTML."""
    storyboard = "; ".join(
        str(item.get("visual", "")) for item in package.storyboard[:3] if item.get("visual")
    ) or "Not provided"
    warnings = "; ".join(package.warnings) or "None"
    values = {
        "product_name": product_name or package.product_id,
        "score_reason": score_reason or package.angle_reason or "Not provided",
        "audience": package.audience,
        "hook": package.hook,
        "script": package.script,
        "storyboard": storyboard,
        "warnings": warnings,
        "package_id": package.id,
    }
    escaped = {key: escape(str(value), quote=True) for key, value in values.items()}
    return (
        f"<b>Affiliate review: {escaped['product_name']}</b>\n"
        f"<b>Score reason:</b> {escaped['score_reason']}\n"
        f"<b>Audience:</b> {escaped['audience']}\n"
        f"<b>Hook:</b> {escaped['hook']}\n"
        f"<b>Script:</b> {escaped['script']}\n"
        f"<b>Storyboard:</b> {escaped['storyboard']}\n"
        f"<b>Warnings:</b> {escaped['warnings']}\n"
        f"<b>Package ID:</b> <code>{escaped['package_id']}</code>"
    )


class TelegramReviewDelivery:
    """Synchronous projection adapter around an injected Telegram bot client."""

    def __init__(self, repository: AffiliateResearchRepository, bot: Any, chat_id: str | int):
        self._repository = repository
        self._bot = bot
        self._chat_id = chat_id

    def send_pending(self, owner_user_id: str, package_ids: Sequence[str]) -> ProjectionResult:
        try:
            packages = {item.id: item for item in self._repository.list_packages(owner_user_id)}
            for package_id in package_ids:
                package = packages.get(package_id)
                if package is None or package.status.value != "pending_review":
                    continue
                product_name = self._product_name(owner_user_id, package.product_id)
                result = self._bot.send_message(
                    chat_id=self._chat_id,
                    text=render_package_html(package, product_name=product_name),
                    parse_mode="HTML",
                    reply_markup=self._markup(package.id),
                )
                if inspect.isawaitable(result):
                    asyncio.run(result)
        except Exception as error:
            return ProjectionResult(ok=False, retryable=True, detail=str(error)[:1000])
        return ProjectionResult(ok=True, retryable=False, detail="delivered")

    def _product_name(self, owner_user_id: str, product_id: str) -> str:
        for product in self._repository.list_products(owner_user_id):
            if product.id == product_id:
                return product.name
        return product_id

    @staticmethod
    def _markup(package_id: str) -> Any:
        from telegram import InlineKeyboardMarkup

        return InlineKeyboardMarkup(build_review_keyboard(package_id))
