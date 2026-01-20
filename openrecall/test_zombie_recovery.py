#!/usr/bin/env python3
"""Test script for zombie recovery - creates a stuck task and verifies recovery."""

import sqlite3
import time
import requests
from pathlib import Path
from PIL import Image
import io

# Configuration
DB_PATH = Path.home() / ".myrecall_data" / "recall.db"
API_URL = "http://localhost:8083/api/upload"
SCREENSHOT_DIR = Path.home() / ".myrecall_data" / "screenshots"

def create_test_screenshot():
    """Create a simple test screenshot."""
    # Create a simple test image
    img = Image.new('RGB', (800, 600), color='white')
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    return img_buffer.getvalue()

def upload_screenshot():
    """Upload a test screenshot to create a PENDING entry."""
    print("📤 Uploading test screenshot...")
    
    files = {
        'screenshot': ('test.png', create_test_screenshot(), 'image/png')
    }
    
    data = {
        'app': 'TestApp',
        'title': 'Zombie Recovery Test'
    }
    
    response = requests.post(API_URL, files=files, data=data)
    print(f"   Response: {response.status_code} - {response.json()}")
    return response.status_code == 202

def create_zombie_task():
    """Manually set an entry to PROCESSING status to simulate a crash."""
    print("\n🧟 Creating zombie task (simulating crash)...")
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Find a PENDING or COMPLETED entry
    cursor.execute("SELECT id, timestamp, status FROM entries LIMIT 1")
    row = cursor.fetchone()
    
    if not row:
        print("   ❌ No entries found in database!")
        conn.close()
        return None
    
    entry_id = row[0]
    old_status = row[2]
    
    # Set it to PROCESSING (stuck state)
    cursor.execute("UPDATE entries SET status='PROCESSING' WHERE id=?", (entry_id,))
    conn.commit()
    
    print(f"   ✅ Set entry #{entry_id} to PROCESSING (was: {old_status})")
    
    # Verify
    cursor.execute("SELECT status FROM entries WHERE id=?", (entry_id,))
    new_status = cursor.fetchone()[0]
    print(f"   📊 Current status: {new_status}")
    
    conn.close()
    return entry_id

def check_recovery(zombie_id):
    """Check if the zombie task was recovered after server restart."""
    print("\n🔍 Checking recovery status...")
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    cursor.execute("SELECT status FROM entries WHERE id=?", (zombie_id,))
    row = cursor.fetchone()
    
    if row:
        status = row[0]
        print(f"   Entry #{zombie_id} status: {status}")
        
        if status == "PENDING":
            print("   ✅ SUCCESS! Zombie was recovered to PENDING")
            return True
        elif status == "PROCESSING":
            print("   ⚠️ Still PROCESSING - recovery may not have run")
            return False
        elif status == "COMPLETED":
            print("   ✅ SUCCESS! Worker processed the recovered zombie")
            return True
        else:
            print(f"   ❓ Unexpected status: {status}")
            return False
    else:
        print(f"   ❌ Entry #{zombie_id} not found!")
        return False
    
    conn.close()

def main():
    """Run the zombie recovery test."""
    print("=" * 60)
    print("🧪 ZOMBIE RECOVERY TEST")
    print("=" * 60)
    
    # Step 1: Ensure server is running and upload a screenshot
    try:
        response = requests.get("http://localhost:8083/api/health", timeout=2)
        if response.status_code != 200:
            print("❌ Server is not responding correctly!")
            return
        print("✅ Server is running\n")
    except requests.exceptions.RequestException:
        print("❌ Server is not running! Start it first with:")
        print("   conda run -n MyRecall python -m openrecall.server")
        return
    
    # Upload a test screenshot if needed
    if upload_screenshot():
        print("   ✅ Screenshot uploaded successfully")
        time.sleep(1)  # Wait for database write
    else:
        print("   ⚠️ Upload failed, but continuing...")
    
    # Step 2: Create zombie task
    zombie_id = create_zombie_task()
    if zombie_id is None:
        return
    
    # Step 3: Instruct user to restart server
    print("\n" + "=" * 60)
    print("📋 NEXT STEPS:")
    print("=" * 60)
    print("1. Stop the server (Ctrl+C or: pkill -f 'python -m openrecall.server')")
    print("2. Start it again: conda run -n MyRecall python -m openrecall.server")
    print("3. Look for this message in the logs:")
    print("   ⚠️ Recovered 1 stuck tasks (Zombies) from previous session.")
    print("4. Run this script again to verify recovery:")
    print(f"   python {__file__} --check {zombie_id}")
    print("=" * 60)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        zombie_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
        if zombie_id:
            check_recovery(zombie_id)
        else:
            print("Usage: python test_zombie_recovery.py --check <entry_id>")
    else:
        main()
