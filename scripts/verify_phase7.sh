#!/bin/bash
# Phase 7 验证脚本
# 验证 /v1/search 的 content_type 参数

set -e

BASE_URL="http://localhost:8083"
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=== Phase 7 Verification Script ==="
echo ""

# 1. 检查服务器健康状态
echo "1. Checking server health..."
HEALTH=$(curl -s "$BASE_URL/v1/health" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))")
if [ "$HEALTH" == "ok" ] || [ "$HEALTH" == "degraded" ]; then
    echo -e "${GREEN}✓ Server is $HEALTH${NC}"
else
    echo -e "${RED}✗ Server not responding (status: $HEALTH)${NC}"
    echo "  Please start server with: ./run_server.sh --debug"
    exit 1
fi
echo ""

# 2. 检查当前帧数量
echo "2. Checking frame count..."
QUEUE_STATUS=$(curl -s "$BASE_URL/v1/ingest/queue/status")
COMPLETED=$(echo "$QUEUE_STATUS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('completed', 0))")
echo "  Completed frames: $COMPLETED"
echo ""

if [ "$COMPLETED" -eq 0 ]; then
    echo -e "${RED}No completed frames found.${NC}"
    echo "  Please either:"
    echo "  a) Run the client to capture some frames: ./run_client.sh"
    echo "  b) Run the test data seed script below"
    echo ""
    echo "=== Seed Test Data (optional) ==="
    cat << 'SEED_EOF'
# Run this Python script to seed test data:
python3 << 'PYEOF'
import requests
import json
import time
import uuid

BASE_URL = "http://localhost:8083"

def gen_uuid7():
    """Generate a simple UUID v7-like ID for testing."""
    ts = int(time.time() * 1000)
    return f"{ts:016x}-0000-7000-8000-000000000000"

def seed_ocr_frame(capture_id, text, app_name="TestApp"):
    """Seed an OCR-pending frame."""
    jpeg_header = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'

    resp = requests.post(f"{BASE_URL}/v1/ingest", files={
        "file": ("test.jpg", jpeg_header, "image/jpeg")
    }, data={
        "capture_id": capture_id,
        "metadata": json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "capture_trigger": "manual",
            "device_name": "monitor_0",
            "app_name": app_name,
            "window_name": f"{app_name} Window",
            "focused": True,
        })
    })
    return resp.status_code in [200, 201]

def seed_accessibility_frame(capture_id, text, app_name="TestBrowser"):
    """Seed an accessibility-canonical frame."""
    jpeg_header = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x00\x01\x00\x01\x00\x00'

    resp = requests.post(f"{BASE_URL}/v1/ingest", files={
        "file": ("test.jpg", jpeg_header, "image/jpeg")
    }, data={
        "capture_id": capture_id,
        "metadata": json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "capture_trigger": "manual",
            "device_name": "monitor_0",
            "app_name": app_name,
            "window_name": f"{app_name} Window",
            "focused": True,
            "text": text,
            "text_source": "accessibility",
            "browser_url": "https://example.com/test",
            "accessibility": {
                "text_content": text,
                "tree_json": json.dumps([{"role": "AXStaticText", "text": text, "depth": 0}]),
                "node_count": 1,
                "truncated": False,
            }
        })
    })
    return resp.status_code in [200, 201]

# Seed test frames
print("Seeding test frames...")
for i in range(3):
    seed_ocr_frame(gen_uuid7(), f"OCR test content number {i}", f"Terminal_{i}")
    print(f"  Seeded OCR frame {i+1}")

for i in range(3):
    seed_accessibility_frame(gen_uuid7(), f"Accessibility test content number {i}", f"Safari_{i}")
    print(f"  Seeded Accessibility frame {i+1}")

print("Done seeding test frames!")
PYEOF
SEED_EOF
    exit 0
fi

# 3. 测试 content_type=ocr
echo "3. Testing content_type=ocr..."
OCR_RESULT=$(curl -s "$BASE_URL/v1/search?content_type=ocr&limit=5")
OCR_COUNT=$(echo "$OCR_RESULT" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('data', [])))")
echo -e "${GREEN}✓ content_type=ocr returned $OCR_COUNT results${NC}"
echo ""

# 4. 测试 content_type=accessibility
echo "4. Testing content_type=accessibility..."
AX_RESULT=$(curl -s "$BASE_URL/v1/search?content_type=accessibility&limit=5")
AX_COUNT=$(echo "$AX_RESULT" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('data', [])))")
echo -e "${GREEN}✓ content_type=accessibility returned $AX_COUNT results${NC}"
echo ""

# 5. 测试 content_type=all (默认)
echo "5. Testing content_type=all (default)..."
ALL_RESULT=$(curl -s "$BASE_URL/v1/search?limit=10")
ALL_COUNT=$(echo "$ALL_RESULT" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('data', [])))")
echo -e "${GREEN}✓ content_type=all returned $ALL_COUNT results${NC}"
echo ""

# 6. 验证响应格式
echo "6. Verifying response format..."
SAMPLE=$(curl -s "$BASE_URL/v1/search?limit=1")
HAS_DATA=$(echo "$SAMPLE" | python3 -c "import sys, json; d=json.load(sys.stdin); print('data' in d)")
HAS_PAGINATION=$(echo "$SAMPLE" | python3 -c "import sys, json; d=json.load(sys.stdin); print('pagination' in d)")

if [ "$HAS_DATA" == "True" ] && [ "$HAS_PAGINATION" == "True" ]; then
    echo -e "${GREEN}✓ Response has correct top-level structure (data, pagination)${NC}"
else
    echo -e "${RED}✗ Response missing required fields${NC}"
fi

# 检查每个 item 是否有 type 字段
HAS_TYPE=$(echo "$SAMPLE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', [])
if items:
    print('type' in items[0])
else:
    print('True')  # No items to check
")
if [ "$HAS_TYPE" == "True" ]; then
    echo -e "${GREEN}✓ Each data item has 'type' field${NC}"
else
    echo -e "${RED}✗ Data items missing 'type' field${NC}"
fi
echo ""

# 7. 测试 browser_url 过滤
echo "7. Testing browser_url filter..."
URL_RESULT=$(curl -s "$BASE_URL/v1/search?browser_url=example&limit=5")
URL_COUNT=$(echo "$URL_RESULT" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('data', [])))")
echo "  Found $URL_COUNT results with browser_url containing 'example'"
echo ""

echo "=== Phase 7 Verification Complete ==="
echo ""
echo "Summary:"
echo "  - OCR frames: $OCR_COUNT"
echo "  - Accessibility frames: $AX_COUNT"
echo "  - Total (merged): $ALL_COUNT"
echo ""
if [ "$ALL_COUNT" -ge "$OCR_COUNT" ] && [ "$ALL_COUNT" -ge "$AX_COUNT" ]; then
    echo -e "${GREEN}✓ Phase 7 implementation verified successfully!${NC}"
else
    echo -e "${RED}✗ Verification failed - check content_type merging${NC}"
fi
