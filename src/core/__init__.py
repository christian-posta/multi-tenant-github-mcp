"""Core framework for multi-tenant-github-mcp MCP server.

This package provides the dynamic tool loading system that automatically
discovers and registers tools from the src/tools/ directory.
"""

from .server import DynamicMCPServer
from .elicitation import elicitation_manager

__all__ = ["DynamicMCPServer", "elicitation_manager"]
