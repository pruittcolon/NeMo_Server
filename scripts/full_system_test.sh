#!/usr/bin/env bash
# Human-operable verification suite for Nemo Server
# Provides granular feature flags, interactive menu, and CLI parity checks.

set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

GATEWAY_URL=${GATEWAY_URL:-http://localhost:8000}
ENABLE_LOGIN_TESTS=${ENABLE_LOGIN_TESTS:-1}
TEST_USERNAME=${TEST_USERNAME:-admin}
TEST_PASSWORD=${TEST_PASSWORD:-admin123}
VERBOSE=${VERBOSE:-0}
FAIL_FAST=${FAIL_FAST:-1}
STACK_READY_TIMEOUT=${STACK_READY_TIMEOUT:-420}
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
START_SCRIPT=${START_SCRIPT:-"$REPO_ROOT/start.sh"}
START_SH_ARGS=${START_SH_ARGS:-"--no-browser --no-logs"}
RUN_ALL=0
INTERACTIVE=0
TRANSCRIPTION_FILE=""
TRANSCRIPTION_TEXT=""
TRANSCRIPTION_TEXT_FILE=""
TRANSCRIPTION_SPEAKER=${TRANSCRIPTION_SPEAKER:-"Speaker 1"}
ANALYZER_STREAM_ID=${ANALYZER_STREAM_ID:-"cli-test-stream"}
ANALYZER_EMOTIONS=${ANALYZER_EMOTIONS:-"anger"}
ANALYZER_DAYS=${ANALYZER_DAYS:-5}
ANALYZER_LIMIT=${ANALYZER_LIMIT:-2}
ANALYZER_PROMPT=${ANALYZER_PROMPT:-"Identify hyperbole and fallacies."}
ANALYZER_CHAT_PROMPT=${ANALYZER_CHAT_PROMPT:-"What are the top 2 risks in this analysis?"}
ANALYZER_CHAT_CONTEXT=${ANALYZER_CHAT_CONTEXT:-"Context: Leadership wants to calm recurring angry escalations observed in the past five days."}
ANALYZER_CHAT_CONTEXT_PROMPT=${ANALYZER_CHAT_CONTEXT_PROMPT:-"Given that chat context, describe how the analysis findings should guide immediate actions."}
ANALYZER_SSE_TIMEOUT=${ANALYZER_SSE_TIMEOUT:-90}
STREAM_ARTIFACT_ID=""
UNIQUE_TAG=${UNIQUE_TAG:-"nemo-cli-$(date +%Y%m%d%H%M%S)-$RANDOM"}
COMPOSED_TRANSCRIPT_TEXT=""
LAST_TRANSCRIPT_JOB_ID=""
LAST_AUDIO_TRANSCRIPT=""
LAST_ARCHIVED_ARTIFACT_ID=""
LAST_SPEAKER_NAME=""
SYSTEM_TEST_DIR=${SYSTEM_TEST_DIR:-"$REPO_ROOT/logs/system-tests"}
mkdir -p "$SYSTEM_TEST_DIR"
CONVO_LOG="$SYSTEM_TEST_DIR/gemma_conversation_${UNIQUE_TAG}.log"
: >"$CONVO_LOG"
CONVO_JSONL="$SYSTEM_TEST_DIR/gemma_conversation_${UNIQUE_TAG}.jsonl"
: >"$CONVO_JSONL"
CONVO_REPORT="$SYSTEM_TEST_DIR/gemma_conversation_report_${UNIQUE_TAG}.json"
CONVO_TONE_WARNINGS=0
CONVO_MAX_TOKENS=${CONVO_MAX_TOKENS:-192}
export CONVO_MAX_TOKENS

FEATURES_ORDER=(
  health
  auth
  transcription
  transcripts
  analysis
  gemma
  rag
  memories
  emotions
  analyzer
  speakers
  patterns
)
REQUESTED_FEATURES=()

usage() {
  cat <<EOF
Usage: $0 [options]
Options:
  --all                      Run every feature (default if none specified)
  --interactive              Prompt for feature selection
  --health                   Run health checks
  --auth                     Login + session checks
  --transcription            Upload WAV or typed transcript
      --transcription-file PATH
      --transcription-text "..."
      --transcription-text-file PATH
      --transcription-speaker NAME
  --transcripts              Transcript listing/query/count
  --analysis                 Archive/list/search artifacts
  --gemma                    Gemma warmup/chat/generate
  --rag                      RAG + semantic searches
  --memories                 Memory create/search/stats
  --emotions                 Emotion analysis (text + stats)
  --analyzer                 Gemma context analyzer (batch + stream)
  --speakers                 Speaker list/enroll checks
  --patterns                 Patterns dashboard mock
  --verbose                  Print verbose responses
  -h, --help                 Show this help
EOF
}

add_feature() {
  local feature=$1
  for item in "${REQUESTED_FEATURES[@]}"; do
    [[ "$item" == "$feature" ]] && return
  done
  REQUESTED_FEATURES+=("$feature")
}

feature_selected() {
  local feature=$1
  if [[ "$RUN_ALL" == "1" ]]; then
    return 0
  fi
  for item in "${REQUESTED_FEATURES[@]}"; do
    [[ "$item" == "$feature" ]] && return 0
  done
  return 1
}

interactive_select() {
  echo -e "${BLUE}Interactive mode: choose features to run (comma separated numbers or 'all').${NC}"
  local idx=1
  for f in "${FEATURES_ORDER[@]}"; do
    printf " %2d) %s\n" "$idx" "$f"
    ((idx++))
  done
  printf "Selection: "
  read -r selection || selection=""
  if [[ -z "$selection" || "$selection" =~ [Aa][Ll][Ll] ]]; then
    RUN_ALL=1
    return
  fi
  IFS=',' read -ra picks <<< "$selection"
  for pick in "${picks[@]}"; do
    pick=${pick//[^0-9]/}
    [[ -z "$pick" ]] && continue
    if (( pick >= 1 && pick <= ${#FEATURES_ORDER[@]} )); then
      add_feature "${FEATURES_ORDER[pick-1]}"
    fi
  done
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) RUN_ALL=1 ;;
    --interactive) INTERACTIVE=1 ;;
    --health) add_feature health ;;
    --auth) add_feature auth ;;
    --transcription) add_feature transcription ;;
    --transcription-file) TRANSCRIPTION_FILE="$2"; shift ;;
    --transcription-text) TRANSCRIPTION_TEXT="$2"; shift ;;
    --transcription-text-file) TRANSCRIPTION_TEXT_FILE="$2"; shift ;;
    --transcription-speaker) TRANSCRIPTION_SPEAKER="$2"; shift ;;
    --transcripts) add_feature transcripts ;;
    --analysis) add_feature analysis ;;
    --gemma) add_feature gemma ;;
    --rag) add_feature rag ;;
    --memories) add_feature memories ;;
    --emotions) add_feature emotions ;;
    --analyzer) add_feature analyzer ;;
    --speakers) add_feature speakers ;;
    --patterns) add_feature patterns ;;
    --verbose) VERBOSE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if [[ "$INTERACTIVE" == "1" ]]; then
  interactive_select
fi

if [[ "$RUN_ALL" != "1" && ${#REQUESTED_FEATURES[@]} -eq 0 ]]; then
  RUN_ALL=1
fi

START_SH_FLAGS=()
for arg in $START_SH_ARGS; do
  START_SH_FLAGS+=("$arg")
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo -e "${RED}Missing required command: $1${NC}" >&2
    exit 1
  fi
}

require_cmd curl
require_cmd python3

ANALYZER_FILTERS=$(python3 - <<'PY'
import os, json
from datetime import datetime, timedelta
days = int(os.environ.get("ANALYZER_DAYS", "5") or 5)
limit = int(os.environ.get("ANALYZER_LIMIT", "2") or 2)
emotions_raw = os.environ.get("ANALYZER_EMOTIONS", "anger")
emotions = [e.strip() for e in emotions_raw.split(",") if e.strip()] or ["anger"]
now = datetime.utcnow()
start = now - timedelta(days=days)
filters = {
    "limit": limit,
    "emotions": emotions,
    "start_date": start.strftime("%Y-%m-%d"),
    "end_date": now.strftime("%Y-%m-%d"),
}
print(json.dumps(filters), end="")
PY
)
export ANALYZER_FILTERS ANALYZER_STREAM_ID ANALYZER_PROMPT ANALYZER_CHAT_PROMPT ANALYZER_CHAT_CONTEXT ANALYZER_CHAT_CONTEXT_PROMPT ANALYZER_SSE_TIMEOUT

COOKIE_JAR=$(mktemp)
trap 'rm -f "$COOKIE_JAR"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
OPTIONAL_MODE=0

log_section() {
  echo -e "\n${BLUE}==> $1${NC}"
}

log_success() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo -e "${GREEN}✓${NC} $1"
}

log_failure() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  echo -e "${RED}✗${NC} $1" >&2
  if [[ "$FAIL_FAST" == "1" ]]; then
    exit 1
  fi
}

