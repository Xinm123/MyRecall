import os
import shutil
import tempfile
import time
import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from flask import Flask

# Set env vars
os.environ["OPENRECALL_AI_PROVIDER"] = "local"
os.environ["OPENRECALL_OCR_PROVIDER"] = "local"
os.environ["OPENRECALL_EMBEDDING_PROVIDER"] = "local"
# Prevent real model loading
os.environ["OPENRECALL_EMBEDDING_MODEL"] = "dummy-model"

# We delay imports of openrecall.server.* to allow patching factory first
from openrecall.shared.config import settings
from openrecall.server.database import SQLStore, VectorStore

class TestPhase5E2E(unittest.TestCase):
    def setUp(self):
        # 1. Setup Temp Directory
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        
        # 2. Patch Settings
        self.original_base_path = settings.base_path
        settings.base_path = self.test_path
        settings.ensure_directories()
        
        # 3. Patch AI Factory globally BEFORE importing api/app
        self.factory_patcher = patch("openrecall.server.ai.factory.get_ai_provider")
        self.mock_get_ai = self.factory_patcher.start()
        
        # Mock the provider instance
        self.mock_ai_instance = MagicMock()
        self.mock_ai_instance.embed_text.return_value = np.zeros(1024, dtype=np.float32)
        self.mock_ai_instance.analyze_image.return_value = {"caption": "test", "scene": "test", "action": "test"}
        self.mock_ai_instance.extract_text.return_value = "test text"
        self.mock_get_ai.return_value = self.mock_ai_instance

        # Also patch get_embedding_provider and get_ocr_provider if they are separate
        self.embed_patcher = patch("openrecall.server.ai.factory.get_embedding_provider")
        self.mock_get_embed = self.embed_patcher.start()
        self.mock_get_embed.return_value = self.mock_ai_instance

        self.ocr_patcher = patch("openrecall.server.ai.factory.get_ocr_provider")
        self.mock_get_ocr = self.ocr_patcher.start()
        self.mock_get_ocr.return_value = self.mock_ai_instance

        # 4. Import Server Modules (Now that factory is patched)
        # We use local imports or importlib to ensure they pick up the patch if not already loaded
        import openrecall.server.api as api
        import openrecall.server.app as server_app
        self.api = api
        self.server_app = server_app

        # 5. Re-initialize Stores with new paths
        self.sql_store = SQLStore()
        self.api.sql_store = self.sql_store
        self.server_app.sql_store = self.sql_store
        
        # Re-init search engine (which uses factory, so it gets mock)
        # SearchEngine calls get_ai_provider("embedding") -> mock
        self.api.search_engine = self.api.SearchEngine()

        # 6. Setup Flask Test Client
        self.app = Flask(__name__)
        self.app.register_blueprint(self.api.api_bp)
        self.client = self.app.test_client()
        
        # 7. Create Dummy Image
        self.image_path = self.test_path / "test_image.png"
        from PIL import Image
        img = Image.new('RGB', (100, 100), color = 'blue')
        img.save(self.image_path)

    def tearDown(self):
        self.factory_patcher.stop()
        self.embed_patcher.stop()
        self.ocr_patcher.stop()
        shutil.rmtree(self.test_dir)
        settings.base_path = self.original_base_path

    def test_e2e_lifecycle(self):
        # --- Step 1: Ingestion (API) ---
        print("\n[Step 1] Ingesting screenshot...")
        timestamp = int(time.time())
        metadata = {
            "timestamp": timestamp,
            "app_name": "Safari",
            "window_title": "OpenRecall E2E Test"
        }
        
        import json
        with open(self.image_path, "rb") as img_file:
            response = self.client.post(
                "/api/upload",
                data={
                    "file": (img_file, "test.png"),
                    "metadata": json.dumps(metadata)
                },
                content_type="multipart/form-data"
            )
        
        self.assertEqual(response.status_code, 202)
        task_id = response.json["task_id"]
        print(f"Task ID: {task_id} accepted.")
        
        # Verify Pending State in DB
        pending_count = self.sql_store.get_pending_count()
        self.assertEqual(pending_count, 1)

        # --- Step 2: Processing (Worker) ---
        print("[Step 2] Processing task...")
        # Instantiate worker
        from openrecall.server.worker import ProcessingWorker
        worker = ProcessingWorker()
        
        # Connect to the temp DB
        import sqlite3
        conn = sqlite3.connect(str(settings.db_path))
        
        # Get the task
        task = self.sql_store.get_next_task(conn)
        self.assertIsNotNone(task)
        self.assertEqual(task.id, task_id)
        
        # Ensure image exists at expected path
        expected_img_path = settings.screenshots_path / f"{timestamp}.png"
        self.assertTrue(expected_img_path.exists())
        
        # Run _process_task
        vector_store = VectorStore()
        
        # _process_task calls get_ai_provider etc internally? 
        # No, it takes them as args.
        # But worker.run() calls them.
        # We are calling _process_task manually, so we pass our mocks.
        
        worker._process_task(
            conn,
            task,
            self.mock_ai_instance, # AI
            self.mock_ai_instance, # OCR
            self.mock_ai_instance, # Embed
            vector_store,
            self.sql_store,
            0 # version
        )
        
        conn.close()
        
        # --- Step 3: Verification ---
        print("[Step 3] Verifying data...")
        
        # 1. Check Status in SQLStore
        conn = sqlite3.connect(str(settings.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT status, text, description FROM entries WHERE id=?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertEqual(row[0], "COMPLETED")
        self.assertEqual(row[1], "test text") 
        self.assertEqual(row[2], "test") 
        
        # 2. Check FTS
        results = self.sql_store.search("test")
        self.assertTrue(len(results) > 0)
        
        # --- Step 4: Retrieval (Search Engine) ---
        print("[Step 4] Searching...")
        
        # Search for "Safari" (Metadata) or "test" (Content)
        results = self.api.search_engine.search("Safari")
        self.assertTrue(len(results) > 0)
        top_result = results[0]
        
        self.assertEqual(top_result.context.app_name, "Safari")
        self.assertEqual(top_result.content.caption, "test")
        
        print("✅ E2E Test Passed!")

if __name__ == "__main__":
    unittest.main()
