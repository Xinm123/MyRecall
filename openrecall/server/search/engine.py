import logging
from typing import List, Dict, Optional
from pathlib import Path

import time
from datetime import datetime, timezone

from openrecall.server.database.vector_store import VectorStore
from openrecall.server.database.sql import SQLStore
from openrecall.server.utils.query_parser import QueryParser
from openrecall.server.schema import SemanticSnapshot
from openrecall.server.ai.factory import get_ai_provider
from openrecall.server.services.reranker import get_reranker

from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


def _resolve_snapshot_image_url(snapshot: SemanticSnapshot) -> str:
    """Resolve a browser URL for a snapshot image path."""
    raw_path = (snapshot.image_path or "").strip()
    if not raw_path:
        return ""

    path = Path(raw_path)
    # Frame extractor persists images as {frame_id}.png under frames path.
    if path.suffix.lower() == ".png" and path.stem.isdigit() and settings.frames_path in path.parents:
        return f"/api/v1/frames/{int(path.stem)}"
    if path.suffix.lower() == ".png":
        return f"/screenshots/{path.name}"
    return ""


def construct_rerank_context(snapshot: SemanticSnapshot) -> str:
    # 1. Human-readable Time
    ts = snapshot.context.timestamp
    time_str = datetime.fromtimestamp(ts).strftime("%A, %Y-%m-%d %H:%M")

    # 2. Build Parts with Explicit Headers and Double Newlines
    parts = [
        # --- Section 1: Metadata (High Priority) ---
        "[Metadata]",
        f"App: {snapshot.context.app_name or 'Unknown App'}",
        f"Title: {snapshot.context.window_title or 'No Title'}",
        f"Time: {time_str}",
        
        # --- Section 2: Visual Context (Medium Priority) ---
        "", # Empty string creates \n\n for paragraph separation
        "[Visual Context]",
        f"Scene: {snapshot.content.scene_tag or 'general'}",
        f"Summary: {snapshot.content.caption or ''}",
        
        # --- Section 3: OCR Content (Low Priority, High Volume) ---
        "",
        "[OCR Content]",
        snapshot.content.ocr_text or ''
    ]
    
    return "\n".join(parts)

