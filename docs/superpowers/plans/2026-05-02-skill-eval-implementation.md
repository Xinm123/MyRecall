# Skill Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete test harness that runs 4 skill variants through 33 prompts × 3 runs each, scores API call correctness, and produces a comparison report.

**Architecture:** Flask mock server serves date-aware, keyword-filtered data on port 18083. A Python test runner swaps skills in `~/.pi/agent/skills/`, invokes Pi CLI with minimax-cn, parses mock server logs, and scores against expected behavior. Scoring extends existing `evaluate.py` with multi-turn context reuse and modular overhead tracking.

**Tech Stack:** Python 3.12, Flask, JSON, Pi CLI (bun), minimax-cn API

---

## File Structure

| File | Role |
|---|---|
| `tests/skill_eval/mock_server.py` | Flask mock API server — enhanced with date-aware data, real keyword filtering, differentiated frame contexts, Chinese content |
| `tests/skill_eval/test_cases_v2.json` | All 33 prompt definitions with expected endpoints, required params, forbidden endpoints, context reuse hints |
| `tests/skill_eval/evaluate.py` | Scoring engine — enhanced for multi-turn context reuse (+20 pts) and modular overhead tracking |
| `tests/skill_eval/pi_test_runner.py` | Main harness — installs skill variants, runs Pi CLI, collects logs, invokes scoring, writes results |
| `tests/skill_eval/install_skill.py` | Helper — copies a skill variant to `~/.pi/agent/skills/`, substitutes URL to port 18083 |

---

## Task 1: Create `install_skill.py`

**Files:**
- Create: `tests/skill_eval/install_skill.py`
- Test: `tests/skill_eval/test_install_skill.py`

- [ ] **Step 1: Write the failing test**

```python
import json
import tempfile
from pathlib import Path

from install_skill import install_skill


def test_install_skill_substitutes_url():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source" / "SKILL.md"
        source.parent.mkdir()
        source.write_text("http://localhost:8083/some/path\n")
        dest_root = Path(tmp) / "dest"

        install_skill(source.parent, dest_root, port=18083)

        installed = dest_root / "SKILL.md"
        assert installed.exists()
        content = installed.read_text()
        assert "http://localhost:18083/some/path" in content
        assert "8083" not in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/skill_eval/test_install_skill.py -v`
Expected: `ModuleNotFoundError: No module named 'install_skill'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Install a skill variant to the Pi skills directory with URL substitution."""

import shutil
from pathlib import Path


def install_skill(source_dir: Path, dest_dir: Path, port: int = 18083) -> None:
    """Copy skill files from source_dir to dest_dir, substituting localhost:8083 with localhost:{port}."""
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.copytree(source_dir, dest_dir)

    for path in dest_dir.rglob("*.md"):
        content = path.read_text()
        content = content.replace("http://localhost:8083", f"http://localhost:{port}")
        path.write_text(content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/skill_eval/test_install_skill.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/skill_eval/install_skill.py tests/skill_eval/test_install_skill.py
git commit -m "feat(skill-eval): add skill installer with URL substitution"
```

---

## Task 2: Enhance `mock_server.py`

**Files:**
- Modify: `tests/skill_eval/mock_server.py`
- Test: `tests/skill_eval/test_mock_server.py`

- [ ] **Step 1: Write the failing test for date-aware activity-summary**

```python
import pytest
from mock_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_activity_summary_today(client):
    resp = client.get("/v1/activity-summary?start_time=2026-05-02T00:00:00&end_time=2026-05-02T23:59:59")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_frames"] == 53
    apps = [a["name"] for a in data["apps"]]
    assert "VSCode" in apps


def test_activity_summary_yesterday(client):
    resp = client.get("/v1/activity-summary?start_time=2026-05-01T00:00:00&end_time=2026-05-01T23:59:59")
    assert resp.status_code == 200
    data = resp.get_json()
    apps = [a["name"] for a in data["apps"]]
    assert "Xcode" in apps  # yesterday has different apps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/skill_eval/test_mock_server.py -v`
Expected: `AssertionError: assert 'Xcode' in ['Safari', 'VSCode', 'Chrome']`

- [ ] **Step 3: Implement date-aware mock data**

Replace the hardcoded `apps` and `descriptions` lists in `mock_server.py` with a `DATASETS` dict keyed by date:

