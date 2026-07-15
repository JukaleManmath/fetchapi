"""Shared FastAPI dependencies.

All application-layer dependencies are resolved here, not in route handlers.
"""

from uuid import UUID

from fetch.config import get_settings


def get_workspace_id() -> UUID:
    """Return the default workspace ID from settings.

    In Phase 1 this is the single-tenant default workspace.
    Multi-tenant auth will inject a different workspace per request later.
    """
    return get_settings().app.workspace_id


def get_settings_dep() -> object:
    """FastAPI dependency that returns the current Settings object."""
    return get_settings()
