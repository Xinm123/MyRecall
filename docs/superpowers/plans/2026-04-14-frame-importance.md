# Frame Importance 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 frame 增加 importance 字段，通过 chat 评分机制影响搜索排序。

**Architecture:**
1. 数据库层：frames 表增加 importance 列
2. API 层：新增 /chat/api/rate 端点处理评分
3. 搜索层：RRF 融合后应用乘法加成重排
4. 前端层：assistant 消息下方显示评分按钮

**Tech Stack:** Python, Flask, SQLite, Alpine.js

---

## 文件结构

```
openrecall/
├── server/
│   ├── database/
│   │   ├── migrations/
│   │   │   └── 20260414120000_add_frame_importance.sql  (新增)
│   │   └── frames_store.py  (修改: 增加 importance 读写方法)
│   └── search/
│       └── hybrid_engine.py  (修改: 增加重排逻辑)
└── client/
    ├── chat/
    │   ├── routes.py  (修改: 增加 /rate 端点)
    │   ├── service.py  (修改: 增加评分处理方法)
    │   ├── types.py  (修改: Message 增加 id/rated/rating 字段)
    │   └── conversation.py  (修改: add_message 生成 UUID)
    └── web/
        └── templates/
            └── chat.html  (修改: 增加评分 UI)

tests/
└── test_frame_importance.py  (新增)
```

---

## Task 1: 数据库迁移 - 添加 importance 列

**Files:**
- Create: `openrecall/server/database/migrations/20260414120000_add_frame_importance.sql`
- Test: 验证迁移文件格式正确

- [ ] **Step 1: 创建迁移文件**

```sql
-- Add importance column to frames table
-- Migration: 20260414120000_add_frame_importance.sql
-- Created: 2026-04-14
-- Description: Add user rating-based importance scoring for search re-ranking

ALTER TABLE frames ADD COLUMN importance REAL DEFAULT 0;

-- Index for efficient sorting during re-ranking
CREATE INDEX IF NOT EXISTS idx_frames_importance ON frames(importance);
```

- [ ] **Step 2: 验证迁移文件命名格式**

迁移文件名格式：`YYYYMMDDHHMMSS_description.sql`
- 20260414120000 符合格式要求

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/database/migrations/20260414120000_add_frame_importance.sql
git commit -m "feat(db): add importance column to frames table for rating-based re-ranking"
```

---

## Task 2: FramesStore - 增加 importance 读写方法

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Test: `tests/test_frame_importance.py`

- [ ] **Step 1: 编写失败测试**

```python
# tests/test_frame_importance.py
"""Unit tests for frame importance feature."""
import pytest
import tempfile
import sqlite3
from pathlib import Path


