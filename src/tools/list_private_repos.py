"""List private repositories tool for multi-tenant-github-mcp MCP server.

This tool lists private repositories for the authenticated GitHub user.
"""

import json
from typing import List, Dict, Any

import sys
import os
# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# mcp instance will be injected by the server
# from core.server import mcp
from core.utils import get_tool_config
from github.client import GitHubClient, GitHubAPIError


@mcp.tool()
def list_private_repos() -> str:
    """List private repositories for the authenticated GitHub user.

    Returns:
        JSON string containing list of private repositories
    """
    try:
        # Get tool-specific configuration
        config = get_tool_config("list_private_repos")
        
        # Initialize GitHub client
        client = GitHubClient()
        
        # List private repositories for the authenticated user
        repos = client.list_repositories(repo_type="private", sort="updated")
        
        # Format the response as JSON
        if not repos:
            return json.dumps({
                "message": "No private repositories found",
                "repositories": []
            })
        
        # Return simplified repository data
        simplified_repos = []
        for repo in repos:
            simplified_repos.append({
                'name': repo['name'],
                'full_name': repo['full_name'],
                'private': repo['private'],
                'html_url': repo['html_url'],
                'clone_url': repo['clone_url'],
                'language': repo.get('language'),
                'size': repo.get('size', 0),
                'stargazers_count': repo.get('stargazers_count', 0),
                'forks_count': repo.get('forks_count', 0),
                'description': repo.get('description'),
                'created_at': repo['created_at'],
                'updated_at': repo['updated_at'],
                'pushed_at': repo.get('pushed_at'),
            })
        
        return json.dumps({
            "message": f"Found {len(simplified_repos)} private repositories",
            "count": len(simplified_repos),
            "repositories": simplified_repos
        }, indent=2)
        
    except GitHubAPIError as e:
        return json.dumps({
            "error": "GitHub API Error",
            "message": str(e)
        })
    except ValueError as e:
        return json.dumps({
            "error": "Configuration Error", 
            "message": str(e)
        })
    except Exception as e:
        return json.dumps({
            "error": "Unexpected Error",
            "message": str(e)
        })
