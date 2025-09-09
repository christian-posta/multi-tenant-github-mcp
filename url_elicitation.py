#!/usr/bin/env python3
"""
URL Elicitation Example - Streamable HTTP Server

This example demonstrates how to use URL elicitation in FastMCP to handle
sensitive interactions like OAuth flows, payment confirmation, and API key collection.

The server provides tools that require user interaction via external URLs,
demonstrating the secure out-of-band interaction pattern described in SEP-1036.

This version uses streamable HTTP transport for easier testing and demonstration.
"""

import asyncio
import uuid
import os
from typing import Any, Dict
from datetime import datetime, timedelta
import threading
import time

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession
from mcp.shared.exceptions import ElicitationRequiredError
from mcp.types import ElicitRequestParams


# Create the FastMCP server
mcp = FastMCP(name="URL Elicitation Example Server", host="0.0.0.0", port=8000)

# Elicitation tracking infrastructure (like TypeScript example)
class ElicitationMetadata:
    def __init__(self, session_id: str, message: str = "In progress"):
        self.status: str = "pending"
        self.progress: int = 0
        self.completed_promise: asyncio.Future = asyncio.Future()
        self.created_at: datetime = datetime.now()
        self.session_id: str = session_id
        self.message: str = message
        self.progress_token: str | None = None
        self.notification_sender: Any = None

# Global state for tracking elicitations
elicitations_map: Dict[str, ElicitationMetadata] = {}
ELICITATION_TTL_HOURS = 1
CLEANUP_INTERVAL_MINUTES = 10

def cleanup_old_elicitations():
    """Clean up old elicitations to prevent memory leaks."""
    now = datetime.now()
    expired_ids = []
    
    for elicitation_id, metadata in elicitations_map.items():
        if now - metadata.created_at > timedelta(hours=ELICITATION_TTL_HOURS):
            expired_ids.append(elicitation_id)
    
    for elicitation_id in expired_ids:
        del elicitations_map[elicitation_id]
        print(f"Cleaned up expired elicitation: {elicitation_id}")

def generate_tracked_elicitation(session_id: str, message: str = "In progress") -> str:
    """Create and track a new elicitation."""
    elicitation_id = str(uuid.uuid4())
    
    metadata = ElicitationMetadata(session_id, message)
    elicitations_map[elicitation_id] = metadata
    
    return elicitation_id

def update_elicitation_progress(elicitation_id: str, message: str | None = None):
    """Update the progress of an elicitation."""
    metadata = elicitations_map.get(elicitation_id)
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

def complete_elicitation(elicitation_id: str, message: str | None = None):
    """Complete an elicitation."""
    metadata = elicitations_map.get(elicitation_id)
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
        metadata.completed_promise.set_result(None)

# Set up periodic cleanup
def start_cleanup_thread():
    """Start background thread for cleanup."""
    def cleanup_loop():
        while True:
            time.sleep(CLEANUP_INTERVAL_MINUTES * 60)
            cleanup_old_elicitations()
    
    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    return thread

