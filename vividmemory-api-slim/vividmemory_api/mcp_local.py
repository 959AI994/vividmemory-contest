"""
Local MCP server entry point for use with Claude Code (HTTP transport).

This is a thin wrapper around the main vividmemory-api server that pre-configures
sensible defaults for local use (embedded PostgreSQL via pg0, warning log level).

The full API runs on localhost:8888. Configure Claude Code's MCP settings:
    claude mcp add --transport http vividmemory http://localhost:8888/mcp/

Or pinned to a specific bank (single-bank mode):
    claude mcp add --transport http vividmemory http://localhost:8888/mcp/default/

Run with:
    vividmemory-local-mcp

Or with uvx:
    uvx vividmemory-api@latest vividmemory-local-mcp

Environment variables:
    VIVIDMEMORY_API_LLM_API_KEY: Required. API key for LLM provider.
    VIVIDMEMORY_API_LLM_PROVIDER: Optional. LLM provider (default: "openai").
    VIVIDMEMORY_API_LLM_MODEL: Optional. LLM model (default: "gpt-4o-mini").
    VIVIDMEMORY_API_DATABASE_URL: Optional. Override database URL (default: pg0://vividmemory-mcp).
"""

import os


def main() -> None:
    """Start the VividMemory API server with local defaults."""
    # Set local defaults (only if not already configured by the user)
    os.environ.setdefault("VIVIDMEMORY_API_DATABASE_URL", "pg0://vividmemory-mcp")

    from vividmemory_api.main import main as api_main

    api_main()


if __name__ == "__main__":
    main()
