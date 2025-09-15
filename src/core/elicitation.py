"""Elicitation management for multi-tenant-github-mcp MCP server.

This module provides infrastructure for managing URL elicitations,
including GitHub token collection flows.
"""

import asyncio
import uuid
import threading
import time
from typing import Any, Dict, Optional
from datetime import datetime, timedelta


class ElicitationMetadata:
    """Metadata for tracking elicitation sessions."""
    
    def __init__(self, session_id: str, message: str = "In progress"):
        self.status: str = "pending"
        self.progress: int = 0
        self.completed_promise: asyncio.Future = asyncio.Future()
        self.created_at: datetime = datetime.now()
        self.session_id: str = session_id
        self.message: str = message
        self.progress_token: Optional[str] = None
        self.notification_sender: Optional[Any] = None
        # Memory-only token storage
        self.collected_token: Optional[str] = None
        self.token_validated: bool = False


class ElicitationManager:
    """Manages elicitation sessions and token collection."""
    
    def __init__(self):
        self.elicitations_map: Dict[str, ElicitationMetadata] = {}
        self.ELICITATION_TTL_HOURS = 1
        self.CLEANUP_INTERVAL_MINUTES = 10
        # Service-specific authentication state per session
        self.session_service_auth: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """Start background thread for cleanup."""
        def cleanup_loop():
            while True:
                time.sleep(self.CLEANUP_INTERVAL_MINUTES * 60)
                self.cleanup_old_elicitations()
        
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
        return thread
    
    def cleanup_old_elicitations(self):
        """Clean up old elicitations to prevent memory leaks."""
        now = datetime.now()
        expired_ids = []
        
        for elicitation_id, metadata in self.elicitations_map.items():
            if now - metadata.created_at > timedelta(hours=self.ELICITATION_TTL_HOURS):
                expired_ids.append(elicitation_id)
        
        for elicitation_id in expired_ids:
            del self.elicitations_map[elicitation_id]
            print(f"Cleaned up expired elicitation: {elicitation_id}")
    
    def generate_tracked_elicitation(self, session_id: str, message: str = "In progress") -> str:
        """Create and track a new elicitation."""
        elicitation_id = str(uuid.uuid4())
        
        metadata = ElicitationMetadata(session_id, message)
        self.elicitations_map[elicitation_id] = metadata
        
        print(f"🔍 Generated elicitation: {elicitation_id} for session: {session_id}")
        return elicitation_id
    
    def update_elicitation_progress(self, elicitation_id: str, message: Optional[str] = None):
        """Update the progress of an elicitation."""
        metadata = self.elicitations_map.get(elicitation_id)
        if not metadata:
            print(f"Warning: Attempted to update unknown elicitation: {elicitation_id}")
            return
        
        if metadata.status == "complete":
            print(f"Warning: Elicitation already complete: {elicitation_id}")
            return
        
        if message:
            metadata.message = message
        
        metadata.progress += 1
        
        # Send progress notification if we have a progress token and notification sender
        if metadata.progress_token and metadata.notification_sender:
            try:
                metadata.notification_sender({
                    "method": "notifications/progress",
                    "params": {
                        "progressToken": metadata.progress_token,
                        "progress": metadata.progress,
                        "message": metadata.message,
                    },
                })
            except Exception as e:
                print(f"Error sending progress notification: {e}")
    
    def complete_elicitation(self, elicitation_id: str, message: Optional[str] = None, token: Optional[str] = None):
        """Complete an elicitation with optional token."""
        metadata = self.elicitations_map.get(elicitation_id)
        if not metadata:
            print(f"Warning: Attempted to complete unknown elicitation: {elicitation_id}")
            return
        
        if metadata.status == "complete":
            print(f"Warning: Elicitation already complete: {elicitation_id}")
            return
        
        # Update metadata
        metadata.status = "complete"
        if message:
            metadata.message = message
        if token:
            metadata.collected_token = token
            metadata.token_validated = True
        metadata.progress += 1
        
        # Send final notification
        if metadata.progress_token and metadata.notification_sender:
            try:
                metadata.notification_sender({
                    "method": "notifications/progress",
                    "params": {
                        "progressToken": metadata.progress_token,
                        "progress": metadata.progress,
                        "total": metadata.progress,
                        "message": metadata.message,
                    },
                })
            except Exception as e:
                print(f"Error sending final notification: {e}")
        
        # Resolve the promise to unblock the request handler
        if not metadata.completed_promise.done():
            print(f"🔍 Resolving promise for elicitation: {elicitation_id}")
            metadata.completed_promise.set_result(None)
            print(f"✅ Promise resolved for elicitation: {elicitation_id}")
        else:
            print(f"⚠️ Promise already resolved for elicitation: {elicitation_id}")
    
    def get_elicitation(self, elicitation_id: str) -> Optional[ElicitationMetadata]:
        """Get elicitation metadata by ID."""
        return self.elicitations_map.get(elicitation_id)
    
    def get_collected_token(self, elicitation_id: str) -> Optional[str]:
        """Get collected token from completed elicitation."""
        metadata = self.elicitations_map.get(elicitation_id)
        if metadata and metadata.status == "complete" and metadata.token_validated:
            return metadata.collected_token
        return None
    
    def accept_elicitation(self, elicitation_id: str, message: Optional[str] = None):
        """Accept an elicitation (for external portal callbacks)."""
        metadata = self.elicitations_map.get(elicitation_id)
        if not metadata:
            print(f"Warning: Attempted to accept unknown elicitation: {elicitation_id}")
            return
        
        if metadata.status in ["complete", "accepted", "declined", "cancelled"]:
            print(f"Warning: Elicitation already processed: {elicitation_id} (status: {metadata.status})")
            return
        
        # Update metadata
        metadata.status = "accepted"
        if message:
            metadata.message = message
        metadata.progress += 1
        
        # Resolve the promise to unblock the request handler
        if not metadata.completed_promise.done():
            print(f"🔍 Resolving promise for accepted elicitation: {elicitation_id}")
            metadata.completed_promise.set_result(None)
            print(f"✅ Promise resolved for accepted elicitation: {elicitation_id}")
        else:
            print(f"⚠️ Promise already resolved for elicitation: {elicitation_id}")
    
    def decline_elicitation(self, elicitation_id: str, message: Optional[str] = None):
        """Decline an elicitation (for external portal callbacks)."""
        metadata = self.elicitations_map.get(elicitation_id)
        if not metadata:
            print(f"Warning: Attempted to decline unknown elicitation: {elicitation_id}")
            return
        
        if metadata.status in ["complete", "accepted", "declined", "cancelled"]:
            print(f"Warning: Elicitation already processed: {elicitation_id} (status: {metadata.status})")
            return
        
        # Update metadata
        metadata.status = "declined"
        if message:
            metadata.message = message
        metadata.progress += 1
        
        # Resolve the promise to unblock the request handler
        if not metadata.completed_promise.done():
            print(f"🔍 Resolving promise for declined elicitation: {elicitation_id}")
            metadata.completed_promise.set_result(None)
            print(f"✅ Promise resolved for declined elicitation: {elicitation_id}")
        else:
            print(f"⚠️ Promise already resolved for elicitation: {elicitation_id}")
    
    def cancel_elicitation(self, elicitation_id: str, message: Optional[str] = None):
        """Cancel an elicitation (for external portal callbacks)."""
        metadata = self.elicitations_map.get(elicitation_id)
        if not metadata:
            print(f"Warning: Attempted to cancel unknown elicitation: {elicitation_id}")
            return
        
        if metadata.status in ["complete", "accepted", "declined", "cancelled"]:
            print(f"Warning: Elicitation already processed: {elicitation_id} (status: {metadata.status})")
            return
        
        # Update metadata
        metadata.status = "cancelled"
        if message:
            metadata.message = message
        metadata.progress += 1
        
        # Resolve the promise to unblock the request handler
        if not metadata.completed_promise.done():
            print(f"🔍 Resolving promise for cancelled elicitation: {elicitation_id}")
            metadata.completed_promise.set_result(None)
            print(f"✅ Promise resolved for cancelled elicitation: {elicitation_id}")
        else:
            print(f"⚠️ Promise already resolved for elicitation: {elicitation_id}")
    
    def get_elicitation_url(self, elicitation_id: str) -> str:
        """Get the appropriate elicitation URL based on .env configuration."""
        import os
        external_url = os.getenv("EXTERNAL_PORTAL_URL")
        if external_url:
            # External portal mode - just use the configured URL
            return external_url
        else:
            # Local form mode (existing behavior)
            return f"http://localhost:8000/github-token-form?id={elicitation_id}"
    
    def is_session_authenticated_for_service(self, session_id: str, service: str) -> bool:
        """Check if session is authenticated for a specific service (INSECURE mode only)."""
        if session_id not in self.session_service_auth:
            return False
        
        service_auth = self.session_service_auth[session_id].get(service, {})
        return service_auth.get("authenticated", False)
    
    def mark_session_authenticated_for_service(self, session_id: str, service: str, elicitation_id: str):
        """Mark session as authenticated for a specific service (INSECURE mode only)."""
        if session_id not in self.session_service_auth:
            self.session_service_auth[session_id] = {}
        
        self.session_service_auth[session_id][service] = {
            "authenticated": True,
            "elicitation_id": elicitation_id,
            "authenticated_at": datetime.now()
        }
        
        print(f"✅ Session {session_id} authenticated for service '{service}' via elicitation {elicitation_id}")
    
    def clear_session_auth_for_service(self, session_id: str, service: str):
        """Clear authentication state for a specific service (INSECURE mode only)."""
        if session_id in self.session_service_auth and service in self.session_service_auth[session_id]:
            del self.session_service_auth[session_id][service]
            print(f"🔓 Session {session_id} authentication cleared for service '{service}'")


# Global elicitation manager instance
elicitation_manager = ElicitationManager()
