"""apps/telegram/bot.py — Telegram Bot Application Entrypoint.

This module serves as the canonical entrypoint for the Telegram bot.
During the migration period, it delegates to the original telegram_bot.py
at the project root. As handlers are gradually extracted into
apps/telegram/handlers/, this file will become the primary bot setup.

Usage:
    python -m apps.telegram.bot
"""

import os
import sys

# Ensure the project root is on the Python path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main():
    """Start the Telegram bot by delegating to the root-level module."""
    # Import the original main() function from the root telegram_bot.py
    from telegram_bot import main as _original_main
    _original_main()


if __name__ == "__main__":
    main()