print_summary() {
  echo -e "\n${BLUE}Summary:${NC} ${GREEN}${PASS_COUNT} passed${NC}, ${FAIL_COUNT} failed"
  [[ $FAIL_COUNT -eq 0 ]]
}

START_SH_DRIVEN=${START_SH_DRIVEN:-0}
DEFAULT_AUTOSTART=1
if [[ "$START_SH_DRIVEN" == "1" ]]; then
  DEFAULT_AUTOSTART=0
fi
AUTOSTART_STACK=${AUTOSTART_STACK:-$DEFAULT_AUTOSTART}
FORCE_START_STACK=${FORCE_START_STACK:-1}

CLI_BIN=(python3 "$REPO_ROOT/scripts/nemo_cli.py" --no-auto-start --base-url "$GATEWAY_URL" --username "$TEST_USERNAME" --password "$TEST_PASSWORD")

run_cli() {
  local label=$1; shift
  local tmp
  tmp=$(mktemp)
  set +e
  "${CLI_BIN[@]}" "$@" >"$tmp" 2>&1
  local status=$?
  set -e
  if [[ $status -eq 0 ]]; then
    log_success "$label"
    if [[ "$VERBOSE" == "1" ]]; then
      cat "$tmp"
    fi
  else
    cat "$tmp" >&2
    log_failure "$label"
  fi
  rm -f "$tmp"
  return $status
}

run_cli_optional() {
  local label=$1; shift
  local tmp
  tmp=$(mktemp)
  set +e
  "${CLI_BIN[@]}" "$@" >"$tmp" 2>&1
  local status=$?
  set -e
  if [[ $status -eq 0 ]]; then
    log_success "$label"
    if [[ "$VERBOSE" == "1" ]]; then
      cat "$tmp"
    fi
  else
    echo -e "${YELLOW}Optional CLI step skipped: $label (exit $status)${NC}" >&2
    if [[ "$VERBOSE" == "1" ]]; then
      cat "$tmp" >&2
    fi
  fi
  rm -f "$tmp"
  return 0
}

poll_artifact_by_analysis() {
  local target_analysis=$1
  local max_attempts=${2:-6}
  local delay_seconds=${3:-2}
  STREAM_ARTIFACT_ID=""
  if [[ -z "$target_analysis" ]]; then
    echo -e "${YELLOW}No analysis_id provided for artifact lookup.${NC}" >&2
    return 1
  fi
  local attempt=1
  while (( attempt <= max_attempts )); do
    local label="Analysis list (post-stream attempt $attempt)"
    perform_request "$label" GET "$GATEWAY_URL/api/analysis/list?limit=25" "" "${AUTH_OPTS[@]}"
    STREAM_ARTIFACT_ID=$(TARGET_ANALYSIS="$target_analysis" JSON_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json, os
target=os.environ.get('TARGET_ANALYSIS','').strip()
if not target:
    print('')
    raise SystemExit
try:
    data=json.loads(os.environ.get('JSON_BODY','') or '{}')
except Exception:
    print('')
    raise SystemExit
items=data.get('items') or data.get('artifacts') or []
for entry in items:
    if isinstance(entry, dict) and entry.get('analysis_id')==target:
        print(entry.get('artifact_id') or '')
        break
else:
    print('')
PY
)
    if [[ -n "$STREAM_ARTIFACT_ID" ]]; then
      return 0
    fi
    attempt=$(( attempt + 1 ))
    sleep "$delay_seconds"
  done
  echo -e "${YELLOW}Artifact for analysis_id $target_analysis not found after $max_attempts attempts.${NC}" >&2
  return 1
}

is_local_artifact_id() {
  local aid=$1
  [[ "$aid" == fallback_* || "$aid" == local-* ]]
}

gateway_healthy() {
  curl -sf "$GATEWAY_URL/health" >/dev/null 2>&1
}

wait_for_gateway_ready() {
  local deadline=$(( $(date +%s) + STACK_READY_TIMEOUT ))
  while (( $(date +%s) <= deadline )); do
    if gateway_healthy; then
      return 0
    fi
    sleep 5
  done
  return 1
}

start_stack() {
  if [[ ! -x "$START_SCRIPT" ]]; then
    echo -e "${RED}Cannot run start.sh: not found at $START_SCRIPT${NC}"
    exit 1
  fi
  echo -e "${BLUE}Bootstrapping services via start.sh...${NC}"
  (
    cd "$REPO_ROOT"
    set +e
    RUN_POST_START_TESTS=0 EXIT_AFTER_START=1 bash "$START_SCRIPT" "${START_SH_FLAGS[@]}"
    local start_status=$?
    set -e
    if [[ $start_status -ne 0 ]]; then
      echo -e "${YELLOW}start.sh exited with status $start_status; continuing to verify health...${NC}"
    fi
  )
  echo -e "${BLUE}Waiting for gateway readiness (timeout ${STACK_READY_TIMEOUT}s)...${NC}"
  if wait_for_gateway_ready; then
    echo -e "${GREEN}Gateway healthy at ${GATEWAY_URL} after start.sh.${NC}"
  else
    echo -e "${RED}Gateway failed to become healthy within timeout after start.sh.${NC}"
    exit 1
  fi
}

ensure_stack_running() {
  echo -e "${BLUE}Ensuring Nemo stack is running...${NC}"
  if [[ "$FORCE_START_STACK" == "1" ]]; then
    start_stack
    return
  fi
  if gateway_healthy; then
    echo -e "${GREEN}Gateway already healthy at ${GATEWAY_URL}${NC}"
    return
  fi
  if [[ "$AUTOSTART_STACK" != "1" ]]; then
    echo -e "${RED}Gateway unreachable and AUTOSTART_STACK=0.${NC}"
    exit 1
  fi
  start_stack
}

