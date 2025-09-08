#!/bin/bash

# GitHub OAuth Device Code Flow Script
# This script implements the OAuth 2.0 Device Authorization Grant flow
# to obtain an access token for GitHub API access.

set -e

# Load environment variables from .env file
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Configuration
CLIENT_ID="${GITHUB_CLIENT_ID:-}"
GITHUB_API_URL="https://api.github.com"
GITHUB_OAUTH_URL="https://github.com/login/device/code"
TOKEN_FILE="access.token"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if required tools are available
check_dependencies() {
    local missing_deps=()
    
    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    fi
    
    if ! command -v jq &> /dev/null; then
        missing_deps+=("jq")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing required dependencies: ${missing_deps[*]}"
        print_info "Please install the missing dependencies and try again."
        exit 1
    fi
}

# Function to validate client ID
validate_client_id() {
    if [ -z "$CLIENT_ID" ]; then
        print_error "GITHUB_CLIENT_ID is not set."
        print_info "Please set your GitHub OAuth App Client ID in the .env file:"
        print_info "GITHUB_CLIENT_ID=your_client_id_here"
        print_info ""
        print_info "Or set it as an environment variable:"
        print_info "export GITHUB_CLIENT_ID=your_client_id_here"
        print_info ""
        print_info "To create a GitHub OAuth App:"
        print_info "1. Go to GitHub Settings → Developer settings → OAuth Apps"
        print_info "2. Click 'New OAuth App'"
        print_info "3. Set Authorization callback URL to: http://localhost:3001/github/callback"
        print_info "4. Copy the Client ID and add it to your .env file"
        exit 1
    fi
}

# Function to request device code
request_device_code() {
    print_info "Requesting device code from GitHub..."
    
    local response
    response=$(curl -s -X POST "$GITHUB_OAUTH_URL" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" \
        -d "{\"client_id\":\"$CLIENT_ID\",\"scope\":\"repo\"}")
    
    if [ $? -ne 0 ]; then
        print_error "Failed to request device code"
        exit 1
    fi
    
    # Parse response
    DEVICE_CODE=$(echo "$response" | jq -r '.device_code')
    USER_CODE=$(echo "$response" | jq -r '.user_code')
    VERIFICATION_URI=$(echo "$response" | jq -r '.verification_uri')
    INTERVAL=$(echo "$response" | jq -r '.interval')
    EXPIRES_IN=$(echo "$response" | jq -r '.expires_in')
    
    # Validate response
    if [ "$DEVICE_CODE" = "null" ] || [ -z "$DEVICE_CODE" ]; then
        print_error "Invalid response from GitHub API"
        echo "$response" | jq .
        exit 1
    fi
    
    print_success "Device code received successfully!"
}

# Function to display user instructions
display_user_instructions() {
    echo ""
    print_info "Please complete the authorization process:"
    echo ""
    echo -e "${YELLOW}1. Open your browser and go to:${NC}"
    echo -e "   ${BLUE}$VERIFICATION_URI${NC}"
    echo ""
    echo -e "${YELLOW}2. Enter this user code:${NC}"
    echo -e "   ${GREEN}$USER_CODE${NC}"
    echo ""
    echo -e "${YELLOW}3. Authorize the application (this will grant access to your repositories)${NC}"
    echo ""
    print_info "Waiting for authorization... (This will timeout in ${EXPIRES_IN} seconds)"
    echo ""
}

# Function to poll for access token
poll_for_token() {
    local token_url="https://github.com/login/oauth/access_token"
    local start_time=$(date +%s)
    local expires_at=$((start_time + EXPIRES_IN))
    
    while [ $(date +%s) -lt $expires_at ]; do
        print_info "Checking for authorization... (timeout in $((expires_at - $(date +%s))) seconds)"
        
        local response
        response=$(curl -s -X POST "$token_url" \
            -H "Accept: application/json" \
            -H "Content-Type: application/json" \
            -d "{\"client_id\":\"$CLIENT_ID\",\"device_code\":\"$DEVICE_CODE\",\"grant_type\":\"urn:ietf:params:oauth:grant-type:device_code\"}")
        
        if [ $? -ne 0 ]; then
            print_error "Failed to check authorization status"
            exit 1
        fi
        
        local error=$(echo "$response" | jq -r '.error // empty')
        local access_token=$(echo "$response" | jq -r '.access_token // empty')
        
        if [ -n "$access_token" ] && [ "$access_token" != "null" ]; then
            ACCESS_TOKEN="$access_token"
            print_success "Authorization successful!"
            return 0
        fi
        
        if [ "$error" = "authorization_pending" ]; then
            sleep "$INTERVAL"
            continue
        elif [ "$error" = "slow_down" ]; then
            print_warning "Rate limited, waiting longer..."
            sleep $((INTERVAL + 5))
            continue
        elif [ "$error" = "expired_token" ]; then
            print_error "Device code has expired. Please run the script again."
            exit 1
        elif [ "$error" = "access_denied" ]; then
            print_error "Authorization was denied by the user."
            exit 1
        else
            print_error "Unexpected error: $error"
            echo "$response" | jq .
            exit 1
        fi
    done
    
    print_error "Authorization timed out. Please run the script again."
    exit 1
}

# Function to validate and display token info
validate_token() {
    print_info "Validating access token..."
    
    local user_info
    user_info=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        "$GITHUB_API_URL/user")
    
    if [ $? -ne 0 ]; then
        print_error "Failed to validate token"
        exit 1
    fi
    
    local login=$(echo "$user_info" | jq -r '.login // empty')
    local name=$(echo "$user_info" | jq -r '.name // empty')
    
    if [ -n "$login" ] && [ "$login" != "null" ]; then
        print_success "Token validated successfully!"
        echo ""
        echo -e "${GREEN}Authenticated as:${NC} $login"
        if [ -n "$name" ] && [ "$name" != "null" ]; then
            echo -e "${GREEN}Name:${NC} $name"
        fi
        echo ""
    else
        print_error "Token validation failed"
        echo "$user_info" | jq .
        exit 1
    fi
}

# Function to save token to file
save_token() {
    print_info "Saving token to $TOKEN_FILE..."
    
    # Overwrite existing file if it exists
    echo "$ACCESS_TOKEN" > "$TOKEN_FILE"
    
    if [ $? -eq 0 ]; then
        print_success "Token saved to $TOKEN_FILE"
    else
        print_error "Failed to save token to file"
        exit 1
    fi
}

# Function to display token
display_token() {
    echo ""
    print_success "Access Token:"
    echo -e "${GREEN}$ACCESS_TOKEN${NC}"
    echo ""
    print_info "You can now use this token with your GitHub CLI tool:"
    print_info "export GITHUB_OAUTH_TOKEN=\"$ACCESS_TOKEN\""
    print_info "uv run github-repos"
    echo ""
}

# Main function
main() {
    echo -e "${BLUE}🔐 GitHub OAuth Device Code Flow${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
    
    # Check dependencies
    check_dependencies
    
    # Validate client ID
    validate_client_id
    
    # Request device code
    request_device_code
    
    # Display instructions
    display_user_instructions
    
    # Poll for token
    poll_for_token
    
    # Validate token
    validate_token
    
    # Save token
    save_token
    
    # Display token
    display_token
    
    print_success "OAuth flow completed successfully!"
}

# Run main function
main "$@"
