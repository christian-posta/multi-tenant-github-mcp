"""GitHub API client with OAuth support."""

import time
from typing import List, Dict, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config


class GitHubAPIError(Exception):
    """Custom exception for GitHub API errors."""
    pass


class GitHubClient:
    """OAuth-enabled GitHub API client."""
    
    def __init__(self, access_token: Optional[str] = None, api_url: Optional[str] = None, insecure: Optional[bool] = None, allow_file: bool = False):
        """Initialize GitHub client with access token, custom API URL, and insecure mode."""
        self.insecure = insecure if insecure is not None else Config.INSECURE
        if not self.insecure:
            # SECURE mode: Use Config.get_access_token for token validation
            self.access_token = Config.get_access_token(access_token, allow_file)
        else:
            # INSECURE mode: Use the token directly (could be JWT from request)
            self.access_token = access_token
        self.api_url = api_url or Config.GITHUB_API_BASE_URL
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """Create a configured requests session with retries."""
        session = requests.Session()
        
        # Configure retries
        retry_strategy = Retry(
            total=Config.MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set default headers
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "multi-tenant-github-mcp/0.1.0",
        }
        
        # Add Authorization header if we have a token (regardless of insecure mode)
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
            print(f"✅ Attaching Authorization header: {self.access_token}")
        else:
            print(f"🔓 No Authorization header attached")
        
        session.headers.update(headers)
        
        return session
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Make authenticated request to GitHub API."""
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.get(url, params=params, timeout=Config.TIMEOUT)
            
            # Handle rate limiting
            if response.status_code == 429:
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                current_time = int(time.time())
                sleep_time = max(1, reset_time - current_time)
                
                raise GitHubAPIError(
                    f"Rate limit exceeded. Reset in {sleep_time} seconds. "
                    f"Try again after {time.ctime(reset_time)}"
                )
            
            # Handle other HTTP errors
            if not response.ok:
                error_msg = f"GitHub API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_msg += f" - {error_data['message']}"
                except:
                    pass
                
                raise GitHubAPIError(error_msg)
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise GitHubAPIError(f"Request failed: {str(e)}")
    
    def _paginate_request(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict[Any, Any]]:
        """Handle paginated GitHub API requests."""
        if params is None:
            params = {}
        
        params.setdefault('per_page', Config.DEFAULT_PER_PAGE)
        params.setdefault('page', 1)
        
        all_items = []
        
        while True:
            data = self._make_request(endpoint, params)
            
            if not data:
                break
            
            all_items.extend(data)
            
            # Check if we have more pages
            if len(data) < params['per_page']:
                break
            
            params['page'] += 1
        
        return all_items
    
    def validate_token(self) -> Dict[str, Any]:
        """Validate the access token and return user information."""
        return self._make_request("/user")
    
    def list_repositories(self, repo_type: str = "all", sort: str = "updated") -> List[Dict[str, Any]]:
        """
        List all repositories for the authenticated user.
        
        Args:
            repo_type: Type of repositories to fetch ('all', 'owner', 'public', 'private', 'member')
            sort: Sort order ('created', 'updated', 'pushed', 'full_name')
        
        Returns:
            List of repository dictionaries
        """
        valid_types = ['all', 'owner', 'public', 'private', 'member']
        if repo_type not in valid_types:
            raise ValueError(f"repo_type must be one of: {', '.join(valid_types)}")
        
        valid_sorts = ['created', 'updated', 'pushed', 'full_name']
        if sort not in valid_sorts:
            raise ValueError(f"sort must be one of: {', '.join(valid_sorts)}")
        
        params = {
            'type': repo_type,
            'sort': sort,
            'direction': 'desc'
        }
        
        return self._paginate_request("/user/repos", params)
    
    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get details for a specific repository."""
        return self._make_request(f"/repos/{owner}/{repo}")
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        return self._make_request("/rate_limit")
