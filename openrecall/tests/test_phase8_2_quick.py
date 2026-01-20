"""Quick Phase 8.2 Integration Test - No User Input Required."""

import json
import urllib.request
import urllib.error
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from openrecall.server.config_runtime import runtime_settings


def test_api(description, method, endpoint, data=None):
    """Test a single API endpoint."""
    try:
        url = f"http://localhost:8083{endpoint}"
        
        if data:
            payload = json.dumps(data).encode()
            req = urllib.request.Request(
                url,
                data=payload,
                method=method,
                headers={"Content-Type": "application/json"}
            )
        else:
            req = urllib.request.Request(url, method=method)
        
        with urllib.request.urlopen(req, timeout=2) as response:
            result = json.loads(response.read().decode())
            print(f"✓ {description}")
            return True, result
    except Exception as e:
        print(f"✗ {description}: {e}")
        return False, None


print("\n" + "="*80)
print("PHASE 8.2 QUICK INTEGRATION TEST")
print("="*80 + "\n")

results = []

# Test 1: Get current config
print("TEST 1: Get current config")
success, data = test_api(
    "GET /api/config",
    "GET",
    "/api/config"
)
results.append(("Get config", success))
if success:
    print(f"  ai_processing_enabled: {data['ai_processing_enabled']}")
    print(f"  recording_enabled: {data['recording_enabled']}")
    print(f"  upload_enabled: {data['upload_enabled']}\n")

# Test 2: Disable AI processing
print("TEST 2: Disable AI processing")
success, data = test_api(
    "POST /api/config (ai_processing_enabled=False)",
    "POST",
    "/api/config",
    {"ai_processing_enabled": False}
)
results.append(("Disable AI", success))
if success:
    print(f"  Response: {data['config']['ai_processing_enabled']}\n")

# Test 3: Verify disabled in runtime settings
print("TEST 3: Verify disabled in runtime settings")
with runtime_settings._lock:
    is_disabled = not runtime_settings.ai_processing_enabled
print(f"✓ ai_processing_enabled is {'disabled' if is_disabled else 'enabled'}\n")
results.append(("Verify disabled", is_disabled))

# Test 4: Disable recording
print("TEST 4: Disable recording")
success, data = test_api(
    "POST /api/config (recording_enabled=False)",
    "POST",
    "/api/config",
    {"recording_enabled": False}
)
results.append(("Disable recording", success))
if success:
    print(f"  Response: {data['config']['recording_enabled']}\n")

# Test 5: Disable upload
print("TEST 5: Disable upload")
success, data = test_api(
    "POST /api/config (upload_enabled=False)",
    "POST",
    "/api/config",
    {"upload_enabled": False}
)
results.append(("Disable upload", success))
if success:
    print(f"  Response: {data['config']['upload_enabled']}\n")

# Test 6: Test heartbeat endpoint
print("TEST 6: Test heartbeat endpoint")
success, data = test_api(
    "POST /api/heartbeat",
    "POST",
    "/api/heartbeat"
)
results.append(("Heartbeat", success))
if success:
    print(f"  client_online: {data['client_online']}")
    print(f"  config values returned\n")

# Test 7: Re-enable all
print("TEST 7: Re-enable all settings")
success, data = test_api(
    "POST /api/config (all enabled)",
    "POST",
    "/api/config",
    {
        "ai_processing_enabled": True,
        "recording_enabled": True,
        "upload_enabled": True
    }
)
results.append(("Re-enable all", success))
if success:
    print(f"  All settings re-enabled\n")

# Test 8: Recorder Phase 8.2 features
print("TEST 8: Recorder Phase 8.2 features")
try:
    from openrecall.client.recorder import ScreenRecorder
    recorder = ScreenRecorder()
    
    has_recording = hasattr(recorder, 'recording_enabled')
    has_upload = hasattr(recorder, 'upload_enabled')
    has_heartbeat = hasattr(recorder, 'last_heartbeat_time')
    has_method = hasattr(recorder, '_send_heartbeat')
    
    all_present = has_recording and has_upload and has_heartbeat and has_method
    
    if all_present:
        print("✓ All Phase 8.2 recorder features present")
    else:
        print("✗ Missing some recorder features")
    
    results.append(("Recorder features", all_present))
except Exception as e:
    print(f"✗ Recorder test failed: {e}")
    results.append(("Recorder features", False))

print("\n" + "="*80)
print("SUMMARY")
print("="*80)

passed = sum(1 for _, success in results if success)
total = len(results)

for name, success in results:
    status = "✓" if success else "✗"
    print(f"{status} {name}")

print(f"\n{passed}/{total} tests passed")

if passed == total:
    print("\n🎉 All Phase 8.2 tests passed!")
    sys.exit(0)
else:
    print(f"\n⚠️  {total - passed} test(s) failed")
    sys.exit(1)
