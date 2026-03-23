# Minor Issue 详细分析: content_type=all 时 FTS Rank 丢失

**问题类型:** 行为偏离 (Behavioral Deviation)
**严重程度:** Low (Minor)
**影响范围:** `/v1/search?content_type=all` 带文本查询时的结果排序
**文件位置:** `openrecall/server/search/engine.py:_search_all()`

---

## 1. 问题描述

### 1.1 当前行为

当调用 `/v1/search?content_type=all&q=某个查询词` 时：

1. 子搜索 `_search_ocr()` 和 `_search_accessibility()` 各自返回按 **FTS rank + timestamp DESC** 排序的结果
2. `_search_all()` 合并这些结果后，**仅按 timestamp DESC** 重新排序
3. 结果是：高相关度的结果可能被时间戳较新但相关度较低的结果覆盖

### 1.2 代码证据

```python
# engine.py:788-829

# 1. 子搜索返回带rank的结果（各自内部已按rank排序）
ocr_results, ocr_total = self._search_ocr(q=q, limit=fetch_limit, offset=0, ...)
ax_results, ax_total = self._search_accessibility(q=q, limit=fetch_limit, offset=0, ...)

# 2. 简单合并（保持各自顺序，但OCR在前Accessibility在后）
merged = []
seen_ids = set()
for r in ocr_results + ax_results:  # OCR结果先加入
    if r.get("frame_id") not in seen_ids:
        seen_ids.add(...)
        merged.append(r)

# 3. 仅按时间戳排序 —— 这里丢失了rank信息！
merged.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
```

### 1.3 对比: 规范 vs 实现

| 场景 | 规范期望 | 实际实现 | 差异 |
|-----|---------|---------|------|
| `content_type=ocr` + q | FTS rank → timestamp | ✅ FTS rank → timestamp | 无 |
| `content_type=accessibility` + q | FTS rank → timestamp | ✅ FTS rank → timestamp | 无 |
| `content_type=all` + q | **全局 relevance** → timestamp | ⚠️ **仅 timestamp** | **丢失 relevance** |

---

## 2. 影响分析

### 2.1 用户场景影响

**场景 A: 用户搜索 " quarterly report "**

假设有以下帧：

| Frame | 来源 | 内容匹配度 | FTS Rank | 时间戳 | 期望位置 | 实际位置 |
|-------|------|-----------|----------|--------|---------|---------|
| #1 | Accessibility | 高 (标题包含) | 0.1 | 10:00 | 第1页 | 第2页 |
| #2 | OCR | 低 (仅正文提及) | 0.8 | 10:05 | 第2页 | 第1页 |

**问题:** 用户可能在第1页看到相关性较低的OCR结果，而高相关度的Accessibility结果被推到后面。

### 2.2 为什么规范要求全局 relevance?

```
mvp.md §891-894:
"for `all`
  - each sub-search fetches enough rows for the global window
  - merged results are sorted globally by timestamp DESC"
```

规范只明确说了 "timestamp DESC"，但隐含意图是：
1. 子搜索获取 "enough rows"（基于 relevance）
2. 合并后按时间排序（简化实现）

这是一种**折中设计** —— 子搜索用 relevance 过滤，合并后用时间排序，确保不会错过高 relevance 结果，但牺牲了全局 relevance 排序。

### 2.3 这真的是 Bug 吗?

**不是 Bug，是简化实现 (Simplification)**

原因：
1. 规范确实写了 "sorted globally by timestamp DESC"
2. 实现完全符合文字描述
3. 但规范没有明确说明是否应该保留 relevance 作为次要排序键

**更准确地说:** 这是一个 "设计债务" (Design Debt) —— MVP 为了简化选择了时间排序，但未来可能需要改进。

---

## 3. 技术深度分析

### 3.1 为什么不能简单保留 rank?

**问题: OCR 和 Accessibility 的 rank 不可直接比较**

```
OCR FTS rank (BM25):
- 基于 ocr_text_fts 表
- 取决于 OCR 文本质量（可能有识别错误）

Accessibility FTS rank (BM25):
- 基于 accessibility_fts 表
- 取决于 AX 文本质量（结构完整但可能不全）
```

**Rank 值范围不同:**
- 不同表、不同文本量 → BM25 分数不在同一尺度
- OCR rank 0.5 ≠ Accessibility rank 0.5（不可直接比较）

### 3.2 可能的解决方案

#### 方案 1: 归一化排序 (Normalized Ranking)

```python
# 在子搜索中返回归一化分数（0-1范围）
ocr_results = normalize_ranks(ocr_results)  # 最高rank = 1.0
ax_results = normalize_ranks(ax_results)    # 最高rank = 1.0

# 合并后按归一化rank + timestamp排序
merged.sort(key=lambda x: (-x['norm_rank'], x['timestamp']), reverse=False)
```

**优点:** 相对公平地比较不同来源
**缺点:** 实现复杂，归一化策略需要 tuning

#### 方案 2: 混合排序 (Hybrid Sorting)

```python
# 按时间分段，每段内按rank排序
time_buckets = group_by_time_window(merged, window_minutes=5)
sorted_results = []
for bucket in time_buckets:
    bucket.sort(key=lambda x: x.get('fts_rank', 1.0))
    sorted_results.extend(bucket)
```

**优点:** 保留时间趋势，局部优化 relevance
**缺点:** 增加了复杂性，window 大小需要 tuning

#### 方案 3: 客户端排序 (Client-Side Sorting)

```python
# API 返回 rank 字段，让客户端决定排序
# Chat/MCP 层可以按 relevance 重新排序
```

