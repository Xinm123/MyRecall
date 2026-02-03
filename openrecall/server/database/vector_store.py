import logging
from typing import List, Tuple, Optional

import lancedb
from openrecall.shared.config import settings
from openrecall.server.schema import SemanticSnapshot

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self):
        self.db_path = settings.lancedb_path
        self.table_name = "semantic_snapshots"
        self.db = lancedb.connect(self.db_path)
        self._init_table()

    def _init_table(self):
        """Initialize the table with Pydantic schema if it doesn't exist."""
        # Check if table exists
        existing_tables = self.db.list_tables()
        
        if self.table_name not in existing_tables:
            logger.info(f"Creating LanceDB table '{self.table_name}'")
            try:
                self.db.create_table(self.table_name, schema=SemanticSnapshot)
            except ValueError as e:
                if "already exists" in str(e):
                    # Race condition or it appeared between list_tables and create_table
                    pass
                else:
                    raise
        else:
            # Table exists, check schema compatibility implicitly by trying to open
            try:
                # Attempt to open and validate schema compatibility (LanceDB might raise error if schema drifted too much)
                # Note: LanceDB's behavior on schema evolution is tricky. 
                # If we changed the Pydantic model (added 'score'), we might need to migrate.
                # Since 'score' is excluded, the stored schema should be same.
                # But if we previously created it with a different schema...
                # Let's just open it. If it fails later, we handle it.
                self.db.open_table(self.table_name)
            except Exception as e:
                logger.warning(f"Schema mismatch/error detected for table '{self.table_name}': {e}")
                logger.warning("Dropping and recreating table to apply new schema...")
                self.db.drop_table(self.table_name)
                self.db.create_table(self.table_name, schema=SemanticSnapshot)

    def add_snapshot(self, snapshot: SemanticSnapshot):
        """Add a single snapshot to the vector store."""
        table = self.db.open_table(self.table_name)
        table.add([snapshot])

    def search(
        self, query_vec: List[float], limit: int = 10, where: Optional[str] = None
    ) -> List[Tuple[SemanticSnapshot, float, float, str]]:
        """Search for similar snapshots using a query vector.
        
        Returns:
            List of (snapshot, score) tuples. Score is 1 - distance.
        """
        table = self.db.open_table(self.table_name)

        metric_used = "default"
        query = table.search(query_vec)
        metric_fn = getattr(query, "metric", None)
        if callable(metric_fn):
            try:
                query = metric_fn("cosine")
                metric_used = "cosine"
            except Exception:
                metric_used = "default"
        
        if where:
            query = query.where(where, prefilter=True)
            
        results = query.limit(limit).to_list()
        
        # Parse results and extract distance
        parsed_results = []
        for r in results:
            distance = r.get('_distance', 0.0)
            snapshot = SemanticSnapshot.model_validate(r)
            score = 1.0 - distance
            parsed_results.append((snapshot, score, float(distance), metric_used))
            
        return parsed_results

    def get_snapshots(self, ids: List[str]) -> List[SemanticSnapshot]:
        """Retrieve snapshots by IDs."""
        if not ids:
            return []
        table = self.db.open_table(self.table_name)
        ids_str = ", ".join([f"'{id}'" for id in ids])
        return table.search().where(f"id IN ({ids_str})").limit(len(ids)).to_pydantic(SemanticSnapshot)