perform_request() {
  local label=$1
  local method=$2
  local url=$3
  local data=${4:-}
  local extra_opts=()
  if (($# >= 5)); then
    extra_opts=("${@:5}")
  fi
  local tmp
  tmp=$(mktemp)
  local status
  set +e
  if [[ "$method" == "GET" ]]; then
    status=$(curl -sS -o "$tmp" -w "%{http_code}" "${extra_opts[@]}" "$url")
  else
    status=$(curl -sS -o "$tmp" -w "%{http_code}" -X "$method" -H 'Content-Type: application/json' -d "$data" "${extra_opts[@]}" "$url")
  fi
  local curl_exit=$?
  set -e
  local body
  body=$(cat "$tmp")
  rm -f "$tmp"
  if [[ $curl_exit -ne 0 ]]; then
    echo "$body" >&2
    if [[ "$OPTIONAL_MODE" == "1" ]]; then
      return 1
    fi
    log_failure "$label (curl exit $curl_exit)"
    return 1
  fi
  if [[ "$status" == 2* ]]; then
    if [[ "$VERBOSE" == "1" ]]; then
      echo "$label response:"
      echo "$body"
    fi
    log_success "$label ($status)"
    LAST_JSON_BODY="$body"
    return 0
  fi
  echo "$body" >&2
  if [[ "$OPTIONAL_MODE" == "1" ]]; then
    return 1
  fi
  log_failure "$label (HTTP $status)"
  return 1
}

perform_request_optional() {
  local label=$1
  shift
  local prev_mode=$OPTIONAL_MODE
  OPTIONAL_MODE=1
  if perform_request "$label" "$@"; then
    OPTIONAL_MODE=$prev_mode
    return 0
  fi
  OPTIONAL_MODE=$prev_mode
  echo -e "${YELLOW}Optional check skipped: $label${NC}" >&2
  return 0
}

response_contains_keyword() {
  local keyword=$1
  LAST_BODY="$LAST_JSON_BODY" python3 - "$keyword" <<'PY'
import os, sys, json
keyword = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
body = os.environ.get('LAST_BODY', '')
text = body
try:
    parsed = json.loads(body)
    text = json.dumps(parsed)
except Exception:
    pass
if keyword and keyword in text.lower():
    sys.exit(0)
sys.exit(1)
PY
}

extract_response_text() {
  LAST_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json, os
body = os.environ.get('LAST_BODY', '')
try:
    data = json.loads(body)
except Exception:
    print('')
    raise SystemExit
for key in ('text','response','answer','message'):
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        print(value.strip())
        raise SystemExit
choices = data.get('choices')
if isinstance(choices, list):
    for option in choices:
        if isinstance(option, dict):
            text = option.get('text')
            if isinstance(text, str) and text.strip():
                print(text.strip())
                raise SystemExit
            message = option.get('message', {})
            if isinstance(message, dict):
                content = message.get('content')
                if isinstance(content, str) and content.strip():
                    print(content.strip())
                    raise SystemExit
print('')
PY
}

log_conversation() {
  local role=$1
  shift
  local message=$*
  printf '[%s] %s\n' "$role" "$message" >> "$CONVO_LOG"
}

record_convo_payload() {
  local stage=$1
  STAGE="$stage" JSONL_PATH="$CONVO_JSONL" LAST_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json, os, sys
path = os.environ.get("JSONL_PATH")
stage = os.environ.get("STAGE") or "unknown"
body_raw = os.environ.get("LAST_BODY", "")
try:
    body = json.loads(body_raw) if body_raw else {}
except Exception:
    body = {"raw": body_raw}
entry = {"stage": stage, "body": body}
with open(path, "a", encoding="utf-8") as handle:
    json.dump(entry, handle)
    handle.write("\n")
PY
}

assert_tone_status() {
  local stage=$1
  local status_output
  status_output=$(STAGE="$stage" LAST_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json, os, sys
stage = os.environ.get("STAGE") or "unknown"
body_raw = os.environ.get("LAST_BODY", "")
try:
    data = json.loads(body_raw)
except Exception:
    print("missing")
    sys.exit(1)
tone = data.get("tone_analysis") or {}
status = tone.get("status")
if not status:
    print("missing")
    sys.exit(1)
print(status)
if status == "fail":
    sys.exit(2)
sys.exit(0)
PY
)
  local exit_code=$?
  if (( exit_code == 2 )); then
    log_failure "Gemma tone failure during ${stage}"
    return 1
  elif (( exit_code != 0 )); then
    log_failure "Gemma tone metadata missing during ${stage}"
    return 1
  fi
  if [[ "$status_output" == "warn" ]]; then
    CONVO_TONE_WARNINGS=$((CONVO_TONE_WARNINGS + 1))
    if (( CONVO_TONE_WARNINGS >= 2 )); then
      log_failure "Gemma tone warnings exceeded threshold near ${stage}"
      return 1
    fi
  else
    CONVO_TONE_WARNINGS=0
  fi
  return 0
}

generate_convo_report() {
  local expected="$1"
  LOG_PATH="$CONVO_LOG" JSONL_PATH="$CONVO_JSONL" REPORT_PATH="$CONVO_REPORT" EXPECTED_QUESTIONS="$expected" python3 - <<'PY'
import json, os, sys
log_path = os.environ.get("LOG_PATH")
jsonl_path = os.environ.get("JSONL_PATH")
report_path = os.environ.get("REPORT_PATH")
expected_raw = os.environ.get("EXPECTED_QUESTIONS", "")
expected = [line.strip() for line in expected_raw.splitlines() if line.strip()]
if not os.path.exists(log_path) or not os.path.exists(jsonl_path):
    print("missing inputs")
    sys.exit(1)
turns = []
with open(log_path, "r", encoding="utf-8") as handle:
    for line in handle:
        stripped = line.strip()
        if not stripped or not stripped.startswith("["):
            continue
        try:
            role, text = stripped.split("]", 1)
        except ValueError:
            continue
        turns.append({"role": role.strip("[]"), "text": text.strip()})
entries = []
with open(jsonl_path, "r", encoding="utf-8") as handle:
    for raw in handle:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entries.append(json.loads(raw))
        except Exception:
            continue
recap_entry = next((entry for entry in entries if entry.get("stage") == "memory-recap"), None)
if recap_entry is None:
    print("missing recap entry")
    sys.exit(1)
body = recap_entry.get("body") or {}
reported = body.get("questions") or []
missing = [question for question in expected if not any(question in reported_item for reported_item in reported)]
report = {
    "session_id": body.get("chat_session_id"),
    "expected_questions": expected,
    "reported_questions": reported,
    "question_entries": body.get("question_entries") or [],
    "turns": turns,
    "stages": [entry.get("stage") for entry in entries],
}
tone_fails = [
    entry.get("stage")
    for entry in entries
    if (entry.get("body") or {}).get("tone_analysis", {}).get("status") == "fail"
]
report["tone_failures"] = tone_fails
with open(report_path, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)
if missing:
    print("missing questions:", ", ".join(missing))
    sys.exit(2)
print("ok")
PY
  local status=$?
  if [[ $status -ne 0 ]]; then
    return 1
  fi
  return 0
}

ensure_sample_wav() {
  local duration=${1:-1.2}
  SAMPLE_WAV=$(mktemp --suffix=.wav)
  python3 - "$SAMPLE_WAV" "$duration" <<'PY'
import sys, wave, struct, math
path = sys.argv[1]
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
rate = 16000
freq = 440.0
amp = 8000
n = int(rate * dur)
wf = wave.open(path, 'w')
wf.setnchannels(1)
wf.setsampwidth(2)
wf.setframerate(rate)
for i in range(n):
    value = int(amp * math.sin(2*math.pi*freq*(i/float(rate))))
    wf.writeframes(struct.pack('<h', value))
wf.close()
print(path)
PY
  SAMPLE_WAV_PATH="$SAMPLE_WAV"
}

perform_multipart_upload() {
  local label=$1
  local url=$2
  local file_field=$3
  local file_path=$4
  local tmp
  tmp=$(mktemp)
  set +e
  local status
  status=$(curl -sS -o "$tmp" -w "%{http_code}" -F "$file_field=@$file_path;type=audio/wav" -b "$COOKIE_JAR" -H "X-CSRF-Token: $CSRF_TOKEN" "$url")
  local curl_exit=$?
  set -e
  local body
  body=$(cat "$tmp")
  rm -f "$tmp"
  if [[ $curl_exit -ne 0 ]]; then
    echo "$body" >&2
    log_failure "$label (curl exit $curl_exit)"
    return 1
  fi
  if [[ "$status" == 2* ]]; then
    if [[ "$VERBOSE" == "1" ]]; then
      echo "$label response:"
      echo "$body"
    fi
    log_success "$label ($status)"
    LAST_JSON_BODY="$body"
    return 0
  fi
  echo "$body" >&2
  log_failure "$label (HTTP $status)"
  return 1
}

AUTH_READY=0
CSRF_TOKEN=""
AUTH_OPTS=()
TRANS_TEXT=""

ensure_login() {
  if [[ "$AUTH_READY" == "1" ]]; then
    return 0
  fi
  if [[ "$ENABLE_LOGIN_TESTS" != "1" ]]; then
    log_failure "Authentication flow disabled"
    return 1
  fi
  log_section "Authentication flow"
  local payload
  payload=$(cat <<JSON
{"username":"$TEST_USERNAME","password":"$TEST_PASSWORD","remember_me":false}
JSON
)
  local login_tmp
  login_tmp=$(mktemp)
  set +e
  local status
  status=$(curl -sS -o "$login_tmp" -w "%{http_code}" -c "$COOKIE_JAR" -H 'Content-Type: application/json' -d "$payload" "$GATEWAY_URL/api/auth/login")
  local curl_exit=$?
  set -e
  local login_body
  login_body=$(cat "$login_tmp")
  rm -f "$login_tmp"
  if [[ $curl_exit -ne 0 ]]; then
    log_failure "Login request failed (curl exit $curl_exit)"
    return 1
  elif [[ "$status" != 2* ]]; then
    log_failure "Login failed (HTTP $status). Body: $login_body"
    return 1
  fi
  local success
  success=$(printf '%s' "$login_body" | python3 -c 'import json,sys; data=json.load(sys.stdin); print("1" if data.get("success") else "0")' 2>/dev/null || echo "0")
  if [[ "$success" != "1" ]]; then
    log_failure "Login API returned success=false"
    return 1
  fi
  CSRF_TOKEN=$(printf '%s' "$login_body" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("csrf_token",""))' 2>/dev/null || echo "")
  if [[ -z "$CSRF_TOKEN" && -s "$COOKIE_JAR" ]]; then
    CSRF_TOKEN=$(awk '$6 == "ws_csrf" {token=$7} END {print token}' "$COOKIE_JAR")
  fi
  AUTH_READY=1
  AUTH_OPTS=(-b "$COOKIE_JAR")
  [[ -n "$CSRF_TOKEN" ]] && AUTH_OPTS+=( -H "X-CSRF-Token: $CSRF_TOKEN" )
  log_success "Login succeeded for user $TEST_USERNAME"
  return 0
}

require_auth() {
  if ensure_login; then
    return 0
  fi
  echo -e "${RED}Authentication required; skipping feature.${NC}" >&2
  return 1
}

run_health() {
  log_section "Gateway health checks"
  perform_request "Gateway /health" GET "$GATEWAY_URL/health"
  perform_request "Gateway /api/health" GET "$GATEWAY_URL/api/health"
}

run_auth() {
  if ! require_auth; then return; fi
  perform_request "Auth check" GET "$GATEWAY_URL/api/auth/check" "" "${AUTH_OPTS[@]}"
  perform_request "Current session" GET "$GATEWAY_URL/api/auth/session" "" "${AUTH_OPTS[@]}"
  perform_request "Logout" POST "$GATEWAY_URL/api/auth/logout" '{}' "${AUTH_OPTS[@]}"
  local previous_cookie="$COOKIE_JAR"
  COOKIE_JAR=$(mktemp)
  rm -f "$previous_cookie"
  AUTH_READY=0
  AUTH_OPTS=()
  CSRF_TOKEN=""
  ensure_login
}

load_transcription_text() {
  local text="$TRANSCRIPTION_TEXT"
  if [[ -n "$TRANSCRIPTION_TEXT_FILE" ]]; then
    if [[ ! -f "$TRANSCRIPTION_TEXT_FILE" ]]; then
      log_failure "Transcription text file not found: $TRANSCRIPTION_TEXT_FILE"
      return 1
    fi
    local file_text
    file_text=$(<"$TRANSCRIPTION_TEXT_FILE")
    text="${text:+$text$'\n'}$file_text"
  fi
  if [[ -z "$text" ]]; then
    log_failure "No transcription text provided"
    return 1
  fi
  local text_file
  text_file=$(mktemp)
  printf "%s" "$text" >"$text_file"
  run_cli "Compose transcript" compose-transcript --text-file "$text_file" --speaker "$TRANSCRIPTION_SPEAKER"
  rm -f "$text_file"
  TRANS_TEXT="$text"
  return 0
}

compose_sample_transcript() {
  local text=$1
  local speaker=${2:-$TRANSCRIPTION_SPEAKER}
  local tmp
  tmp=$(mktemp)
  printf "%s" "$text" >"$tmp"
  run_cli "Compose transcript (auto)" compose-transcript --text-file "$tmp" --speaker "$speaker"
  rm -f "$tmp"
  TRANS_TEXT="$text"
  COMPOSED_TRANSCRIPT_TEXT="$text"
}

run_transcription() {
  if ! require_auth; then return; fi
  log_section "Transcription upload"
  if [[ -n "$TRANSCRIPTION_TEXT" || -n "$TRANSCRIPTION_TEXT_FILE" ]]; then
    load_transcription_text || return
  else
    local typed_text="Automated Nemo CLI typed transcript ${UNIQUE_TAG}."
    compose_sample_transcript "$typed_text" "$TRANSCRIPTION_SPEAKER"
  fi
  local wav_path="$TRANSCRIPTION_FILE"
  if [[ -n "$wav_path" ]]; then
    if [[ ! -f "$wav_path" ]]; then
      log_failure "Transcription file not found: $wav_path"
      return
    fi
  else
    ensure_sample_wav
    wav_path="$SAMPLE_WAV_PATH"
  fi
  perform_multipart_upload "Transcribe sample wav" "$GATEWAY_URL/api/transcription/transcribe" "file" "$wav_path"
  LAST_TRANSCRIPT_JOB_ID=$(JSON_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json, os
try:
  data=json.loads(os.environ.get('JSON_BODY','') or '{}')
except Exception:
  data={}
for key in ('job_id','id','transcript_id','jobId'):
  value=data.get(key)
  if isinstance(value,str) and value.strip():
    print(value.strip())
    break
else:
  print('')
PY
)
  local text
  text=$(JSON_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json, os
try:
  data=json.loads(os.environ.get('JSON_BODY','') or '{}')
  if data.get('text'):
    print(data['text'])
  else:
    seg=data.get('segments') or []
    print(' '.join((s or {}).get('text','') for s in seg))
except Exception:
  print('')
PY
)
  if [[ -n "$text" ]]; then
    LAST_AUDIO_TRANSCRIPT="$text"
  fi
  if [[ -z "$TRANS_TEXT" ]]; then
    if [[ -n "$COMPOSED_TRANSCRIPT_TEXT" ]]; then
      TRANS_TEXT="$COMPOSED_TRANSCRIPT_TEXT"
    else
      TRANS_TEXT=${text:-"Automated system test content."}
    fi
  fi
}

run_transcripts() {
  if ! require_auth; then return; fi
  log_section "Transcript endpoints"
  perform_request "Transcripts recent" GET "$GATEWAY_URL/api/transcripts/recent?limit=3" "" "${AUTH_OPTS[@]}"
  if [[ -z "$LAST_TRANSCRIPT_JOB_ID" ]]; then
    LAST_TRANSCRIPT_JOB_ID=$(JSON_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json, os
try:
  data=json.loads(os.environ.get('JSON_BODY','') or '{}')
except Exception:
  data={}
items=data.get('transcripts') or data.get('items') or []
if isinstance(items, list):
  for entry in items:
    job=entry.get('job_id') or entry.get('transcript_id')
    if isinstance(job, str) and job:
      print(job)
      break
  else:
    print('')
else:
  print('')
PY
)
  fi
  if [[ -n "$LAST_TRANSCRIPT_JOB_ID" ]]; then
    perform_request "Transcript detail" GET "$GATEWAY_URL/api/transcript/$LAST_TRANSCRIPT_JOB_ID" "" "${AUTH_OPTS[@]}"
  else
    echo -e "${YELLOW}No transcript job_id available for detail lookup.${NC}" >&2
  fi
  perform_request "Transcripts count" POST "$GATEWAY_URL/api/transcripts/count" '{"last_days":7}' "${AUTH_OPTS[@]}"
  perform_request_optional "Transcript speakers" GET "$GATEWAY_URL/api/transcripts/speakers" "" "${AUTH_OPTS[@]}"
  local transcripts_query
  transcripts_query=$(UNIQUE_TAG="$UNIQUE_TAG" python3 - <<'PY'
import json, os
keyword=os.environ.get('UNIQUE_TAG', 'Automated')
print(json.dumps({
  "limit": 5,
  "match": "any",
  "keywords": keyword,
  "emotions": ["neutral"]
}))
PY
)
  perform_request "Transcripts query (keywords)" POST "$GATEWAY_URL/api/transcripts/query" "$transcripts_query" "${AUTH_OPTS[@]}"
}

ensure_trans_text() {
  if [[ -z "$TRANS_TEXT" ]]; then
    TRANS_TEXT="Automated system test content."
  fi
}

run_analysis() {
  if ! require_auth; then return; fi
  ensure_trans_text
  log_section "Analysis artifacts"
  local archive_payload
  archive_payload=$(python3 - <<PY
import json,os
print(json.dumps({"title":"CLI System Test Artifact","body":os.environ.get('TRANS_TEXT','Automated verification payload'),"filters":{}}))
PY
)
  perform_request "Archive artifact" POST "$GATEWAY_URL/api/analysis/archive" "$archive_payload" "${AUTH_OPTS[@]}"
  local archive_resp="$LAST_JSON_BODY"
  LAST_ARCHIVED_ARTIFACT_ID=$(JSON_BODY="$archive_resp" python3 - <<'PY'
import json, os
try:
  data=json.loads(os.environ.get('JSON_BODY','') or '{}')
except Exception:
  data={}
print(data.get('artifact_id',''))
PY
)
  perform_request "Analysis list" GET "$GATEWAY_URL/api/analysis/list?limit=5" "" "${AUTH_OPTS[@]}"
  local analysis_list_body="$LAST_JSON_BODY"
  perform_request_optional "Analysis search" POST "$GATEWAY_URL/api/analysis/search" '{"query":"Automated"}' "${AUTH_OPTS[@]}"

  # Gemma conversation on artifact: turn 1 (ask about the analysis)
  ARTIFACT_ID=$(JSON_BODY="$analysis_list_body" python3 - <<'PY'
import json, os
try:
  data=json.loads(os.environ.get('JSON_BODY','') or '{}')
  items=data.get('items') or data.get('artifacts') or []
  if isinstance(items,list) and items:
    aid=items[0].get('artifact_id') or items[0].get('id')
    print(aid or '')
  else:
    print('')
except Exception:
  print('')
PY
)
  if [[ -n "$ARTIFACT_ID" ]]; then
    local analysis_question="Summarize this artifact in one sentence."
    local artifact_body=""
    local use_local_chat=0
    if is_local_artifact_id "$ARTIFACT_ID"; then
      use_local_chat=1
      perform_request "Fetch artifact body (analysis)" GET "$GATEWAY_URL/api/analysis/$ARTIFACT_ID" "" "${AUTH_OPTS[@]}"
      artifact_body=$(JSON_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json,os
try:
  data=json.loads(os.environ.get('JSON_BODY','') or '{}')
  artifact=data.get('artifact') or {}
  print((artifact.get('body') or '').strip())
except Exception:
  print('')
PY
)
    fi
    log_conversation "user" "[analysis artifact] $analysis_question"
    if [[ "$use_local_chat" -eq 0 ]]; then
      CHAT1_PAYLOAD=$(ARTIFACT_ID="$ARTIFACT_ID" ANALYSIS_QUESTION="$analysis_question" python3 - <<'PY'
import json,os
aid=os.environ.get('ARTIFACT_ID','')
question=os.environ.get('ANALYSIS_QUESTION',"Summarize this artifact in one sentence.")
print(json.dumps({
  "artifact_id": aid,
  "message": question,
  "mode": "rag",
  "max_tokens": 128,
  "temperature": 0.3
}))
PY
)
      perform_request "Chat on artifact (turn 1)" POST "$GATEWAY_URL/api/gemma/chat-on-artifact" "$CHAT1_PAYLOAD" "${AUTH_OPTS[@]}"
    else
      CHAT1_FALLBACK=$(ARTIFACT_CONTEXT="$artifact_body" ANALYSIS_QUESTION="$analysis_question" python3 - <<'PY'
import json, os
context=os.environ.get('ARTIFACT_CONTEXT','').strip()
if len(context) > 4000:
    context = context[-4000:]
question=os.environ.get('ANALYSIS_QUESTION',"Summarize this artifact in one sentence.")
query=f"{question}\n\nContext:\n{context}" if context else question
payload={
  "query": query,
  "max_tokens": 384,
  "temperature": 0.4,
  "top_k_results": 4,
  "session_id": None,
  "history_messages": [],
  "user_message": question,
}
print(json.dumps(payload))
PY
)
      perform_request "Chat on artifact (turn 1, local fallback)" POST "$GATEWAY_URL/api/gemma/chat-rag" "$CHAT1_FALLBACK" "${AUTH_OPTS[@]}"
    fi

    # Extract assistant reply text for continuity
    ASSIST_TEXT=$(JSON_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json,os
try:
  d=json.loads(os.environ.get('JSON_BODY','') or '{}')
  for key in ('text','response','answer'):
    v=d.get(key)
    if isinstance(v,str) and v.strip():
      print(v.strip()); raise SystemExit
  ch=d.get('choices')
  if isinstance(ch,list) and ch and isinstance(ch[0],dict):
    t=ch[0].get('text') or ch[0].get('message',{}).get('content','')
    print((t or '').strip())
  else:
    print('')
except Exception:
  print('')
PY
)
    if [[ -n "$ASSIST_TEXT" ]]; then
      log_conversation "assistant" "[analysis artifact] $ASSIST_TEXT"
      CHAT2_PAYLOAD=$(python3 - <<PY
import json,os
assist=os.environ.get('ASSIST_TEXT','')
print(json.dumps({
  "messages":[
    {"role":"user","content":"Summarize this artifact in one sentence."},
    {"role":"assistant","content":assist},
    {"role":"user","content":"Give two bullet points expanding on your last answer."}
  ],
  "max_tokens": 192,
  "temperature": 0.3
}))
PY
)
      perform_request "Gemma chat (turn 2)" POST "$GATEWAY_URL/api/gemma/chat" "$CHAT2_PAYLOAD" "${AUTH_OPTS[@]}"
      log_conversation "user" "[analysis artifact] Give two bullet points expanding on your last answer."
      CHAT2_REPLY=$(extract_response_text)
      if [[ -n "$CHAT2_REPLY" ]]; then
        log_conversation "assistant" "[analysis artifact] $CHAT2_REPLY"
      fi
    else
      echo -e "${YELLOW}Assistant reply missing; skipping turn 2 chat continuity.${NC}" >&2
    fi
  else
    echo -e "${YELLOW}No artifact available to chat about; skipping artifact conversation.${NC}" >&2
  fi
}

run_gemma() {
  if ! require_auth; then return; fi
  ensure_trans_text
  log_section "Gemma proxy"
  perform_request "Gemma generate" POST "$GATEWAY_URL/api/gemma/generate" '{"prompt":"Return a single sentence greeting for system check.","max_tokens":64,"temperature":0.2}' "${AUTH_OPTS[@]}"
  perform_request "Gemma chat" POST "$GATEWAY_URL/api/gemma/chat" '{"messages":[{"role":"user","content":"Say hello and mention Nemo."}],"max_tokens":64,"temperature":0.2}' "${AUTH_OPTS[@]}"
  perform_request "Gemma warmup" POST "$GATEWAY_URL/api/gemma/warmup" '{}' "${AUTH_OPTS[@]}"
  perform_request "Gemma stats" GET "$GATEWAY_URL/api/gemma/stats" "" "${AUTH_OPTS[@]}"
  local rag_payload
  rag_payload=$(python3 - <<PY
import json,os
print(json.dumps({
  "query": "Use context to summarize.",
  "user_message": "Use context to summarize.",
  "history_messages": [{"role":"user","content":"Use context to summarize."}],
  "context": os.environ.get('TRANS_TEXT','Automated verification payload'),
  "max_tokens": 64
}))
PY
)
  perform_request "Gemma chat-rag" POST "$GATEWAY_URL/api/gemma/chat-rag" "$rag_payload" "${AUTH_OPTS[@]}"
  log_conversation "user" "[gemma rag] Use context to summarize."
  local RAG_REPLY
  RAG_REPLY=$(extract_response_text)
  if [[ -n "$RAG_REPLY" ]]; then
    log_conversation "assistant" "[gemma rag] $RAG_REPLY"
  fi

  log_section "Gemma conversational memory"
  local convo_auth_opts=("${AUTH_OPTS[@]}" -H "X-Conversation-Test: 1")
  local convo_session="conv-${UNIQUE_TAG}"
  local convo_questions=(
    "What are the top two compliance priorities for ${UNIQUE_TAG}?"
    "How should I brief leadership about ${UNIQUE_TAG}?"
    "Which teams depend on the outcomes tied to ${UNIQUE_TAG}?"
    "What risks could delay work related to ${UNIQUE_TAG}?"
    "Which metrics prove ${UNIQUE_TAG} is successful?"
  )
  for idx in "${!convo_questions[@]}"; do
    local question="${convo_questions[$idx]}"
    local payload
    payload=$(SESSION_ID="$convo_session" QUESTION="$question" python3 - <<'PY'
import json, os
max_tokens = int(os.environ.get("CONVO_MAX_TOKENS", "192") or 192)
print(json.dumps({
  "session_id": os.environ.get("SESSION_ID"),
  "messages": [{"role": "user", "content": os.environ.get("QUESTION", "")}],
  "max_tokens": max_tokens,
  "temperature": 0.3
}))
PY
)
    local stage="memory-q$((idx+1))"
    perform_request "Gemma memory Q$((idx+1))" POST "$GATEWAY_URL/api/gemma/chat" "$payload" "${convo_auth_opts[@]}"
    log_conversation "user" "[memory-test] $question"
    local answer
    answer=$(extract_response_text)
    if [[ -n "$answer" ]]; then
      log_conversation "assistant" "[memory-test] $answer"
    fi
    record_convo_payload "$stage"
    assert_tone_status "$stage"
  done

  local recap_payload
recap_payload=$(SESSION_ID="$convo_session" python3 - <<'PY'
import json, os
max_tokens = int(os.environ.get("CONVO_MAX_TOKENS", "192") or 192)
print(json.dumps({
  "session_id": os.environ.get("SESSION_ID"),
  "messages": [{"role": "user", "content": "What questions have I asked you so far?"}],
  "max_tokens": max_tokens,
  "temperature": 0.3
}))
PY
)
  perform_request "Gemma question recap" POST "$GATEWAY_URL/api/gemma/chat" "$recap_payload" "${convo_auth_opts[@]}"
  log_conversation "user" "[memory-test] What questions have I asked you so far?"
  local recap_body="$LAST_JSON_BODY"
  local recap_check
  recap_check=$(EXPECTED_QUESTIONS="$(printf '%s\n' "${convo_questions[@]}")" BODY="$recap_body" python3 - <<'PY'
import os, json
expected = [line.strip() for line in os.environ.get('EXPECTED_QUESTIONS','').split('\n') if line.strip()]
body = os.environ.get('BODY','')
try:
    data = json.loads(body)
except Exception:
    print("invalid json")
    raise SystemExit(1)
returned = data.get('questions') or []
text = data.get('message') or data.get('text') or ''
missing = []
for question in expected:
    if not any(question in q for q in returned) and question not in text:
        missing.append(question)
if missing:
    print("Missing questions:", missing)
    raise SystemExit(1)
print("ok")
PY
)
  if [[ "$recap_check" != "ok" ]]; then
    log_failure "Gemma question recap missing items"
  else
    log_success "Gemma question recap captured all prompts"
  fi
  log_conversation "assistant" "[memory-test] $(extract_response_text)"
  record_convo_payload "memory-recap"
  assert_tone_status "memory-recap"

  local followups=(
    "Please recap the answer you gave for the second question."
    "Which earlier question should I prioritize first and why?"
  )
  local follow_idx=0
  for follow in "${followups[@]}"; do
    follow_idx=$((follow_idx + 1))
    local follow_payload
    follow_payload=$(SESSION_ID="$convo_session" QUESTION="$follow" python3 - <<'PY'
import json, os
max_tokens = int(os.environ.get("CONVO_MAX_TOKENS", "192") or 192)
print(json.dumps({
  "session_id": os.environ.get("SESSION_ID"),
  "messages": [{"role": "user", "content": os.environ.get("QUESTION", "")}],
  "max_tokens": max_tokens,
  "temperature": 0.3
}))
PY
)
    local follow_stage="memory-follow-$follow_idx"
    perform_request "Gemma memory follow-up" POST "$GATEWAY_URL/api/gemma/chat" "$follow_payload" "${convo_auth_opts[@]}"
    log_conversation "user" "[memory-test] $follow"
    local follow_answer
    follow_answer=$(extract_response_text)
    if [[ -n "$follow_answer" ]]; then
      log_conversation "assistant" "[memory-test] $follow_answer"
    fi
    record_convo_payload "$follow_stage"
    assert_tone_status "$follow_stage"
  done
  local expected_blob
  expected_blob=$(printf '%s\n' "${convo_questions[@]}")
  if generate_convo_report "$expected_blob"; then
    log_success "Gemma conversation dossier ready at $CONVO_REPORT"
  else
    log_failure "Gemma conversation dossier generation failed"
  fi
}

run_rag() {
  if ! require_auth; then return; fi
  ensure_trans_text
  log_section "RAG + Semantic search"
  local rag_payload
  rag_payload=$(python3 - <<'PY'
import json, os
query = f"Locate insights referencing {os.environ.get('UNIQUE_TAG','Automated')}"
print(json.dumps({"query": query}))
PY
)
  local rag_found=1
  for attempt in 1 2 3; do
    perform_request "RAG query (attempt ${attempt}/3)" POST "$GATEWAY_URL/api/rag/query" "$rag_payload" "${AUTH_OPTS[@]}" || return
    if response_contains_keyword "$UNIQUE_TAG"; then
      rag_found=0
      break
    fi
    sleep 5
  done
  if [[ $rag_found -ne 0 ]]; then
    log_failure "RAG query result missing keyword $UNIQUE_TAG"
  fi

  local semantic_payload
  semantic_payload=$(python3 - <<'PY'
import json, os
keyword = os.environ.get('UNIQUE_TAG','Automated')
print(json.dumps({"query": keyword, "top_k": 5}))
PY
)
  local semantic_found=1
  for attempt in 1 2 3; do
    perform_request "Semantic search (attempt ${attempt}/3)" POST "$GATEWAY_URL/api/search/semantic" "$semantic_payload" "${AUTH_OPTS[@]}" || return
    if response_contains_keyword "$UNIQUE_TAG"; then
      semantic_found=0
      break
    fi
    sleep 5
  done
  if [[ $semantic_found -ne 0 ]]; then
    log_failure "Semantic search missing keyword $UNIQUE_TAG"
  fi
}

run_memories() {
  if ! require_auth; then return; fi
  ensure_trans_text
  log_section "Memories"
  local memory_payload
  memory_payload=$(python3 - <<PY
import json,os
print(json.dumps({
  "title":"CLI System Test Memory",
  "body": os.environ.get('TRANS_TEXT','Automated verification payload'),
  "metadata":{"source":"cli_test"}
}))
PY
)
  perform_request "Memory create" POST "$GATEWAY_URL/api/memory/create" "$memory_payload" "${AUTH_OPTS[@]}"
  local memory_search_payload
  memory_search_payload=$(python3 - <<'PY'
import json, os
print(json.dumps({"query": os.environ.get('UNIQUE_TAG','Automated'), "limit": 3}))
PY
)
  perform_request "Memory search" POST "$GATEWAY_URL/api/memory/search" "$memory_search_payload" "${AUTH_OPTS[@]}"
  if ! response_contains_keyword "$UNIQUE_TAG"; then
    log_failure "Memory search missing keyword $UNIQUE_TAG"
  fi
  perform_request "Memory stats" GET "$GATEWAY_URL/api/memory/stats" "" "${AUTH_OPTS[@]}"
  perform_request "Memory emotions stats" GET "$GATEWAY_URL/api/memory/emotions/stats" "" "${AUTH_OPTS[@]}"
}

run_emotions() {
  if ! require_auth; then return; fi
  ensure_trans_text
  log_section "Emotions"
  local payload
  payload=$(python3 - <<PY
import json,os
print(json.dumps({"text": os.environ.get('TRANS_TEXT','Automated verification payload')}))
PY
)
  perform_request "Emotion analyze" POST "$GATEWAY_URL/api/emotion/analyze" "$payload" "${AUTH_OPTS[@]}"
}

run_analyzer() {
  if ! require_auth; then return; fi
  ensure_trans_text
  log_section "Gemma analyzer"
  local analyzer_payload
  analyzer_payload=$(python3 - <<'PY'
import os, json
filters = json.loads(os.environ.get("ANALYZER_FILTERS", "{}") or "{}")
prompt = os.environ.get("ANALYZER_PROMPT", "Identify hyperbole and fallacies.")
payload = {
    "filters": filters,
    "custom_prompt": prompt,
    "max_tokens": 512,
    "temperature": 0.4,
}
print(json.dumps(payload), end="")
PY
)
  perform_request "Gemma analyze" POST "$GATEWAY_URL/api/gemma/analyze" "$analyzer_payload" "${AUTH_OPTS[@]}"
  local analyzer_validation
  analyzer_validation=$(JSON_BODY="$LAST_JSON_BODY" ANALYZER_LIMIT="$ANALYZER_LIMIT" ANALYZER_EMOTIONS="$ANALYZER_EMOTIONS" python3 - <<'PY'
import json, os
data = {}
try:
    data = json.loads(os.environ.get('JSON_BODY', '') or '{}')
except Exception:
    pass
limit_target = int(os.environ.get('ANALYZER_LIMIT', '2') or 2)
targets = [e.strip().lower() for e in (os.environ.get('ANALYZER_EMOTIONS', '') or '').split(',') if e.strip()]

filters = data.get('filters_applied') or data.get('filters') or {}
limit_value = filters.get('limit') if isinstance(filters, dict) else None
if limit_value is None:
    limit_value = data.get('limit')
try:
    limit_value = int(limit_value)
except Exception:
    limit_value = None
limit_ok = (limit_value == limit_target)

em_filter = []
if isinstance(filters, dict):
    emo = filters.get('emotions') or filters.get('emotions_selected')
    if isinstance(emo, (list, tuple)):
        em_filter = [str(e).lower() for e in emo]
    elif isinstance(emo, str):
        em_filter = [emo.lower()]
em_targets_ok = (not targets) or (sorted(set(em_filter)) == sorted(set(targets)))

items = data.get('items') or data.get('results') or data.get('analysis_rows') or data.get('segments') or []
if isinstance(items, dict):
    nested = items.get('items')
    if isinstance(nested, list):
        items = nested
count_items = len(items) if isinstance(items, list) else 0
transcripts = data.get('transcripts_analyzed')
try:
    transcripts = int(transcripts)
except Exception:
    transcripts = None
if transcripts is None and count_items:
    transcripts = count_items
transcripts = transcripts or 0
transcripts_ok = transcripts <= limit_target and transcripts > 0

if limit_ok and em_targets_ok and transcripts_ok:
    print(f"OK limit={limit_value} emotions={em_filter} transcripts={transcripts}")
else:
    print(f"ERR limit={limit_value} target={limit_target} emotions={em_filter} targets={targets} transcripts={transcripts}")
PY
)
  if [[ "$analyzer_validation" == OK* ]]; then
    log_success "Analyzer batch matched filters ($analyzer_validation)"
  else
    log_failure "Analyzer batch mismatch: $analyzer_validation"
  fi
  local stream_payload
  stream_payload=$(python3 - <<'PY'
import os, json
filters = json.loads(os.environ.get("ANALYZER_FILTERS", "{}") or "{}")
prompt = os.environ.get("ANALYZER_PROMPT", "Identify hyperbole and fallacies.")
stream_id = os.environ.get("ANALYZER_STREAM_ID", "cli-test-stream")
payload = {
    "analysis_id": stream_id,
    "filters": filters,
    "custom_prompt": prompt,
    "max_tokens": 512,
    "temperature": 0.4,
}
print(json.dumps(payload), end="")
PY
)
  if perform_request "Gemma analyze (stream job)" POST "$GATEWAY_URL/api/gemma/analyze/stream" "$stream_payload" "${AUTH_OPTS[@]}"; then
    local job_id
    job_id=$(printf '%s' "$LAST_JSON_BODY" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("job_id",""))')
    if [[ -n "$job_id" ]]; then
      # Stream SSE updates for up to ANALYZER_SSE_TIMEOUT seconds
      local sse_tmp
      sse_tmp=$(mktemp)
      local sse_timeout=${ANALYZER_SSE_TIMEOUT:-45}
      set +e
      timeout "$sse_timeout" curl -sS -N -b "$COOKIE_JAR" -H "X-CSRF-Token: $CSRF_TOKEN" "$GATEWAY_URL/api/gemma/analyze/stream/$job_id" >"$sse_tmp"
      local sse_status=$?
      set -e
      if [[ $sse_status -eq 0 ]]; then
        log_success "Gemma analyze SSE stream captured"
      elif [[ $sse_status -eq 124 ]]; then
        echo -e "${YELLOW}Gemma analyze SSE capture hit timeout (${sse_timeout}s). Using partial stream.${NC}" >&2
      else
        echo -e "${YELLOW}Gemma analyze SSE capture failed (exit $sse_status).${NC}" >&2
      fi
      # Try to extract artifact_id from any 'done' event in the stream, else pick by analysis_id from list
      local stream_artifact_id
      stream_artifact_id=$(python3 - "$sse_tmp" <<'PY'
import sys, json, re
path=sys.argv[1]
aid=""
data=open(path,'r',encoding='utf-8',errors='ignore').read()
for m in re.finditer(r"^event:\s*done\s*\ndata:\s*(\{.*?\})\s*\n\n", data, flags=re.M|re.S):
    try:
        obj=json.loads(m.group(1))
        a=obj.get('artifact_id') or ''
        if a:
            aid=a; break
    except Exception:
        pass
print(aid)
PY
)
      if [[ -z "$stream_artifact_id" ]]; then
        local archive_payload
        archive_payload=$(TARGET_ANALYSIS="$ANALYZER_STREAM_ID" python3 - "$sse_tmp" <<'PY'
import sys, json, re, os
from datetime import datetime
path=sys.argv[1]
try:
    data=open(path,'r',encoding='utf-8',errors='ignore').read()
except Exception:
    print("")
    raise SystemExit
sections=[]
for match in re.finditer(r"event:\s*(\w+)\s*\ndata:\s*(\{.*?\})(?:\n\n|\Z)", data, flags=re.S):
    event=match.group(1).strip()
    payload_str=match.group(2).strip()
    try:
        payload=json.loads(payload_str)
    except Exception:
        continue
    if event != "result":
        continue
    item=payload.get("item") or {}
    lines=[]
    idx=payload.get("i")
    total=payload.get("total")
    lines.append(f"Statement {idx or '?'} of {total or '?'}")
    speaker=item.get("speaker") or "Unknown"
    emotion=item.get("emotion") or "n/a"
    lines.append(f"Speaker: {speaker} (emotion: {emotion})")
    if item.get("text"):
        lines.append(f"Statement text: {item.get('text')}")
    ctx=item.get("context_before") or []
    if ctx:
        lines.append("Context before:")
        for entry in ctx:
            lines.append(f"  - {(entry or {}).get('speaker') or 'Speaker'}: {(entry or {}).get('text') or ''}")
    response=payload.get("response") or ""
    if response.strip():
        lines.append("Gemma response:")
        lines.append(response.strip())
    sections.append("\n".join(lines))
if not sections:
    print("")
else:
    metadata={"analysis_id": os.environ.get("TARGET_ANALYSIS",""), "source": "cli_test_stream_local"}
    title=f"Streaming Analysis ({datetime.utcnow().isoformat()}Z)"
    body="\n\n".join(sections)
    payload={"title": title, "body": body, "metadata": metadata}
    if metadata.get("analysis_id"):
        payload["analysis_id"]=metadata["analysis_id"]
    print(json.dumps(payload))
PY
)
        if [[ -n "$archive_payload" ]]; then
          perform_request "Archive streamed artifact (local)" POST "$GATEWAY_URL/api/analysis/archive" "$archive_payload" "${AUTH_OPTS[@]}"
          stream_artifact_id=$(JSON_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json,os
try:
  data=json.loads(os.environ.get('JSON_BODY','') or '{}')
  print(data.get('artifact_id',''))
except Exception:
  print('')
PY
)
        fi
      fi
      if [[ -z "$stream_artifact_id" ]]; then
        if poll_artifact_by_analysis "$ANALYZER_STREAM_ID" 12 5; then
          stream_artifact_id="$STREAM_ARTIFACT_ID"
        else
          stream_artifact_id=""
        fi
      fi
      rm -f "$sse_tmp"
      if [[ -n "$stream_artifact_id" ]]; then
        # Ask about the freshly created analysis artifact (turn 1)
        local stream_question="$ANALYZER_CHAT_PROMPT"
        local stream_artifact_body=""
        local stream_use_local=0
        if is_local_artifact_id "$stream_artifact_id"; then
          stream_use_local=1
          perform_request "Fetch streamed artifact body" GET "$GATEWAY_URL/api/analysis/$stream_artifact_id" "" "${AUTH_OPTS[@]}"
          stream_artifact_body=$(JSON_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json,os
try:
  data=json.loads(os.environ.get('JSON_BODY','') or '{}')
  artifact=data.get('artifact') or {}
  print((artifact.get('body') or '').strip())
except Exception:
  print('')
PY
)
        fi
        if [[ "$stream_use_local" -eq 0 ]]; then
          local CHAT_S1
          CHAT_S1=$(stream_artifact_id="$stream_artifact_id" ANALYZER_CHAT_PROMPT="$stream_question" python3 - <<'PY'
import json,os
aid=os.environ.get('stream_artifact_id','')
prompt=os.environ.get('ANALYZER_CHAT_PROMPT',"What are the top 2 risks in this analysis?")
print(json.dumps({
  "artifact_id": aid,
  "message": prompt,
  "mode": "rag",
  "max_tokens": 128,
  "temperature": 0.3
}), end="")
PY
)
          perform_request "Chat on streamed artifact (turn 1)" POST "$GATEWAY_URL/api/gemma/chat-on-artifact" "$CHAT_S1" "${AUTH_OPTS[@]}"
        else
          local CHAT_S1_FALLBACK
          CHAT_S1_FALLBACK=$(ARTIFACT_CONTEXT="$stream_artifact_body" ANALYZER_CHAT_PROMPT="$stream_question" python3 - <<'PY'
import json, os
context=os.environ.get('ARTIFACT_CONTEXT','').strip()
if len(context) > 4000:
    context = context[-4000:]
prompt=os.environ.get('ANALYZER_CHAT_PROMPT',"What are the top 2 risks in this analysis?")
query=f"{prompt}\n\nContext:\n{context}" if context else prompt
payload={
  "query": query,
  "max_tokens": 384,
  "temperature": 0.4,
  "top_k_results": 4,
  "session_id": None,
  "history_messages": [],
  "user_message": prompt,
}
print(json.dumps(payload))
PY
)
          perform_request "Chat on streamed artifact (turn 1, local fallback)" POST "$GATEWAY_URL/api/gemma/chat-rag" "$CHAT_S1_FALLBACK" "${AUTH_OPTS[@]}"
        fi
        log_conversation "user" "[analyzer stream] $stream_question"
        # Extract assistant reply and continue the conversation (turn 2)
        local S1_REPLY
        S1_REPLY=$(JSON_BODY="$LAST_JSON_BODY" python3 - <<'PY'
import json,os
try:
  d=json.loads(os.environ.get('JSON_BODY','') or '{}')
  for key in ('text','response','answer'):
    v=d.get(key)
    if isinstance(v,str) and v.strip():
      print(v.strip()); raise SystemExit
  ch=d.get('choices')
  if isinstance(ch,list) and ch and isinstance(ch[0],dict):
    t=ch[0].get('text') or ch[0].get('message',{}).get('content','')
    print((t or '').strip())
  else:
    print('')
except Exception:
  print('')
PY
)
        if [[ -n "$S1_REPLY" ]]; then
          log_conversation "assistant" "[analyzer stream] $S1_REPLY"
          local CHAT_S2
          CHAT_S2=$(S1_REPLY="$S1_REPLY" python3 - <<'PY'
import json,os
reply=os.environ.get('S1_REPLY','')
first=os.environ.get('ANALYZER_CHAT_PROMPT',"What are the top 2 risks in this analysis?")
context=os.environ.get('ANALYZER_CHAT_CONTEXT',"Context: Provide more detail.")
follow=os.environ.get('ANALYZER_CHAT_CONTEXT_PROMPT',"Given that chat context, elaborate on actionable steps.")
messages=[
  {"role":"user","content":first},
  {"role":"assistant","content":reply},
  {"role":"user","content":f"{follow} Chat context: {context}"}
]
print(json.dumps({
  "messages": messages,
  "max_tokens": 192,
  "temperature": 0.3
}), end="")
PY
)
          perform_request "Gemma chat (turn 2, follow-up)" POST "$GATEWAY_URL/api/gemma/chat" "$CHAT_S2" "${AUTH_OPTS[@]}"
          local follow_prompt
          follow_prompt="${ANALYZER_CHAT_CONTEXT_PROMPT} Chat context: ${ANALYZER_CHAT_CONTEXT}"
          log_conversation "user" "[analyzer stream] $follow_prompt"
          local CHAT_S2_REPLY
          CHAT_S2_REPLY=$(extract_response_text)
          if [[ -n "$CHAT_S2_REPLY" ]]; then
            log_conversation "assistant" "[analyzer stream] $CHAT_S2_REPLY"
          else
            log_failure "Follow-up chat lacked assistant reply"
          fi
        else
          log_failure "Streamed artifact reply missing; cannot perform follow-up chat"
        fi
      else
        log_failure "Could not locate streamed artifact for analysis_id $ANALYZER_STREAM_ID"
      fi
    fi
  fi
}

run_speakers() {
  if ! require_auth; then return; fi
  log_section "Speakers"
  perform_request "Speakers list" GET "$GATEWAY_URL/api/enroll/speakers" "" "${AUTH_OPTS[@]}"
  local base_name
  base_name=$(printf '%s' "$UNIQUE_TAG" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9-_')
  [[ -z "$base_name" ]] && base_name="speaker"
  local speaker_name="${base_name:0:48}-enroll"
  ensure_sample_wav 95
  local enrollment_wav="$SAMPLE_WAV_PATH"
  local form_opts=(-b "$COOKIE_JAR")
  if [[ -n "$CSRF_TOKEN" ]]; then
    form_opts+=(-H "X-CSRF-Token: $CSRF_TOKEN")
  fi
  local enroll_tmp
  enroll_tmp=$(mktemp)
  set +e
  local status
  status=$(curl -sS -o "$enroll_tmp" -w "%{http_code}" -F "speaker=$speaker_name" -F "audio=@$enrollment_wav;type=audio/wav" "${form_opts[@]}" "$GATEWAY_URL/api/enroll/upload")
  local curl_exit=$?
  set -e
  local body
  body=$(cat "$enroll_tmp")
  rm -f "$enroll_tmp"
  if [[ $curl_exit -ne 0 ]]; then
    echo "$body" >&2
    log_failure "Enroll speaker (curl exit $curl_exit)"
  elif [[ "$status" == 2* ]]; then
    log_success "Enroll speaker $speaker_name ($status)"
    LAST_SPEAKER_NAME="$speaker_name"
  else
    echo "$body" >&2
    log_failure "Enroll speaker (HTTP $status)"
  fi
  perform_request_optional "Speakers list (post-enroll)" GET "$GATEWAY_URL/api/enroll/speakers" "" "${AUTH_OPTS[@]}"
  if [[ -n "$LAST_SPEAKER_NAME" ]]; then
    if response_contains_keyword "$LAST_SPEAKER_NAME"; then
      log_success "Speaker $LAST_SPEAKER_NAME visible in list"
    else
      log_failure "Speaker $LAST_SPEAKER_NAME missing from list"
    fi
  fi
}

run_patterns() {
  if ! require_auth; then return; fi
  log_section "Patterns"
  perform_request_optional "Patterns (today)" GET "$GATEWAY_URL/api/analyze/patterns?time_period=today" "" "${AUTH_OPTS[@]}"
}

ensure_stack_running

for feature in "${FEATURES_ORDER[@]}"; do
  if feature_selected "$feature"; then
    case "$feature" in
      health) run_health ;;
      auth) run_auth ;;
      transcription) run_transcription ;;
      transcripts) run_transcripts ;;
      analysis) run_analysis ;;
      gemma) run_gemma ;;
      rag) run_rag ;;
      memories) run_memories ;;
      emotions) run_emotions ;;
      analyzer) run_analyzer ;;
      speakers) run_speakers ;;
      patterns) run_patterns ;;
    esac
  fi
done

if [[ -s "$CONVO_LOG" ]]; then
  echo -e "${BLUE}Conversation log:${NC} $CONVO_LOG"
fi

print_summary
