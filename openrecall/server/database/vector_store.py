import logging
from pathlib import Path
from typing import List, Optional, Protocol, Tuple, cast

import lancedb
from openrecall.shared.config import settings
from openrecall.server.schema import SemanticSnapshot

logger = logging.getLogger(__name__)


class VectorQuery(Protocol):
    def metric(self, name: str) -> "VectorQuery": ...

    def where(self, where: str, prefilter: bool = True) -> "VectorQuery": ...

    def limit(self, limit: int) -> "VectorQuery": ...

    def to_list(self) -> list[dict[str, object]]: ...

    def to_pydantic(self, model: type[SemanticSnapshot]) -> list[SemanticSnapshot]: ...


class VectorStore:
    def __init__(self, device_id: str = "legacy"):
        self.device_id = device_id
        self.db_path = self._resolve_db_path(device_id)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.table_name = "semantic_snapshots"
        self.db = lancedb.connect(self.db_path)
        self._init_table()

    def _resolve_db_path(self, device_id: str) -> Path:
        if device_id in {"legacy", settings.legacy_device_id}:
            return settings.lancedb_path
        return settings.lancedb_path / device_id

    def _init_table(self):
        """Initialize the table with Pydantic schema if it doesn't exist."""
        # Check if table exists
        existing_tables_raw = list(self.db.list_tables())
        table_names = {
            table[0] if isinstance(table, (list, tuple)) else str(table)
            for table in existing_tables_raw
        }

        if self.table_name not in table_names:
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
                logger.warning(
                    f"Schema mismatch/error detected for table '{self.table_name}': {e}"
                )
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
        query = cast(VectorQuery, cast(object, table.search(query_vec)))
        try:
            query = query.metric("cosine")
            metric_used = "cosine"
        except AttributeError:
            metric_used = "default"
        except Exception:
            metric_used = "default"

        where_fn = getattr(query, "where", None)
        if where and callable(where_fn):
            query = cast(VectorQuery, where_fn(where, prefilter=True))

        limit_fn = getattr(query, "limit", None)
        if not callable(limit_fn):
            return []

        query = cast(VectorQuery, limit_fn(limit))
        results = query.to_list()

        # Parse results and extract distance
        parsed_results = []
        for r in results:
            distance_value = r.get("_distance", 0.0)
            distance: float
            if isinstance(distance_value, (int, float)):
                distance = float(distance_value)
            else:
                distance = 0.0
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
        query = cast(VectorQuery, cast(object, table.search()))
        return (
            query.where(f"id IN ({ids_str})")
            .limit(len(ids))
            .to_pydantic(SemanticSnapshot)
        )
