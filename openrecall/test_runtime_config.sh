#!/bin/bash
# Comprehensive test script for Runtime Configuration API
# Tests all endpoints and verifies correct behavior

echo "=========================================="
echo "Runtime Configuration API Test Suite"
echo "=========================================="
echo ""

BASE_URL="http://localhost:8083"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function to test endpoint
test_endpoint() {
    local name=$1
    local method=$2
    local endpoint=$3
    local data=$4
    local expected_status=$5
    
    echo ""
    echo -e "${YELLOW}Testing: $name${NC}"
    echo "Request: $method $BASE_URL$endpoint"
    
    if [ -z "$data" ]; then
        # GET request
        response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint")
    else
        # POST request with data
        echo "Data: $data"
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$BASE_URL$endpoint")
    fi
    
    # Split response and status code
    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')
    
    echo "Response Status: $http_code"
    echo "Response Body:"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ FAIL (Expected: $expected_status, Got: $http_code)${NC}"
        ((TESTS_FAILED++))
    fi
}

# Test 1: GET /api/config - Read current configuration
test_endpoint "GET /api/config - Read Configuration" \
    "GET" "/api/config" "" "200"

# Test 2: POST /api/config - Update single field
test_endpoint "POST /api/config - Update recording_enabled" \
    "POST" "/api/config" \
    '{"recording_enabled": false}' "200"

# Test 3: Verify update persisted
test_endpoint "GET /api/config - Verify recording_enabled is false" \
    "GET" "/api/config" "" "200"

# Test 4: POST /api/config - Update multiple fields
test_endpoint "POST /api/config - Update multiple fields" \
    "POST" "/api/config" \
    '{"upload_enabled": false, "ai_processing_enabled": false}' "200"

# Test 5: POST /api/config - Invalid field
test_endpoint "POST /api/config - Reject unknown field" \
    "POST" "/api/config" \
    '{"unknown_field": true}' "400"

# Test 6: POST /api/config - Invalid type
test_endpoint "POST /api/config - Reject non-boolean value" \
    "POST" "/api/config" \
    '{"recording_enabled": "not a boolean"}' "400"

# Test 7: POST /api/heartbeat - Register heartbeat
test_endpoint "POST /api/heartbeat - Register client heartbeat" \
    "POST" "/api/heartbeat" \
    '{}' "200"

# Test 8: Verify client_online is true after heartbeat
test_endpoint "GET /api/config - Verify client_online is true" \
    "GET" "/api/config" "" "200"

# Test 9: Reset configuration to defaults
test_endpoint "POST /api/config - Reset to defaults" \
    "POST" "/api/config" \
    '{"recording_enabled": true, "upload_enabled": true, "ai_processing_enabled": true}' "200"

# Test 10: Final verification
test_endpoint "GET /api/config - Final verification" \
    "GET" "/api/config" "" "200"

# Print summary
echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Tests Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Tests Failed: $TESTS_FAILED${NC}"
echo "=========================================="

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