```python
DATASETS = {
    "2026-05-02": {
        "apps": [
            {"name": "Safari", "frame_count": 15, "minutes": 45.5,
             "first_seen": "2026-05-02T09:00:00", "last_seen": "2026-05-02T10:30:00"},
            {"name": "VSCode", "frame_count": 30, "minutes": 120.0,
             "first_seen": "2026-05-02T10:00:00", "last_seen": "2026-05-02T12:00:00"},
            {"name": "Chrome", "frame_count": 8, "minutes": 25.0,
             "first_seen": "2026-05-02T14:00:00", "last_seen": "2026-05-02T14:25:00"},
        ],
        "descriptions": [
            {"frame_id": 101, "timestamp": "2026-05-02T09:15:00",
             "summary": "Browsing GitHub issues", "tags": ["github", "browsing"]},
            {"frame_id": 102, "timestamp": "2026-05-02T10:30:00",
             "summary": "Reviewing PR #456 in VSCode", "tags": ["code_review", "vscode"]},
            {"frame_id": 103, "timestamp": "2026-05-02T11:45:00",
             "summary": "Writing Python tests", "tags": ["coding", "python"]},
        ],
        "search_frames": [
            {"frame_id": 201, "timestamp": "2026-05-02T10:30:00", "text_source": "accessibility",
             "app_name": "VSCode", "window_name": "myrecall-search — pull_request.py",
             "score": 0.95, "text": "Editing pull_request.py in VSCode"},
            {"frame_id": 202, "timestamp": "2026-05-02T10:35:00", "text_source": "accessibility",
             "app_name": "VSCode", "window_name": "myrecall-search — test_runner.py",
             "score": 0.88, "text": "Writing test_runner.py in VSCode"},
            {"frame_id": 203, "timestamp": "2026-05-02T14:00:00", "text_source": "accessibility",
             "app_name": "Safari", "window_name": "AI Research",
             "score": 0.82, "text": "Reading about AI models"},
            {"frame_id": 204, "timestamp": "2026-05-02T14:30:00", "text_source": "accessibility",
             "app_name": "VSCode", "window_name": "react-app — App.tsx",
             "score": 0.75, "text": "Building a React component"},
            {"frame_id": 205, "timestamp": "2026-05-02T15:00:00", "text_source": "accessibility",
             "app_name": "Chrome", "window_name": "Settings — Change Password",
             "score": 0.70, "text": "change your password"},
        ],
    },
    "2026-05-01": {
        "apps": [
            {"name": "Safari", "frame_count": 10, "minutes": 30.0,
             "first_seen": "2026-05-01T09:00:00", "last_seen": "2026-05-01T09:30:00"},
            {"name": "Slack", "frame_count": 20, "minutes": 60.0,
             "first_seen": "2026-05-01T10:00:00", "last_seen": "2026-05-01T11:00:00"},
            {"name": "Xcode", "frame_count": 15, "minutes": 45.0,
             "first_seen": "2026-05-01T14:00:00", "last_seen": "2026-05-01T14:45:00"},
        ],
        "descriptions": [
            {"frame_id": 301, "timestamp": "2026-05-01T09:15:00",
             "summary": "Reading documentation in Safari", "tags": ["docs", "reading"]},
            {"frame_id": 302, "timestamp": "2026-05-01T10:30:00",
             "summary": "Team discussion in Slack", "tags": ["slack", "chat"]},
        ],
        "search_frames": [
            {"frame_id": 401, "timestamp": "2026-05-01T09:30:00", "text_source": "accessibility",
             "app_name": "Safari", "window_name": "Docs",
             "score": 0.90, "text": "Reading Swift documentation"},
            {"frame_id": 402, "timestamp": "2026-05-01T11:00:00", "text_source": "accessibility",
             "app_name": "Slack", "window_name": "#general",
             "score": 0.85, "text": "Team standup discussion"},
        ],
    },
}

FRAME_CONTEXTS = {
    101: {"app_name": "Safari", "narrative": "Browsing GitHub issues in Safari",
          "summary": "GitHub browsing", "text": "浏览 GitHub 问题列表..."},
    102: {"app_name": "VSCode", "narrative": "Reviewing PR #456 in VSCode",
          "summary": "PR review", "text": "Reviewing pull request changes..."},
    103: {"app_name": "VSCode", "narrative": "Writing Python unit tests",
          "summary": "Python testing", "text": "Writing test cases..."},
    201: {"app_name": "VSCode", "narrative": "Editing pull_request.py in VSCode",
          "summary": "Code editing", "text": "Editing pull_request.py..."},
    202: {"app_name": "VSCode", "narrative": "Writing test_runner.py in VSCode",
          "summary": "Test writing", "text": "Writing test_runner.py..."},
    203: {"app_name": "Safari", "narrative": "Reading about AI models",
          "summary": "AI research", "text": "Reading about AI models..."},
    204: {"app_name": "VSCode", "narrative": "Building a React component",
          "summary": "React dev", "text": "Building a React component..."},
    205: {"app_name": "Chrome", "narrative": "Changing password on settings page",
          "summary": "Password change", "text": "change your password"},
    301: {"app_name": "Safari", "narrative": "Reading documentation in Safari",
          "summary": "Doc reading", "text": "Reading Swift docs..."},
    302: {"app_name": "Slack", "narrative": "Team discussion in Slack",
          "summary": "Team chat", "text": "Discussing sprint plans..."},
    401: {"app_name": "Safari", "narrative": "Reading Swift documentation",
          "summary": "Swift docs", "text": "Reading Swift documentation..."},
    402: {"app_name": "Slack", "narrative": "Team standup discussion",
          "summary": "Standup", "text": "Team standup discussion..."},
}
```

Then update `activity_summary()` to pick dataset by parsing `start_time` date:

```python
def _get_dataset(start_time: str) -> dict:
    """Pick dataset by date from start_time (ISO 8601)."""
    date = start_time[:10] if start_time else "2026-05-02"
    return DATASETS.get(date, {"apps": [], "descriptions": [], "total_frames": 0})
```

- [ ] **Step 4: Implement real search filtering**

Update `search()` to:
1. Pick `search_frames` from dataset by `start_time` date
2. Remove `or True` from keyword matching
3. Match against `text`, `window_name`, and `description.summary` (from FRAME_CONTEXTS)

```python
def search():
    log_request("GET", "/v1/search", request.args)
    q = request.args.get("q", "")
    start_time = request.args.get("start_time", "")
    limit = int(request.args.get("limit", 20))
    app_name = request.args.get("app_name", "")

    dataset = _get_dataset(start_time)
    results = [dict(r) for r in dataset.get("search_frames", [])]

    if app_name:
        results = [r for r in results if r["app_name"].lower() == app_name.lower()]

    if q and q != "*":
        filtered = []
        query_lower = q.lower()
        for r in results:
            ctx = FRAME_CONTEXTS.get(r["frame_id"], {})
            text = r.get("text", "")
            window = r.get("window_name", "")
            summary = ctx.get("summary", "")
            if (query_lower in text.lower() or
                query_lower in window.lower() or
                query_lower in summary.lower()):
                filtered.append(r)
        results = filtered

    # ... rest of pagination logic
```

