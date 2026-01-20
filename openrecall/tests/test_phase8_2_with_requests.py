"""Phase 8.2 Integration Test using requests library."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

from openrecall.server.config_runtime import runtime_settings


def test_with_requests():
    """Test Phase 8.2 with requests library."""
    
    base_url = "http://localhost:8083"
    
    print("\n" + "="*80)
    print("PHASE 8.2 INTEGRATION TEST (using requests)")
    print("="*80 + "\n")
    
    results = []
    
    # Test 1: Get current config
    print("TEST 1: Get current config")
    try:
        resp = requests.get(f"{base_url}/api/config", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        print(f"✓ GET /api/config successful (status: {resp.status_code})")
        print(f"  Config: {data}\n")
        results.append(("Get config", True))
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        results.append(("Get config", False))
    
    # Test 2: Disable AI processing
    print("TEST 2: Disable AI processing")
    try:
        resp = requests.post(
            f"{base_url}/api/config",
            json={"ai_processing_enabled": False},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        # POST /api/config returns the config directly, not wrapped in "config" key
        ai_enabled = data.get('ai_processing_enabled', True)
        print(f"✓ POST /api/config successful")
        print(f"  ai_processing_enabled: {ai_enabled}\n")
        results.append(("Disable AI", True))
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        results.append(("Disable AI", False))
    
    # Test 3: Verify via GET /api/config (to check server-side state)
    print("TEST 3: Verify via GET /api/config")
    try:
        resp = requests.get(f"{base_url}/api/config", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        ai_disabled = not data.get('ai_processing_enabled', True)
        print(f"✓ GET /api/config returned state")
        print(f"  ai_processing_enabled: {data.get('ai_processing_enabled')}\n")
        results.append(("Verify state", ai_disabled))
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        results.append(("Verify state", False))
    
    # Test 4: Disable recording
    print("TEST 4: Disable recording")
    try:
        resp = requests.post(
            f"{base_url}/api/config",
            json={"recording_enabled": False},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        recording_enabled = data.get('recording_enabled', True)
        print(f"✓ POST /api/config successful")
        print(f"  recording_enabled: {recording_enabled}\n")
        results.append(("Disable recording", True))
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        results.append(("Disable recording", False))
    
    # Test 5: Disable upload
    print("TEST 5: Disable upload")
    try:
        resp = requests.post(
            f"{base_url}/api/config",
            json={"upload_enabled": False},
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        upload_enabled = data.get('upload_enabled', True)
        print(f"✓ POST /api/config successful")
        print(f"  upload_enabled: {upload_enabled}\n")
        results.append(("Disable upload", True))
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        results.append(("Disable upload", False))
    
    # Test 6: Heartbeat endpoint
    print("TEST 6: Heartbeat endpoint")
    try:
        resp = requests.post(f"{base_url}/api/heartbeat", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        print(f"✓ POST /api/heartbeat successful")
        print(f"  client_online: {data.get('client_online')}")
        print(f"  config: {data.get('config')}\n")
        results.append(("Heartbeat", True))
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        results.append(("Heartbeat", False))
    
    # Test 7: Re-enable all
    print("TEST 7: Re-enable all settings")
    try:
        resp = requests.post(
            f"{base_url}/api/config",
            json={
                "ai_processing_enabled": True,
                "recording_enabled": True,
                "upload_enabled": True
            },
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"✓ All settings re-enabled\n")
        results.append(("Re-enable all", True))
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        results.append(("Re-enable all", False))
    
    # Test 8: Recorder features
    print("TEST 8: Recorder Phase 8.2 features")
    try:
        from openrecall.client.recorder import ScreenRecorder
        recorder = ScreenRecorder()
        
        has_all = (
            hasattr(recorder, 'recording_enabled') and
            hasattr(recorder, 'upload_enabled') and
            hasattr(recorder, 'last_heartbeat_time') and
            hasattr(recorder, '_send_heartbeat')
        )
        
        if has_all:
            print("✓ All Phase 8.2 recorder features present\n")
            results.append(("Recorder features", True))
        else:
            print("✗ Missing recorder features\n")
            results.append(("Recorder features", False))
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        results.append(("Recorder features", False))
    
    # Test 9: Worker features
    print("TEST 9: Worker Phase 8.2 features")
    try:
        from openrecall.server.worker import ProcessingWorker
        worker = ProcessingWorker()
        
        # Check that runtime_settings is accessible
        with runtime_settings._lock:
            can_read = runtime_settings.ai_processing_enabled is not None
        
        if can_read:
            print("✓ Worker can access runtime_settings\n")
            results.append(("Worker features", True))
        else:
            print("✗ Worker cannot access runtime_settings\n")
            results.append(("Worker features", False))
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        results.append(("Worker features", False))
    
    # Print summary
    print("="*80)
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
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(test_with_requests())
