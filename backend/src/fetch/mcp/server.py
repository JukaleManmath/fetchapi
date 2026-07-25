from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="fetchapi",
    instructions=(
        "FetchAPI gives you structured, citation-backed knowledge of any OpenAPI-described API. "
        "Use fetch_list_sources to see available APIs, fetch_search_docs to find relevant operations "
        "or schemas, and the other tools to get full details, generate integration code, validate "
        "requests, or compare API versions."
    ),
)

# Import and register all tools
from fetch.mcp.tools import (  # noqa: E402, F401
    auth,
    comparisons,
    integrations,
    operations,
    schemas,
    search,
    sources,
    validation,
)