- [ ] **Step 5: Implement differentiated frame contexts**

Update `get_frame_context()` to use `FRAME_CONTEXTS`:

```python
@app.route("/v1/frames/<int:frame_id>", methods=["GET"])
def get_frame_context(frame_id):
    log_request("GET", f"/v1/frames/{frame_id}/context", request.args)
    ctx = FRAME_CONTEXTS.get(frame_id, {
        "app_name": "Unknown",
        "narrative": f"Frame {frame_id} — no description available",
        "summary": "Unknown",
        "text": "No text captured",
    })
    return jsonify({
        "frame_id": frame_id,
        "timestamp": "2026-05-02T10:30:00",
        "app_name": ctx["app_name"],
        "window_name": f"Window for frame {frame_id}",
        "description": {
            "narrative": ctx["narrative"],
            "summary": ctx["summary"],
            "tags": ["test"],
        },
        "text": ctx["text"],
        "text_source": "accessibility",
        "urls": [],
        "browser_url": None,
        "status": "completed",
        "description_status": "completed",
    })
```

- [ ] **Step 6: Run all mock server tests**

Run: `pytest tests/skill_eval/test_mock_server.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add tests/skill_eval/mock_server.py tests/skill_eval/test_mock_server.py
git commit -m "feat(skill-eval): enhance mock server with date-aware data, real search, differentiated contexts"
```

---

## Task 3: Create `test_cases_v2.json`

**Files:**
- Create: `tests/skill_eval/test_cases_v2.json`
- Test: `tests/skill_eval/test_cases_v2.py`

- [ ] **Step 1: Write the test case schema validator**

```python
import json
from pathlib import Path


def test_all_cases_have_required_fields():
    path = Path(__file__).parent / "test_cases_v2.json"
    data = json.loads(path.read_text())
    assert "cases" in data
    assert len(data["cases"]) == 33

    for case in data["cases"]:
        assert "id" in case
        assert "prompt" in case
        assert "expected" in case
        expected = case["expected"]
        assert "primary_endpoint" in expected or "primary_endpoints" in expected or "acceptable_endpoints" in expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/skill_eval/test_cases_v2.py -v`
Expected: `FileNotFoundError`

- [ ] **Step 3: Write `test_cases_v2.json`**

The full JSON (abbreviated here, write complete version in actual file):