class TestFrameImportance:
    """Tests for importance field operations."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database with frames table."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capture_id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                importance REAL DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
        return db_path

    def test_update_importance_adds_value(self, temp_db):
        """Test that update_importance adds the delta to existing value."""
        from openrecall.server.database.frames_store import FramesStore

        # Insert a test frame
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            "INSERT INTO frames (capture_id, timestamp, importance) VALUES (?, ?, ?)",
            ("test-1", "2026-04-14T12:00:00Z", 1.5)
        )
        conn.commit()

        # Get the frame_id
        row = conn.execute(
            "SELECT id FROM frames WHERE capture_id = ?", ("test-1",)
        ).fetchone()
        frame_id = row[0]
        conn.close()

        # Update importance
        store = FramesStore(db_path=temp_db)
        store.update_importance(frame_id, 2.0)

        # Verify
        conn = sqlite3.connect(str(temp_db))
        row = conn.execute(
            "SELECT importance FROM frames WHERE id = ?", (frame_id,)
        ).fetchone()
        assert row[0] == 3.5  # 1.5 + 2.0
        conn.close()

    def test_update_importance_negative_value(self, temp_db):
        """Test that update_importance handles negative deltas."""
        from openrecall.server.database.frames_store import FramesStore

        # Insert a test frame
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            "INSERT INTO frames (capture_id, timestamp, importance) VALUES (?, ?, ?)",
            ("test-2", "2026-04-14T12:00:00Z", 1.0)
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM frames WHERE capture_id = ?", ("test-2",)
        ).fetchone()
        frame_id = row[0]
        conn.close()

        # Update with negative delta
        store = FramesStore(db_path=temp_db)
        store.update_importance(frame_id, -1.5)

        # Verify
        conn = sqlite3.connect(str(temp_db))
        row = conn.execute(
            "SELECT importance FROM frames WHERE id = ?", (frame_id,)
        ).fetchone()
        assert row[0] == -0.5  # 1.0 + (-1.5)
        conn.close()

    def test_batch_update_importance(self, temp_db):
        """Test batch update of multiple frames."""
        from openrecall.server.database.frames_store import FramesStore

        # Insert test frames
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            "INSERT INTO frames (capture_id, timestamp, importance) VALUES (?, ?, ?)",
            ("test-3", "2026-04-14T12:00:00Z", 0)
        )
        conn.execute(
            "INSERT INTO frames (capture_id, timestamp, importance) VALUES (?, ?, ?)",
            ("test-4", "2026-04-14T12:01:00Z", 0)
        )
        conn.commit()
        row1 = conn.execute(
            "SELECT id FROM frames WHERE capture_id = ?", ("test-3",)
        ).fetchone()
        row2 = conn.execute(
            "SELECT id FROM frames WHERE capture_id = ?", ("test-4",)
        ).fetchone()
        frame_id_1, frame_id_2 = row1[0], row2[0]
        conn.close()

        # Batch update
        store = FramesStore(db_path=temp_db)
        updates = {frame_id_1: 1.0, frame_id_2: 2.0}
        store.batch_update_importance(updates)

        # Verify
        conn = sqlite3.connect(str(temp_db))
        imp1 = conn.execute(
            "SELECT importance FROM frames WHERE id = ?", (frame_id_1,)
        ).fetchone()[0]
        imp2 = conn.execute(
            "SELECT importance FROM frames WHERE id = ?", (frame_id_2,)
        ).fetchone()[0]
        assert imp1 == 1.0
        assert imp2 == 2.0
        conn.close()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_frame_importance.py -v
```

Expected: 测试失败，因为 `update_importance` 和 `batch_update_importance` 方法不存在

- [ ] **Step 3: 实现 update_importance 方法**

在 `openrecall/server/database/frames_store.py` 的 `FramesStore` 类中添加：

```python
def update_importance(self, frame_id: int, delta: float) -> bool:
    """Update the importance of a frame by adding delta.

    Args:
        frame_id: The frame ID to update
        delta: The amount to add to importance (can be negative)

    Returns:
        True if the update was successful
    """
    try:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE frames SET importance = importance + ? WHERE id = ?",
                (delta, frame_id),
            )
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error("update_importance failed frame_id=%s: %s", frame_id, e)
        return False

def batch_update_importance(self, updates: dict[int, float]) -> int:
    """Batch update importance for multiple frames.

    Args:
        updates: Dict mapping frame_id to importance delta

    Returns:
        Number of frames updated
    """
    if not updates:
        return 0

    try:
        with self._connect() as conn:
            cursor = conn.executemany(
                "UPDATE frames SET importance = importance + ? WHERE id = ?",
                [(delta, fid) for fid, delta in updates.items()],
            )
            conn.commit()
            return cursor.rowcount
    except sqlite3.Error as e:
        logger.error("batch_update_importance failed: %s", e)
        return 0
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_frame_importance.py -v
```

Expected: 所有测试通过

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_frame_importance.py
git commit -m "feat(db): add update_importance methods to FramesStore"
```

---

## Task 3: Message 类型 - 增加 id/rated/rating 字段

**Files:**
- Modify: `openrecall/client/chat/types.py`
- Modify: `openrecall/client/chat/conversation.py`
- Test: `tests/test_frame_importance.py`

- [ ] **Step 1: 编写失败测试**

在 `tests/test_frame_importance.py` 添加：

```python
class TestMessageTypes:
    """Tests for Message type with rating fields."""

    def test_message_has_id_field(self):
        """Test that Message has an id field."""
        from openrecall.client.chat.types import Message
        import uuid

        msg = Message(role="assistant", content="test")
        assert hasattr(msg, 'id')
        assert msg.id is not None
        # Verify it's a valid UUID
        uuid.UUID(msg.id)  # Will raise if not valid

    def test_message_has_rated_field(self):
        """Test that Message has a rated field."""
        from openrecall.client.chat.types import Message

        msg = Message(role="assistant", content="test")
        assert hasattr(msg, 'rated')
        assert msg.rated == False

    def test_message_to_dict_includes_rating_fields(self):
        """Test that to_dict includes id and rating fields."""
        from openrecall.client.chat.types import Message

        msg = Message(role="assistant", content="test")
        msg.rated = True
        msg.rating = 5
        d = msg.to_dict()
        assert 'id' in d
        assert 'rated' in d
        assert d['rated'] == True
        assert d['rating'] == 5
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_frame_importance.py::TestMessageTypes -v
```

Expected: 测试失败

- [ ] **Step 3: 修改 Message 数据类**

修改 `openrecall/client/chat/types.py`：

```python
"""Data models for Chat Service."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class ToolCall:
    """Represents a tool call made by the assistant."""
    id: str
    name: str
    args: dict
    status: str  # "running" | "done" | "error"
    result: Optional[dict | str] = None  # Can be dict (from Pi) or str (for display)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "args": self.args,
            "status": self.status,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolCall":
        return cls(
            id=d["id"],
            name=d["name"],
            args=d["args"],
            status=d["status"],
            result=d.get("result"),
        )


