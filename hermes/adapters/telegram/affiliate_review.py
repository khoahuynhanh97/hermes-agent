from __future__ import annotations

import asyncio
import inspect
import os
from collections.abc import Mapping
from html import escape
from typing import Any, Callable, Sequence

from hermes.application.affiliate_run_service import DisabledReviewDelivery
from hermes.domain.affiliate_research import ContentPackage, ProjectionResult
from hermes.ports.affiliate_research import AffiliateResearchRepository


_CALLBACK_PREFIXES = {
    "approve": "affiliate_approve",
    "revise": "affiliate_revise",
    "reject": "affiliate_reject",
}


def review_delivery_from_environment(
    repository: AffiliateResearchRepository,
    *,
    environ: Mapping[str, str] | None = None,
    bot_factory: Callable[[str], Any] | None = None,
) -> TelegramReviewDelivery | DisabledReviewDelivery:
    """Create Telegram delivery only when both required environment values exist."""
    settings = os.environ if environ is None else environ
    token = str(settings.get("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(settings.get("TELEGRAM_REVIEW_CHAT_ID", "")).strip()
    if not token or not chat_id:
        return DisabledReviewDelivery()
    if bot_factory is None:
        from telegram import Bot

        bot_factory = lambda configured_token: Bot(token=configured_token)
    return TelegramReviewDelivery(repository, bot_factory(token), chat_id)


def parse_review_callback(data: str) -> tuple[str, str] | None:
    """Parse only compact affiliate review callback payloads."""
    if not isinstance(data, str) or len(data.encode("utf-8")) > 64:
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
        if len(callback_data.encode("utf-8")) > 64:
            raise ValueError("affiliate package id is too long for Telegram callback data")
        buttons.append(button_factory(label, callback_data=callback_data))
    return (tuple(buttons),)


def render_package_html(
    package: ContentPackage,
    *,
    product_name: str = "",
    score: float | None = None,
    score_reason: str = "",
    max_length: int = 4096,
) -> str:
    """Render untrusted package data as Telegram-safe HTML."""
    storyboard = "; ".join(
        str(item.get("visual", "")) for item in package.storyboard[:3] if item.get("visual")
    ) or "Not provided"
    warnings = "; ".join(package.warnings) or "None"
    values = {
        "product_name": _truncate(product_name or package.product_id, 100),
        "score": "Not scored" if score is None else f"{score:g}/100",
        "score_reason": _truncate(
            score_reason or package.angle_reason or "Not provided", 180
        ),
        "audience": _truncate(package.audience, 80),
        "hook": _truncate(package.hook, 180),
        "script": _truncate(package.script, 220),
        "storyboard": _truncate(storyboard, 180),
        "warnings": _truncate(warnings, 160),
        "package_id": package.id,
    }
    escaped = {key: escape(str(value), quote=True) for key, value in values.items()}
    lines = [
        f"<b>Affiliate review: {escaped['product_name']}</b>",
        f"<b>Package ID:</b> <code>{escaped['package_id']}</code>",
        f"<b>Score:</b> {escaped['score']}",
        f"<b>Score reason:</b> {escaped['score_reason']}",
        f"<b>Audience:</b> {escaped['audience']}",
        f"<b>Hook:</b> {escaped['hook']}",
        f"<b>Script:</b> {escaped['script']}",
        f"<b>Storyboard:</b> {escaped['storyboard']}",
        f"<b>Warnings:</b> {escaped['warnings']}",
    ]
    bounded = []
    for line in lines:
        candidate = "\n".join((*bounded, line))
        if len(candidate) <= max_length:
            bounded.append(line)
    return "\n".join(bounded)


def _truncate(value: str, maximum: int) -> str:
    if len(value) <= maximum:
        return value
    return value[: max(0, maximum - 3)].rstrip() + "..."


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
                ensure_item = getattr(
                    self._repository, "ensure_projection_item", None
                )
                if ensure_item is not None:
                    ensure_item(package.run_id, "telegram", package.id)
                pending_items = getattr(
                    self._repository, "pending_projection_items", None
                )
                if pending_items is not None and not pending_items(
                    package.run_id, "telegram", (package.id,)
                ):
                    continue
                product = self._product(
                    owner_user_id, package.product_id, package.run_id
                )
                product_name = getattr(product, "name", package.product_id)
                score = getattr(product, "score", None)
                score_reason = getattr(product, "score_reason", "")
                image_urls = tuple(getattr(product, "image_urls", ()) or ())
                message = render_package_html(
                    package,
                    product_name=product_name,
                    score=score,
                    score_reason=score_reason,
                    max_length=1024 if image_urls else 4096,
                )
                if image_urls:
                    try:
                        sent_message = self._resolve(
                            self._bot.send_photo(
                                chat_id=self._chat_id,
                                photo=image_urls[0],
                                caption=message,
                                parse_mode="HTML",
                                reply_markup=self._markup(package.id),
                            )
                        )
                    except Exception:
                        sent_message = self._resolve(
                            self._bot.send_message(
                                chat_id=self._chat_id,
                                text=render_package_html(
                                    package,
                                    product_name=product_name,
                                    score=score,
                                    score_reason=score_reason,
                                    max_length=4096,
                                ),
                                parse_mode="HTML",
                                reply_markup=self._markup(package.id),
                            )
                        )
                else:
                    sent_message = self._resolve(
                        self._bot.send_message(
                            chat_id=self._chat_id,
                            text=message,
                            parse_mode="HTML",
                            reply_markup=self._markup(package.id),
                        )
                    )
                mark_delivered = getattr(
                    self._repository, "mark_projection_item_delivered", None
                )
                if mark_delivered is not None:
                    mark_delivered(
                        package.run_id,
                        "telegram",
                        package.id,
                        str(getattr(sent_message, "message_id", "") or ""),
                    )
        except Exception as error:
            return ProjectionResult(ok=False, retryable=True, detail=str(error)[:1000])
        return ProjectionResult(ok=True, retryable=False, detail="delivered")

    def _product(
        self, owner_user_id: str, product_id: str, run_id: str
    ) -> Any:
        for product in self._repository.list_products(
            owner_user_id, run_id=run_id
        ):
            if product.id == product_id:
                return product
        return None

    @staticmethod
    def _resolve(result: Any) -> Any:
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return result

    @staticmethod
    def _markup(package_id: str) -> Any:
        from telegram import InlineKeyboardMarkup

        return InlineKeyboardMarkup(build_review_keyboard(package_id))