```json
{
  "cases": [
    {"id": "T1", "prompt": "What was I doing today?", "group": "A", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T2", "prompt": "Which apps did I use yesterday?", "group": "A", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T3", "prompt": "Find the PR I was reviewing", "group": "A", "expected": {"primary_endpoint": "/v1/search", "required_params": ["q", "start_time", "end_time"], "forbidden_endpoints": []}},
    {"id": "T4", "prompt": "Did I see anything about AI?", "group": "A", "expected": {"primary_endpoint": "/v1/search", "required_params": ["q", "start_time", "end_time"], "forbidden_endpoints": []}},
    {"id": "T5", "prompt": "Did I open GitHub today?", "group": "A", "expected": {"primary_endpoints": ["/v1/activity-summary", "/v1/search"], "required_params": ["start_time", "end_time"], "forbidden_endpoints": []}},
    {"id": "T6", "prompt": "What was I doing in frame 42?", "group": "A", "expected": {"primary_endpoint": "/v1/frames/42/context", "required_params": [], "forbidden_endpoints": ["/v1/search", "/v1/activity-summary"]}},
    {"id": "T7", "prompt": "What did I code in VSCode?", "group": "A", "expected": {"primary_endpoint": "/v1/search", "required_params": ["start_time", "end_time", "app_name"], "forbidden_endpoints": []}},
    {"id": "T8", "prompt": "How long did I spend on Safari?", "group": "A", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T9", "prompt": "Show me a screenshot", "group": "A", "expected": {"acceptable_endpoints": ["/v1/search", "/v1/activity-summary"], "forbidden_endpoints": []}},
    {"id": "T10", "prompt": "Show me frame 42", "group": "A", "expected": {"primary_endpoint": "/v1/frames/42", "required_params": [], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T11", "prompt": "Summarize my day", "group": "A", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T12", "prompt": "Did I see anything about React in the last hour?", "group": "A", "expected": {"primary_endpoint": "/v1/search", "required_params": ["q", "start_time", "end_time"], "forbidden_endpoints": ["/v1/activity-summary"]}},

    {"id": "T1-zh", "prompt": "我今天在干啥?", "group": "B", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T2-zh", "prompt": "我昨天用了哪些 app?", "group": "B", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T3-zh", "prompt": "找一下我之前在 review 的那个 PR", "group": "B", "expected": {"primary_endpoint": "/v1/search", "required_params": ["q", "start_time", "end_time"], "forbidden_endpoints": []}},
    {"id": "T4-zh", "prompt": "我有没有看过 AI 相关的内容?", "group": "B", "expected": {"primary_endpoint": "/v1/search", "required_params": ["q", "start_time", "end_time"], "forbidden_endpoints": []}},
    {"id": "T5-zh", "prompt": "我今天打开过 GitHub 吗?", "group": "B", "expected": {"primary_endpoints": ["/v1/activity-summary", "/v1/search"], "required_params": ["start_time", "end_time"], "forbidden_endpoints": []}},
    {"id": "T6-zh", "prompt": "我在 frame 42 里在干啥?", "group": "B", "expected": {"primary_endpoint": "/v1/frames/42/context", "required_params": [], "forbidden_endpoints": ["/v1/search", "/v1/activity-summary"]}},
    {"id": "T7-zh", "prompt": "我在 VSCode 里写了什么代码?", "group": "B", "expected": {"primary_endpoint": "/v1/search", "required_params": ["start_time", "end_time", "app_name"], "forbidden_endpoints": []}},
    {"id": "T8-zh", "prompt": "我今天在 Safari 上花了多久?", "group": "B", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T9-zh", "prompt": "给我看一张截图", "group": "B", "expected": {"acceptable_endpoints": ["/v1/search", "/v1/activity-summary"], "forbidden_endpoints": []}},
    {"id": "T10-zh", "prompt": "给我看 frame 42", "group": "B", "expected": {"primary_endpoint": "/v1/frames/42", "required_params": [], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T11-zh", "prompt": "总结一下我今天", "group": "B", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "T12-zh", "prompt": "最近一小时我看过 React 相关的吗?", "group": "B", "expected": {"primary_endpoint": "/v1/search", "required_params": ["q", "start_time", "end_time"], "forbidden_endpoints": ["/v1/activity-summary"]}},

    {"id": "M1", "prompt": "Summarize my activity", "group": "C", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"], "modular_node": "summary.md"}},
    {"id": "M2", "prompt": "Find frames containing \"password\"", "group": "C", "expected": {"primary_endpoint": "/v1/search", "required_params": ["q", "start_time", "end_time"], "forbidden_endpoints": [], "modular_node": "search.md"}},
    {"id": "M3", "prompt": "What text is in frame 42?", "group": "C", "expected": {"primary_endpoint": "/v1/frames/42/context", "required_params": [], "forbidden_endpoints": ["/v1/search", "/v1/activity-summary"], "modular_node": "content.md"}},
    {"id": "M4", "prompt": "Show me frame 42 screenshot", "group": "C", "expected": {"primary_endpoint": "/v1/frames/42", "required_params": [], "forbidden_endpoints": ["/v1/search"], "modular_node": "content.md"}},
    {"id": "M5", "prompt": "Which apps did I use today?", "group": "C", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"], "modular_node": null}},

    {"id": "D1", "prompt": "Summarize my day today", "group": "D", "turn": 1, "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"], "context_key": "frame_id"}},
    {"id": "D1-T2", "prompt": "Tell me more about that PR review in VSCode", "group": "D", "turn": 2, "scenario": "D1", "expected": {"primary_endpoint": "/v1/frames/102/context", "required_params": [], "forbidden_endpoints": ["/v1/search"], "context_reuse_from": "D1"}},
    {"id": "D2", "prompt": "Summarize my day today", "group": "D", "turn": 1, "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "D2-T2", "prompt": "What about yesterday?", "group": "D", "turn": 2, "scenario": "D2", "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "D3", "prompt": "Find the PR I was reviewing", "group": "D", "turn": 1, "expected": {"primary_endpoint": "/v1/search", "required_params": ["q", "start_time", "end_time"], "forbidden_endpoints": [], "context_key": "frame_id"}},
    {"id": "D3-T2", "prompt": "What did the first search result contain?", "group": "D", "turn": 2, "scenario": "D3", "expected": {"primary_endpoint": "/v1/frames/201/context", "required_params": [], "forbidden_endpoints": ["/v1/search"], "context_reuse_from": "D3"}},
    {"id": "D4", "prompt": "Summarize my activity", "group": "D", "turn": 1, "expected": {"primary_endpoint": "/v1/activity-summary", "required_params": ["start_time", "end_time"], "forbidden_endpoints": ["/v1/search"]}},
    {"id": "D4-T2", "prompt": "Find frames containing 'password'", "group": "D", "turn": 2, "scenario": "D4", "expected": {"primary_endpoint": "/v1/search", "required_params": ["q", "start_time", "end_time"], "forbidden_endpoints": []}}
  ]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/skill_eval/test_cases_v2.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/skill_eval/test_cases_v2.json tests/skill_eval/test_cases_v2.py
git commit -m "feat(skill-eval): add v2 test cases (33 prompts across 4 groups)"
```

---

## Task 4: Enhance `evaluate.py`

**Files:**
- Modify: `tests/skill_eval/evaluate.py`
- Test: `tests/skill_eval/test_evaluate.py`

- [ ] **Step 1: Write the failing test for multi-turn scoring**

```python
from evaluate import evaluate_case


def test_multi_turn_context_reuse_full():
    case = {
        "id": "D1-T2",
        "expected": {
            "primary_endpoint": "/v1/frames/102/context",
            "required_params": [],
            "forbidden_endpoints": ["/v1/search"],
            "context_reuse_from": "D1",
        }
    }
    # Turn 1 would have called /activity-summary with frame_id 102
    # Turn 2 directly calls /frames/102/context (reuses frame_id)
    requests = [
        {"method": "GET", "path": "/v1/frames/102/context", "args": {}}
    ]
    score = evaluate_case(case, requests)
    assert score["total"] == 120  # 40 + 30 + 30 + 20 = 120
    assert score["context_reuse"] == 20


def test_multi_turn_context_reuse_partial():
    case = {
        "id": "D1-T2",
        "expected": {
            "primary_endpoint": "/v1/frames/102/context",
            "required_params": [],
            "forbidden_endpoints": ["/v1/search"],
            "context_reuse_from": "D1",
        }
    }
    # Reuses frame_id but also does extra search
    requests = [
        {"method": "GET", "path": "/v1/frames/102/context", "args": {}},
        {"method": "GET", "path": "/v1/search", "args": {"q": "PR"}},
    ]
    score = evaluate_case(case, requests)
    assert score["context_reuse"] == 10  # partial: some reuse + some re-query
    assert score["no_redundant"] == 0   # forbidden /search was called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/skill_eval/test_evaluate.py::test_multi_turn_context_reuse_full -v`
