import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import tempfile
import shutil
import os
from pathlib import Path
from uuid import uuid4

# Adjust path to allow imports
import sys
sys.path.insert(0, os.getcwd())

from openrecall.server.worker import ProcessingWorker
from openrecall.shared.models import RecallEntry
from openrecall.server.schema import SemanticSnapshot, Context, Content

# Mocks for classes that might require DB connection
class MockVectorStore:
    def add_snapshot(self, snapshot):
        pass

class MockFTSStore:
    def add_document(self, id, text, caption, keywords):
        pass

class TestPhase3Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp_dir)
        
    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_pipeline(self):
        # Setup mocks
        mock_ai = MagicMock()
        mock_ocr = MagicMock()
        mock_emb = MagicMock()
        
        mock_ocr.extract_text.return_value = "def hello(): print('world')"
        mock_ai.analyze_image.return_value = {"caption": "User coding", "scene": "coding", "action": "typing"}
        mock_emb.embed_text.return_value = np.zeros(1024, dtype=np.float32)
        
        mock_vs = MagicMock()
        mock_fts = MagicMock()
        
        # Patch everything
        with patch("openrecall.server.worker.VectorStore", return_value=mock_vs), \
             patch("openrecall.server.worker.FTSStore", return_value=mock_fts), \
             patch("openrecall.server.worker.KeywordExtractor") as MockKW, \
             patch("openrecall.server.worker.runtime_settings") as mock_runtime_settings, \
             patch("openrecall.server.worker.settings") as mock_settings, \
             patch("openrecall.server.database.mark_task_completed", return_value=True) as mark_completed, \
             patch("openrecall.server.database.mark_task_processing", return_value=True), \
             patch("openrecall.server.database.mark_task_cancelled_if_processing"):
            
            # Setup Keyword Extractor
            mock_kw = MockKW.return_value
            mock_kw.extract.return_value = ["def", "hello", "world"]
            
            # Setup Runtime Settings
            mock_runtime_settings.ai_processing_enabled = True
            mock_runtime_settings.ai_processing_version = 1
            mock_runtime_settings._lock = MagicMock()
            mock_runtime_settings._lock.__enter__ = MagicMock()
            mock_runtime_settings._lock.__exit__ = MagicMock()
            
            # Setup Config Settings
            mock_settings.screenshots_path = self.tmp_path
            mock_settings.embedding_dim = 1024
            mock_settings.debug = True
            
            # Initialize Worker
            worker = ProcessingWorker()
            
            # Create dummy task and image
            task = RecallEntry(
                id=1,
                timestamp=1700000000,
                app="VSCode",
                title="main.py - OpenRecall",
                status="PENDING"
            )
            image_path = self.tmp_path / "1700000000.png"
            image_path.write_bytes(b"fake_png_data")
            
            # Call _process_task
            conn = MagicMock()
            worker._process_task(
                conn,
                task,
                mock_ai,
                mock_ocr,
                mock_emb,
                mock_vs,
                mock_fts,
                ai_processing_version=1
            )
            
            # Verifications
            mock_ocr.extract_text.assert_called_once()
            mock_ai.analyze_image.assert_called_once()
            mock_emb.embed_text.assert_called_once()
            
            # Check VS Store
            mock_vs.add_snapshot.assert_called_once()
            snapshot = mock_vs.add_snapshot.call_args[0][0]
            self.assertIsInstance(snapshot, SemanticSnapshot)
            self.assertEqual(snapshot.content.scene_tag, "coding")
            self.assertEqual(snapshot.content.caption, "User coding")
            self.assertIn("hello", snapshot.content.ocr_text)
            
            # Check FTS Store
            mock_fts.add_document.assert_called_once()
            
            # Check Legacy DB
            mark_completed.assert_called_once()
            
            print("Phase 3 Pipeline Logic Verified Successfully!")

if __name__ == "__main__":
    unittest.main()
