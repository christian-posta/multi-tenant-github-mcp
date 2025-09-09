"""List private repositories tool for multi-tenant-github-mcp MCP server.

This tool lists private repositories for the authenticated GitHub user.
Uses URL elicitation to securely collect GitHub tokens when needed.
"""

import json
import uuid
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
from core.elicitation import elicitation_manager
from github.client import GitHubClient, GitHubAPIError
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession


@mcp.tool(description="List private repositories with secure token collection")
async def list_private_repos(ctx: Context[ServerSession, None]) -> str:
    """List private repositories for the authenticated GitHub user.
    
    This tool will securely collect a GitHub token via URL elicitation
    if no valid token is available from existing sources.

    Returns:
        JSON string containing list of private repositories
    """
    try:
        # Get tool-specific configuration
        config = get_tool_config("list_private_repos")
        
        # Try to get a token from existing sources first
        github_token = None
        try:
            # Try to initialize GitHub client with existing token sources
            # Check if we should allow file-based tokens from server config
            from core.server import mcp
            server_instance = getattr(mcp, '_server_instance', None)
            allow_file = getattr(server_instance, 'access_token_file_enabled', False) if server_instance else False
            client = GitHubClient(allow_file=allow_file)
            # Test if the token works by validating it
            client.validate_token()
            github_token = client.access_token
            print(f"✅ Using existing GitHub token from configuration")
        except (ValueError, GitHubAPIError) as e:
            print(f"⚠️ No valid existing token found: {e}")
            # No valid token available, proceed with elicitation
        
        # Check if there are any completed elicitations we can use
        if not github_token:
            # Look for any completed elicitations in the current session
            session_id = getattr(ctx.request_context.session, 'session_id', 'unknown')
            for elicitation_id, metadata in elicitation_manager.elicitations_map.items():
                if (metadata.session_id == session_id and 
                    metadata.status == "complete" and 
                    metadata.token_validated):
                    github_token = metadata.collected_token
                    print(f"✅ Using token from completed elicitation: {elicitation_id}")
                    break
        
        # If no valid token, initiate elicitation
        if not github_token:
            # Get session ID for tracking
            session_id = getattr(ctx.request_context.session, 'session_id', 'unknown')
            
            # Create and track the elicitation
            elicitation_id = elicitation_manager.generate_tracked_elicitation(
                session_id,
                "GitHub token collection for repository access"
            )
            
            # Use local server URL for GitHub token collection
            token_url = f"http://localhost:8000/github-token-form?id={elicitation_id}"
            print(f"🔗 Generated GitHub token URL: {token_url}")
            
            # Use URL elicitation to direct user to token collection form
            result = await ctx.elicit_url(
                message="Please provide your GitHub Personal Access Token to access private repositories. This token will only be used for this session and will not be saved.",
                url=token_url,
                elicitationId=elicitation_id,
            )
            
            if result.action == "accept":
                print(f"✅ User accepted GitHub token elicitation: {elicitation_id}")
                
                # Check if elicitation is already complete (user was fast)
                metadata = elicitation_manager.get_elicitation(elicitation_id)
                if metadata and metadata.status == "complete":
                    github_token = elicitation_manager.get_collected_token(elicitation_id)
                    if github_token:
                        print(f"✅ GitHub token already collected and validated")
                    else:
                        return json.dumps({
                            "error": "Token Collection Failed",
                            "message": "No valid token was collected during the elicitation process"
                        })
                else:
                    # Return pending status - user needs to complete the form
                    return json.dumps({
                        "status": "pending",
                        "message": f"Please complete the token collection at: {token_url}",
                        "elicitation_id": elicitation_id,
                        "url": token_url,
                        "instructions": "After submitting your token, call this tool again to list repositories"
                    })
            elif result.action == "decline":
                return json.dumps({
                    "error": "Access Denied",
                    "message": "GitHub token collection was declined by user"
                })
            else:
                return json.dumps({
                    "error": "Access Cancelled",
                    "message": "GitHub token collection was cancelled by user"
                })
        
        # Initialize GitHub client with the token (either existing or elicited)
        client = GitHubClient(access_token=github_token)
        
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