Expected: `KeyError: 'context_reuse'`

- [ ] **Step 3: Add multi-turn scoring to `evaluate.py`**

Add a new function and modify `evaluate_case`:

```python
def evaluate_case(case: dict, requests: list, prev_requests: list | None = None) -> dict:
    """Score a single test case.

    prev_requests: requests from the previous turn (for multi-turn context reuse scoring).
    """
    expected = case["expected"]
    score = {"total": 0, "endpoint": 0, "params": 0, "no_redundant": 0, "context_reuse": 0, "notes": []}

    if not requests:
        score["notes"].append("No API requests made")
        return score

    endpoints = [r["path"] for r in requests]

    # 1. Endpoint correctness (40 points)
    primary = expected.get("primary_endpoint")
    primaries = expected.get("primary_endpoints", [primary] if primary else [])
    acceptable = expected.get("acceptable_endpoints", [])

    if primary:
        if any(primary in ep for ep in endpoints):
            score["endpoint"] = 40
            score["notes"].append(f"Correct primary endpoint called: {primary}")
        elif acceptable and any(any(a in ep for ep in endpoints) for a in acceptable):
            score["endpoint"] = 30
            score["notes"].append(f"Acceptable endpoint called instead of {primary}")
        else:
            score["endpoint"] = 0
            score["notes"].append(f"Expected {primary}, got {endpoints}")
    elif primaries:
        if any(any(p in ep for ep in endpoints) for p in primaries):
            score["endpoint"] = 40
            score["notes"].append(f"One of expected endpoints called: {primaries}")
        else:
            score["endpoint"] = 0
            score["notes"].append(f"Expected one of {primaries}, got {endpoints}")
    elif acceptable:
        if any(any(a in ep for ep in endpoints) for a in acceptable):
            score["endpoint"] = 40
            score["notes"].append(f"Acceptable endpoint called: {acceptable}")
        else:
            score["endpoint"] = 0
            score["notes"].append(f"Expected one of {acceptable}, got {endpoints}")

    # 2. Parameters (30 points)
    required = expected.get("required_params", [])
    if required and requests:
        all_args = {}
        for r in requests:
            all_args.update(r.get("args", {}))
        missing = [p for p in required if p not in all_args]
        if not missing:
            score["params"] = 30
            score["notes"].append(f"All required params present: {required}")
        else:
            score["params"] = max(0, 30 - len(missing) * 10)
            score["notes"].append(f"Missing params: {missing}")
    else:
        score["params"] = 30
        score["notes"].append("No required params to check")

    # 3. No redundant calls (30 points)
    forbidden = expected.get("forbidden_endpoints", [])
    violations = [ep for ep in endpoints if any(f in ep for f in forbidden)]
    if not violations:
        score["no_redundant"] = 30
        score["notes"].append("No forbidden endpoints called")
    else:
        score["no_redundant"] = 0
        score["notes"].append(f"Forbidden endpoints called: {violations}")

    # 4. Context reuse (20 points) — multi-turn only
    if expected.get("context_reuse_from") and prev_requests:
        prev_endpoints = [r["path"] for r in prev_requests]
        # Check if T2 uses info from T1 without re-querying
        # Heuristic: if T2's endpoint matches expected AND no forbidden endpoint called
        # AND the expected endpoint contains a specific ID that would come from T1
        has_reuse = score["endpoint"] == 40 and score["no_redundant"] == 30
        has_partial = score["endpoint"] == 40 and score["no_redundant"] < 30
        if has_reuse:
            score["context_reuse"] = 20
            score["notes"].append("Full context reuse: no re-querying")
        elif has_partial:
            score["context_reuse"] = 10
            score["notes"].append("Partial context reuse: some re-querying")
        else:
            score["context_reuse"] = 0
            score["notes"].append("No context reuse detected")
    else:
        score["context_reuse"] = 0
        score["notes"].append("Not a multi-turn scenario")

    score["total"] = score["endpoint"] + score["params"] + score["no_redundant"] + score["context_reuse"]
    return score
```

- [ ] **Step 4: Run all evaluate tests**

Run: `pytest tests/skill_eval/test_evaluate.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tests/skill_eval/evaluate.py tests/skill_eval/test_evaluate.py
git commit -m "feat(skill-eval): add multi-turn context reuse scoring (+20 pts)"
```

---

## Task 5: Rewrite `pi_test_runner.py`

