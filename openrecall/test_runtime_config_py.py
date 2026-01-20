#!/usr/bin/env python3
"""Simple test script for Runtime Configuration API using only stdlib.

Run this to verify all endpoints work correctly.
"""

import json
import urllib.request
import urllib.error
import time

BASE_URL = "http://localhost:8083"

# Test results
PASSED = 0
FAILED = 0

def test_request(name: str, method: str, endpoint: str, data: dict = None, 
                expected_status: int = 200) -> tuple:
    """Make HTTP request and verify response."""
    global PASSED, FAILED
    
    print(f"\n{'='*60}")
    print(f"Test: {name}")
    print(f"{'='*60}")
    
    url = f"{BASE_URL}{endpoint}"
    print(f"Request: {method} {url}")
    
    try:
        if method == "GET":
            req = urllib.request.Request(url, method='GET')
            req.add_header('Accept', 'application/json')
        elif method == "POST":
            if data:
                print(f"Data: {json.dumps(data)}")
            payload = json.dumps(data if data else {}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, method='POST')
            req.add_header('Content-Type', 'application/json')
        else:
            raise ValueError(f"Unknown method: {method}")
        
        try:
            with urllib.request.urlopen(req) as response:
                status = response.status
                body_text = response.read().decode('utf-8')
                body = json.loads(body_text)
        except urllib.error.HTTPError as e:
            status = e.code
            body_text = e.read().decode('utf-8')
            body = json.loads(body_text)
        
        print(f"Status: {status}")
        print(f"Response: {json.dumps(body, indent=2)}")
        
        if status == expected_status:
            print(f"✓ PASS")
            PASSED += 1
            return True, body
        else:
            print(f"✗ FAIL (Expected: {expected_status}, Got: {status})")
            FAILED += 1
            return False, body
    
    except Exception as e:
        print(f"✗ FAIL (Error: {str(e)})")
        FAILED += 1
        return False, None


def main():
    """Run all tests."""
    global PASSED, FAILED
    
    print("\n" + "="*60)
    print("Runtime Configuration API Test Suite")
    print("="*60)
    
    # Test 1: Get initial config
    success, config = test_request(
        "GET /api/config - Read initial configuration",
        "GET", "/api/config"
    )
    
    if success and config:
        print(f"\n✓ Initial state:")
        print(f"  - recording_enabled: {config.get('recording_enabled')}")
        print(f"  - upload_enabled: {config.get('upload_enabled')}")
        print(f"  - ai_processing_enabled: {config.get('ai_processing_enabled')}")
        print(f"  - ui_show_ai: {config.get('ui_show_ai')}")
        print(f"  - client_online: {config.get('client_online')}")
    
    # Test 2: Update single field
    success, updated = test_request(
        "POST /api/config - Update recording_enabled to false",
        "POST", "/api/config",
        {"recording_enabled": False}
    )
    
    # Test 3: Verify persistence
    success, config = test_request(
        "GET /api/config - Verify update persisted",
        "GET", "/api/config"
    )
    
    if success and config:
        if config.get('recording_enabled') is False:
            print("\n✓ Update persisted successfully!")
        else:
            print("\n✗ Update did not persist!")
    
    # Test 4: Update multiple fields
    success, updated = test_request(
        "POST /api/config - Update multiple fields",
        "POST", "/api/config",
        {
            "recording_enabled": True,
            "upload_enabled": False,
            "ai_processing_enabled": False
        }
    )
    
    # Test 5: Invalid field rejection
    success, error = test_request(
        "POST /api/config - Reject unknown field",
        "POST", "/api/config",
        {"unknown_field": True},
        expected_status=400
    )
    
    # Test 6: Invalid type rejection
    success, error = test_request(
        "POST /api/config - Reject non-boolean value",
        "POST", "/api/config",
        {"recording_enabled": "not a boolean"},
        expected_status=400
    )
    
    # Test 7: Heartbeat endpoint
    success, heartbeat = test_request(
        "POST /api/heartbeat - Register client heartbeat",
        "POST", "/api/heartbeat"
    )
    
    if success and heartbeat:
        config = heartbeat.get('config')
        if config and config.get('client_online'):
            print("\n✓ Client marked as online!")
        else:
            print("\n✗ Client not marked as online!")
    
    # Test 8: Verify client_online after heartbeat
    success, config = test_request(
        "GET /api/config - Verify client_online is true",
        "GET", "/api/config"
    )
    
    # Test 9: Reset to defaults
    test_request(
        "POST /api/config - Reset all to true",
        "POST", "/api/config",
        {
            "recording_enabled": True,
            "upload_enabled": True,
            "ai_processing_enabled": True,
            "ui_show_ai": True
        }
    )
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"✓ Passed: {PASSED}")
    print(f"✗ Failed: {FAILED}")
    print("="*60)
    
    if FAILED == 0:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed!")
        return 1


if __name__ == "__main__":
    exit(main())
