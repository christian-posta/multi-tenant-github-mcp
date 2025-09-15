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
        # Log Authorization header if available in the context
        if hasattr(ctx.request_context, 'request') and hasattr(ctx.request_context.request, 'headers'):
            auth_header = ctx.request_context.request.headers.get("authorization")
            if auth_header:
                # Mask the token for security (show first 10 chars + ...)
                if len(auth_header) > 10:
                    masked_auth = auth_header[:10] + "..."
                else:
                    masked_auth = auth_header
                print(f"🔐 Authorization header: {masked_auth}")
            else:
                print(f"🔓 No Authorization header present")
        else:
            print(f"🔓 No request context available for Authorization header logging")
        
        # Get tool-specific configuration
        config = get_tool_config("list_private_repos")
        
        # Get session ID for tracking
        session_id = getattr(ctx.request_context.session, 'session_id', 'unknown')
        
        # Check if we're in INSECURE mode
        import os
        insecure_mode = os.getenv("INSECURE", "false").lower() in ("true", "1", "yes")
        
        github_token = None
        needs_elicitation = False
        
        if insecure_mode:
            # INSECURE mode: Check service-specific authentication state
            print(f"🔓 INSECURE mode: Checking GitHub authentication state for session {session_id}")
            
            if elicitation_manager.is_session_authenticated_for_service(session_id, "github"):
                print(f"✅ Session already authenticated for GitHub service")
                # No token needed - agentgateway will inject it
            else:
                print(f"⚠️ Session not authenticated for GitHub service - initiating elicitation")
                needs_elicitation = True
        else:
            # SECURE mode: Check for actual tokens (existing behavior)
            print(f"🔒 SECURE mode: Checking for GitHub token")
            
            try:
                # Try to initialize GitHub client with existing token sources
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
                for elicitation_id, metadata in elicitation_manager.elicitations_map.items():
                    if (metadata.session_id == session_id and 
                        metadata.status == "complete" and 
                        metadata.token_validated):
                        github_token = metadata.collected_token
                        print(f"✅ Using token from completed elicitation: {elicitation_id}")
                        break
            
            # If no valid token, initiate elicitation
            if not github_token:
                needs_elicitation = True
        
        # Initiate elicitation if needed
        if needs_elicitation:
            # Create and track the elicitation
            elicitation_id = elicitation_manager.generate_tracked_elicitation(
                session_id,
                "GitHub token collection for repository access"
            )
            
            # Use elicitation manager to get the appropriate URL (local or external)
            token_url = elicitation_manager.get_elicitation_url(elicitation_id)
            print(f"🔗 Generated elicitation URL: {token_url}")
            
            # Use URL elicitation to direct user to token collection form
            result = await ctx.elicit_url(
                message="Please provide your GitHub Personal Access Token to access private repositories. This token will only be used for this session and will not be saved.",
                url=token_url,
                elicitationId=elicitation_id,
            )
            
            if result.action == "accept":
                print(f"✅ User accepted GitHub token elicitation: {elicitation_id}")
                
                # Check elicitation status
                metadata = elicitation_manager.get_elicitation(elicitation_id)
                if metadata and metadata.status == "complete":
                    # Local form was completed with token
                    if insecure_mode:
                        # INSECURE mode: Mark service as authenticated (no token needed)
                        elicitation_manager.mark_session_authenticated_for_service(session_id, "github", elicitation_id)
                        print(f"✅ GitHub service authenticated for session (INSECURE mode)")
                    else:
                        # SECURE mode: Use the collected token
                        github_token = elicitation_manager.get_collected_token(elicitation_id)
                        if github_token:
                            print(f"✅ GitHub token already collected and validated")
                        else:
                            return json.dumps({
                                "error": "Token Collection Failed",
                                "message": "No valid token was collected during the elicitation process"
                            })
                elif metadata and metadata.status == "accepted":
                    # External portal accepted
                    if insecure_mode:
                        # INSECURE mode: Mark service as authenticated (no token needed)
                        elicitation_manager.mark_session_authenticated_for_service(session_id, "github", elicitation_id)
                        print(f"✅ GitHub service authenticated via external portal (INSECURE mode)")
                    else:
                        # SECURE mode: Proceed without token (agentgateway will inject)
                        print(f"✅ External portal accepted elicitation - proceeding with agentgateway token injection")
                else:
                    # Return pending status - user needs to complete the form/portal
                    return json.dumps({
                        "status": "pending",
                        "message": f"Please complete the token collection at: {token_url}",
                        "elicitation_id": elicitation_id,
                        "url": token_url,
                        "instructions": "After completing the authentication, call this tool again to list repositories"
                    })
            elif result.action == "decline":
                # Check if external portal declined
                metadata = elicitation_manager.get_elicitation(elicitation_id)
                if metadata and metadata.status == "declined":
                    return json.dumps({
                        "error": "Access Denied",
                        "message": "GitHub token collection was declined by external portal"
                    })
                else:
                    return json.dumps({
                        "error": "Access Denied",
                        "message": "GitHub token collection was declined by user"
                    })
            else:  # cancel
                # Check if external portal cancelled
                metadata = elicitation_manager.get_elicitation(elicitation_id)
                if metadata and metadata.status == "cancelled":
                    return json.dumps({
                        "error": "Access Cancelled",
                        "message": "GitHub token collection was cancelled by external portal"
                    })
                else:
                    return json.dumps({
                        "error": "Access Cancelled",
                        "message": "GitHub token collection was cancelled by user"
                    })
        
        # Initialize GitHub client
        if insecure_mode:
            # INSECURE mode: Extract JWT from Authorization header
            jwt_token = None
            if hasattr(ctx.request_context, 'request') and hasattr(ctx.request_context.request, 'headers'):
                auth_header = ctx.request_context.request.headers.get("authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    jwt_token = auth_header[7:]  # Remove "Bearer " prefix
                    print(f"🔓 Extracted JWT from Authorization header for INSECURE mode: {jwt_token[:20]}...")
                else:
                    print(f"⚠️ No Bearer token found in Authorization header for INSECURE mode")
                    print(f"⚠️ Auth header was: {auth_header}")
            
            print(f"🔓 Initializing GitHub client in INSECURE mode with JWT: {jwt_token[:20] if jwt_token else 'None'}...")
            client = GitHubClient(access_token=jwt_token, insecure=True)
        else:
            # SECURE mode: Use the token (either existing or elicited)
            print(f"🔒 Initializing GitHub client with token")
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