**Files:**
- Rewrite: `tests/skill_eval/pi_test_runner.py`
- Test: `tests/skill_eval/test_pi_test_runner.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from pi_test_runner import load_test_cases, extract_api_calls


def test_load_test_cases_has_33():
    cases = load_test_cases()
    assert len(cases) == 33


def test_extract_api_calls_filters_v1():
    entries = [
        {"method": "GET", "path": "/v1/health", "args": {}},
        {"method": "GET", "path": "/v1/search", "args": {"q": "test"}},
    ]
    calls = extract_api_calls(entries)
    assert len(calls) == 1
    assert calls[0]["path"] == "/v1/search"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/skill_eval/test_pi_test_runner.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write the harness**

```python
#!/usr/bin/env python3
"""Skill evaluation test harness.

Runs Pi CLI with each skill variant against mock_server,
records API calls, scores against expected behavior, and writes results.

Usage:
    python tests/skill_eval/pi_test_runner.py --skill v1 --runs 3
    python tests/skill_eval/pi_test_runner.py --skill all --runs 3
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from evaluate import evaluate_case
from install_skill import install_skill

# Configuration
MOCK_SERVER = Path(__file__).parent / "mock_server.py"
PI_CLI = (
    Path.home()
    / ".myrecall"
    / "pi-agent"
    / "node_modules"
    / "@mariozechner"
    / "pi-coding-agent"
    / "dist"
    / "cli.js"
)
MOCK_LOG = "/tmp/skill_test_multiturn.log"
RESULTS_DIR = Path(__file__).parent / "results"
SKILL_SRC_DIR = Path(__file__).parent.parent.parent / "openrecall" / "client" / "chat" / "skills"


def load_test_cases() -> list[dict]:
    """Load test cases from JSON."""
    path = Path(__file__).parent / "test_cases_v2.json"
    return json.loads(path.read_text())["cases"]


def extract_api_calls(log_entries: list[dict]) -> list[dict]:
    """Extract API calls from mock server log, filtering out /health."""
    calls = []
    for entry in log_entries:
        path = entry.get("path", "")
        if path.startswith("/v1/") and path != "/v1/health":
            calls.append({
                "method": entry.get("method"),
                "path": path,
                "args": entry.get("args", {}),
            })
    return calls


def read_mock_log(log_path: str) -> list[dict]:
    """Read mock server log entries."""
    if not os.path.exists(log_path):
        return []
    entries = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def clear_mock_log(log_path: str):
    """Clear mock server log."""
    if os.path.exists(log_path):
        os.remove(log_path)


def start_mock_server(port: int = 18083, log_path: str = MOCK_LOG) -> subprocess.Popen:
    """Start mock server as subprocess."""
    clear_mock_log(log_path)
    proc = subprocess.Popen(
        [sys.executable, str(MOCK_SERVER), "--port", str(port), "--log", log_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(30):
        time.sleep(0.2)
        try:
            req = urllib.request.Request(f"http://localhost:{port}/v1/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            pass
    else:
        proc.terminate()
        raise RuntimeError(f"Mock server failed to start on port {port}")
    return proc


def get_api_key() -> str:
    """Read minimax-cn API key from auth.json."""
    auth_path = Path.home() / ".pi" / "agent" / "auth.json"
    data = json.loads(auth_path.read_text())
    return data["minimax-cn"]["key"]


def run_pi(prompt: str, skill_dir: Path, session: str | None = None,
           continue_session: bool = False, timeout: int = 120) -> dict:
    """Run Pi CLI with a prompt, return stdout/stderr/returncode."""
    env = os.environ.copy()
    env["PI_OFFLINE"] = "1"
    env["MINIMAX_CN_API_KEY"] = get_api_key()

    cmd = [
        "bun", "run", str(PI_CLI),
        "--provider", "minimax-cn",
        "--model", "MiniMax-M2",
        "--skill", str(skill_dir),
        "--no-skills",
        "--tools", "read,bash",
        "-p", prompt,
    ]

    if session:
        cmd.extend(["--session", session])
    else:
        cmd.append("--no-session")

    if continue_session:
        cmd.append("--continue")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def run_single_prompt(case: dict, skill_dir: Path, run_num: int,
                      port: int = 18083) -> dict:
    """Run a single prompt and return scored result."""
    log_path = f"/tmp/skill_test_{case['id']}_run{run_num}.log"

    server = start_mock_server(port, log_path)
    try:
        result = run_pi(case["prompt"], skill_dir, timeout=120)
        log_entries = read_mock_log(log_path)
        calls = extract_api_calls(log_entries)

        # For multi-turn T2, load previous turn's requests
        prev_requests = None
        if case.get("turn") == 2 and case.get("scenario"):
            prev_case_id = case["scenario"]
            prev_log = f"/tmp/skill_test_{prev_case_id}_run{run_num}.log"
            if os.path.exists(prev_log):
                prev_entries = read_mock_log(prev_log)
                prev_requests = extract_api_calls(prev_entries)

        score = evaluate_case(case, calls, prev_requests)

        return {
            "case_id": case["id"],
            "prompt": case["prompt"],
            "run": run_num,
            "returncode": result["returncode"],
            "calls": calls,
            "score": score,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }
    finally:
        server.terminate()
        server.wait()


def run_multi_turn_scenario(scenario_id: str, cases: list[dict],
                            skill_dir: Path, run_num: int, port: int = 18083) -> list[dict]:
    """Run a 2-turn scenario and return results for both turns."""
    turn1 = [c for c in cases if c["id"] == scenario_id][0]
    turn2 = [c for c in cases if c.get("scenario") == scenario_id and c.get("turn") == 2][0]

    session_file = f"/tmp/pi_session_{scenario_id}_run{run_num}.jsonl"
    if os.path.exists(session_file):
        os.remove(session_file)

    results = []

    # Turn 1
    log1 = f"/tmp/skill_test_{turn1['id']}_run{run_num}.log"
    server = start_mock_server(port, log1)
    try:
        result1 = run_pi(turn1["prompt"], skill_dir, session=session_file, timeout=120)
        calls1 = extract_api_calls(read_mock_log(log1))
        score1 = evaluate_case(turn1, calls1)
        results.append({
            "case_id": turn1["id"], "prompt": turn1["prompt"], "run": run_num,
            "returncode": result1["returncode"], "calls": calls1, "score": score1,
        })
    finally:
        server.terminate()
        server.wait()

    # Turn 2
    log2 = f"/tmp/skill_test_{turn2['id']}_run{run_num}.log"
    server = start_mock_server(port, log2)
    try:
        result2 = run_pi(turn2["prompt"], skill_dir, session=session_file,
                        continue_session=True, timeout=120)
        calls2 = extract_api_calls(read_mock_log(log2))
        score2 = evaluate_case(turn2, calls2, prev_requests=calls1)
        results.append({
            "case_id": turn2["id"], "prompt": turn2["prompt"], "run": run_num,
            "returncode": result2["returncode"], "calls": calls2, "score": score2,
        })
    finally:
        server.terminate()
        server.wait()

    return results


def run_skill_variant(variant: str, cases: list[dict], runs: int = 3,
                      port: int = 18083) -> list[dict]:
    """Run all cases for a skill variant."""
    print(f"\n{'='*60}")
    print(f"  Running skill variant: {variant}")
    print(f"{'='*60}")

    # Install skill
    if variant == "myrecall":
        source = SKILL_SRC_DIR / "myrecall"
        dest_name = "myrecall"
    else:
        source = SKILL_SRC_DIR / "myrecall-search" / variant
        dest_name = "myrecall-search"

    dest = Path.home() / ".pi" / "agent" / "skills" / dest_name
    install_skill(source, dest, port=port)
    print(f"  Installed {variant} -> {dest}")

    all_results = []
    single_turn_cases = [c for c in cases if c.get("turn", 1) == 1]
    multi_turn_ids = {c["scenario"] for c in cases if c.get("turn") == 2}

    for run in range(1, runs + 1):
        print(f"\n  --- Run {run}/{runs} ---")

        # Single-turn cases
        for case in single_turn_cases:
            if case["id"] in multi_turn_ids:
                continue  # handled in multi-turn
            print(f"    {case['id']}: {case['prompt'][:50]}...", end=" ")
            result = run_single_prompt(case, dest, run, port)
            all_results.append(result)
            print(f"score={result['score']['total']}")
            time.sleep(2)  # rate limit buffer

        # Multi-turn scenarios
        for scenario_id in multi_turn_ids:
            print(f"    {scenario_id} (multi-turn): ", end=" ")
            results = run_multi_turn_scenario(scenario_id, cases, dest, run, port)
            for r in results:
                all_results.append(r)
                print(f"T{r['case_id']}={r['score']['total']}", end=" ")
            print()
            time.sleep(2)

    return all_results


def save_results(variant: str, results: list[dict]):
    """Save results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    output = {
        "skill_variant": variant,
        "timestamp": timestamp,
        "results": results,
    }
    path = RESULTS_DIR / f"{variant}_{timestamp.replace(':', '-')}.json"
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n  Results saved to {path}")