@dataclass
class Message:
    """Represents a single message in a conversation."""
    id: str = field(default_factory=_gen_uuid)
    role: str = "user"  # "user" | "assistant"
    content: str = ""
    tool_calls: Optional[list["ToolCall"]] = None
    rated: bool = False  # Whether this message has been rated
    rating: Optional[int] = None  # 1-5 if rated
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls] if self.tool_calls else None,
            "rated": self.rated,
            "rating": self.rating,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        tool_calls = None
        if d.get("tool_calls"):
            tool_calls = [ToolCall.from_dict(tc) for tc in d["tool_calls"]]
        created_at = d.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = _utc_now()
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            role=d["role"],
            content=d["content"],
            tool_calls=tool_calls,
            rated=d.get("rated", False),
            rating=d.get("rating"),
            created_at=created_at,
        )


# Conversation, ConversationMeta, PiStatus classes remain unchanged...
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_frame_importance.py::TestMessageTypes -v
```

Expected: 所有测试通过

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/chat/types.py tests/test_frame_importance.py
git commit -m "feat(chat): add id/rated/rating fields to Message type"
```

---

## Task 4: Chat Service - 增加评分处理逻辑

**Files:**
- Modify: `openrecall/client/chat/service.py`
- Test: `tests/test_frame_importance.py`

- [ ] **Step 1: 编写失败测试**

在 `tests/test_frame_importance.py` 添加：

