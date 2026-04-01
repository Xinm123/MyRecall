# GET /v1/activity-summary 端点设计优化

> **Date:** 2026-04-01
> **Status:** Draft
> **Owner:** MyRecall Chat Team

## 背景

对 `/v1/activity-summary` 端点进行设计复盘，分析并优化以下四个议题：
1. `recent_texts` 字段的必要性
2. `description` 中各字段的顺序
3. `max_description` 的优化方向
4. app 使用时间的计算方式

参考实现：`_ref/screenpipe/crates/screenpipe-engine/src/routes/activity_summary.rs`

---

## 决策

### 1. 移除 `recent_texts` 字段

**决策：完全移除。**

`recent_texts` 提供的是从 `elements` 表提取的原始屏幕文本，与 `descriptions` 的 AI 生成描述存在信息冗余。对于有视觉理解能力的 AI 模型，`summary` + `intent` + `entities` 已经足够描述用户活动。移除后节省约 200-500 tokens，降低维护复杂度。

### 2. 重新设计 `description` 字段

**决策：按以下顺序返回字段，并新增 `timestamp`。**

```json
{
  "frame_id": 108,
  "timestamp": "2026-03-26T14:32:05Z",
  "summary": "Editing API reference docs",
  "intent": "writing documentation",
  "entities": ["Claude Code", "API", "activity-summary"]
}
```

**设计理由：**
- `frame_id` 靠前：需要跳转 frame context 时立即可查
- `timestamp` 新增：让 AI 重建时间线，与 `time_range` 配合使用
- `summary` + `intent` + `entities`：三字段组合对"了解用户干了什么"已足够精简
- 移除 `narrative`：activity-summary 的目标是轻量概览，详细描述通过 `/v1/frames/{id}/context` 获取

### 3. 重新设计 `max_descriptions` 策略

**决策：不设置默认上限，但允许调用方指定。**

- **移除默认 limit**：不做硬性限制，调用方按需指定 `max_descriptions`
- **简化 description 字段**：每条只返回 `frame_id`, `timestamp`, `summary`, `intent`, `entities`
- **移除 token 目标约束**：不再要求 200-500 tokens，activity-summary 本质是信息聚合，AI 端按需截断

### 4. 改进 app 使用时间计算

**决策：采用 screenpipe 的时间差计算方式。**

```json
{
  "name": "Claude Code",
  "frame_count": 180,
  "minutes": 42.5,
  "first_seen": "2026-03-26T10:05:22Z",
  "last_seen": "2026-03-26T11:32:08Z"
}
```

**设计理由：**
- **基于实际时间戳差**：用 SQLite `LEAD()` 窗口函数计算相邻帧的实际间隔，而非假设固定 2 秒/帧
- **5 分钟阈值**：`gap_sec < 300` 时才计入使用时间，过滤"离开电脑"的时间段
- **新增 first_seen/last_seen**：让 AI 知道精确的时间窗口，而非只知道总时长

**SQL 实现参考（screenpipe）：**
```sql
SELECT app_name,
       COUNT(*) as frame_count,
       ROUND(SUM(CASE WHEN gap_sec < 300 THEN gap_sec ELSE 0 END) / 60.0, 1) as minutes,
       MIN(ts) as first_seen,
       MAX(ts) as last_seen
FROM (
  SELECT app_name, timestamp as ts,
    (JULIANDAY(LEAD(timestamp) OVER (PARTITION BY app_name ORDER BY timestamp))
     - JULIANDAY(timestamp)) * 86400 AS gap_sec
  FROM frames
  WHERE timestamp BETWEEN ? AND ?
    AND app_name IS NOT NULL AND app_name != ''
    AND status = 'completed'
) gaps
GROUP BY app_name
ORDER BY minutes DESC
LIMIT 20
```

**注意：** 原 screenpipe 实现未过滤 `status = 'completed'`，需补上以确保只统计已完成的帧。

```json
{
  "apps": [
    {
      "name": "Claude Code",
      "frame_count": 180,
      "minutes": 42.5,
      "first_seen": "2026-03-26T10:05:22Z",
      "last_seen": "2026-03-26T11:32:08Z"
    }
  ],
  "total_frames": 360,
  "time_range": {
    "start": "2026-03-26T09:00:00Z",
    "end": "2026-03-26T18:00:00Z"
  },
  "audio_summary": {
    "segment_count": 0,
    "speakers": []
  },
  "descriptions": [
    {
      "frame_id": 108,
      "timestamp": "2026-03-26T14:32:05Z",
      "summary": "Editing API reference docs",
      "intent": "writing documentation",
      "entities": ["Claude Code", "API", "activity-summary"]
    }
  ]
}
```

### 变更对照

| 变更 | 旧 | 新 |
|------|----|----|
| `recent_texts` | 保留，限 10 条 | **移除** |
| `apps[].minutes` | `frame_count * 2 / 60` | `SUM(gap_sec < 300) / 60` |
| `apps[].first_seen` | 无 | **新增** |
| `apps[].last_seen` | 无 | **新增** |
| `apps` 排序 | `ORDER BY frame_count DESC` | `ORDER BY minutes DESC` |
| `descriptions[].frame_id` | 在首 | 保持在前 |
| `descriptions[].timestamp` | 无 | **新增** |
| `descriptions[].summary` | 在末 | 移至第三位 |
| `descriptions[].intent` | 在第四 | 移至第四位 |
| `descriptions[].entities` | 在第二 | 移至第五位 |
| `descriptions[].narrative` | 在第二 | **移除** |
| `descriptions[].time_offset_seconds` | 无 | **不添加** |
| `max_descriptions` 默认值 | 20 | 移除默认值（无上限） |

---

## 需要更新的文档

1. `docs/v3/chat/api-fields-reference.md` — 更新 GET /v1/activity-summary 的完整 schema 和示例
2. `docs/v3/chat/mvp.md` — 同步更新 activity-summary 描述
3. `openrecall/client/chat/skills/myrecall-search/SKILL.md` — 移除 `recent_texts` 相关说明，更新 token 估算
4. `openrecall/server/api_v1.py` — 更新 `activity_summary()` 端点的实现

---

## 实现任务

1. 修改 `FramesStore.get_activity_summary_apps()` — 改用时间差 + 阈值查询，新增 first_seen/last_seen
2. 修改 `FramesStore.get_activity_summary_recent_texts()` — **删除整个方法**（不再使用）
3. 修改 `FramesStore.get_recent_descriptions()` — 更新字段列表，新增 timestamp，移除 narrative
4. 修改 `api_v1.py` 中的 `activity_summary()` — 移除 recent_texts 返回
5. 更新相关测试文件
6. 更新 API 文档和 SKILL.md
