# telegram_bot.py
import sys
from pathlib import Path

# Add the 'src' directory to the Python path
# This allows importing modules from the hermes package
sys.path.insert(0, str(Path(__file__).parent / "src"))

from hermes.channels.gateway.platforms.telegram import bot as _canonical_bot

if __name__ == "__main__":
    _canonical_bot.main()
else:
    # Keep legacy imports and monkeypatches attached to the canonical module.
    sys.modules[__name__] = _canonical_bot