```python
class TestRatingService:
    """Tests for rating service logic."""

    def test_rating_to_importance_mapping(self):
        """Test rating to importance delta mapping."""
        from openrecall.client.chat.service import rating_to_importance_delta

        assert rating_to_importance_delta(5) == 2.0
        assert rating_to_importance_delta(4) == 1.0
        assert rating_to_importance_delta(3) == -0.5
        assert rating_to_importance_delta(2) == -1.0
        assert rating_to_importance_delta(1) == -1.5

    def test_calculate_importance_weights(self):
        """Test importance weight calculation with 1/rank decay."""
        from openrecall.client.chat.service import calculate_importance_weights

        # 3 frames with rating 5
        weights = calculate_importance_weights([101, 102, 103], rating=5)
        assert weights[101] == 2.0 / 1  # rank 1
        assert weights[102] == 2.0 / 2  # rank 2
        assert weights[103] == 2.0 / 3  # rank 3

    def test_calculate_importance_weights_empty_list(self):
        """Test weight calculation with empty frame list."""
        from openrecall.client.chat.service import calculate_importance_weights

        weights = calculate_importance_weights([], rating=5)
        assert weights == {}

    def test_extract_frame_ids_from_tool_calls(self):
        """Test extracting frame IDs from tool calls."""
        from openrecall.client.chat.service import extract_frame_ids_from_tool_calls
        from openrecall.client.chat.types import ToolCall

        tool_calls = [
            ToolCall(
                id="tc-1",
                name="myrecall-search",
                args={"q": "test"},
                status="done",
                result={"data": [
                    {"frame_id": 101},
                    {"frame_id": 102},
                    {"frame_id": 103},
                ]}
            )
        ]

        frame_ids = extract_frame_ids_from_tool_calls(tool_calls)
        assert frame_ids == [101, 102, 103]

    def test_extract_frame_ids_no_search_tool(self):
        """Test extracting frame IDs when no search tool was called."""
        from openrecall.client.chat.service import extract_frame_ids_from_tool_calls
        from openrecall.client.chat.types import ToolCall

        tool_calls = [
            ToolCall(
                id="tc-1",
                name="other-tool",
                args={},
                status="done",
                result={}
            )
        ]

        frame_ids = extract_frame_ids_from_tool_calls(tool_calls)
        assert frame_ids == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_frame_importance.py::TestRatingService -v
```

Expected: 测试失败

- [ ] **Step 3: 实现评分处理函数**

在 `openrecall/client/chat/service.py` 文件顶部（import 之后，class 之前）添加：

```python
# Rating to importance delta mapping
RATING_TO_IMPORTANCE = {
    5: 2.0,
    4: 1.0,
    3: -0.5,
    2: -1.0,
    1: -1.5,
}


def rating_to_importance_delta(rating: int) -> float:
    """Convert rating (1-5) to importance delta value.

    Args:
        rating: User rating 1-5

    Returns:
        Importance delta to add to frame importance
    """
    return RATING_TO_IMPORTANCE.get(rating, 0.0)


def calculate_importance_weights(frame_ids: list[int], rating: int) -> dict[int, float]:
    """Calculate importance weights for frames using 1/rank decay.

    Args:
        frame_ids: List of frame IDs in order of relevance (rank 1, 2, 3...)
        rating: User rating 1-5

    Returns:
        Dict mapping frame_id to importance delta
    """
    if not frame_ids:
        return {}

    base_delta = rating_to_importance_delta(rating)
    weights = {}

    for rank, frame_id in enumerate(frame_ids, start=1):
        weights[frame_id] = base_delta / rank

    return weights


def extract_frame_ids_from_tool_calls(tool_calls: list) -> list[int]:
    """Extract frame IDs from myrecall-search tool call results.

    Args:
        tool_calls: List of ToolCall objects

    Returns:
        List of frame IDs in order of appearance
    """
    frame_ids = []

    for tc in tool_calls:
        # Look for search tool calls
        if tc.name and "search" in tc.name.lower():
            result = tc.result
            if isinstance(result, dict) and "data" in result:
                for item in result["data"]:
                    if isinstance(item, dict) and "frame_id" in item:
                        frame_ids.append(item["frame_id"])

    return frame_ids
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_frame_importance.py::TestRatingService -v
```

