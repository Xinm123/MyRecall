import importlib
import os
import sqlite3
import time
from datetime import datetime, timedelta

import numpy as np


def main():
    base_dir = "/tmp/openrecall_phase10_acceptance"
    os.environ["OPENRECALL_DATA_DIR"] = base_dir
    os.environ["OPENRECALL_MM_EMBEDDING_PROVIDER"] = "api"
    os.environ["OPENRECALL_RERANK_ENABLED"] = "true"
    os.environ["OPENRECALL_RERANK_TOPK"] = "10"

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)
    settings = openrecall.shared.config.settings

    import openrecall.server.database
    importlib.reload(openrecall.server.database)
    db = openrecall.server.database
    db.create_db()

    import openrecall.server.app
    importlib.reload(openrecall.server.app)

    now = datetime.now()
    yesterday = now - timedelta(days=1)
    y_afternoon = yesterday.replace(hour=15, minute=20, second=0, microsecond=0)
    y_morning = yesterday.replace(hour=9, minute=10, second=0, microsecond=0)
    today = now.replace(hour=11, minute=10, second=0, microsecond=0)

    dim = int(settings.embedding_dim)
    v_bug = np.zeros(dim, dtype=np.float32)
    v_bug[0] = 1.0
    v_other = np.zeros(dim, dtype=np.float32)
    v_other[1] = 1.0

    def insert(ts: int, text: str, desc: str, img_vec: np.ndarray):
        with sqlite3.connect(str(settings.db_path)) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO entries(app,title,text,description,timestamp,embedding,image_embedding,status) "
                "VALUES(?,?,?,?,?,?,?,'COMPLETED')",
                (
                    "IDE",
                    "VS Code",
                    text,
                    desc,
                    ts,
                    np.zeros(dim, dtype=np.float32).tobytes(),
                    img_vec.astype(np.float32).tobytes(),
                ),
            )
            entry_id = int(cur.lastrowid)
            conn.commit()
            db.fts_upsert_entry(conn, entry_id=entry_id, app="IDE", title="VS Code", text=text, description=desc)
        return entry_id

    insert(int(y_afternoon.timestamp()), "修复失败 BUG TypeError", "User fixing bug in code", v_bug)
    insert(int((y_afternoon + timedelta(minutes=15)).timestamp()), "调试 BUG 堆栈", "Debugging stacktrace", v_bug)
    insert(int(y_morning.timestamp()), "开会 计划", "Meeting notes", v_other)
    insert(int(today.timestamp()), "看视频", "Watching video", v_other)

    class _StubMM:
        def embed_text(self, text: str) -> np.ndarray:
            t = (text or "").lower()
            if "bug" in t or "typeerror" in t:
                return v_bug
            return v_other

        def embed_image(self, image_path: str) -> np.ndarray:
            return v_other

    class _StubRerank:
        def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
            out = []
            for c in candidates:
                t = (c.get("text") or "") + " " + (c.get("description") or "")
                score = 0.9 if "TypeError" in t else 0.1
                d = dict(c)
                d["rerank_score"] = score
                out.append(d)
            out.sort(key=lambda x: float(x.get("rerank_score") or 0.0), reverse=True)
            return out

    from unittest import mock

    with mock.patch("openrecall.server.ai.factory.get_mm_embedding_provider", return_value=_StubMM()), mock.patch(
        "openrecall.server.ai.factory.get_reranker_provider", return_value=_StubRerank()
    ):
        client = openrecall.server.app.app.test_client()
        resp = client.get("/search?q=%E6%98%A8%E5%A4%A9%E4%B8%8B%E5%8D%88%20%E4%BF%AE%E6%94%B9%E4%BB%A3%E7%A0%81BUG")
        html = resp.get_data(as_text=True)
        lines = []
        for line in html.splitlines():
            if "/screenshots/" in line and ".png" in line:
                lines.append(line.strip())
        print("top results lines:")
        for l in lines[:10]:
            print(l)
        assert resp.status_code == 200
        assert "关键词" in html or "语义" in html


if __name__ == "__main__":
    main()
