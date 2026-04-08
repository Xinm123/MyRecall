# Description Fields Redesign

**Date:** 2026-04-08
**Author:** Claude
**Status:** ✅ Implemented

## Overview

重构 FrameDescription 数据结构，将原来的 4 个字段（narrative, entities, intent, summary）精简为 3 个字段（narrative, summary, tags）。

目标是让 AI agent 在不同对话场景下可以使用不同粒度的描述：
- **Tags** — 快速判断帧的活动类型（3-8 个关键词）
- **Summary** — 一句话概括关键活动（快读场景）
- **Narrative** — 详细的自然语言描述（深入分析场景）

## 字段对比

### 旧结构（4 字段）

```python
class FrameDescription(BaseModel):
    narrative: str       # max 512 chars
    entities: List[str]  # max 10 items
    intent: str          # 意图短语，如 "authenticating to GitHub"
    summary: str         # max 200 chars
```

### 新结构（3 字段）

```python
class FrameDescription(BaseModel):
    narrative: str       # max 1024 chars
    summary: str         # max 256 chars
    tags: List[str]      # 3-8 lowercase keywords
```

| 字段 | 变化 | 原因 |
|------|------|------|
| narrative | 512 → 1024 | 提供更详细的描述供深度分析 |
| entities | 删除 | 由 tags 替代，更灵活 |
| intent | 删除 | 由 tags 替代，分解为关键词 |
| summary | 200 → 256 | 适应更复杂的总结 |
| tags | 新增 | 快速关键词匹配，分类活动 |

## Prompt 设计

```
Analyze this screenshot and output a strictly valid JSON object.

App context: {ctx_str}

Output format:
{
  "narrative": "detailed natural language description of what is on screen in detail and what the user is doing. (max 1024 characters)",
  "summary": "one sentence capturing the key activity. (max 256 characters)",
  "tags": ["keyword1", "keyword2", ...]  // 3-8 lowercase keywords
}

Example output:
{
  "narrative": "用户正在 GitHub 仓库页面，头部导航栏显示仓库名称和所有者信息。左侧边栏包含文件列表，主内容区显示 README.md 的 Markdown 渲染内容，包含项目描述、安装步骤和使用说明。光标停留在代码文件列表上。",
  "summary": "用户在浏览 GitHub 仓库的 README 文档",
  "tags": ["github", "repository", "readme", "browsing", "documentation"]
}

IMPORTANT: Output only valid JSON. No markdown, no explanation.
```

### Prompt 设计要点

1. **Few-shot 示例** — 提供实际输出样例，降低 JSON 解析失败率
2. **语言跟随** — 模型根据界面主语言选择输出语言
3. **Tags 固定小写** — 无论中英文都输出小写，便于统一检索
4. **严格格式约束** — `IMPORTANT` 提醒减少 markdown 包裹

## 数据库 Schema 变更

### frame_descriptions 表

```sql
-- 旧字段删除
ALTER TABLE frame_descriptions DROP COLUMN entities_json;
ALTER TABLE frame_descriptions DROP COLUMN intent;

-- 字段调整（通过数据迁移完成）
-- narrative: TEXT NOT NULL (原数据保留，扩展长度限制)
-- summary: TEXT NOT NULL (原数据保留，扩展长度限制)

-- 新字段
ALTER TABLE frame_descriptions ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]';
```

### 新表结构

```sql
CREATE TABLE frame_descriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    narrative TEXT NOT NULL,        -- max 1024 chars
    summary TEXT NOT NULL,          -- max 256 chars
    tags_json TEXT NOT NULL,        -- JSON array of strings
    description_model TEXT,         -- 'qwen3-vl', 'gpt-4o', etc.
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(frame_id)
);
```

## Provider 更新

三个 provider 需要统一更新：

| Provider | 文件 |
|----------|------|
| OpenAI | `openrecall/server/description/providers/openai.py` |
| DashScope | `openrecall/server/description/providers/dashscope.py` |
| Local (Qwen3 VL) | `openrecall/server/description/providers/local.py` |

更新内容：
1. 替换 prompt 模板
2. 解析 JSON 时读取 `tags` 字段（而非 `entities` + `intent`）
3. 构建 `FrameDescription` 对象时使用新字段

## API 变更

### GET /v1/frames/<frame_id>/context

**Response 变化：**

```json
// 旧
{
  "description": {
    "narrative": "...",
    "entities": ["..."],
    "intent": "...",
    "summary": "..."
  }
}

// 新
{
  "description": {
    "narrative": "...",
    "summary": "...",
    "tags": ["...", "..."]
  }
}
```

