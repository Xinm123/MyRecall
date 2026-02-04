# Phase 0 (Foundation) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 v3（timeline/keyword/chat）打底：新增 v3 API 骨架 + SQLite 稳定性策略 + frames 分页/增量接口 + 对应测试。

**Architecture:** 在不破坏现有 `/api/*` 与旧页面的前提下，新建 `/api/v3/*`；SQLStore 的连接策略统一设置（WAL/busy_timeout/重试）；frames 接口面向 timeline-v3 分页与 polling。

**Tech Stack:** Flask（现有 app）、sqlite3 + FTS5（现有）、LanceDB（现有，Phase0 不强依赖）

## Scope
- In:
  - v3 blueprint 注册与基础路由
  - SQLite 连接策略统一化（WAL/busy_timeout/写入重试）
  - `GET /api/v3/frames`（before/after/limit/status/app/window）
  - pytest 覆盖（至少 frames 的边界 + fixture 更新）
- Out:
  - timeline-v3 UI（Phase 1）
  - keyword/snippet（Phase 1）
  - chat（Phase 2）

## Sources of Truth
- `MyRecall/openrecall/server/app.py`
- `MyRecall/openrecall/server/api.py`
- `MyRecall/openrecall/server/database/sql.py`
- 测试 fixture：`MyRecall/tests/conftest.py`

---

### Task 1: 修正测试 fixture 的数据目录隔离（避免写到 ~/MRS, ~/MRC）

**Files:**
- Modify: `MyRecall/tests/conftest.py`

**Step 1: Write the failing test**
- 新增一个断言用例（或在现有 fixture 内）验证 settings 的 `server_data_dir/client_data_dir` 都指向 `tmp_path`。

示例（放在 `MyRecall/tests/test_shared_utils_smoke.py` 或新建文件都可）：
```python
def test_test_fixture_uses_tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
    import importlib
    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)
    assert str(openrecall.shared.config.settings.server_data_dir).startswith(str(tmp_path))
```

**Step 2: Run test to verify it fails**
Run: `cd MyRecall && pytest -q`  
Expected: FAIL（当前 fixture 只设置 `OPENRECALL_DATA_DIR`，不会影响 server/client split dirs）

**Step 3: Write minimal implementation**
- 在 `flask_app` fixture 中新增：
  - `OPENRECALL_SERVER_DATA_DIR=<tmp_path>/MRS`
  - `OPENRECALL_CLIENT_DATA_DIR=<tmp_path>/MRC`
- 并保留 `OPENRECALL_DATA_DIR`（兼容 legacy）

**Step 4: Run test to verify it passes**
Run: `cd MyRecall && pytest -q`  
Expected: PASS

**Step 5: Commit**
`git commit -m "v3-0: isolate test data dirs"`

---

### Task 2: 新增 v3 API blueprint 并注册到 Flask app

**Files:**
- Create: `MyRecall/openrecall/server/api_v3.py`
- Modify: `MyRecall/openrecall/server/app.py`
- Test: `MyRecall/tests/test_api_v3_smoke.py`

**Step 1: Write the failing test**
`MyRecall/tests/test_api_v3_smoke.py`
```python
def test_v3_frames_route_exists(flask_client):
    resp = flask_client.get("/api/v3/frames?limit=1")
    assert resp.status_code in (200, 400)
```

**Step 2: Run test to verify it fails**
Run: `cd MyRecall && pytest -q`  
Expected: 404 Not Found

**Step 3: Write minimal implementation**
- `api_v3.py`：
  - `v3_bp = Blueprint("api_v3", __name__, url_prefix="/api/v3")`
  - 先加一个占位 `GET /frames` 返回 `{"items":[],"next_before":null}`
- `app.py`：
  - `app.register_blueprint(v3_bp)`

**Step 4: Run test to verify it passes**
Expected: 200

**Step 5: Commit**
`git commit -m "v3-0: add api v3 blueprint"`

---

### Task 3: 统一 SQLite 连接策略（WAL + busy_timeout + 轻量重试）

**Files:**
- Modify: `MyRecall/openrecall/server/database/sql.py`
- Test: `MyRecall/tests/test_sqlite_connection_pragmas.py`

**Step 1: Write the failing test**
思路：在 `SQLStore` 暴露一个“查询 pragma”方法（或在测试里直接 connect 并 query），断言 busy_timeout 非 0；并尽量断言 journal_mode=wal（允许因平台差异做“包含 wal 或 memory”容错）。

**Step 2: Run test to verify it fails**
Expected: 默认 pragma 未设置（busy_timeout=0 或 journal_mode=delete）

**Step 3: Write minimal implementation**
- 在 `SQLStore` 内新增私有 helper：
  - `_connect_db()` / `_connect_fts()`：统一设置：
    - `PRAGMA journal_mode=WAL;`
    - `PRAGMA busy_timeout=5000;`
    - `PRAGMA synchronous=NORMAL;`
    - `PRAGMA temp_store=MEMORY;`
- 写入路径：在所有 `sqlite3.connect(...)` 替换成这些 helper
- 写入重试：对写事务（INSERT/UPDATE）包一层 retry（例如 3 次，指数退避 50ms/100ms/200ms），仅对 `sqlite3.OperationalError: database is locked` 生效

**Step 4: Run test to verify it passes**
Expected: pragma 生效

**Step 5: Commit**
`git commit -m "v3-0: harden sqlite connections"`

---

### Task 4: 实现 `GET /api/v3/frames`（分页 + 增量）

**Files:**
- Modify: `MyRecall/openrecall/server/api_v3.py`
- Modify: `MyRecall/openrecall/server/database/sql.py`
- Test: `MyRecall/tests/test_api_v3_frames.py`

**Step 1: Write the failing test**
覆盖：
- 空库
- limit 上限
- after 增量（timestamp > after）
- before 分页（timestamp < before）
- status 过滤（PENDING/COMPLETED）
- app/window 模糊匹配（contains）

**Step 2: Run test to verify it fails**
Expected: 未实现

**Step 3: Write minimal implementation**
- SQLStore 新增方法：
  - `get_frames(before: int|None, after: int|None, limit: int, status: str|None, app: str|None, window: str|None) -> (items, next_before)`
- `api_v3.py` 返回 JSON：
  - `items: [{id,timestamp,app_name,window_title,description,status,image_url}]`
  - `next_before`：当按 before 分页时为最后一条 timestamp；否则可省略或返回 null
  - `server_time`: `int(time.time())`

**Step 4: Run test to verify it passes**
Run: `cd MyRecall && pytest -q`

**Step 5: Commit**
`git commit -m "v3-0: add frames paging api"`

---

### Task 5: 文档更新（仅说明 v3 API，不改实现）

**Files:**
- (Optional) Modify: `MyRecall/docs/plan/2026-02-04-MyRecall-v3-roadmap.md`（补充接口说明）

**Step:** 仅同步文档（若实现与文档偏差）。

