"""Example echo tool for multi-tenant-github-mcp MCP server.

This is an example tool showing the basic structure for FastMCP tools.
Each tool file should contain a function decorated with @mcp.tool().
"""

import sys
import os
# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# mcp instance will be injected by the server
# from core.server import mcp
from core.utils import get_tool_config


@mcp.tool()
def echo(message: str) -> str:
    """Echo a message back to the client.

    Args:
        message: The message to echo

    Returns:
        The echoed message with any configured prefix
    """
    # Get tool-specific configuration
    config = get_tool_config("echo")
    prefix = config.get("prefix", "")

    # Return the message with optional prefix
    return f"{prefix}{message}" if prefix else message
