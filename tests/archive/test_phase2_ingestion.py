import io
import json
import unittest
import shutil
import sqlite3
from pathlib import Path
from PIL import Image

from openrecall.server.app import app
from openrecall.shared.config import settings

class TestPhase2Ingestion(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.test_timestamp = 1234567890
        self.test_file = settings.screenshots_path / f"{self.test_timestamp}.png"
        
        # Ensure screenshot dir exists
        settings.screenshots_path.mkdir(parents=True, exist_ok=True)
        
        # Clean up before test
        if self.test_file.exists():
            self.test_file.unlink()
            
        # Clean up DB entry
        with sqlite3.connect(str(settings.db_path)) as conn:
            conn.execute("DELETE FROM entries WHERE timestamp = ?", (self.test_timestamp,))
            conn.commit()

    def tearDown(self):
        # Clean up file
        if self.test_file.exists():
            self.test_file.unlink()
            
        # Clean up DB entry
        with sqlite3.connect(str(settings.db_path)) as conn:
            conn.execute("DELETE FROM entries WHERE timestamp = ?", (self.test_timestamp,))
            conn.commit()

    def test_upload_multipart(self):
        # 1. Create dummy image
        img = Image.new('RGB', (100, 100), color = 'red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        # 2. Prepare metadata
        metadata = {
            "timestamp": self.test_timestamp,
            "app_name": "TestApp",
            "window_title": "TestWindow"
        }
        
        # 3. Send POST request
        response = self.client.post(
            '/api/upload',
            data={
                'file': (img_byte_arr, 'test.png'),
                'metadata': json.dumps(metadata)
            },
            content_type='multipart/form-data'
        )
        
        # 4. Assertions
        self.assertEqual(response.status_code, 202)
        
        # Verify file created
        self.assertTrue(self.test_file.exists(), "Screenshot file was not created")
        self.assertGreater(self.test_file.stat().st_size, 0, "Screenshot file is empty")
        
        # Verify DB entry
        with sqlite3.connect(str(settings.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, app, title FROM entries WHERE timestamp = ?", (self.test_timestamp,))
            row = cursor.fetchone()
            self.assertIsNotNone(row, "DB entry not found")
            self.assertEqual(row[0], "PENDING")
            self.assertEqual(row[1], "TestApp")
            self.assertEqual(row[2], "TestWindow")
            
if __name__ == '__main__':
    unittest.main()
