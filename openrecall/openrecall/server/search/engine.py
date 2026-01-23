import logging
from typing import List, Dict, Optional

import time
from datetime import datetime, timezone

from openrecall.server.database.vector_store import VectorStore
from openrecall.server.database.sql import FTSStore
from openrecall.server.utils.query_parser import QueryParser
from openrecall.server.schema import SemanticSnapshot
from openrecall.server.ai.factory import get_ai_provider

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

class SearchEngine:
    def __init__(self, vector_store: Optional[VectorStore] = None, fts_store: Optional[FTSStore] = None):
        self.vector_store = vector_store or VectorStore()
        self.fts_store = fts_store or FTSStore()
        self.query_parser = QueryParser()
        self.embedding_provider = get_ai_provider("embedding")

    def search(self, user_query: str, limit: int = 50) -> List[SemanticSnapshot]:
        sorted_results = self._search_impl(user_query=user_query, limit=limit)
        return [self._attach_score(item['snapshot'], item['score']) for item in sorted_results[:limit]]

    def search_debug(self, user_query: str, limit: int = 50) -> List[dict]:
        sorted_results = self._search_impl(user_query=user_query, limit=limit)
        out: List[dict] = []
        for idx, item in enumerate(sorted_results[:limit]):
            snap = item["snapshot"]
            dbg = item["debug"]
            ts = snap.context.timestamp
            out.append(
                {
                    "id": snap.id,
                    "timestamp": ts,
                    "app": snap.context.app_name,
                    "title": snap.context.window_title,
                    "description": snap.content.caption,
                    "filename": f"{int(ts)}.png",
                    "final_rank": idx + 1,
                    "final_score": float(item["score"]),
                    "vector_rank": dbg.get("vector_rank"),
                    "vector_score": float(dbg.get("vector_score") or 0.0),
                    "vector_distance": dbg.get("vector_distance"),
                    "vector_metric": dbg.get("vector_metric"),
                    "fts_rank": dbg.get("fts_rank"),
                    "fts_bm25": dbg.get("fts_bm25"),
                    "fts_boost": float(dbg.get("fts_boost") or 0.0),
                }
            )
        return out

    def _search_impl(self, user_query: str, limit: int = 50) -> List[dict]:
        t0 = time.perf_counter()
        parsed = self.query_parser.parse(user_query)
        logger.info(
            f"Searching for: '{parsed.text}' (Time: {parsed.start_time}-{parsed.end_time}, Keywords: {parsed.mandatory_keywords})"
        )

        results_map: Dict[str, dict] = {}
        where_clause_used: Optional[str] = None
        vector_candidates = 0
        vector_where_unfiltered_candidates = 0
        vector_where_pass = 0
        vector_where_filtered_out = 0
        fts_candidates = 0
        fetched_from_fts_only = 0
        filtered_from_fts_only = 0
        embedding_ms = 0.0
        vector_ms = 0.0
        vector_unfiltered_ms = 0.0
        fts_ms = 0.0
        fts_only_added_ids: List[str] = []
        fts_only_filtered_ids: List[str] = []
        fts_missing_ids: List[str] = []
        fts_boost_events: List[tuple] = []

        if settings.debug:
            start_iso = (
                datetime.fromtimestamp(parsed.start_time, tz=timezone.utc).isoformat()
                if parsed.start_time
                else None
            )
            end_iso = (
                datetime.fromtimestamp(parsed.end_time, tz=timezone.utc).isoformat()
                if parsed.end_time
                else None
            )
            provider_name = type(self.embedding_provider).__name__
            logger.debug(
                f"🔎 Search Debug Input | q='{user_query}' | parsed.text='{parsed.text}' | "
                f"mandatory_keywords={parsed.mandatory_keywords} | time_utc={start_iso}..{end_iso} | "
                f"limit={limit} | embedding_provider={provider_name}"
            )

        if parsed.text:
            where_clause = None
            try:
                t_embed0 = time.perf_counter()
                query_vec = self.embedding_provider.embed_text(parsed.text)
                if hasattr(query_vec, 'tolist'):
                    query_vec = query_vec.tolist()
                embedding_ms = (time.perf_counter() - t_embed0) * 1000.0

                conditions = []
                if parsed.start_time:
                    conditions.append(f"context.timestamp >= {parsed.start_time}")
                if parsed.end_time:
                    conditions.append(f"context.timestamp <= {parsed.end_time}")
                
                if conditions:
                    where_clause = " AND ".join(conditions)
                where_clause_used = where_clause

                t_vec0 = time.perf_counter()
                vector_results = self.vector_store.search(query_vec, limit=limit * 2, where=where_clause)
                vector_ms = (time.perf_counter() - t_vec0) * 1000.0
                vector_candidates = len(vector_results)

                if settings.debug:
                    qlen = len(query_vec) if hasattr(query_vec, "__len__") else None
                    logger.debug(
                        f"🧠 Vector Search | where={where_clause} | qvec_len={qlen} | "
                        f"candidates={vector_candidates} | embed_ms={embedding_ms:.1f} | vec_ms={vector_ms:.1f}"
                    )
                    if where_clause:
                        t_vec1 = time.perf_counter()
                        unfiltered = self.vector_store.search(query_vec, limit=limit * 2, where=None)
                        vector_unfiltered_ms = (time.perf_counter() - t_vec1) * 1000.0
                        vector_where_unfiltered_candidates = len(unfiltered)
                        for item in unfiltered:
                            snap = item[0]
                            ts = float(snap.context.timestamp)
                            if parsed.start_time and ts < parsed.start_time:
                                continue
                            if parsed.end_time and ts > parsed.end_time:
                                continue
                            vector_where_pass += 1
                        vector_where_filtered_out = vector_where_unfiltered_candidates - vector_where_pass
                        logger.debug(
                            f"🧠 Vector Where Filter | unfiltered_candidates={vector_where_unfiltered_candidates} | "
                            f"pass={vector_where_pass} | filtered_out={vector_where_filtered_out} | "
                            f"unfiltered_ms={vector_unfiltered_ms:.1f}"
                        )

                for vector_rank, item in enumerate(vector_results):
                    snapshot = item[0]
                    score = float(item[1])
                    distance = float(item[2]) if len(item) >= 3 else None
                    metric = str(item[3]) if len(item) >= 4 else None
                    results_map[snapshot.id] = {
                        'snapshot': snapshot,
                        'score': score,
                        'debug': {
                            'vector_score': score,
                            'vector_rank': vector_rank,
                            'vector_distance': distance,
                            'vector_metric': metric,
                            'base_score': score,
                            'fts_rank': None,
                            'fts_boost': 0.0,
                            'is_fts_match': False
                        }
                    }
            except Exception as e:
                logger.exception(f"Vector search failed: {e}")
            finally:
                if settings.debug and parsed.text:
                    logger.debug(f"🧠 Vector Search Summary | where={where_clause} | merged={len(results_map)}")

        fts_query = parsed.text
        if parsed.mandatory_keywords:
            fts_query = " ".join([f'"{k}"' for k in parsed.mandatory_keywords])
        
        if fts_query:
            try:
                t_fts0 = time.perf_counter()
                fts_rows = self.fts_store.search(fts_query, limit=limit)
                fts_ms = (time.perf_counter() - t_fts0) * 1000.0
                fts_candidates = len(fts_rows)
                fts_ids = [sid for sid, _score in fts_rows]
                fts_bm25_by_id = {sid: float(score) for sid, score in fts_rows}

                if settings.debug:
                    logger.debug(
                        f"🔤 FTS Search | q='{fts_query}' | candidates={fts_candidates} | fts_ms={fts_ms:.1f}"
                    )
                
                missing_ids = [uid for uid in fts_ids if uid not in results_map]
                fts_missing_ids = list(missing_ids)
                if settings.debug and missing_ids:
                    logger.debug(f"🔤 FTS-only IDs (missing from vector) | count={len(missing_ids)}")
                    logger.debug(
                        "🔤 FTS-only IDs | "
                        + ", ".join([f"{sid}({fts_bm25_by_id.get(sid)})" for sid in missing_ids])
                    )
                
                if missing_ids:
                    fetched_snaps = self.vector_store.get_snapshots(missing_ids)
                    for snap in fetched_snaps:
                        ts = snap.context.timestamp
                        if parsed.start_time and ts < parsed.start_time:
                            filtered_from_fts_only += 1
                            fts_only_filtered_ids.append(snap.id)
                            continue
                        if parsed.end_time and ts > parsed.end_time:
                            filtered_from_fts_only += 1
                            fts_only_filtered_ids.append(snap.id)
                            continue
                            
                        base_score = 0.2
                        results_map[snap.id] = {
                            'snapshot': snap,
                            'score': base_score,
                            'debug': {
                                'vector_score': 0.0,
                                'vector_distance': None,
                                'vector_metric': None,
                                'base_score': base_score,
                                'fts_rank': None,
                                'fts_boost': 0.0,
                                'is_fts_match': True,
                                'fts_bm25': fts_bm25_by_id.get(snap.id)
                            }
                        }
                        fetched_from_fts_only += 1
                        fts_only_added_ids.append(snap.id)

                for rank, snap_id in enumerate(fts_ids):
                    if snap_id in results_map:
                        item = results_map[snap_id]
                        score_before = float(item['score'])
                        boost = 0.3 * (1.0 - (rank / len(fts_ids)))
                        item['score'] += boost
                        score_after = float(item['score'])
                        if settings.debug:
                            fts_boost_events.append(
                                (
                                    rank,
                                    snap_id,
                                    boost,
                                    score_before,
                                    score_after,
                                    len(fts_ids),
                                    fts_bm25_by_id.get(snap_id),
                                )
                            )
                        
                        item['debug']['fts_rank'] = rank
                        item['debug']['fts_boost'] = boost
                        item['debug']['is_fts_match'] = True
                        item['debug']['fts_bm25'] = fts_bm25_by_id.get(snap_id)
                        
            except Exception as e:
                logger.exception(f"FTS search failed: {e}")
                
        sorted_results = sorted(
            results_map.values(), 
            key=lambda x: x['score'], 
            reverse=True
        )
        
        if settings.debug:
            total_ms = (time.perf_counter() - t0) * 1000.0
            logger.debug(
                f"Search Summary | results={len(sorted_results)} | "
                f"vector_candidates={vector_candidates} | fts_candidates={fts_candidates} | "
                f"fts_only_added={fetched_from_fts_only} | fts_only_filtered={filtered_from_fts_only} | "
                f"total_ms={total_ms:.1f}"
            )
            logger.debug(
                f"Search Filter Summary | where_clause={where_clause_used} | "
                f"vector_unfiltered={vector_where_unfiltered_candidates} | vector_pass={vector_where_pass} | "
                f"vector_filtered_out={vector_where_filtered_out}"
            )

            logger.debug(f"FTS-only Missing IDs | count={len(fts_missing_ids)}")
            if fts_missing_ids:
                logger.debug("FTS-only Missing IDs | " + ", ".join(fts_missing_ids))

            logger.debug(f"FTS-only Added IDs | count={len(fts_only_added_ids)}")
            if fts_only_added_ids:
                logger.debug("FTS-only Added IDs | " + ", ".join(fts_only_added_ids))

            logger.debug(f"FTS-only Filtered IDs | count={len(fts_only_filtered_ids)}")
            if fts_only_filtered_ids:
                logger.debug("FTS-only Filtered IDs | " + ", ".join(fts_only_filtered_ids))

            logger.debug(f"FTS Boost Details | count={len(fts_boost_events)}")
            for rank, snap_id, boost, score_before, score_after, total, bm25_score in fts_boost_events:
                logger.debug(
                    f"FTS Boost | rank={rank}/{total-1 if total else 0} | "
                    f"id={snap_id} | bm25={bm25_score} | boost={boost:.4f} | score_before={score_before:.4f} | score_after={score_after:.4f}"
                )
            logger.debug(f"🔍 Search Debug Report | q='{user_query}' | showing_top={min(limit, len(sorted_results))}")
            for i, item in enumerate(sorted_results[:limit]):
                snap = item['snapshot']
                dbg = item['debug']
                ts = snap.context.timestamp
                img = f"{int(ts)}.png"
                logger.debug(
                    f"#{i+1} [Score: {item['score']:.4f}] "
                    f"ID={snap.id[:8]}... | "
                    f"Base={dbg['base_score']:.4f} | "
                    f"Vector={dbg['vector_score']:.4f} "
                    f"(dist={dbg.get('vector_distance')}, metric={dbg.get('vector_metric')}) | "
                    f"FTS_Match={'YES' if dbg['is_fts_match'] else 'NO'} "
                    f"(Rank={dbg['fts_rank']}, bm25={dbg.get('fts_bm25')}, Boost={dbg['fts_boost']:.4f}) | "
                    f"App='{snap.context.app_name}' Time={ts} Img={img}"
                )
        
        return sorted_results

    def _attach_score(self, snapshot: SemanticSnapshot, score: float) -> SemanticSnapshot:
        snapshot.score = score
        return snapshot
