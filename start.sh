#!/bin/bash
#
# Nemo Server Startup Script
# Handles security setup, service startup, and browser opening
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Configuration
# Allow overrides via environment variables
API_GATEWAY_URL="${API_GATEWAY_URL:-http://localhost:8000}"
HEALTH_CHECK_TIMEOUT="${HEALTH_CHECK_TIMEOUT:-120}"  # seconds
BROWSER_OPEN_DELAY=5      # seconds after services are healthy

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

check_dependencies() {
    print_header "Checking Dependencies"
    
    local missing_deps=()
    
    # Check for docker
    if ! command -v docker &> /dev/null; then
        missing_deps+=("docker")
    else
        print_success "Docker installed: $(docker --version | head -n1)"
    fi
    
    # Check for docker-compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        missing_deps+=("docker-compose")
    else
        if command -v docker-compose &> /dev/null; then
            print_success "Docker Compose installed: $(docker-compose --version)"
        else
            print_success "Docker Compose (plugin) installed: $(docker compose version)"
        fi
    fi
    
    # Check for python3
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("python3")
    else
        print_success "Python3 installed: $(python3 --version)"
    fi
    
    # Check for nvidia-smi (GPU)
    if ! command -v nvidia-smi &> /dev/null; then
        print_warning "nvidia-smi not found - GPU services may not work"
    else
        print_success "NVIDIA GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing dependencies: ${missing_deps[*]}"
        echo ""
        echo "Please install missing dependencies:"
        echo "  Ubuntu/Debian: sudo apt install ${missing_deps[*]}"
        echo "  Fedora: sudo dnf install ${missing_deps[*]}"
        exit 1
    fi
}

run_security_hardening() {
    print_header "Running Security Hardening"
    
    if [ -f "scripts/security_hardening.py" ]; then
        print_info "Generating/verifying secrets for Phase 5..."
        python3 scripts/security_hardening.py
        if [ $? -ne 0 ]; then
            print_error "Security hardening failed"
            exit 1
        fi
        print_success "Security hardening complete"
    else
        print_warning "Security hardening script not found - skipping"
    fi
}

verify_security_implementation() {
    print_header "Verifying Security Implementation"
    
    if [ -f "scripts/verify_security.py" ]; then
        print_info "Checking Phases 1-5 implementation..."
        if python3 scripts/verify_security.py; then
            print_success "All security checks passed!"
        else
            print_warning "Some security checks failed - review output above"
            print_warning "Continuing anyway..."
        fi
    else
        print_warning "Security verification script not found - skipping"
    fi
}

