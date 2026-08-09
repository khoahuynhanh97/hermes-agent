"""Repository-wide test isolation for developer-specific local paths."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


# The application may use a developer-configured knowledge root in `.env`.
# Tests must remain hermetic and must never require a mounted personal drive.
_TEST_KNOWLEDGE_ROOT = Path(tempfile.mkdtemp(prefix="hermes-pytest-knowledge-"))
os.environ["KNOWLEDGE_BASE_ROOT"] = str(_TEST_KNOWLEDGE_ROOT)
