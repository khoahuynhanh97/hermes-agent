"""apps/web_studio/app.py — Web Studio Application Entrypoint.

Delegates to the root-level web_studio.py during migration.

Usage:
    python -m apps.web_studio.app
"""

import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main():
    """Start the Web Studio server."""
    from web_studio import main as _original_main
    _original_main()


if __name__ == "__main__":
    main()