# Add API key form endpoints directly to FastMCP server
@mcp.custom_route("/api-key-form", methods=["GET"])
async def api_key_form_get(request):
    """Serve the API key collection form."""
    from fastapi.responses import HTMLResponse
    
    service_name = request.query_params.get("service")
    elicitation_id = request.query_params.get("id")
    
    if not service_name or not elicitation_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Missing required parameters")
    
    # Update progress
    update_elicitation_progress(elicitation_id, f"Waiting for you to submit your {service_name} API key...")
    
    # Serve HTML form (like TypeScript example)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Submit Your API Key</title>
        <style>
            body {{ font-family: sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; }}
            input[type="text"] {{ width: 100%; padding: 8px; margin: 10px 0; box-sizing: border-box; }}
            button {{ background: #007bff; color: white; padding: 10px 20px; border: none; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
            .user {{ background: #d1ecf1; padding: 8px; margin-bottom: 10px; }}
            .info {{ color: #666; font-size: 0.9em; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <h1>API Key Required</h1>
        <div class="user">✓ Demo mode (no authentication required)</div>
        <form method="POST" action="/api-key-form">
            <input type="hidden" name="elicitation" value="{elicitation_id}" />
            <input type="hidden" name="service" value="{service_name}" />
            <label>API Key for {service_name}:<br>
                <input type="text" name="apiKey" required placeholder="Enter your {service_name} API key" />
            </label>
            <button type="submit">Submit</button>
        </form>
        <div class="info">This is a demo showing how a server can elicit sensitive data from a user.</div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@mcp.custom_route("/api-key-form", methods=["POST"])
async def api_key_form_post(request):
    """Handle API key form submission."""
    from fastapi import HTTPException
    from fastapi.responses import HTMLResponse
    
    form_data = await request.form()
    service = form_data.get("service")
    apiKey = form_data.get("apiKey")
    elicitation = form_data.get("elicitation")
    
    print(f"🔍 API Key form data received: {dict(form_data)}")  # Debug logging
    print(f"🔍 Parsed values: service={service}, apiKey={apiKey}, elicitation={elicitation}")
    
    if not service or not apiKey or not elicitation:
        missing = []
        if not service: missing.append("service")
        if not apiKey: missing.append("apiKey")
        if not elicitation: missing.append("elicitation")
        print(f"❌ Missing parameters: {missing}")
        raise HTTPException(status_code=400, detail=f"Missing required parameters: {', '.join(missing)}")
    
    # Log the received API key
    print(f"🔑 Received API key {apiKey} for service {service}")
    
    # Complete the elicitation
    complete_elicitation(elicitation, "API key received")
    
    # Send success response
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Success</title>
        <style>
            body {{ font-family: sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; text-align: center; }}
            .success {{ background: #d4edda; color: #155724; padding: 20px; margin: 20px 0; }}
        </style>
    </head>
    <body>
        <div class="success">
            <h1>Success ✓</h1>
            <p>API key received for {service}.</p>
        </div>
        <p>You can close this window and return to your MCP client.</p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Add payment confirmation form endpoint
@mcp.custom_route("/confirm-payment", methods=["GET"])
async def payment_confirmation_get(request):
    """Serve the payment confirmation form."""
    from fastapi.responses import HTMLResponse
    
    amount = request.query_params.get("amount", "0.00")
    currency = request.query_params.get("currency", "USD")
    elicitation_id = request.query_params.get("id")
    
    if not elicitation_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Missing elicitation ID")
    
    # Update progress
    update_elicitation_progress(elicitation_id, "Waiting for payment confirmation...")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Confirm Payment</title>
        <style>
            body {{ font-family: sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; }}
            .payment-info {{ background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 5px; }}
            button {{ background: #28a745; color: white; padding: 10px 20px; border: none; cursor: pointer; margin: 5px; }}
            button:hover {{ background: #218838; }}
            .cancel {{ background: #dc3545; }}
            .cancel:hover {{ background: #c82333; }}
        </style>
    </head>
    <body>
        <h1>Confirm Payment</h1>
        <div class="payment-info">
            <h3>Payment Details</h3>
            <p><strong>Amount:</strong> {amount} {currency}</p>
            <p><strong>Status:</strong> Pending confirmation</p>
        </div>
        <form method="POST" action="/confirm-payment" style="display: inline;">
            <input type="hidden" name="elicitation" value="{elicitation_id}" />
            <input type="hidden" name="amount" value="{amount}" />
            <input type="hidden" name="currency" value="{currency}" />
            <input type="hidden" name="action" value="confirm" />
            <button type="submit">Confirm Payment</button>
        </form>
        <form method="POST" action="/confirm-payment" style="display: inline;">
            <input type="hidden" name="elicitation" value="{elicitation_id}" />
            <input type="hidden" name="amount" value="{amount}" />
            <input type="hidden" name="currency" value="{currency}" />
            <input type="hidden" name="action" value="cancel" />
            <button type="submit" class="cancel">Cancel</button>
        </form>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@mcp.custom_route("/confirm-payment", methods=["POST"])
async def payment_confirmation_post(request):
    """Handle payment confirmation."""
    from fastapi import HTTPException
    from fastapi.responses import HTMLResponse
    
    form_data = await request.form()
    print(f"🔍 Form data received: {dict(form_data)}")  # Debug logging
    elicitation = form_data.get("elicitation")
    amount = form_data.get("amount")
    currency = form_data.get("currency")
    action = form_data.get("action")
    
    print(f"🔍 Parsed values: elicitation={elicitation}, amount={amount}, currency={currency}, action={action}")  # Debug logging
    print(f"🔍 Validation checks:")
    print(f"  - elicitation: {bool(elicitation)} (value: '{elicitation}')")
    print(f"  - amount: {bool(amount)} (value: '{amount}')")
    print(f"  - currency: {bool(currency)} (value: '{currency}')")
    print(f"  - action: {bool(action)} (value: '{action}')")
    
    if not elicitation or not amount or not currency or not action:
        missing = []
        if not elicitation: missing.append("elicitation")
        if not amount: missing.append("amount")
        if not currency: missing.append("currency")
        if not action: missing.append("action")
        print(f"❌ Missing parameters: {missing}")
        raise HTTPException(status_code=400, detail=f"Missing required parameters: {', '.join(missing)}")
    
    if action == "confirm":
        print(f"💳 Payment confirmed: {amount} {currency}")
        complete_elicitation(elicitation, f"Payment confirmed: {amount} {currency}")
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Payment Confirmed</title>
            <style>
                body { font-family: sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; text-align: center; }
                .success { background: #d4edda; color: #155724; padding: 20px; margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="success">
                <h1>Payment Confirmed ✓</h1>
                <p>Your payment has been processed successfully.</p>
            </div>
            <p>You can close this window and return to your MCP client.</p>
        </body>
        </html>
        """
    else:  # cancel
        print(f"💳 Payment cancelled: {amount} {currency}")
        complete_elicitation(elicitation, "Payment cancelled")
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Payment Cancelled</title>
            <style>
                body { font-family: sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; text-align: center; }
                .cancelled { background: #f8d7da; color: #721c24; padding: 20px; margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="cancelled">
                <h1>Payment Cancelled</h1>
                <p>Your payment has been cancelled.</p>
            </div>
            <p>You can close this window and return to your MCP client.</p>
        </body>
        </html>
        """
    
    return HTMLResponse(content=html_content)


async def oauth_authorize(
    provider: str, 
    scope: str, 
    ctx: Context[ServerSession, None]
) -> str:
    """
    Simulate an OAuth authorization flow that requires user interaction.
    This version demonstrates progress tracking.
    
    Args:
        provider: The OAuth provider (e.g., "github", "google")
        scope: The requested scope (e.g., "repo", "user:email")
        ctx: The FastMCP context
    """
    # Get session ID for tracking
    session_id = getattr(ctx.request_context.session, 'session_id', 'unknown')
    
    # Create and track the elicitation
    elicitation_id = generate_tracked_elicitation(
        session_id, 
        f"OAuth authorization for {provider}"
    )
    
    # Simulate OAuth URL (in real implementation, this would be a proper OAuth URL)
    oauth_url = f"https://{provider}.com/oauth/authorize?client_id=demo&scope={scope}&state={elicitation_id}"
    
    # Simulate OAuth callback after 5 seconds
    def simulate_oauth_callback():
        time.sleep(5)
        print(f"Simulating OAuth callback for elicitation {elicitation_id}")
        update_elicitation_progress(elicitation_id, "Received OAuth callback")
        
        # Simulate token received after another 5 seconds
        time.sleep(5)
        print(f"Simulating OAuth token received for elicitation {elicitation_id}")
        complete_elicitation(elicitation_id, "Received OAuth token(s)")
    
    # Start simulation in background
    threading.Thread(target=simulate_oauth_callback, daemon=True).start()
    
    # Use URL elicitation to direct user to OAuth provider
    result = await ctx.elicit_url(
        message=f"Please authorize access to your {provider} account with scope '{scope}' to continue.",
        url=oauth_url,
        elicitationId=elicitation_id,
    )
    
    if result.action == "accept":
        return f"OAuth authorization initiated for {provider} with scope '{scope}'. Elicitation ID: {elicitation_id}"
    elif result.action == "decline":
        return "OAuth authorization declined by user."
    else:
        return "OAuth authorization cancelled by user."


@mcp.tool(description="Simulate payment confirmation")
async def confirm_payment(
    amount: float, 
    currency: str, 
    description: str,
    ctx: Context[ServerSession, None]
) -> str:
    """
    Simulate a payment confirmation flow that requires user interaction.
    
    Args:
        amount: The payment amount
        currency: The currency code (e.g., "USD", "EUR")
        description: Description of what is being purchased
        ctx: The FastMCP context
    """
    elicitation_id = str(uuid.uuid4())
    
    # Debug logging
    print(f"💳 confirm_payment called with: amount={amount}, currency='{currency}', description='{description}'")
    
    # Use local server URL for payment confirmation (like TypeScript example)
    payment_url = f"http://localhost:8000/confirm-payment?amount={amount}&currency={currency}&id={elicitation_id}"
    print(f"🔗 Generated payment URL: {payment_url}")
    
    result = await ctx.elicit_url(
        message=f"Please confirm payment of {amount} {currency} for: {description}",
        url=payment_url,
        elicitationId=elicitation_id,
    )
    
    if result.action == "accept":
        return f"Payment confirmation initiated for {amount} {currency}. Elicitation ID: {elicitation_id}"
    elif result.action == "decline":
        return "Payment confirmation declined by user."
    else:
        return "Payment confirmation cancelled by user."


@mcp.tool(description="Collect API key securely")
async def collect_api_key(
    service_name: str,
    ctx: Context[ServerSession, None]
) -> str:
    """
    Collect an API key securely via external form.
    
    Args:
        service_name: The name of the service requiring the API key
        ctx: The FastMCP context
    """
    elicitation_id = str(uuid.uuid4())
    
    # Debug logging
    print(f"🔑 collect_api_key called with: service_name='{service_name}'")
    
    # Use local server URL for API key collection (like TypeScript example)
    api_key_url = f"http://localhost:8000/api-key-form?service={service_name}&id={elicitation_id}"
    print(f"🔗 Generated API key URL: {api_key_url}")
    
    result = await ctx.elicit_url(
        message=f"Please provide your {service_name} API key securely. This will not be visible to the MCP client.",
        url=api_key_url,
        elicitationId=elicitation_id,
    )
    
    if result.action == "accept":
        return f"API key collection initiated for {service_name}. Elicitation ID: {elicitation_id}"
    elif result.action == "decline":
        return "API key collection declined by user."
    else:
        return "API key collection cancelled by user."


@mcp.tool(description="Demonstrate ElicitationRequiredError")
async def require_elicitation(
    ctx: Context[ServerSession, None]
) -> str:
    """
    Demonstrate how to use ElicitationRequiredError to indicate that
    a request cannot be processed until an elicitation is completed.
    """
    elicitation_id = str(uuid.uuid4())
    
    # Create elicitation parameters
    elicit_params = ElicitRequestParams(
        mode="url",
        message="This tool requires additional authorization. Please complete the authorization flow.",
        elicitationId=elicitation_id,
        url=f"https://auth.example.com/authorize?id={elicitation_id}",
    )
    
    # Raise ElicitationRequiredError - this is equivalent to sending an elicitation/create request
    raise ElicitationRequiredError([elicit_params])


@mcp.tool(description="Collect API key securely with progress tracking")
async def collect_api_key(
    service_name: str,
    ctx: Context[ServerSession, None]
) -> str:
    """
    Collect an API key securely via external form with progress tracking.
    
    Args:
        service_name: The name of the service requiring the API key
        ctx: The FastMCP context
    """
    # Get session ID for tracking
    session_id = getattr(ctx.request_context.session, 'session_id', 'unknown')
    
    # Create and track the elicitation
    elicitation_id = generate_tracked_elicitation(
        session_id,
        f"API key collection for {service_name}"
    )
    
    # Use local server URL for API key collection (like TypeScript example)
    api_key_url = f"http://localhost:8000/api-key-form?session={session_id}&elicitation={elicitation_id}"
    
    result = await ctx.elicit_url(
        message=f"Please provide your {service_name} API key securely. This will not be visible to the MCP client.",
        url=api_key_url,
        elicitationId=elicitation_id,
    )
    
    if result.action == "accept":
        return f"API key collection initiated for {service_name}. Elicitation ID: {elicitation_id}"
    elif result.action == "decline":
        return "API key collection declined by user."
    else:
        return "API key collection cancelled by user."


@mcp.tool(description="Compare form vs URL elicitation")
async def compare_elicitation_modes(
    ctx: Context[ServerSession, None]
) -> str:
    """
    Demonstrate both form and URL elicitation modes.
    """
    # First, try form elicitation
    from pydantic import BaseModel, Field
    
    class UserInfo(BaseModel):
        name: str = Field(description="Your name")
        email: str = Field(description="Your email address")
    
    form_result = await ctx.elicit(
        message="Please provide your basic information:",
        schema=UserInfo,
    )
    
    if form_result.action != "accept":
        return "Form elicitation was not completed."
    
    # Then, try URL elicitation
    elicitation_id = str(uuid.uuid4())
    url_result = await ctx.elicit_url(
        message="Now please verify your identity via our secure portal:",
        url=f"https://verify.example.com/identity?id={elicitation_id}",
        elicitationId=elicitation_id,
    )
    
    if url_result.action == "accept":
        return f"Both elicitations completed successfully! Form data: {form_result.data}, URL elicitation ID: {elicitation_id}"
    else:
        return f"Form elicitation completed, but URL elicitation was {url_result.action}."


if __name__ == "__main__":
    # Start cleanup thread
    start_cleanup_thread()
    
    print("🚀 Starting URL Elicitation Server...")
    print("📋 Available tools:")
    print("   - oauth_authorize: OAuth authorization with progress tracking")
    print("   - confirm_payment: Payment confirmation")
    print("   - collect_api_key: API key collection with progress tracking")
    print("   - require_elicitation: Demonstrates ElicitationRequiredError")
    print("   - compare_elicitation_modes: Form vs URL elicitation comparison")
    print()
    print("🌐 MCP Server will be available at: http://localhost:8000/mcp")
    print("📝 API key form will be available at: http://localhost:8000/api-key-form")
    print("💳 Payment confirmation will be available at: http://localhost:8000/confirm-payment")
    print()
    
    # Run FastMCP with streamable HTTP transport
    mcp.run("streamable-http")