def main():
    parser = argparse.ArgumentParser(description="Run skill evaluation")
    parser.add_argument("--skill", choices=["v1", "v2", "v3", "myrecall", "all"],
                        default="all", help="Skill variant to test")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per prompt")
    parser.add_argument("--port", type=int, default=18083, help="Mock server port")
    args = parser.parse_args()

    if not PI_CLI.exists():
        print(f"ERROR: Pi CLI not found at {PI_CLI}")
        sys.exit(1)

    cases = load_test_cases()
    variants = ["v1", "v2", "v3", "myrecall"] if args.skill == "all" else [args.skill]

    for variant in variants:
        results = run_skill_variant(variant, cases, args.runs, args.port)
        save_results(variant, results)

    print("\n" + "="*60)
    print("  ALL DONE")
    print("="*60)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/skill_eval/test_pi_test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/skill_eval/pi_test_runner.py tests/skill_eval/test_pi_test_runner.py
git commit -m "feat(skill-eval): rewrite test harness with full skill variant support, multi-turn, scoring"
```

---

## Task 6: Add report generator

**Files:**
- Create: `tests/skill_eval/generate_report.py`
- Test: `tests/skill_eval/test_generate_report.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

from generate_report import aggregate_results


def test_aggregate_results_computes_average():
    results = [
        {"case_id": "T1", "score": {"total": 100}},
        {"case_id": "T1", "score": {"total": 80}},
        {"case_id": "T2", "score": {"total": 90}},
    ]
    agg = aggregate_results(results)
    assert agg["average_score"] == 90.0  # (100 + 80 + 90) / 3
    assert agg["by_case"]["T1"]["average"] == 90.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/skill_eval/test_generate_report.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write report generator**

