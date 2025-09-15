"""Dynamic MCP server implementation with automatic tool discovery.

This server automatically discovers and loads tools from the tools directory.
Each tool file should contain a function decorated with @mcp.tool().
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.session import ServerSession

from .utils import load_config
from .elicitation import elicitation_manager

# Global FastMCP instance for tools to import
mcp: FastMCP = FastMCP(name="Dynamic Server")


class DynamicMCPServer:
    """MCP server with dynamic tool loading capabilities."""

    def __init__(self, name: str, tools_dir: str = "src/tools", access_token_file_enabled: bool = False):
        """Initialize the dynamic MCP server.

        Args:
            name: Server name
            tools_dir: Directory containing tool files
            access_token_file_enabled: Whether to allow reading tokens from access.token file
        """
        global mcp
        self.name = name
        self.tools_dir = Path(tools_dir)
        self.access_token_file_enabled = access_token_file_enabled
        self.config = self._load_config()

        # Load local environment variables if configured
        self._load_local_env()

        # Update global FastMCP instance
        global mcp
        mcp = FastMCP(name=self.name)
        self.mcp = mcp
        
        # Store reference to server instance for tools to access
        mcp._server_instance = self

        # Track loaded tools
        self.loaded_tools: list[str] = []
        
        # Add GitHub token collection routes
        self._add_github_token_routes()

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from kmcp.yaml."""
        return load_config("kmcp.yaml")

    def _load_local_env(self) -> None:
        """Load environment variables from a .env file if it exists."""
        # load_dotenv will search for a .env file and load it.
        # It does not fail if the file is not found.
        if load_dotenv(override=True):
            logging.info("Loaded environment variables from .env file")
    
    def _add_github_token_routes(self):
        """Add GitHub token collection routes to the FastMCP server."""
        
        @self.mcp.custom_route("/github-token-form", methods=["GET"])
        async def github_token_form_get(request):
            """Serve the GitHub token collection form."""
            from fastapi.responses import HTMLResponse
            
            elicitation_id = request.query_params.get("id")
            
            if not elicitation_id:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Missing elicitation ID")
            
            # Update progress
            elicitation_manager.update_elicitation_progress(
                elicitation_id, 
                "Waiting for you to submit your GitHub token..."
            )
            
            # Serve HTML form
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>GitHub Token Required</title>
                <style>
                    body {{ font-family: sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; }}
                    input[type="text"] {{ width: 100%; padding: 8px; margin: 10px 0; box-sizing: border-box; }}
                    button {{ background: #007bff; color: white; padding: 10px 20px; border: none; cursor: pointer; }}
                    button:hover {{ background: #0056b3; }}
                    .info {{ background: #d1ecf1; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
                    .instructions {{ background: #f8f9fa; padding: 15px; margin: 20px 0; border-radius: 5px; }}
                    .warning {{ background: #fff3cd; padding: 10px; margin: 10px 0; border-radius: 5px; }}
                    ol {{ margin: 10px 0; padding-left: 20px; }}
                    li {{ margin: 5px 0; }}
                </style>
            </head>
            <body>
                <h1>GitHub Token Required</h1>
                <div class="info">
                    <strong>✓ Secure Token Collection</strong><br>
                    Your token will be used only for this session and will not be saved.
                </div>
                
                <div class="instructions">
                    <h3>How to get your GitHub token:</h3>
                    <ol>
                        <li>Go to <a href="https://github.com/settings/tokens" target="_blank">GitHub Settings → Personal Access Tokens</a></li>
                        <li>Click "Generate new token (classic)"</li>
                        <li>Give it a name like "MCP Server Access"</li>
                        <li>Select these scopes:
                            <ul>
                                <li><strong>repo</strong> (for private repositories)</li>
                                <li><strong>read:org</strong> (optional, for organization access)</li>
                            </ul>
                        </li>
                        <li>Click "Generate token"</li>
                        <li>Copy the token (starts with ghp_ or gho_)</li>
                    </ol>
                </div>
                
                <form method="POST" action="/github-token-form">
                    <input type="hidden" name="elicitation" value="{elicitation_id}" />
                    <label>GitHub Personal Access Token:<br>
                        <input type="password" name="githubToken" required 
                               placeholder="Enter your GitHub token" 
                               pattern="^(ghp_|gho_|ghu_|ghs_|ghr_).*"
                               title="GitHub token should start with ghp_, gho_, ghu_, ghs_, or ghr_" />
                    </label>
                    <button type="submit">Submit Token</button>
                </form>
                
                <div class="warning">
                    <strong>Security Note:</strong> This token will only be used for this session and will not be stored permanently.
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
        
        @self.mcp.custom_route("/github-token-form", methods=["POST"])
        async def github_token_form_post(request):
            """Handle GitHub token form submission."""
            from fastapi import HTTPException
            from fastapi.responses import HTMLResponse
            
            form_data = await request.form()
            github_token = form_data.get("githubToken")
            elicitation = form_data.get("elicitation")
            
            print(f"🔍 GitHub token form data received: elicitation={elicitation}")
            
            if not github_token or not elicitation:
                missing = []
                if not github_token: missing.append("githubToken")
                if not elicitation: missing.append("elicitation")
                print(f"❌ Missing parameters: {missing}")
                raise HTTPException(status_code=400, detail=f"Missing required parameters: {', '.join(missing)}")
            
            # Validate token format
            if not github_token.startswith(('ghp_', 'gho_', 'ghu_', 'ghs_', 'ghr_')):
                print(f"❌ Invalid token format: {github_token[:10]}...")
                raise HTTPException(status_code=400, detail="Invalid GitHub token format")
            
            # Validate token with GitHub API
            try:
                import requests
                headers = {
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "multi-tenant-github-mcp/0.1.0"
                }
                response = requests.get("https://api.github.com/user", headers=headers, timeout=10)
                
                if response.status_code == 401:
                    print(f"❌ Invalid GitHub token: {github_token[:10]}...")
                    raise HTTPException(status_code=400, detail="Invalid GitHub token - authentication failed")
                elif not response.ok:
                    print(f"❌ GitHub API error: {response.status_code}")
                    raise HTTPException(status_code=400, detail=f"GitHub API error: {response.status_code}")
                
                user_data = response.json()
                print(f"✅ Valid GitHub token for user: {user_data.get('login', 'unknown')}")
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Network error validating token: {e}")
                raise HTTPException(status_code=400, detail="Failed to validate token with GitHub API")
            
            # Complete the elicitation with the validated token
            print(f"🔍 Completing elicitation: {elicitation}")
            print(f"🔍 Available elicitations: {list(elicitation_manager.elicitations_map.keys())}")
            
            elicitation_manager.complete_elicitation(
                elicitation, 
                f"GitHub token validated for user: {user_data.get('login', 'unknown')}",
                github_token
            )
            print(f"✅ Elicitation completed successfully")
            
            # Send success response
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Token Validated</title>
                <style>
                    body {{ font-family: sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; text-align: center; }}
                    .success {{ background: #d4edda; color: #155724; padding: 20px; margin: 20px 0; border-radius: 5px; }}
                    .user-info {{ background: #f8f9fa; padding: 15px; margin: 20px 0; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="success">
                    <h1>Token Validated ✓</h1>
                    <p>Your GitHub token has been successfully validated!</p>
                </div>
                <div class="user-info">
                    <strong>Authenticated as:</strong> {user_data.get('login', 'unknown')}<br>
                    <strong>Name:</strong> {user_data.get('name', 'Not provided')}<br>
                    <strong>Email:</strong> {user_data.get('email', 'Not provided')}
                </div>
                <p>You can close this window and return to your MCP client.</p>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
        
        # Add elicitation callback endpoint for external portals
        @self.mcp.custom_route("/elicitation/callback", methods=["POST"])
        async def elicitation_callback(request):
            """Handle callbacks from external portals."""
            from fastapi import HTTPException
            from fastapi.responses import JSONResponse
            
            try:
                data = await request.json()
                elicitation_id = data.get("elicitation_id")
                action = data.get("action")  # "accept", "decline", or "cancel"
                
                print(f"🔍 Elicitation callback received: elicitation_id={elicitation_id}, action={action}")
                
                if not elicitation_id or not action:
                    missing = []
                    if not elicitation_id: missing.append("elicitation_id")
                    if not action: missing.append("action")
                    print(f"❌ Missing parameters: {missing}")
                    raise HTTPException(status_code=400, detail=f"Missing required parameters: {', '.join(missing)}")
                
                if action not in ["accept", "decline", "cancel"]:
                    print(f"❌ Invalid action: {action}")
                    raise HTTPException(status_code=400, detail="Invalid action. Must be 'accept', 'decline', or 'cancel'")
                
                # Update the elicitation state following MCP spec
                if action == "accept":
                    elicitation_manager.accept_elicitation(elicitation_id, f"External portal accepted elicitation")
                    
                    # In INSECURE mode, also mark the service as authenticated
                    import os
                    insecure_mode = os.getenv("INSECURE", "false").lower() in ("true", "1", "yes")
                    if insecure_mode:
                        # Get the session ID from the elicitation metadata
                        metadata = elicitation_manager.get_elicitation(elicitation_id)
                        if metadata:
                            elicitation_manager.mark_session_authenticated_for_service(
                                metadata.session_id, "github", elicitation_id
                            )
                            print(f"✅ Service authentication marked for session {metadata.session_id} (INSECURE mode)")
                elif action == "decline":
                    elicitation_manager.decline_elicitation(elicitation_id, f"External portal declined elicitation")
                elif action == "cancel":
                    elicitation_manager.cancel_elicitation(elicitation_id, f"External portal cancelled elicitation")
                
                print(f"✅ Elicitation callback processed: {elicitation_id} -> {action}")
                
                return JSONResponse(content={
                    "status": "success",
                    "elicitation_id": elicitation_id,
                    "action": action,
                    "message": f"Elicitation {action}ed successfully"
                })
                
            except Exception as e:
                print(f"❌ Error processing elicitation callback: {e}")
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    def load_tools(self) -> None:
        """Discover and load all tools from the tools directory."""
        if not self.tools_dir.exists():
            print(f"Tools directory {self.tools_dir} does not exist")
            return

        # Find all Python files in tools directory
        tool_files = list(self.tools_dir.glob("*.py"))
        tool_files = [f for f in tool_files if f.name != "__init__.py"]

        if not tool_files:
            logging.warning(f"No tool files found in {self.tools_dir}")
            return

        loaded_count = 0
        has_errors = False

        for tool_file in tool_files:
            try:
                # Get the number of tools before importing
                tools_before = len(mcp._tool_manager._tools)

                # Simply import the module - tools auto-register via @mcp.tool()
                # decorator
                tool_name = tool_file.stem
                if self._import_tool_module(tool_file, tool_name):
                    # Check if any tools were actually registered
                    tools_after = len(mcp._tool_manager._tools)
                    if tools_after > tools_before:
                        self.loaded_tools.append(tool_name)
                        loaded_count += 1
                        logging.info(f"Loaded tool module: {tool_name}")
                    else:
                        logging.error(
                            f"Tool file {tool_name} did not register any tools"
                        )
                        has_errors = True
                else:
                    logging.error(f"Failed to load tool module: {tool_name}")
                    has_errors = True

            except Exception as e:
                logging.error(f"Error loading tool {tool_file.name}: {e}")
                has_errors = True

        # Fail fast - if any tool fails to load, stop the server
        if has_errors:
            sys.exit(1)

        logging.info(f"📦 Successfully loaded {loaded_count} tools")

        if loaded_count == 0:
            logging.warning("No tools loaded. Server starting without tools.")

    def _import_tool_module(self, tool_file: Path, tool_name: str) -> bool:
        """Import a tool module, which auto-registers tools via decorators.

        Args:
            tool_file: Path to the tool file
            tool_name: Name of the tool (same as filename)

        Returns:
            True if module was imported successfully
        """
        try:
            # Ensure src directory is in Python path for imports
            src_dir = tool_file.parent.parent
            if str(src_dir) not in sys.path:
                sys.path.insert(0, str(src_dir))

            # Load the module
            spec = importlib.util.spec_from_file_location(tool_name, tool_file)
            if spec is None or spec.loader is None:
                return False

            module = importlib.util.module_from_spec(spec)

            # Add to sys.modules so it can be imported by other modules
            sys.modules[f"tools.{tool_name}"] = module

            # Set the mcp instance in the module's namespace so tools can access it
            module.mcp = self.mcp
            
            # Execute the module - this will trigger @mcp.tool() decorators
            spec.loader.exec_module(module)

            return True

        except Exception as e:
            print(f"Error importing {tool_file}: {e}")
            return False

    def get_tools_sync(self) -> dict[str, Any]:
        """Get tools synchronously for testing purposes."""
        # This is a simplified version for testing - in real usage, use get_tools()
        # async
        return mcp._tool_manager._tools

    def run(self, transport_mode: str = "stdio", host: str = "localhost", port: int = 3000) -> None:
        """Run the FastMCP server.

        Args:
            transport_mode: Transport mode - "stdio", "http", or "streamable-http"
            host: Host to bind to in HTTP mode
            port: Port to bind to in HTTP mode
        """

        if transport_mode == "http":
            self.mcp.run(transport="http", host=host, port=port, path="/mcp")
        elif transport_mode == "streamable-http":
            # Streamable HTTP mode - enables custom routes alongside MCP protocol
            self.mcp.run("streamable-http")
        elif transport_mode == "stdio":
            # Default to stdio mode
            self.mcp.run()
