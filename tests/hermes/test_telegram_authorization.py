from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class TelegramAuthorizationTests(unittest.TestCase):
    def test_allowlist_fails_closed_and_is_owner_scoped(self) -> None:
        from core.telegram_auth import is_authorized_update, is_authorized_user_id

        with patch.dict(
            os.environ,
            {"TELEGRAM_ALLOWED_USER_IDS": "42, 84", "TELEGRAM_REVIEW_CHAT_ID": ""},
            clear=False,
        ):
            self.assertTrue(is_authorized_user_id(42))
            self.assertFalse(is_authorized_user_id(99))
            self.assertTrue(is_authorized_update(SimpleNamespace(effective_user=SimpleNamespace(id=84))))
            self.assertFalse(is_authorized_update(SimpleNamespace(effective_user=None)))

        with patch.dict(
            os.environ,
            {"TELEGRAM_ALLOWED_USER_IDS": "", "TELEGRAM_REVIEW_CHAT_ID": ""},
            clear=False,
        ), patch("core.telegram_auth.config.TELEGRAM_ALLOWED_USER_IDS", ""), patch(
            "core.telegram_auth.config.TELEGRAM_REVIEW_CHAT_ID", ""
        ):
            self.assertFalse(is_authorized_user_id(42))


if __name__ == "__main__":
    unittest.main()
