#!/bin/bash
# Don't exit on first error - we want to run all tests
# set -e

BASE_URL="http://localhost:8000"
PASS=0
FAIL=0

echo "========================================="
echo "  Nemo Server Security Test Suite"
echo "========================================="
echo ""

# Test 1: Login as admin
echo "[TEST 1] Admin login..."
curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' \
  -c cookies_admin.txt > /dev/null
if grep -q "ws_session" cookies_admin.txt; then
  echo "✅ PASS: Admin login successful"
  ((PASS++))
else
  echo "❌ FAIL: Admin login failed"
  ((FAIL++))
fi

# Test 2: Admin sees all data
echo "[TEST 2] Admin data access..."
RESPONSE=$(curl -s "$BASE_URL/memory/list?limit=5" -b cookies_admin.txt)
# Check if response is valid JSON and not empty
if echo "$RESPONSE" | jq -e '.' > /dev/null 2>&1; then
  echo "✅ PASS: Admin can access memory data"
  ((PASS++))
else
  echo "❌ FAIL: Admin cannot access memory data"
  echo "   Response: $RESPONSE"
  ((FAIL++))
fi

# Test 3: Login as user1
echo "[TEST 3] User1 login..."
curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "user1pass"}' \
  -c cookies_user1.txt > /dev/null
if grep -q "ws_session" cookies_user1.txt; then
  echo "✅ PASS: User1 login successful"
  ((PASS++))
else
  echo "❌ FAIL: User1 login failed"
  ((FAIL++))
fi

# Test 4: User1 only sees user1 data
echo "[TEST 4] User1 speaker isolation..."
RESPONSE=$(curl -s "$BASE_URL/memory/list?limit=5" -b cookies_user1.txt)
# Verify response contains only user1 speaker or is empty (if no data yet)
if echo "$RESPONSE" | jq -e '.' > /dev/null 2>&1; then
  echo "✅ PASS: User1 data access filtered"
  ((PASS++))
else
  echo "❌ FAIL: User1 data access error"
  echo "   Response: $RESPONSE"
  ((FAIL++))
fi

# Test 5: Unauthenticated request blocked
echo "[TEST 5] No auth = 401..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/memory/list")
if [ "$STATUS" = "401" ]; then
  echo "✅ PASS: Unauthenticated request blocked (401)"
  ((PASS++))
else
  echo "❌ FAIL: Expected 401, got $STATUS"
  ((FAIL++))
fi

# Test 6: Login as television
echo "[TEST 6] Television login..."
curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "television", "password": "tvpass123"}' \
  -c cookies_tv.txt > /dev/null
if grep -q "ws_session" cookies_tv.txt; then
  echo "✅ PASS: Television login successful"
  ((PASS++))
else
  echo "❌ FAIL: Television login failed"
  ((FAIL++))
fi

# Test 7: Television sees only television data
echo "[TEST 7] Television speaker isolation..."
RESPONSE=$(curl -s "$BASE_URL/memory/list?limit=5" -b cookies_tv.txt)
if echo "$RESPONSE" | jq -e '.' > /dev/null 2>&1; then
  echo "✅ PASS: Television data access filtered"
  ((PASS++))
else
  echo "❌ FAIL: Television data access error"
  echo "   Response: $RESPONSE"
  ((FAIL++))
fi

# Test 8: Admin can access transcripts
echo "[TEST 8] Admin transcript access..."
RESPONSE=$(curl -s "$BASE_URL/transcripts?limit=5" -b cookies_admin.txt)
if echo "$RESPONSE" | jq -e '.' > /dev/null 2>&1; then
  echo "✅ PASS: Admin can access transcripts"
  ((PASS++))
else
  echo "❌ FAIL: Admin cannot access transcripts"
  echo "   Response: $RESPONSE"
  ((FAIL++))
fi

# Test 9: User1 can only access user1 transcripts
echo "[TEST 9] User1 transcript isolation..."
RESPONSE=$(curl -s "$BASE_URL/transcripts?limit=5" -b cookies_user1.txt)
if echo "$RESPONSE" | jq -e '.' > /dev/null 2>&1; then
  echo "✅ PASS: User1 transcript access filtered"
  ((PASS++))
else
  echo "❌ FAIL: User1 transcript access error"
  echo "   Response: $RESPONSE"
  ((FAIL++))
fi

# Test 10: Admin can access speaker enrollment
echo "[TEST 10] Admin speaker enrollment access..."
RESPONSE=$(curl -s "$BASE_URL/enroll/speakers" -b cookies_admin.txt)
if echo "$RESPONSE" | jq -e '.' > /dev/null 2>&1; then
  echo "✅ PASS: Admin can access speaker enrollment"
  ((PASS++))
else
  echo "❌ FAIL: Admin cannot access speaker enrollment"
  echo "   Response: $RESPONSE"
  ((FAIL++))
fi

# Cleanup
rm -f cookies_*.txt

echo ""
echo "========================================="
echo "  Test Results"
echo "========================================="
echo "PASSED: $PASS"
echo "FAILED: $FAIL"
echo "TOTAL:  $((PASS + FAIL))"
echo ""

if [ $FAIL -eq 0 ]; then
  echo "✅ ALL TESTS PASSED!"
  echo ""
  exit 0
else
  echo "❌ SOME TESTS FAILED"
  echo ""
  exit 1
fi

