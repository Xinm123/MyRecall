# Frame Importance 设计规范

> 创建日期: 2026-04-14
> 状态: Draft

## 概述

为 frame 增加 `importance` 字段，通过 chat 评分机制影响搜索排序。用户对 assistant 回复评分后，相关 frame 的 importance 会调整，进而影响未来搜索结果的重排。

## 核心设计决策

| 决策项 | 选择 | 说明 |
|--------|------|------|
| 影响范围 | 按 rank 递减 | weight = 1/rank |
| 计算方式 | 累加式 | importance += rating_value × (1/rank) |
| 评分存储 | 仅存累计值 | frames.importance 列 |
| UI 样式 | 数字选择器 | [1] [2] [3] [4] [5] |
| 评分限制 | 仅可评分一次 | 点击后禁用，不可修改 |
| 默认值 | 0 | 中性起点 |
| 重排算法 | 乘法加成 | score × (1 + 0.2 × normalized_importance) |

## 评分映射表

| 用户评分 | importance 变化 |
|---------|----------------|
| 5 分 | +2.0 / rank |
| 4 分 | +1.0 / rank |
| 3 分 | -0.5 / rank |
| 2 分 | -1.0 / rank |
| 1 分 | -1.5 / rank |

**示例**：用户打 5 分，引用了 3 个 frame（rank 分别为 1, 2, 3）：
- Frame 1: +2.0 / 1 = +2.0
- Frame 2: +2.0 / 2 = +1.0
- Frame 3: +2.0 / 3 = +0.67

## 数据库设计

### 迁移文件

**路径**: `openrecall/server/database/migrations/20260414120000_add_frame_importance.sql`

```sql
-- Add importance column to frames table
ALTER TABLE frames ADD COLUMN importance REAL DEFAULT 0;

-- Index for efficient sorting during re-ranking
CREATE INDEX IF NOT EXISTS idx_frames_importance ON frames(importance);
```

### 字段说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| importance | REAL | 0 | frame 重要性分数，可正可负 |

## API 设计

### 新增端点: POST /chat/api/rate

**请求**:
```json
{
  "message_id": "uuid-v4",
  "rating": 5
}
```

**响应 (成功)**:
```json
{
  "success": true,
  "frames_updated": 3
}
```

**响应 (已评分)**:
```json
{
  "success": false,
  "error": "already_rated",
  "message": "该消息已评分"
}
```

**响应 (无引用 frame)**:
```json
{
  "success": false,
  "error": "no_frames",
  "message": "该消息未引用任何 frame"
}
```

### 实现逻辑

1. 检查 `message_id` 是否已评分（前端状态 + 后端可选校验）
2. 从消息的 `tool_calls` 中提取搜索结果，获取 frame_id 列表
3. 按 rank 顺序计算各 frame 的 importance 变化值
4. 批量更新 frames 表：`UPDATE frames SET importance = importance + ? WHERE id = ?`
5. 返回更新的 frame 数量

### 评分影响范围

**仅影响 `myrecall-search` 工具调用的结果：**

| 工具调用 | 是否影响 importance | 说明 |
|----------|-------------------|------|
| `myrecall-search` | ✅ 是 | 从 `result.data[].frame_id` 提取 |
| `myrecall-activity-summary` | ❌ 否 | 活动摘要不含 frame 细节，评分返回 `no_frames` 错误 |
| 其他工具 | ❌ 否 | 评分返回 `no_frames` 错误 |

**多轮对话处理：**
- 每条 assistant 消息都有独立的评分按钮
- 评分只影响该条消息引用的 frames
- 历史消息可以评分（用户滚动回去点击）
- 无 frame 引用的消息评分时显示错误提示

## 前端 UI 设计

### 组件位置

assistant 消息气泡下方，显示评分按钮。

### 交互流程

1. assistant 消息渲染完成后，显示 `[1] [2] [3] [4] [5]` 按钮
2. 用户点击某分数，发送 POST /chat/api/rate 请求
3. 请求成功后，按钮禁用，显示"已评分 ✓"
4. 若失败，显示错误提示

### 状态管理