Expected: 所有测试通过

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/chat/service.py tests/test_frame_importance.py
git commit -m "feat(chat): add rating calculation functions for importance"
```

---

## Task 5: Chat Routes - 增加 /rate 端点

**Files:**
- Modify: `openrecall/client/chat/routes.py`
- Test: `tests/test_frame_importance.py`

- [ ] **Step 1: 编写失败测试**

在 `tests/test_frame_importance.py` 添加：

```python
class TestRateEndpoint:
    """Tests for /chat/api/rate endpoint."""

    @pytest.fixture
    def app(self):
        """Create a test Flask app."""
        from flask import Flask
        from openrecall.client.chat.routes import chat_bp

        app = Flask(__name__)
        app.register_blueprint(chat_bp)
        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return app.test_client()

    def test_rate_endpoint_success(self, client, monkeypatch):
        """Test successful rating."""
        # Mock the chat service
        from openrecall.client.chat import routes

        class MockService:
            def rate_message(self, message_id, rating):
                return {"success": True, "frames_updated": 3}

        monkeypatch.setattr(routes, 'get_chat_service', lambda: MockService())

        response = client.post(
            "/chat/api/rate",
            json={"message_id": "test-msg-id", "rating": 5},
            content_type="application/json"
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] == True
        assert data["frames_updated"] == 3

    def test_rate_endpoint_already_rated(self, client, monkeypatch):
        """Test rating an already-rated message."""
        from openrecall.client.chat import routes

        class MockService:
            def rate_message(self, message_id, rating):
                return {"success": False, "error": "already_rated"}

        monkeypatch.setattr(routes, 'get_chat_service', lambda: MockService())

        response = client.post(
            "/chat/api/rate",
            json={"message_id": "test-msg-id", "rating": 5},
            content_type="application/json"
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] == False
        assert data["error"] == "already_rated"

    def test_rate_endpoint_invalid_rating(self, client):
        """Test rating with invalid value."""
        response = client.post(
            "/chat/api/rate",
            json={"message_id": "test-msg-id", "rating": 6},
            content_type="application/json"
        )

        assert response.status_code == 400

    def test_rate_endpoint_missing_message_id(self, client):
        """Test rating without message_id."""
        response = client.post(
            "/chat/api/rate",
            json={"rating": 5},
            content_type="application/json"
        )

        assert response.status_code == 400
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_frame_importance.py::TestRateEndpoint -v
```

Expected: 测试失败（404 或端点不存在）

- [ ] **Step 3: 在 ChatService 中添加 rate_message 方法**

在 `openrecall/client/chat/service.py` 的 `ChatService` 类中添加：

```python
def rate_message(self, message_id: str, rating: int) -> dict:
    """Rate a message and update frame importance.

    Args:
        message_id: The message ID to rate
        rating: User rating 1-5

    Returns:
        Dict with success status and frames_updated count
    """
    # Validate rating
    if rating < 1 or rating > 5:
        return {"success": False, "error": "invalid_rating", "message": "评分必须在 1-5 之间"}

    # Find the message in all conversations
    for conv_path in self.chats_dir.glob("*.json"):
        try:
            conv_data = json.loads(conv_path.read_text())
            for msg_data in conv_data.get("messages", []):
                if msg_data.get("id") == message_id:
                    # Check if already rated
                    if msg_data.get("rated"):
                        return {"success": False, "error": "already_rated", "message": "该消息已评分"}

                    # Extract frame IDs from tool calls
                    tool_calls = msg_data.get("tool_calls", [])
                    from .types import ToolCall
                    tc_list = [ToolCall.from_dict(tc) for tc in tool_calls] if tool_calls else []
                    frame_ids = extract_frame_ids_from_tool_calls(tc_list)

                    if not frame_ids:
                        return {"success": False, "error": "no_frames", "message": "该消息未引用任何 frame"}

                    # Calculate importance weights
                    weights = calculate_importance_weights(frame_ids, rating)

                    # Update frames in database
                    from openrecall.server.database.frames_store import FramesStore
                    frames_store = FramesStore()
                    frames_updated = frames_store.batch_update_importance(weights)

                    # Mark message as rated
                    msg_data["rated"] = True
                    msg_data["rating"] = rating
                    conv_path.write_text(json.dumps(conv_data, indent=2))

                    return {"success": True, "frames_updated": frames_updated}
        except (json.JSONDecodeError, KeyError):
            continue

    return {"success": False, "error": "message_not_found", "message": "消息未找到"}