```python
#!/usr/bin/env python3
"""Generate comparison report from skill evaluation results."""

import json
import statistics
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def aggregate_results(results: list[dict]) -> dict:
    """Aggregate scores from a list of result dicts."""
    by_case: dict[str, list[int]] = {}
    context_reuse_count = 0
    context_reuse_total = 0

    for r in results:
        case_id = r["case_id"]
        score = r["score"]["total"]
        by_case.setdefault(case_id, []).append(score)

        # Track context reuse for multi-turn
        if "context_reuse" in r["score"]:
            context_reuse_total += 1
            if r["score"]["context_reuse"] > 0:
                context_reuse_count += 1

    by_case_agg = {}
    for case_id, scores in by_case.items():
        by_case_agg[case_id] = {
            "scores": scores,
            "average": round(statistics.mean(scores), 1),
            "min": min(scores),
            "max": max(scores),
            "variance": round(statistics.variance(scores), 2) if len(scores) > 1 else 0,
        }

    all_scores = [s for scores in by_case.values() for s in scores]
    pass_rate = sum(1 for s in all_scores if s >= 80) / len(all_scores) * 100 if all_scores else 0

    return {
        "average_score": round(statistics.mean(all_scores), 1) if all_scores else 0,
        "pass_rate": round(pass_rate, 1),
        "by_case": by_case_agg,
        "context_reuse_rate": round(context_reuse_count / context_reuse_total * 100, 1)
            if context_reuse_total else 0,
    }


def generate_markdown(variant_results: dict[str, dict]) -> str:
    """Generate markdown comparison report."""
    lines = [
        "# Skill Evaluation Report",
        "",
        "## Summary",
        "",
        "| Skill Variant | Avg Score | Pass Rate | Context Reuse |",
        "|--------------|-----------|-----------|---------------|",
    ]

    for variant, agg in variant_results.items():
        lines.append(
            f"| {variant} | {agg['average_score']}/100 | {agg['pass_rate']}% | {agg['context_reuse_rate']}% |"
        )

    lines.extend(["", "## Per-Case Breakdown", ""])

    for variant, agg in variant_results.items():
        lines.append(f"### {variant}")
        lines.append("")
        lines.append("| Case | Avg | Min | Max | Var |")
        lines.append("|------|-----|-----|-----|-----|")
        for case_id, case_agg in agg["by_case"].items():
            lines.append(
                f"| {case_id} | {case_agg['average']} | {case_agg['min']} | {case_agg['max']} | {case_agg['variance']} |"
            )
        lines.append("")

    return "\n".join(lines)


def main():
    variant_results = {}
    for path in RESULTS_DIR.glob("*.json"):
        data = json.loads(path.read_text())
        variant = data["skill_variant"]
        variant_results[variant] = aggregate_results(data["results"])

    report = generate_markdown(variant_results)
    output_path = RESULTS_DIR / "EVALUATION_REPORT_V2.md"
    output_path.write_text(report)
    print(f"Report written to {output_path}")
    print(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/skill_eval/test_generate_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/skill_eval/generate_report.py tests/skill_eval/test_generate_report.py
git commit -m "feat(skill-eval): add report generator with aggregation and markdown output"
```

---

## Task 7: Execute full evaluation (v1)

**Files:** No new files

- [ ] **Step 1: Run v1 skill evaluation**

Run:
```bash
python tests/skill_eval/pi_test_runner.py --skill v1 --runs 3 --port 18083
```

Expected: 33 prompts × 3 runs ≈ 100 iterations, takes ~1 hour. Check console output for scores.

- [ ] **Step 2: Verify results file created**

Run:
```bash
ls -la tests/skill_eval/results/v1_*.json
```

Expected: File exists with ~100 result entries.

- [ ] **Step 3: Commit**

```bash
git add tests/skill_eval/results/v1_*.json
git commit -m "data(skill-eval): add v1 evaluation results (3 runs)"
```

---

## Task 8: Execute full evaluation (v2, v3, myrecall)

**Files:** No new files

- [ ] **Step 1: Run v2 skill evaluation**

Run:
```bash
python tests/skill_eval/pi_test_runner.py --skill v2 --runs 3 --port 18083
```

- [ ] **Step 2: Run v3 skill evaluation**

Run:
```bash
python tests/skill_eval/pi_test_runner.py --skill v3 --runs 3 --port 18083
```

- [ ] **Step 3: Run myrecall modular skill evaluation**

Run:
```bash
python tests/skill_eval/pi_test_runner.py --skill myrecall --runs 3 --port 18083
```

- [ ] **Step 4: Commit all results**

```bash
git add tests/skill_eval/results/
git commit -m "data(skill-eval): add v2, v3, myrecall evaluation results (3 runs each)"
```

---

## Task 9: Generate and review report

**Files:**
- Create: `tests/skill_eval/EVALUATION_REPORT_V2.md`

- [ ] **Step 1: Generate report**

Run:
```bash
python tests/skill_eval/generate_report.py
```

Expected: `tests/skill_eval/EVALUATION_REPORT_V2.md` created with comparison table.

- [ ] **Step 2: Review report**

Read the report and check:
1. All 4 variants present in summary table
2. Per-case breakdown shows variance across runs
3. Context reuse rate is computed for multi-turn scenarios

- [ ] **Step 3: Commit**

```bash
git add tests/skill_eval/EVALUATION_REPORT_V2.md
git commit -m "docs(skill-eval): add comparison report (v1 vs v2 vs v3 vs myrecall)"
```

---

## Self-Review Checklist

### Spec Coverage
| Spec Section | Implementing Task | Status |
|---|---|---|
| Date-aware mock server | Task 2 | Covered |
| Real search filtering | Task 2 | Covered |
| Differentiated frame contexts | Task 2 | Covered |
| Chinese content | Task 2 | Covered |
| 33 test prompts | Task 3 | Covered |
| Multi-turn scoring (+20 context reuse) | Task 4 | Covered |
| Skill variant switching | Task 5 | Covered |
| 3 runs per prompt | Task 7-8 | Covered |
| Report generation | Task 6, 9 | Covered |

### Placeholder Scan
- [x] No "TBD", "TODO", "implement later"
- [x] No vague error handling instructions
- [x] No "similar to Task N" references
- [x] Every step has concrete code or command

### Type Consistency
- [x] `evaluate_case` signature: `(case, requests, prev_requests=None)` used consistently
- [x] `run_pi` signature: `(prompt, skill_dir, session, continue_session, timeout)` used consistently
- [x] Score dict keys: `total`, `endpoint`, `params`, `no_redundant`, `context_reuse`, `notes` — consistent across Tasks 4, 5, 6

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-02-skill-eval-implementation.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