Message 对象新增字段：
```javascript
msg.rated = false;           // 是否已评分
msg.rating = null;           // 评分值 1-5
msg.ratingLoading = false;   // 加载中
```

### 样式规格

- 5 个并排按钮，默认灰色边框
- 点击后高亮（蓝色背景），其他按钮禁用
- "已评分" 状态显示为绿色勾号 + 评分值

## 搜索重排设计

### 重排位置

`HybridSearchEngine._hybrid_search()` 方法末尾，RRF 融合之后。

### 算法

```python
def apply_importance_rerank(results: list[dict]) -> list[dict]:
    """Apply importance-based re-ranking using multiplicative boost."""
    if not results:
        return results

    # 找到最大 importance 用于归一化
    max_importance = max(r.get('importance', 0) for r in results)
    if max_importance <= 0:
        max_importance = 1  # 避免 max=0 时的除零

    # 乘法加成
    for r in results:
        normalized = r.get('importance', 0) / max_importance
        # 最高提升 20%
        boost = 1 + 0.2 * normalized
        # 确保 boost 不低于 0（负数 importance 时 score 降为 0）
        boost = max(0, boost)
        r['final_score'] = r['score'] * boost

    # 按 final_score 降序排列
    results.sort(key=lambda x: x['final_score'], reverse=True)

    return results
```

### 边界情况处理

| 场景 | 处理方式 |
|------|----------|
| 所有 importance = 0 | max_importance 设为 1，所有 frame 的 boost = 1，顺序不变 |
| 所有 importance < 0 | max_importance 设为 1，负数归一化为更小的负数，boost = max(0, 1 + 负数) = 0，所有 frame 的 final_score = 0 |
| 混合正负 importance | 正数正常归一化，负数可能使 boost 降为 0 |
| 极大 importance 值 | 归一化后仍为 1.0，不影响算法稳定性 |

### 效果示例

| frame | score | importance | normalized | final_score |
|-------|-------|------------|------------|-------------|
| A     | 0.008 | 0.0        | 0.0        | 0.008       |
| B     | 0.007 | 5.0        | 1.0        | 0.0084      |
| C     | 0.007 | 2.5        | 0.5        | 0.0077      |

排序结果：B > A > C（importance 让 B 反超 A）

### 权重系数说明

- `0.2` 表示 importance 最高能给 score 加成 20%
- 这是一个保守值，不会逆转明显不同的相关性
- 可根据实际效果调整

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `openrecall/server/database/migrations/20260414120000_add_frame_importance.sql` | 数据库迁移 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `openrecall/server/database/frames_store.py` | 增加 importance 字段读写方法，更新 get_frames_by_ids 返回 importance |
| `openrecall/server/search/hybrid_engine.py` | 增加重排逻辑，覆盖所有搜索模式（fts/vector/hybrid） |
| `openrecall/client/chat/routes.py` | 增加 /chat/api/rate 端点 |
| `openrecall/client/chat/service.py` | 增加评分处理逻辑 |
| `openrecall/client/chat/types.py` | Message 增加 id/rated/rating 字段 |
| `openrecall/client/chat/conversation.py` | 确保 add_message 正确处理新字段 |
| `openrecall/client/web/templates/chat.html` | 增加评分 UI |

## 测试要点

### 单元测试

- [ ] 评分映射计算正确性（各分数对应的 importance 变化）
- [ ] 按 rank 递减权重计算
- [ ] 乘法加成重排算法
- [ ] 边界条件：importance 全为 0、负数、极大值

### 集成测试

- [ ] POST /chat/api/rate 端点完整流程
- [ ] 已评分消息拒绝重复评分
- [ ] 无 frame 消息返回错误
- [ ] 搜索结果按 importance 重排

### 手动测试

- [ ] UI 交互流畅，状态切换正确
- [ ] 评分后搜索结果确实变化

## 未来扩展

以下功能当前不做，但架构上预留扩展空间：

1. **评分历史表**：记录每次评分明细，用于分析和审计
2. **用户区分**：区分不同用户的评分，支持个性化
3. **时间衰减**：importance 随时间衰减，保持新鲜度
4. **可调节权重**：让用户自定义 importance 加成比例