**优点:** 灵活性最高
**缺点:** 需要返回更多数据（offset/limit 逻辑变复杂）

#### 方案 4: 保持现状 (Current Behavior)

```python
# 仅按时间排序，简单可靠
merged.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
```

**优点:** 简单、可预测、符合当前规范文字
**缺点:** 可能错过高 relevance 结果

---

## 4. 业务影响评估

### 4.1 何时会影响用户?

| 条件 | 影响程度 | 说明 |
|-----|---------|------|
| 搜索词具体 + 结果少 | 低 | 所有结果都相关，排序不重要 |
| 搜索词宽泛 + 结果多 | 中 | 可能错过最相关的帧 |
| 时间跨度大 + 结果多 | 高 | 旧的高 relevance 结果被淹没 |
| 用户只看前10条 | 高 | 如果高 relevance 结果在10条后 |

### 4.2 实际场景测试

假设用户搜索 "API contract"，系统中有：

**OCR 结果 (较新):**
- Frame A: 包含 "API"（在代码注释中）rank=0.6
- Frame B: 包含 "contract"（在变量名中）rank=0.7

**Accessibility 结果 (较旧):**
- Frame C: 标题 "API Contract Review" rank=0.2（高 relevance）

**当前实现返回顺序:**
1. Frame B (OCR, 10:05, rank 0.7)
2. Frame A (OCR, 10:03, rank 0.6)
3. Frame C (Accessibility, 10:00, rank 0.2) ← 最相关但在最后

**理想顺序:**
1. Frame C (Accessibility, 10:00, rank 0.2) ← 最相关
2. Frame B (OCR, 10:05, rank 0.7)
3. Frame A (OCR, 10:03, rank 0.6)

---

## 5. 建议决策

### 5.1 短期 (MVP 发布)

**推荐: 方案 4 - 保持现状**

理由：
1. 当前实现符合规范文字描述
2. 简单可靠，没有引入新 complexity 的风险
3. MVP 的主要目标是功能可用，排序优化是锦上添花
4. 可以通过 Agent Policy 缓解（建议用户优先查看 frame context）

**缓解措施 (Mitigation):**

在 `mvp.md` Agent Policy 中添加：
```markdown
### Search Result Ordering Note

When using `content_type=all`, results are sorted by timestamp only.
The agent should not assume relevance-based ordering.
For critical queries, consider:
1. Using `content_type=accessibility` or `content_type=ocr` separately
2. Fetching more results (higher limit) and manually filtering
3. Using `/v1/frames/{id}/context` to verify relevance
```

### 5.2 中期 (Post-MVP)

**推荐: 方案 1 - 归一化排序**

实施条件：
1. 用户反馈表明排序是个问题
2. 有资源进行 tuning 和测试
3. 可以承受额外的 complexity

实施步骤：
1. 在子搜索中添加归一化逻辑
2. A/B 测试验证用户体验提升
3. 逐步 rollout

### 5.3 长期

**考虑更智能的排序:**
- 用户行为信号（点击、停留时间）
- 机器学习 relevance 模型
- 个性化排序

---

## 6. 代码修改示例

如果决定实施方案 1 (归一化排序)，以下是修改示例：

```python
def _search_all(...):
    # ... 获取 ocr_results 和 ax_results ...

    # 归一化 rank
    def normalize_ranks(results):
        if not results or not any(r.get('fts_rank') for r in results):
            return results

        # 提取有效 rank
        ranks = [r.get('fts_rank', 1.0) for r in results if r.get('fts_rank')]
        if not ranks:
            return results

        min_rank, max_rank = min(ranks), max(ranks)
        rank_range = max_rank - min_rank if max_rank != min_rank else 1.0

        for r in results:
            if r.get('fts_rank'):
                # 归一化到 0-1，越低越好
                r['norm_rank'] = (r['fts_rank'] - min_rank) / rank_range
            else:
                r['norm_rank'] = 1.0  # 无 rank 放最后
        return results

    ocr_results = normalize_ranks(ocr_results)
    ax_results = normalize_ranks(ax_results)

    # 合并
    merged = []
    seen_ids = set()
    for r in ocr_results + ax_results:
        fid = r.get("frame_id")
        if fid not in seen_ids:
            seen_ids.add(fid)
            merged.append(r)

    # 按归一化 rank (升序，越小越好) + timestamp (降序) 排序
    merged.sort(key=lambda x: (x.get('norm_rank', 1.0), -x.get('timestamp', '').timestamp()))

    # ... 分页 ...
```

---

## 7. 测试建议

如果保留当前行为，添加测试明确文档化：

```python
def test_search_all_sorts_by_timestamp_not_rank(client):
    """Verify that content_type=all sorts by timestamp, losing FTS rank ordering.

    This is intentional MVP behavior. If this test fails due to ranking changes,
    ensure the new behavior is documented and approved.
    """
    # Setup: Create OCR frame with low rank but recent timestamp
    #        Create Accessibility frame with high rank but old timestamp

    # Execute search with content_type=all

    # Assert: Recent OCR frame comes before old Accessibility frame
    #         even if Accessibility has better FTS rank
```

---

## 8. 总结

| 维度 | 评估 |
|-----|------|
| 是否是 Bug | 否，是简化实现 |
| 是否影响 MVP 发布 | 否 |
| 是否需要立即修复 | 否 |
| 是否需要在文档中标注 | 是 |
| 未来改进价值 | 中-高 (取决于用户反馈) |

**最终建议:**
- 保持当前实现
- 在 mvp.md 中添加关于排序行为的注释
- 收集用户反馈，如果排序成为痛点再考虑改进
