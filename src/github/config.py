"""Configuration module for GitHub API client."""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for GitHub API client."""
    
    # GitHub API configuration
    GITHUB_API_BASE_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")
    GITHUB_OAUTH_BASE_URL = "https://github.com/login/oauth"
    
    # Insecure mode (skip token authentication)
    INSECURE = os.getenv("INSECURE", "false").lower() in ("true", "1", "yes")
    
    # OAuth Client Configuration (for future OAuth flow implementation)
    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
    
    # OAuth Access Token
    GITHUB_OAUTH_TOKEN = os.getenv("GITHUB_OAUTH_TOKEN")
    
    # API Settings
    DEFAULT_PER_PAGE = 100  # GitHub API max is 100
    MAX_RETRIES = 3
    TIMEOUT = 30
    
    @classmethod
    def get_access_token(cls, token: Optional[str] = None, allow_file: bool = False) -> str:
        """Get OAuth access token from parameter, environment variable, or optionally from file.
        
        Args:
            token: Direct token parameter (highest priority)
            allow_file: Whether to check for access.token file
        """
        if token:
            return token
        
        if cls.GITHUB_OAUTH_TOKEN and cls.GITHUB_OAUTH_TOKEN != "your_oauth_access_token_here":
            return cls.GITHUB_OAUTH_TOKEN
        
        # Only check for access.token file if explicitly allowed
        if allow_file:
            token_file = "access.token"
            if os.path.exists(token_file):
                try:
                    with open(token_file, 'r') as f:
                        file_token = f.read().strip()
                        if file_token and file_token.startswith(('gho_', 'ghp_')):
                            return file_token
                except (IOError, OSError):
                    pass  # Continue to error message
            
        raise ValueError(
            "No OAuth access token provided. Set GITHUB_OAUTH_TOKEN environment variable, "
            "pass token as parameter" + (", or ensure access.token file exists" if allow_file else "") + "."
        )
    
    @classmethod
    def validate_oauth_config(cls) -> bool:
        """Check if OAuth configuration is available."""
        return bool(cls.GITHUB_CLIENT_ID and cls.GITHUB_CLIENT_SECRET)
