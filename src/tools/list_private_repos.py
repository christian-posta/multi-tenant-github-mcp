"""List private repositories tool for multi-tenant-github-mcp MCP server.

This tool lists private repositories for a given GitHub organization or user.
Currently stubbed out as an echo tool for development purposes.
"""

from core.server import mcp
from core.utils import get_tool_config


@mcp.tool()
def list_private_repos(owner: str) -> str:
    """List private repositories for a GitHub owner (organization or user).

    Args:
        owner: The GitHub organization or username to list private repos for

    Returns:
        A list of private repositories (currently stubbed as echo response)
    """
    # Get tool-specific configuration
    config = get_tool_config("list_private_repos")
    prefix = config.get("prefix", "")
    
    # Stubbed implementation - just echo the owner name for now
    response = f"Private repositories for '{owner}': [stubbed - would list actual repos]"
    
    # Return the response with optional prefix
    return f"{prefix}{response}" if prefix else response
