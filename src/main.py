#!/usr/bin/env python3
"""multi-tenant-github-mcp MCP server with dynamic tool loading.

This server automatically discovers and loads tools from the src/tools/ directory.
Each tool file should contain a function decorated with @mcp.tool().

Usage Examples:
  # Stdio mode (default MCP transport)
  python src/main.py
  
  # HTTP mode with MCP protocol over HTTP
  python src/main.py --transport http
  
  # Streamable HTTP mode (enables custom routes + MCP protocol)
  python src/main.py --transport streamable-http
  
  # Enable reading GitHub token from access.token file (CLI flag)
  python src/main.py --access-token-file
  
  # Enable reading GitHub token from access.token file (env var)
  ACCESS_TOKEN_FILE_ENABLED=true python src/main.py
  
  # Streamable HTTP with file-based token support
  python src/main.py --transport streamable-http --access-token-file
  
  # Custom host/port
  python src/main.py --transport http --host localhost --port 8080
  
  # Environment variable mode
  MCP_TRANSPORT_MODE=streamable-http ACCESS_TOKEN_FILE_ENABLED=true python src/main.py
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

from core.server import DynamicMCPServer  # noqa: E402


def main() -> None:
    """Main entry point for the MCP server."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="multi-tenant-github-mcp MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "streamable-http"],
        default="stdio",
        help="Transport mode: stdio, http, or streamable-http"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "localhost"),
        help="Host to bind to in HTTP mode (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "3000")),
        help="Port to bind to in HTTP mode (default: 3000)"
    )
    parser.add_argument(
        "--access-token-file",
        action="store_true",
        help="Enable reading GitHub token from access.token file (can also be set via ACCESS_TOKEN_FILE_ENABLED env var)"
    )

    args = parser.parse_args()

    # Check environment variable for transport mode
    transport_mode = os.getenv("MCP_TRANSPORT_MODE", args.transport)
    
    # Check environment variable for access token file setting
    access_token_file_enabled = args.access_token_file or os.getenv("ACCESS_TOKEN_FILE_ENABLED", "false").lower() in ("true", "1", "yes")

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr)
        ]
    )

    try:
        # Create server with dynamic tool loading
        server = DynamicMCPServer(
            name="multi-tenant-github-mcp",
            tools_dir="src/tools",
            access_token_file_enabled=access_token_file_enabled
        )

        # Load tools and start server
        server.load_tools()

        if transport_mode not in ["http", "stdio", "streamable-http"]:
            raise ValueError(f"Invalid transport mode: {transport_mode}. Must be one of: http, stdio, or streamable-http")
        
        server.run(transport_mode=transport_mode, host=args.host, port=args.port)

    except KeyboardInterrupt:
        print("\nShutting down server...")
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
