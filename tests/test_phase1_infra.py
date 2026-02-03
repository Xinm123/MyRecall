import os
import shutil
import tempfile
import uuid
import time
from pathlib import Path
import random
import sys
import sqlite3

# Ensure we can import openrecall
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Set environment variable BEFORE importing settings to use a temp dir
TEMP_DIR = tempfile.mkdtemp()
os.environ["OPENRECALL_DATA_DIR"] = TEMP_DIR

print(f"Using temporary directory: {TEMP_DIR}")

try:
    # Now import the modules
    from openrecall.shared.config import settings
    
    # Force ensure directories again
    settings.ensure_directories()
    
    from openrecall.server.schema import SemanticSnapshot, Context, Content
    from openrecall.server.database.vector_store import VectorStore
    from openrecall.server.database.sql import FTSStore

    def test_infra():
        # Initialize Stores
        print("Initializing VectorStore and FTSStore...")
        # Initialize FTS first to check if LanceDB causes interference
        print("Initializing FTSStore...")
        fts_store = FTSStore()
        print("Initializing VectorStore...")
        vector_store = VectorStore()
        
        # Mock Data
        snapshot_id = str(uuid.uuid4()) # Use string for UUID
        vector = [random.random() for _ in range(1024)]
        
        snapshot = SemanticSnapshot(
            id=snapshot_id,
            image_path="/tmp/fake_image.png",
            context=Context(
                app_name="VSCode",
                window_title="test_phase1_infra.py - OpenRecall",
                timestamp=time.time(),
                time_bucket="2024-01-24-10"
            ),
            content=Content(
                ocr_text="def hello_world(): print('hi')",
                ocr_head="def hello_world(): print('hi')",
                caption="User is writing Python code",
                keywords=["python", "coding", "vscode"],
                scene_tag="coding",
                action_tag="debugging"
            ),
            embedding_vector=vector,
            embedding_model="qwen-text-v1",
            embedding_dim=1024
        )
        
        print(f"Created snapshot with ID: {snapshot_id}")
        
        # Insert
        print("Inserting into VectorStore...")
        vector_store.add_snapshot(snapshot)
        
        print("Inserting into FTSStore...")
        fts_store.add_document(
            snapshot.id,
            snapshot.content.ocr_text,
            snapshot.content.caption,
            snapshot.content.keywords
        )
        
        # Verify Vector Search
        print("Verifying Vector Search...")
        # Search with the same vector
        results = vector_store.search(vector, limit=1)
        if results and results[0].id == snapshot_id:
            print("✅ Vector Search: Success")
        else:
            print(f"❌ Vector Search: Failed. Results: {results}")

        # Verify Keyword Search
        print("Verifying Keyword Search...")
        # Search for "hello_world"
        fts_results = fts_store.search("hello_world", limit=1)
        if fts_results and fts_results[0] == str(snapshot_id):
            print("✅ Keyword Search (OCR): Success")
        else:
            print(f"❌ Keyword Search (OCR): Failed. Results: {fts_results}")

        # Search for "coding" (keyword/caption)
        fts_results_2 = fts_store.search("coding", limit=1)
        if fts_results_2 and fts_results_2[0] == str(snapshot_id):
            print("✅ Keyword Search (Keyword): Success")
        else:
            print(f"❌ Keyword Search (Keyword): Failed. Results: {fts_results_2}")

    if __name__ == "__main__":
        test_infra()

except ImportError as e:
    print(f"❌ Import Failed: {e}")
    print("Please ensure lancedb and pydantic are installed.")
    sys.exit(1)
except Exception as e:
    print(f"❌ Setup Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    # Cleanup
    if os.path.exists(TEMP_DIR):
        print("Cleaning up...")
        shutil.rmtree(TEMP_DIR)
        print("Done.")