```

需要在文件顶部添加 `import json`。

- [ ] **Step 4: 在 routes.py 中添加 rate 端点**

在 `openrecall/client/chat/routes.py` 中添加：

```python
@chat_bp.route("/api/rate", methods=["POST"])
def rate_message():
    """
    Rate an assistant message and update frame importance.

    Request:
        {
            "message_id": "uuid-v4",
            "rating": 5  // 1-5
        }

    Response (success):
        {
            "success": true,
            "frames_updated": 3
        }

    Response (error):
        {
            "success": false,
            "error": "already_rated" | "no_frames" | "invalid_rating" | "message_not_found",
            "message": "错误信息"
        }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "missing_body"}), 400

    message_id = data.get("message_id")
    rating = data.get("rating")

    if not message_id:
        return jsonify({"success": False, "error": "missing_message_id"}), 400

    if rating is None:
        return jsonify({"success": False, "error": "missing_rating"}), 400

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            return jsonify({"success": False, "error": "invalid_rating", "message": "评分必须在 1-5 之间"}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "invalid_rating", "message": "评分必须是 1-5 的整数"}), 400

    service = get_chat_service()
    result = service.rate_message(message_id, rating)

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 400
```

- [ ] **Step 5: 运行测试确认通过**

```bash
pytest tests/test_frame_importance.py::TestRateEndpoint -v
```

Expected: 所有测试通过

- [ ] **Step 6: Commit**

```bash
git add openrecall/client/chat/routes.py openrecall/client/chat/service.py tests/test_frame_importance.py
git commit -m "feat(chat): add /chat/api/rate endpoint for message rating"
```

---

## Task 6: HybridSearchEngine - 增加乘法加成重排

**Files:**
- Modify: `openrecall/server/search/hybrid_engine.py`
- Test: `tests/test_frame_importance.py`

- [ ] **Step 1: 编写失败测试**

在 `tests/test_frame_importance.py` 添加：

```python
class TestImportanceRerank:
    """Tests for importance-based re-ranking."""

    def test_apply_importance_rerank_basic(self):
        """Test basic re-ranking with importance."""
        from openrecall.server.search.hybrid_engine import apply_importance_rerank

        results = [
            {"frame_id": 1, "score": 0.008, "importance": 0.0},
            {"frame_id": 2, "score": 0.007, "importance": 5.0},
            {"frame_id": 3, "score": 0.007, "importance": 2.5},
        ]

        reranked = apply_importance_rerank(results)

        # Frame 2 should now be first (0.007 * 1.2 = 0.0084 > 0.008)
        assert reranked[0]["frame_id"] == 2
        assert "final_score" in reranked[0]

    def test_apply_importance_rerank_preserves_order_when_zero(self):
        """Test that zero importance doesn't change order."""
        from openrecall.server.search.hybrid_engine import apply_importance_rerank

        results = [
            {"frame_id": 1, "score": 0.008, "importance": 0.0},
            {"frame_id": 2, "score": 0.007, "importance": 0.0},
            {"frame_id": 3, "score": 0.006, "importance": 0.0},
        ]

        reranked = apply_importance_rerank(results)

        # Order should remain the same
        assert reranked[0]["frame_id"] == 1
        assert reranked[1]["frame_id"] == 2
        assert reranked[2]["frame_id"] == 3

    def test_apply_importance_rerank_empty_results(self):
        """Test re-ranking with empty results."""
        from openrecall.server.search.hybrid_engine import apply_importance_rerank

        reranked = apply_importance_rerank([])
        assert reranked == []

    def test_apply_importance_rerank_negative_importance(self):
        """Test re-ranking with negative importance."""
        from openrecall.server.search.hybrid_engine import apply_importance_rerank

        results = [
            {"frame_id": 1, "score": 0.008, "importance": 0.0},
            {"frame_id": 2, "score": 0.008, "importance": -5.0},
        ]

        reranked = apply_importance_rerank(results)

        # Frame with negative importance should be penalized
        # When max_importance is 0, we use 1 to avoid division by zero
        # So normalized importance for frame 2 is -5/1 = -5, clamped
        # final_score = 0.008 * (1 + 0.2 * -5) = 0.008 * 0 = 0
        # Frame 1 should be first
        assert reranked[0]["frame_id"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_frame_importance.py::TestImportanceRerank -v
```

Expected: 测试失败

- [ ] **Step 3: 实现 apply_importance_rerank 函数**

在 `openrecall/server/search/hybrid_engine.py` 中添加：

```python
def apply_importance_rerank(
    results: List[Dict[str, Any]],
    boost_factor: float = 0.2,
) -> List[Dict[str, Any]]:
    """Apply importance-based re-ranking using multiplicative boost.

    The algorithm normalizes importance to 0-1 range and applies a multiplicative
    boost to the score: final_score = score * (1 + boost_factor * normalized_importance)

    Args:
        results: List of search results with 'score' and optional 'importance' keys
        boost_factor: Maximum boost factor (default 0.2 = 20% boost)

    Returns:
        Re-sorted results with 'final_score' field added
    """
    if not results:
        return results

    # Find max importance for normalization
    max_importance = max(r.get('importance', 0) for r in results)
    if max_importance <= 0:
        max_importance = 1  # Avoid division by zero

    # Apply multiplicative boost
    for r in results:
        importance = r.get('importance', 0)
        normalized = importance / max_importance

        # Calculate final score with multiplicative boost
        base_score = r.get('score', 0)
        boost = 1 + boost_factor * normalized

        # Ensure boost doesn't go below 0 (for negative importance)
        boost = max(0, boost)

        r['final_score'] = base_score * boost

    # Sort by final_score descending
    results.sort(key=lambda x: x.get('final_score', 0), reverse=True)

    return results
```

- [ ] **Step 4: 在 _hybrid_search 中调用重排**

修改 `HybridSearchEngine._hybrid_search` 方法，在返回之前添加重排：

找到 `results = []` 循环结束的位置，在 `return results, total` 之前添加：

```python
        # Apply importance-based re-ranking
        results = apply_importance_rerank(results)

        return results, total
```

同时需要在 `get_frames_by_ids` 返回的数据中包含 `importance` 字段。检查 `FramesStore.get_frames_by_ids` 方法，确保它返回 `importance`。

- [ ] **Step 5: 确保 get_frames_by_ids 返回 importance**

检查 `openrecall/server/database/frames_store.py` 中的 `get_frames_by_ids` 方法，确保 SELECT 语句包含 `importance` 列。如果没有，添加它。

- [ ] **Step 6: 运行测试确认通过**

```bash
pytest tests/test_frame_importance.py::TestImportanceRerank -v
```

Expected: 所有测试通过

- [ ] **Step 7: Commit**

```bash
git add openrecall/server/search/hybrid_engine.py tests/test_frame_importance.py
git commit -m "feat(search): add importance-based re-ranking with multiplicative boost"
```

---

## Task 7: 前端 UI - 增加评分按钮

**Files:**
- Modify: `openrecall/client/web/templates/chat.html`

- [ ] **Step 1: 添加评分按钮 CSS**

在 `chat.html` 的 `{% block extra_head %}` 部分的 `<style>` 标签内添加：

```css
  /* === Rating Buttons === */
  .rating-container {
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .rating-label {
    font-size: 12px;
    color: var(--text-secondary);
    margin-right: 4px;
  }

  .rating-btn {
    width: 32px;
    height: 32px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-body);
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .rating-btn:hover:not(:disabled) {
    background: var(--accent-color);
    color: white;
    border-color: var(--accent-color);
  }

  .rating-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .rating-btn.selected {
    background: var(--accent-color);
    color: white;
    border-color: var(--accent-color);
  }

  .rating-done {
    font-size: 12px;
    color: #34c759;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .rating-error {
    font-size: 12px;
    color: #ff3b30;
  }
```

- [ ] **Step 2: 添加评分按钮 HTML 模板**

找到 assistant 消息渲染部分（约 869 行附近），在 tool-calls-container 之后添加：

```html
            <!-- Rating Section -->
            <template x-if="msg.role === 'assistant' && !msg.rated && !msg.ratingLoading">
              <div class="rating-container">
                <span class="rating-label">评分:</span>
                <template x-for="r in [1,2,3,4,5]" :key="r">
                  <button class="rating-btn"
                          :class="{ 'selected': msg.rating === r }"
                          @click="rateMessage(msg, r)"
                          :disabled="msg.ratingLoading"
                          x-text="r">
                  </button>
                </template>
              </div>
            </template>

            <!-- Rating Loading -->
            <template x-if="msg.role === 'assistant' && msg.ratingLoading">
              <div class="rating-container">
                <span class="rating-label">提交中...</span>
              </div>
            </template>

            <!-- Rating Done -->
            <template x-if="msg.role === 'assistant' && msg.rated">
              <div class="rating-container">
                <span class="rating-done">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                  已评分 <span x-text="msg.rating"></span> 分
                </span>
              </div>
            </template>

            <!-- Rating Error -->
            <template x-if="msg.role === 'assistant' && msg.ratingError">
              <div class="rating-container">
                <span class="rating-error" x-text="msg.ratingError"></span>
              </div>
            </template>
```

- [ ] **Step 3: 添加 rateMessage JavaScript 方法**

在 `chatApp()` 函数的 `return { ... }` 对象中添加方法：

```javascript
      async rateMessage(msg, rating) {
        if (msg.rated || msg.ratingLoading) return;

        msg.ratingLoading = true;
        msg.ratingError = null;

        try {
          const resp = await fetch('/chat/api/rate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              message_id: msg.id,
              rating: rating
            })
          });

          const data = await resp.json();

          if (data.success) {
            msg.rated = true;
            msg.rating = rating;
          } else {
            // Handle specific errors
            if (data.error === 'already_rated') {
              msg.rated = true;
              msg.rating = rating; // Already rated, just show done
            } else {
              msg.ratingError = data.message || '评分失败';
            }
          }
        } catch (e) {
          console.error('Rating failed:', e);
          msg.ratingError = '网络错误';
        } finally {
          msg.ratingLoading = false;
        }
      },