### GET /v1/activity-summary

**Response 变化：**

```json
// 旧
descriptions: [{"frame_id": 123, "summary": "...", "intent": "..."}]

// 新
descriptions: [{"frame_id": 123, "summary": "...", "tags": ["..."]}]
```

## WebUI 变更

文件：`openrecall/client/web/templates/index.html`

需要更新 Description Tab 的展示逻辑：

### 当前代码（需要修改）

```html
<!-- Intent Section -->
<div class="metadata-section" x-show="selectedEntry?.description?.intent">
  <h3>Intent</h3>
  <div class="metadata-value" style="font-style: italic;" x-text="selectedEntry.description.intent"></div>
</div>

<!-- Entities Section -->
<div class="metadata-section" x-show="selectedEntry?.description?.entities?.length">
  <h3>Entities</h3>
  <div style="display: flex; flex-wrap: wrap; gap: 8px;">
    <template x-for="entity in selectedEntry.description.entities" :key="entity">
      <span style="..." x-text="entity"></span>
    </template>
  </div>
</div>
```

### 新代码

```html
<!-- Tags Section -->
<div class="metadata-section" x-show="selectedEntry?.description?.tags?.length">
  <h3>Tags</h3>
  <div style="display: flex; flex-wrap: wrap; gap: 8px;">
    <template x-for="tag in selectedEntry.description.tags" :key="tag">
      <span style="
        display: inline-flex;
        align-items: center;
        padding: 4px 12px;
        background: rgba(0, 122, 255, 0.12);
        color: #007AFF;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
      " x-text="tag"></span>
    </template>
  </div>
</div>
```

**变更点：**
- 删除 Intent Section
- 删除 Entities Section
- 添加 Tags Section（复用 Entities 的样式）

## 实施步骤

1. **更新 FrameDescription model** — `openrecall/server/description/models.py`
2. **更新三个 provider** — 统一 prompt 和解析逻辑
3. **数据库迁移** — 删除/重命名字段，添加 tags_json
4. **更新 FramesStore** — 插入/查询逻辑调整
5. **更新 API** — response 结构调整
6. **更新 WebUI** — `index.html` 替换 entities/intent 为 tags
7. **更新 tests** — 测试用例适配新结构

## 兼容性

这是一个 **breaking change**：
- 旧数据：`entities_json` 和 `intent` 字段将被丢弃
- API response 结构变化，前端需要适配
- 建议在低峰期执行，配合版本升级

## 非目标

- 不保留 `entities` 字段作为兼容字段
- 不迁移旧数据的 entities/intent 到新结构
- 不添加 fallback 机制（直接替换）

---

## 实施总结

**实施日期：** 2026-04-08
**实施状态：** ✅ 已完成

### 变更文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `openrecall/server/description/models.py` | 修改 | FrameDescription 模型更新 |
| `openrecall/server/description/providers/openai.py` | 修改 | Prompt 和解析逻辑更新 |
| `openrecall/server/description/providers/local.py` | 修改 | Prompt 和解析逻辑更新 |
| `openrecall/server/description/providers/dashscope.py` | 修改 | Prompt 和解析逻辑更新 |
| `openrecall/server/description/providers/base.py` | 修改 | Docstring 更新 |
| `openrecall/server/description/service.py` | 修改 | 使用新 to_db_dict() 字段 |
| `openrecall/server/database/frames_store.py` | 修改 | CRUD 更新为 tags_json |
| `openrecall/server/api_v1.py` | 修改 | API response 结构调整 |
| `openrecall/client/web/templates/index.html` | 修改 | WebUI 显示 Tags |
| `openrecall/server/database/migrations/20260408120000_description_fields_redesign.sql` | 新增 | 数据库迁移 |
| `tests/test_description_*.py` | 修改 | 测试更新 |

### 测试结果

```
46 passed, 12 warnings in 3.56s
```

### 运行时验证

API 返回示例：
```json
{
  "frame_id": 19,
  "summary": "Developer editing a PyTorch model file...",
  "tags": ["python", "pytorch", "machine-learning", "code-editor", "terminal", "macos"]
}
```

### Breaking Changes 确认

- ✅ API response 不再包含 `entities` 和 `intent`
- ✅ 数据库表结构已迁移到 `tags_json`
- ✅ WebUI 显示 Tags 而非 Intent/Entities