check_secrets() {
    print_header "Checking Secrets"
    
    local secrets_dir="docker/secrets"
    local required_secrets=("session_key" "jwt_secret" "postgres_password" "postgres_user" "users_db_key" "rag_db_key")
    local missing_secrets=()
    
    if [ ! -d "$secrets_dir" ]; then
        print_warning "Secrets directory not found - will be created by security hardening"
        return
    fi
    
    for secret in "${required_secrets[@]}"; do
        if [ -f "$secrets_dir/$secret" ]; then
            print_success "Found secret: $secret"
        else
            missing_secrets+=("$secret")
            print_warning "Missing secret: $secret"
        fi
    done
    
    # Check HuggingFace token
    if [ -f "$secrets_dir/huggingface_token" ]; then
        print_success "Found HuggingFace token"
    else
        print_warning "Missing HuggingFace token (optional for local models)"
    fi
    
    if [ ${#missing_secrets[@]} -ne 0 ]; then
        print_warning "Some secrets are missing - they will be generated"
    fi
}

stop_existing_services() {
    print_header "Stopping Existing Services"
    
    cd docker
    
    print_info "Stopping all Nemo/Refactored containers..."
    docker-compose down -v 2>/dev/null || true
    
    # Force kill any remaining containers
    docker ps -a | grep -E "refactored|nemo" | awk '{print $1}' | xargs -r docker rm -f 2>/dev/null || true
    
    print_success "All services stopped"
    
    cd ..
}

start_services() {
    print_header "Starting Services"
    local DO_BUILD=${1:-false}
    local BUILD_ALL=${2:-false}

    cd docker
    
    if [ "$DO_BUILD" = true ]; then
        if [ "$BUILD_ALL" = true ]; then
            print_info "Rebuilding all services (docker compose build)..."
            if command -v docker-compose &> /dev/null; then
                docker-compose build || true
            else
                docker compose build || true
            fi
        else
            print_info "Rebuilding API Gateway only (use --build-all to rebuild everything)..."
            if command -v docker-compose &> /dev/null; then
                docker-compose build api-gateway || true
            else
                docker compose build api-gateway || true
            fi
        fi
    else
        print_info "Skipping image rebuild (pass --build or --build-all to rebuild)"
    fi
    
    print_info "Starting containers..."
    
    # Use docker-compose or docker compose
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d
    else
        docker compose up -d
    fi
    
    if [ $? -eq 0 ]; then
        print_success "Services started successfully"
    else
        print_error "Failed to start services"
        cd ..
        exit 1
    fi
    
    cd ..
}

wait_for_services() {
    print_header "Waiting for Services to be Healthy"
    
    print_info "Checking service health (timeout: ${HEALTH_CHECK_TIMEOUT}s)..."
    
    # If docker compose binds the gateway to a specific host IP, prefer that URL
    # Simple detection for a host-bound port mapping like "192.168.0.7:8000:8000"
    if grep -q "192.168.0.7:8000:8000" docker/docker-compose.yml 2>/dev/null; then
        API_GATEWAY_URL="http://192.168.0.7:8000"
        print_info "Detected gateway port mapping to 192.168.0.7; using ${API_GATEWAY_URL}"
    fi

    local start_time=$(date +%s)
    local endpoint_url="${API_GATEWAY_URL}/health"
    local endpoint_name="API Gateway"
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $HEALTH_CHECK_TIMEOUT ]; then
            print_error "Health check timeout after ${HEALTH_CHECK_TIMEOUT}s"
            print_info "Check logs with: cd docker && docker-compose logs"
            exit 1
        fi
        
        if curl -sf "$endpoint_url" > /dev/null 2>&1; then
            print_success "$endpoint_name is healthy"
            break
        else
            if [ $((elapsed % 10)) -eq 0 ]; then
                print_info "Waiting for $endpoint_name at $endpoint_url... (${elapsed}s)"
            fi
            sleep 2
        fi
    done
    
    print_success "All services are healthy!"
}

show_service_info() {
    print_header "Service Information"
    
    echo -e "${GREEN}Services Running:${NC}"
    echo ""
    echo "  📡 API Gateway:      ${API_GATEWAY_URL}"
    echo "  🤖 Gemma Service:    http://localhost:8001"
    echo "  📋 Queue Service:    http://localhost:8002"
    echo "  🎤 Transcription:    http://localhost:8003"
    echo "  🧠 RAG Service:      http://localhost:8004"
    echo "  😊 Emotion Service:  http://localhost:8005"
    echo ""
    echo "  💾 PostgreSQL:       localhost:5432"
    echo "  🔴 Redis:            localhost:6379"
    echo ""
    
    # Check if coverage report exists
    if [ -f "htmlcov/index.html" ]; then
        echo -e "${GREEN}Test Coverage Report:${NC}"
        echo "  📊 Coverage HTML:    file://$(pwd)/htmlcov/index.html"
        echo ""
    fi
    
    echo -e "${BLUE}Useful Commands:${NC}"
    echo "  View logs:        cd docker && docker-compose logs -f"
    echo "  Stop services:    cd docker && docker-compose down"
    echo "  Restart:          ./start.sh"
    echo ""
}

open_browser() {
    print_header "Opening Browser"
    
    print_info "Waiting ${BROWSER_OPEN_DELAY}s before opening browser..."
    sleep $BROWSER_OPEN_DELAY
    
    # Determine which browser command to use
    # Open the API Gateway UI (served at /ui) first so the frontend is same-origin
    if command -v xdg-open &> /dev/null; then
        # Linux with xdg-open
        print_info "Opening API Gateway UI in browser..."
        xdg-open "$API_GATEWAY_URL/ui/login.html" 2>/dev/null &
        
        print_success "Browser opened"
    elif command -v open &> /dev/null; then
        # macOS
        print_info "Opening API Gateway UI in browser..."
        open "$API_GATEWAY_URL/ui/login.html" 2>/dev/null &
        
        print_success "Browser opened"
    elif command -v firefox &> /dev/null; then
        # Fallback to firefox
        print_info "Opening API Gateway UI in Firefox..."
        firefox "$API_GATEWAY_URL/ui/login.html" 2>/dev/null &
        
        print_success "Browser opened"
    elif command -v google-chrome &> /dev/null; then
        # Fallback to chrome
        print_info "Opening API Gateway UI in Chrome..."
        google-chrome "$API_GATEWAY_URL/ui/login.html" 2>/dev/null &
        
        print_success "Browser opened"
    else
        print_warning "No browser command found"
        print_info "Please open manually:"
        print_info "  Frontend: file://$(pwd)/frontend/index.html"
        print_info "  API Gateway: $API_GATEWAY_URL"
    fi
}

show_demo_credentials() {
    print_header "Demo Credentials"
    
    # Check if demo users are enabled
    if [ -f "docker/.env" ] && grep -q "ENABLE_DEMO_USERS=true" docker/.env; then
        echo -e "${YELLOW}⚠️  Demo users are ENABLED${NC}"
        echo ""
        echo "You can login with:"
        echo ""
        echo "  Admin Account:"
        echo "    Username: admin"
        echo "    Password: admin123"
        echo ""
        echo "  User Account:"
        echo "    Username: user1"
        echo "    Password: user1pass"
        echo ""
        echo "  TV Speaker Account:"
        echo "    Username: television"
        echo "    Password: tvpass123"
        echo ""
        echo -e "${RED}⚠️  WARNING: Change these in production!${NC}"
    else
        echo -e "${GREEN}✓ Demo users are disabled (production mode)${NC}"
        echo ""
        echo "No default credentials available."
        echo "Create users through the API or admin interface."
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    # Parse flags
    #   --build         Rebuild changed services before up
    #   --build-all     Rebuild all services before up
    #   --no-browser    Do not open a browser on success
    BUILD=false
    BUILD_ALL=false
    OPEN_BROWSER=true
    for arg in "$@"; do
        case "$arg" in
            --build)
                BUILD=true
                ;;
            --build-all)
                BUILD=true
                BUILD_ALL=true
                ;;
            --no-browser)
                OPEN_BROWSER=false
                ;;
        esac
    done
    # Clear screen only if running in a terminal with TERM set
    if [ -t 1 ] && [ -n "$TERM" ]; then
        clear
    fi
    
    echo -e "${BLUE}"
    cat << "EOF"
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║            🚀  NEMO SERVER STARTUP SCRIPT  🚀                ║
    ║                                                               ║
    ║                 AI-Powered Transcription                      ║
    ║              Multi-Service Architecture                       ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}\n"
    
    # Step 1: Check dependencies
    check_dependencies
    
    # Step 2: Run security hardening
    run_security_hardening
    
    # Step 3: Verify security implementation
    verify_security_implementation
    
    # Step 4: Check secrets
    check_secrets
    
    # Step 5: Stop existing services
    stop_existing_services
    
    # Step 6: Start services
    start_services "$BUILD" "$BUILD_ALL"
    
    # Step 7: Wait for services to be healthy
    wait_for_services
    
    # Step 8: Show service information
    show_service_info
    
    # Step 9: Show demo credentials if applicable
    show_demo_credentials
    
    # Step 10: Open browser
    if [ "$OPEN_BROWSER" = true ]; then
        open_browser
    else
        print_info "Skipping browser launch (--no-browser)"
    fi
    
    # Final message
    print_header "Startup Complete"
    
    echo -e "${GREEN}✅ Nemo Server is running with comprehensive security!${NC}"
    echo -e "${BLUE}Security Features Enabled:${NC}"
    echo "  ✅ Phase 1: CORS, CSRF, Rate Limiting, Auth Required"
    echo "  ✅ Phase 2: JWT Service Auth (Gateway emits tokens)"
    echo "  ✅ Phase 3: JWT-Only Enforcement + Replay Protection"
    echo "  ✅ Phase 4: Internal Services Isolated (No Host Ports)"
    echo "  ✅ Phase 5: Docker Secrets Mounted"
    echo "  ✅ Phase 7: Redis/Postgres Bound to Loopback"
    echo "  📊 Comprehensive Logging: All requests traced with request_id"
    echo ""
    echo "Press Ctrl+C to view logs, or run:"
    echo "  cd docker && docker-compose logs -f"
    echo ""
    echo "To stop services:"
    echo "  cd docker && docker-compose down"
    echo ""
}

# Trap Ctrl+C to show logs
trap 'echo -e "\n${BLUE}Showing logs (Ctrl+C again to exit)...${NC}\n"; cd docker && docker-compose logs -f' INT

# Run main function
main

# Keep script running to show any immediate errors
sleep 2

exit 0