```

- [ ] **Step 4: 确保 messages 加载时包含 rating 状态**

修改 `selectConversation` 方法中加载消息的部分，确保消息对象包含 rating 相关字段：

找到约 1212 行的 `this.messages.push({...})` 部分，添加 rating 字段：

```javascript
            this.messages.push({
              id: m.id || this.nextId(),  // Use backend ID if available
              role: m.role,
              rawContent: m.content,
              content: m.role === 'assistant' ? marked.parse(m.content) : this.escapeHtml(m.content),
              toolCalls: m.tool_calls ? m.tool_calls.map(tc => ({ ...tc, expanded: false })) : [],
              thinking: '',
              thinkingExpanded: false,
              rated: m.rated || false,
              rating: m.rating || null,
              ratingLoading: false,
              ratingError: null,
            });
```

- [ ] **Step 5: 手动测试**

启动服务器：
```bash
./run_server.sh --mode local --debug
./run_client.sh --mode local --debug
```

1. 打开 http://localhost:8889/chat
2. 发送一条消息触发搜索
3. 验证 assistant 回复下方显示评分按钮
4. 点击评分，验证状态变为"已评分 ✓"
5. 刷新页面，验证评分状态持久化

- [ ] **Step 6: Commit**

```bash
git add openrecall/client/web/templates/chat.html
git commit -m "feat(ui): add rating buttons for assistant messages"
```

---

## Task 8: 集成测试与验收

**Files:**
- Test: 手动验收测试

- [ ] **Step 1: 运行所有单元测试**

```bash
pytest tests/test_frame_importance.py -v
```

Expected: 所有测试通过

- [ ] **Step 2: 运行集成测试（如果存在）**

```bash
pytest -m integration -v
```

- [ ] **Step 3: 手动验收测试清单**

- [ ] 创建新对话，发送消息触发搜索
- [ ] 验证 assistant 回复下方显示 [1] [2] [3] [4] [5] 按钮
- [ ] 点击评分，验证按钮禁用，显示"已评分 ✓"
- [ ] 刷新页面，验证评分状态保留
- [ ] 再次搜索相同内容，验证 importance 影响排序
- [ ] 测试错误场景：无 frame 的消息评分

- [ ] **Step 4: Final Commit**

```bash
git add -A
git commit -m "feat: complete frame importance implementation"
```

---

## 自检清单

| 检查项 | 状态 |
|--------|------|
| Spec 覆盖完整 | ✅ |
| 无 TBD/TODO 占位符 | ✅ |
| 类型/方法名一致 | ✅ |
| TDD 流程遵循 | ✅ |
| 每步可独立执行 | ✅ |
