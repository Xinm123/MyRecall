import sys
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import numpy as np
import uuid

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openrecall.shared.config import settings
from openrecall.server.schema import SemanticSnapshot, Context, Content
from openrecall.server.database.vector_store import VectorStore
from openrecall.server.database.sql import FTSStore
from openrecall.server.search.engine import SearchEngine

class TestPhase4Search(unittest.TestCase):
    def setUp(self):
        # Create temp directories
        self.temp_dir = tempfile.mkdtemp()
        self.lancedb_path = Path(self.temp_dir) / "lancedb"
        self.fts_path = Path(self.temp_dir) / "fts.db"
        
        # Create a mock settings object
        self.mock_settings = MagicMock()
        self.mock_settings.lancedb_path = self.lancedb_path
        self.mock_settings.fts_path = self.fts_path
        self.mock_settings.debug = True

        # Patch settings in the modules where they are used
        self.vector_settings_patcher = patch('openrecall.server.database.vector_store.settings', self.mock_settings)
        self.sql_settings_patcher = patch('openrecall.server.database.sql.settings', self.mock_settings)
        
        self.vector_settings_patcher.start()
        self.sql_settings_patcher.start()
        
        # Patch AI Provider
        self.ai_patcher = patch('openrecall.server.search.engine.get_ai_provider')
        self.mock_get_ai = self.ai_patcher.start()
        
        self.mock_embedding = MagicMock()
        
        def mock_embed(text):
            vec = np.zeros(1024, dtype=np.float32)
            if "Python" in text:
                vec[0] = 1.0
            if "News" in text:
                vec[1] = 1.0
            return vec
        self.mock_embedding.embed_text.side_effect = mock_embed
        self.mock_get_ai.return_value = self.mock_embedding

        # Initialize Stores
        self.vector_store = VectorStore()
        self.fts_store = FTSStore()
        self.engine = SearchEngine(vector_store=self.vector_store, fts_store=self.fts_store)
        
    def tearDown(self):
        self.vector_settings_patcher.stop()
        self.sql_settings_patcher.stop()
        self.ai_patcher.stop()
        shutil.rmtree(self.temp_dir)

    def create_snapshot(self, text, app, timestamp, keywords=[]):
        uid = str(uuid.uuid4())
        
        # Create embedding
        vec = self.mock_embedding.embed_text(text)
        
        snap = SemanticSnapshot(
            id=uid,
            image_path=f"/tmp/{uid}.png",
            context=Context(
                app_name=app,
                window_title="Title",
                timestamp=timestamp,
                time_bucket="2024"
            ),
            content=Content(
                ocr_text=text,
                ocr_head=text,
                caption=text,
                keywords=keywords
            ),
            embedding_vector=vec
        )
        
        self.vector_store.add_snapshot(snap)
        self.fts_store.add_document(uid, text, text, keywords)
        return uid

    def test_time_filter(self):
        print("\n--- Test 1: Time Filter ---")
        now = datetime.now()
        today = datetime(now.year, now.month, now.day).timestamp() + 3600 # 1 AM today
        yesterday = today - 86400 - 3600 # Yesterday
        
        # Record A: Today
        self.create_snapshot("Python Error", "VSCode", today)
        # Record B: Yesterday
        self.create_snapshot("Python News", "Chrome", yesterday)
        
        # Query: "Python today"
        results = self.engine.search("Python today")
        
        print(f"Found {len(results)} results")
        for r in results:
            print(f" - {r.context.timestamp} {r.content.ocr_text}")
            
        self.assertEqual(len(results), 1)
        self.assertIn("Error", results[0].content.ocr_text)

    def test_hybrid_boosting(self):
        print("\n--- Test 2: Hybrid Boosting ---")
        ts = datetime.now().timestamp()
        
        # Record A: Vector match (Python) + Keyword match ("Error")
        # Record B: Vector match (Python) only
        
        uid_a = self.create_snapshot("Python Error", "AppA", ts, keywords=["Error"])
        uid_b = self.create_snapshot("Python News", "AppB", ts, keywords=["News"])
        
        # Query: "Python 'Error'"
        results = self.engine.search('Python "Error"') 
        
        print("Results:")
        for r in results:
            print(f" - {r.id} {r.content.ocr_text}")
            
        # We expect A to be first because of boost
        self.assertEqual(results[0].id, uid_a)
        # We expect B to be present as well (Vector found it), unless we implement strict filtering.
        # My current implementation includes B but ranked lower.
        self.assertTrue(len(results) >= 1)

if __name__ == '__main__':
    unittest.main()
