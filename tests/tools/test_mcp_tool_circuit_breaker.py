from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from tools import mcp_tool


class _ErrorSession:
    async def call_tool(self, _tool_name, arguments):
        return SimpleNamespace(
            isError=True,
            content=[SimpleNamespace(text="invalid creative brief payload")],
        )


class _HealthyServer:
    def __init__(self):
        self.session = _ErrorSession()
        self._rpc_lock = asyncio.Lock()
        self._pending_call_context = None

    def mark_tool_call(self):
        return None


def test_tool_validation_error_does_not_open_server_circuit(monkeypatch):
    server_name = "schema-test-server"
    server = _HealthyServer()
    mcp_tool._server_error_counts[server_name] = 2
    mcp_tool._server_breaker_opened_at.pop(server_name, None)
    monkeypatch.setattr(mcp_tool, "_get_connected_server_for_call", lambda _name: server)
    monkeypatch.setattr(
        mcp_tool,
        "_run_on_mcp_loop",
        lambda coroutine_factory, timeout: asyncio.run(coroutine_factory()),
    )

    result = mcp_tool._make_tool_handler(server_name, "save", 5.0)({})

    assert "invalid creative brief payload" in json.loads(result)["error"]
    assert mcp_tool._server_error_counts[server_name] == 0
