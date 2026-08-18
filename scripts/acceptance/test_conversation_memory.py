"""Tests for bounded, per-user conversation memory."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.append(str(Path(__file__).resolve().parent.parent))

from hermes.application.core.conversation_memory import ConversationMemory


def run_tests():
    with TemporaryDirectory() as tmp:
        memory = ConversationMemory(Path(tmp) / "memory.json", max_messages=4, max_chars=500)
        memory.add(1, "user", "hello")
        memory.add(1, "assistant", "hi")
        memory.add(2, "user", "private")
        assert "hello" in memory.context(1)
        assert "private" not in memory.context(1)
        for index in range(10):
            memory.add(1, "user", f"message-{index}")
        assert "message-9" in memory.context(1)
        assert len(memory.context(1)) <= 500
        memory.clear(1)
        assert memory.context(1) == ""
        assert "private" in memory.context(2)
    print("conversation memory tests: PASS")


if __name__ == "__main__":
    run_tests()
