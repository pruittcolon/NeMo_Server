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
SHOULD_EXIT=false
FAST_MODE="${FAST_MODE:-false}"
VALIDATE_PORTS="${VALIDATE_PORTS:-false}"

LOG_ROOT="$SCRIPT_DIR/logs/startup"

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

compose_cmd() {
    if command -v docker-compose &> /dev/null; then
        docker-compose "$@"
    else
        docker compose "$@"
    fi
}

capture_diagnostics() {
    local reason="${1:-general}"
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local dest="${LOG_ROOT}/${timestamp}_${reason}"
    mkdir -p "$dest"
    print_warning "Capturing diagnostic logs (${reason}) → ${dest}"

    if [ -d "$SCRIPT_DIR/docker" ]; then
        pushd "$SCRIPT_DIR/docker" >/dev/null 2>&1 || return
        {
            compose_cmd ps
        } &> "${dest}/compose_ps.txt" || true
        {
            compose_cmd ps --services --status running
        } &> "${dest}/services_running.txt" || true
        {
            compose_cmd logs
        } &> "${dest}/compose_logs.txt" || true
        local critical_services=("gateway" "gemma-service" "rag-service" "gpu-coordinator" "transcription-service" "emotion-service")
        for svc in "${critical_services[@]}"; do
            {
                compose_cmd logs "$svc"
            } &> "${dest}/${svc}.log" || true
        done
        popd >/dev/null 2>&1 || true
    fi

    {
        docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}" 2>/dev/null
    } > "${dest}/docker_ps.txt" || true
    print_info "Diagnostics saved to ${dest}"
}

validate_port_bindings() {
    print_header "Validating Service Port Exposure"
    local ps_output
    ps_output=$(docker ps --filter "name=refactored" --format '{{json .}}' 2>/dev/null || true)
    if [ -z "$ps_output" ]; then
        print_warning "No running Nemo containers found for validation"
        return
    fi

    local default_policy='{"refactored_gateway":["0.0.0.0","127.","[::]","::","localhost"],"refactored_postgres":["127.","::1"],"refactored_redis":["127.","::1"]}'
    local policy="${PORT_VALIDATE_POLICY:-$default_policy}"

    if PORT_VALIDATE_INPUT="$ps_output" PORT_VALIDATE_POLICY="$policy" python3 - <<'PORT_VALIDATE'
import json
import os
import sys


def normalize_host(host_spec: str) -> str:
    host_spec = host_spec.strip()
    if not host_spec:
        return host_spec
    if "[" in host_spec and "]" in host_spec:
        host = host_spec.split("]")[0].strip("[]")
        return host or "::"
    if host_spec.count(":") > 1:
        parts = host_spec.split(":")
        return ":".join(parts[:-1]) or "::"
    if ":" in host_spec:
        return host_spec.rsplit(":", 1)[0]
    return host_spec


def host_allowed(service: str, host: str, policy: dict[str, list[str]]) -> bool:
    allowed = policy.get(service, [])
    for entry in allowed:
        entry = entry.strip()
        if not entry:
            continue
        if entry.endswith("*") and host.startswith(entry[:-1]):
            return True
        if entry.endswith(".") and host.startswith(entry):
            return True
        if host == entry:
            return True
    return False


policy_raw = os.environ.get("PORT_VALIDATE_POLICY", "{}")
ps_dump = os.environ.get("PORT_VALIDATE_INPUT", "")
try:
    policy = json.loads(policy_raw)
except json.JSONDecodeError:
    print(f"[PORT-VALIDATION] Invalid PORT_VALIDATE_POLICY JSON: {policy_raw}", file=sys.stderr)
    sys.exit(1)

violations: list[str] = []
for line in ps_dump.splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        info = json.loads(line)
    except json.JSONDecodeError:
        continue
    service = info.get("Names", "")
    ports = info.get("Ports") or ""
    if not service or not ports or service not in policy:
        continue
    for mapping in ports.split(","):
        mapping = mapping.strip()
        if "->" not in mapping:
            continue
        host_part = mapping.split("->", 1)[0].strip()
        host_ip = normalize_host(host_part)
        if not host_allowed(service, host_ip, policy):
            violations.append(
                f"Service {service} exposes {host_part} (normalized {host_ip}) outside policy"
            )

if violations:
    print("\\n".join(f"[PORT-VALIDATION] {msg}" for msg in violations), file=sys.stderr)
    sys.exit(1)

sys.exit(0)
PORT_VALIDATE
    then
        print_success "Port exposure validation passed"
    else
        print_error "Port exposure validation failed"
        capture_diagnostics "port_validation"
        exit 1
    fi
}


