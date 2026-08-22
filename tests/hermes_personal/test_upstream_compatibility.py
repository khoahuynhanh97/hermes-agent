import inspect


def test_upstream_agent_turn_surface_is_available():
    from run_agent import AIAgent

    parameters = inspect.signature(AIAgent.run_conversation).parameters
    assert {"user_message", "conversation_history", "task_id"} <= set(parameters)


def test_upstream_gateway_session_surface_is_available():
    from gateway.session import SessionContext, SessionStore

    assert SessionContext is not None
    assert SessionStore is not None


def test_upstream_tool_and_mcp_discovery_surfaces_are_available():
    from tools.mcp_tool import discover_mcp_tools, refresh_agent_mcp_tools
    from tools.registry import ToolRegistry

    assert callable(discover_mcp_tools)
    assert callable(refresh_agent_mcp_tools)
    assert callable(ToolRegistry.register)
    assert callable(ToolRegistry.get_definitions)
    assert callable(ToolRegistry.dispatch)
