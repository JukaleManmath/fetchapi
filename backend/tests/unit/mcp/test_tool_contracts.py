"""Verify that all 9 MCP tools are registered and have correct metadata."""

import asyncio

from fetch.mcp.server import mcp


def _get_tools() -> list:
    return asyncio.run(mcp.list_tools())


def test_all_tools_registered() -> None:
    tools = _get_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "fetch_list_sources",
        "fetch_search_docs",
        "fetch_get_operation",
        "fetch_get_schema",
        "fetch_get_auth",
        "fetch_generate_integration",
        "fetch_validate_request",
        "fetch_explain_error",
        "fetch_compare_versions",
    }
    assert expected == tool_names


def test_tool_descriptions_non_empty() -> None:
    tools = _get_tools()
    for tool in tools:
        assert tool.description, f"Tool {tool.name} has no description"