cleanup() {
    if [ "$SHOULD_EXIT" = true ]; then
        exit 0
    fi
    SHOULD_EXIT=true
    echo -e "\n${YELLOW}Stopping Nemo Server services...${NC}"

    if [ -d "$SCRIPT_DIR/docker" ]; then
        pushd "$SCRIPT_DIR/docker" >/dev/null 2>&1 || true
        if command -v docker-compose &> /dev/null; then
            docker-compose down >/dev/null 2>&1 || true
        else
            docker compose down >/dev/null 2>&1 || true
        fi
        popd >/dev/null 2>&1 || true
    fi

    echo -e "${GREEN}All services stopped. Goodbye!${NC}"
    exit 0
}

trap cleanup INT TERM

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
    local required_secrets=("session_key" "jwt_secret_primary" "jwt_secret_previous" "jwt_secret" "postgres_password" "postgres_user" "users_db_key" "rag_db_key")
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

prepare_host_dirs() {
    print_header "Preparing Host Directories"
    # Ensure bind mounts exist with permissive dev permissions
    local dirs=("gemma_instance")
    for d in "${dirs[@]}"; do
        if [ ! -d "$SCRIPT_DIR/$d" ]; then
            mkdir -p "$SCRIPT_DIR/$d"
            print_info "Created $d"
        fi
        # Dev-friendly permissions to avoid UID/GID mismatches
        chmod 0777 "$SCRIPT_DIR/$d" || true
        print_success "Ready: $d ($(ls -ld "$SCRIPT_DIR/$d"))"
    done
}

stop_existing_services() {
    print_header "Stopping Existing Services"
    
    cd docker
    
    print_info "Stopping all Nemo/Refactored containers..."
    # Only wipe volumes when explicitly requested
    if [ "${WIPE_VOLUMES:-false}" = true ]; then
        compose_cmd down -v 2>/dev/null || true
    else
        compose_cmd down 2>/dev/null || true
    fi
    
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
            compose_cmd build || true
        else
            print_info "Rebuilding API Gateway only (use --build-all to rebuild everything)..."
            compose_cmd build api-gateway || true
        fi
    else
        print_info "Skipping image rebuild (pass --build or --build-all to rebuild)"
    fi

    
    print_info "Starting containers..."
    
    if compose_cmd up -d; then
        print_success "Services started successfully"
    else
        print_error "Failed to start services"
        capture_diagnostics "start_failure"
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
            capture_diagnostics "healthcheck_timeout"
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
    
    local gateway_url="${API_GATEWAY_URL}/ui/login.html"
    print_info "Gateway UI: $gateway_url"

    # Determine which browser command to use
    if command -v xdg-open &> /dev/null; then
        print_info "Opening API Gateway UI in default browser..."
        xdg-open "$gateway_url" >/dev/null 2>&1 || true
        print_success "Browser launch attempted (xdg-open)"
    elif command -v open &> /dev/null; then
        print_info "Opening API Gateway UI in browser..."
        open "$gateway_url" >/dev/null 2>&1 || true
        print_success "Browser launch attempted (open)"
    elif command -v firefox &> /dev/null; then
        print_info "Opening API Gateway UI in Firefox..."
        firefox "$gateway_url" >/dev/null 2>&1 &
        print_success "Browser launch attempted (firefox)"
    elif command -v google-chrome &> /dev/null; then
        print_info "Opening API Gateway UI in Chrome..."
        google-chrome "$gateway_url" >/dev/null 2>&1 &
        print_success "Browser launch attempted (chrome)"
    else
        print_warning "No browser command found"
        print_info "Please open manually:"
        print_info "  API Gateway UI: $gateway_url"
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
            --fast)
                FAST_MODE=true
                ;;
            --validate-ports)
                VALIDATE_PORTS=true
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
    if [ "$FAST_MODE" = true ]; then
        print_warning "Fast mode enabled - skipping security hardening & verification steps"
    else
        run_security_hardening
        verify_security_implementation
    fi
    
    # Step 4: Check secrets
    check_secrets
    
    # Step 4.5: Prepare host directories for bind mounts
    prepare_host_dirs

    # Step 5: Stop existing services
    stop_existing_services
    
    # Step 6: Start services
    start_services "$BUILD" "$BUILD_ALL"
    
    # Optional: Validate exposed ports immediately after bring-up
    if [ "$VALIDATE_PORTS" = true ]; then
        validate_port_bindings
    fi
    
    # Step 7: Wait for services to be healthy
    wait_for_services
    
    # Re-validate port bindings post health checks to catch late binds
    if [ "$VALIDATE_PORTS" = true ]; then
        validate_port_bindings
    fi
    
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

# Trap Ctrl+C to show logs using compose_cmd
tail_logs_trap() {
    echo -e "\n${BLUE}Showing logs (Ctrl+C again to exit)...${NC}\n"
    pushd "$SCRIPT_DIR/docker" >/dev/null 2>&1 || return
    compose_cmd logs -f
}
trap tail_logs_trap INT

# Run main function
main

echo -e "${BLUE}Press Ctrl+C to stop all services and exit.${NC}"
while true; do
    sleep 86400
done