class SearchEngine:
    def __init__(self, vector_store: Optional[VectorStore] = None, sql_store: Optional[SQLStore] = None):
        self.vector_store = vector_store or VectorStore()
        self.sql_store = sql_store or SQLStore()
        self.query_parser = QueryParser()
        self.embedding_provider = get_ai_provider("embedding")
        self.reranker = get_reranker()
        logger.info(f"SearchEngine initialized with Reranker: {settings.reranker_mode} ({settings.reranker_model})")

    def search(self, user_query: str, limit: int = 50) -> list:
        sorted_results = self._search_impl(user_query=user_query, limit=limit)
        output: list = []
        for item in sorted_results[:limit]:
            snap = item.get("snapshot")
            if snap is not None:
                output.append(self._attach_score(snap, item["score"]))
            elif item.get("source") == "video_frame":
                # Phase 2.6 retrieval contract: only video frame dicts pass through.
                output.append(item)
        return output

    def search_debug(self, user_query: str, limit: int = 50) -> List[dict]:
        sorted_results = self._search_impl(user_query=user_query, limit=limit)
        out: List[dict] = []
        for idx, item in enumerate(sorted_results[:limit]):
            if item.get("snapshot") is None and item.get("source") == "video_frame":
                vr = item.get("video_data") or {}
                frame_id = vr.get("frame_id")
                ts = float(vr.get("timestamp") or 0)
                dbg = item.get("debug") or {}
                out.append(
                    {
                        "id": f"vframe:{frame_id}",
                        "timestamp": ts,
                        "app": vr.get("app_name") or "Unknown",
                        "title": vr.get("window_name") or "Unknown",
                        "description": vr.get("text_snippet") or "",
                        "filename": None,
                        "image_url": f"/api/v1/frames/{frame_id}" if frame_id is not None else "",
                        "final_rank": idx + 1,
                        "final_score": float(item.get("score") or 0.0),
                        "rerank_rank": dbg.get("rerank_rank"),
                        "rerank_score": float(dbg.get("rerank_score") or 0.0) if dbg.get("rerank_score") is not None else None,
                        "combined_rank": dbg.get("combined_rank"),
                        "vector_rank": dbg.get("vector_rank"),
                        "vector_score": float(dbg.get("vector_score") or 0.0),
                        "vector_distance": dbg.get("vector_distance"),
                        "vector_metric": dbg.get("vector_metric"),
                        "fts_rank": dbg.get("fts_rank"),
                        "fts_bm25": dbg.get("fts_bm25"),
                        "fts_boost": float(dbg.get("fts_boost") or 0.0),
                    }
                )
                continue

            if item.get("snapshot") is None:
                continue

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
                    "image_url": _resolve_snapshot_image_url(snap),
                    "final_rank": idx + 1,
                    "final_score": float(item["score"]),
                    "rerank_rank": item["debug"].get("rerank_rank"),
                    "rerank_score": float(item["debug"].get("rerank_score") or 0.0) if item["debug"].get("rerank_score") is not None else None,
                    "combined_rank": item["debug"].get("combined_rank"),
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
                fts_rows = self.sql_store.search(fts_query, limit=limit)
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

        # Phase 1: Video FTS search
        if fts_query:
            try:
                video_fts_results = self.sql_store.search_video_fts(fts_query, limit=limit)
                for vr in video_fts_results:
                    key = f"vframe:{vr['frame_id']}"
                    if key not in results_map:
                        results_map[key] = {
                            'snapshot': None,
                            'score': 0.15,
                            'source': 'video_frame',
                            'video_data': vr,
                            'debug': {
                                'vector_score': 0.0,
                                'vector_distance': None,
                                'vector_metric': None,
                                'base_score': 0.15,
                                'fts_rank': None,
                                'fts_boost': 0.0,
                                'is_fts_match': True,
                                'fts_bm25': vr.get('score'),
                            }
                        }
                if settings.debug:
                    logger.debug(f"Video FTS | q='{fts_query}' | candidates={len(video_fts_results)}")
            except Exception as e:
                logger.warning(f"Video FTS search failed: {e}")

        sorted_results = sorted(
            results_map.values(), 
            key=lambda x: x['score'], 
            reverse=True
        )

        # Record Combined Rank (Stage 2 Rank)
        for rank, item in enumerate(sorted_results):
            item['debug']['combined_rank'] = rank

        # --- Stage 3: Deep Reranking (Top 30) ---
        candidates = [c for c in sorted_results[:30] if c.get("snapshot") is not None]
        if candidates and (parsed.text or user_query):
            try:
                doc_texts = [construct_rerank_context(c['snapshot']) for c in candidates]
                
                if settings.debug:
                    # Log context length summary first (as requested)
                    total_chars = sum(len(d) for d in doc_texts)
                    logger.debug(
                        f"🧠 Reranker Input Stats | Candidates={len(doc_texts)} | "
                        f"Total Context Length={total_chars} chars | "
                        f"Avg Context Length={total_chars // len(doc_texts) if doc_texts else 0} chars | "
                        f"Query Length={len(parsed.text or user_query)} chars"
                    )

                    # Log full context to file for inspection
                    try:
                        # User requested logs in project_root/logs
                        log_dir = Path("logs").resolve()
                        log_dir.mkdir(parents=True, exist_ok=True)
                        log_file = log_dir / "rerank_debug.log"
                        
                        with open(log_file, "a", encoding="utf-8") as f:
                            f.write(f"\n\n{'='*60}\n")
                            f.write(f"Query: {parsed.text or user_query}\n")
                            f.write(f"Time: {datetime.now().isoformat()}\n")
                            f.write(f"Candidates: {len(doc_texts)}\n")
                            f.write(f"{'='*60}\n")
                            for i, text in enumerate(doc_texts):
                                f.write(f"\n--- [Doc #{i+1}] ---\n{text}\n-------------------\n")
                        
                        logger.debug(f"🧠 Reranker Input (Full Context) logged to {log_file}")
                        logger.debug(f"🧠 Reranker Input Preview (Doc 1/{len(doc_texts)}):\n{doc_texts[0]}...$$")
                        logger.debug(f"🧠 Reranker Input Preview (Doc 2/{len(doc_texts)}):\n{doc_texts[1]}...$$")
                    except Exception as e:
                        logger.error(f"Failed to write rerank debug log: {e}")
                
                scores = self.reranker.compute_score(parsed.text or user_query, doc_texts)
                
                # If scores are not all zero (resilience check)
                if any(s != 0.0 for s in scores):
                    for i, c in enumerate(candidates):
                        c['score'] = scores[i]
                        c['debug']['rerank_score'] = scores[i]
                    
                    # Re-sort candidates
                    candidates.sort(key=lambda x: x['score'], reverse=True)
                    
                    # Update ranks
                    for rank, c in enumerate(candidates):
                        c['debug']['rerank_rank'] = rank

                    # Update the main list
                    sorted_results[:30] = candidates

                    # Log Top Reranked Results
                    if settings.debug:
                        logger.debug(f"🧠 Reranked Top Results (Top {len(candidates)}):")
                        query_text = parsed.text or user_query
                        for i, c in enumerate(candidates):
                            # doc_preview = construct_rerank_context(c['snapshot']).replace('\n', ' ')[:145]
                            full_context = construct_rerank_context(c['snapshot'])
                            doc_preview = full_context[:845]
                            ocr_len = len(c['snapshot'].content.ocr_text or "")
                            caption_len = len(c['snapshot'].content.caption or "")
                            pair_len = len(query_text) + len(full_context)
                            logger.debug(f"#{i+1} Score: {c['score']:.4f} | OCR_len={ocr_len} Cap_len={caption_len} Pair_len={pair_len} |\nDoc:\n{doc_preview}...\n")

                else:
                    logger.warning("⚠️ Reranker returned all zeros. Keeping RRF order.")
                    
            except Exception as e:
                logger.exception(f"Reranking stage failed: {e}")

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
                snap = item.get("snapshot")
                dbg = item.get("debug") or {}

                rerank_info = ""
                if dbg.get('rerank_score') is not None:
                    rerank_info = f" | Rerank={dbg['rerank_score']:.4f} (Rank={dbg.get('rerank_rank')})"

                if snap is None:
                    video_data = item.get("video_data") or {}
                    ts = float(video_data.get("timestamp") or 0.0)
                    img = f"/api/v1/frames/{video_data.get('frame_id')}"
                    logger.debug(
                        f"#{i+1} [Score: {item['score']:.4f}] "
                        f"ID=vframe:{video_data.get('frame_id')} | "
                        f"Base={dbg.get('base_score', 0.0):.4f} | "
                        f"Vector={dbg.get('vector_score', 0.0):.4f} "
                        f"(dist={dbg.get('vector_distance')}, metric={dbg.get('vector_metric')}) | "
                        f"FTS_Match={'YES' if dbg.get('is_fts_match') else 'NO'} "
                        f"(Rank={dbg.get('fts_rank')}, bm25={dbg.get('fts_bm25')}, Boost={dbg.get('fts_boost', 0.0):.4f}){rerank_info} | "
                        f"App='{video_data.get('app_name') or 'Unknown'}' Time={ts} Img={img}"
                    )
                    continue

                ts = snap.context.timestamp
                img = f"{int(ts)}.png"
                logger.debug(
                    f"#{i+1} [Score: {item['score']:.4f}] "
                    f"ID={snap.id[:8]}... | "
                    f"Base={dbg['base_score']:.4f} | "
                    f"Vector={dbg['vector_score']:.4f} "
                    f"(dist={dbg.get('vector_distance')}, metric={dbg.get('vector_metric')}) | "
                    f"FTS_Match={'YES' if dbg['is_fts_match'] else 'NO'} "
                    f"(Rank={dbg['fts_rank']}, bm25={dbg.get('fts_bm25')}, Boost={dbg['fts_boost']:.4f}){rerank_info} | "
                    f"App='{snap.context.app_name}' Time={ts} Img={img}"
                )
        
        return sorted_results

    def _attach_score(self, snapshot: SemanticSnapshot, score: float) -> SemanticSnapshot:
        snapshot.score = score
        return snapshot
