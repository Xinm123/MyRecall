# MyRecall-v3 评估标准与关键指标（Metrics / KPI）

> 生成日期：2026-02-04  
> 状态：Proposed（仅落盘文档，暂不实现）  
> 目标：给 MyRecall-v3 的落地效果一个“可量化/可验收”的 Scorecard

## 1. 指标范围（我们要证明什么）

v3 的成功标准分 4 类：
1) 体验（Timeline 可用、顺滑、增量稳定）
2) 检索（keyword 高亮正确、filters 可复现、混合检索不退化）
3) Chat（tool-call 受控、回答可追溯、延迟可接受）
4) 稳定性（SQLite 锁冲突显著降低、队列可恢复）

> 注意：v3 不做视频分片/音频/UI events，所以不对标 screenpipe 的资源曲线（只做记录）。

## 2. Scorecard（建议的“通过线”）

| 类别 | 指标 | 目标阈值（MVP） | 测量方式（建议） |
|---|---|---:|---|
| Timeline | TTFF（首屏时间） | ≤ 1s（本地） | 浏览器 DevTools + 手工计时 |
| Timeline | 增量刷新延迟 | ≤ 3s | poll 间隔 2-3s，观察新帧出现 |
| Timeline | 去重/乱序 | 0（不重复、不倒序） | 观察/日志（按 timestamp） |
| Search | `/api/v3/search` p95 | ≤ 1.5s（limit=50） | server 日志打点 p95 |
| Search | keyword 高亮正确率 | ≥ 95%（抽样 50 条） | 手工核对 snippet 是否命中 |
| Chat | p95 总响应时间 | ≤ 10s（非 streaming） | server 日志打点 p95 |
| Chat | tool 输出预算 | 单条 ≤300 chars；总 ≤4000 chars；limit≤10 | tool_trace / debug |
| Chat | 引用（citations）覆盖 | 有检索结果时 ≥3 条引用 | 响应字段校验 |
| Stability | “database is locked” | 0（正常运行 4h） | 日志 grep 统计 |
| Stability | client/server 目录隔离 | 0（无跨目录写入） | 启动后检查 `$ROOT/server` 与 `$ROOT/client` 目录树；越界应 fail-fast |
| Reliability | 队列可恢复 | 恢复后 30min 内积压回落 | `/api/queue/status` 观察 |

## 3. 指标口径（定义）

### 3.1 TTFF（Time to First Frame）
- 定义：打开 timeline-v3 页面到第一批卡片（或第一张图片）可见的时间
- 约束：需要“首批 API 返回 + 前端渲染”都完成

### 3.2 Search 延迟
- 定义：从 server 收到请求到返回响应（不含网络 RTT）
- 建议日志字段：
  - `request_id`
  - `route`
  - `limit`
  - `db_ms` / `fts_ms` / `vector_ms` / `rerank_ms`
  - `result_count`
  - `total_ms`

### 3.3 keyword 高亮正确率
- 定义：抽样 N 条 keyword 搜索结果，snippet 中 `<mark>` 包含查询 term（或其规范化形式）
- 注意：FTS query 语法可能包含引号/AND/OR，抽样时需记录原始 query

### 3.4 Chat 的“受控 tool-call”
- 定义：Chat 不直接塞库；仅通过 search 工具拿有限上下文
- 强约束（建议写死为常量）：
  - `SEARCH_LIMIT_CAP=10`
  - `ITEM_TEXT_CAP=300`
  - `TOTAL_TEXT_CAP=4000`
  - `TOOL_CALL_ROUNDS_CAP=3`
  - `TOOL_TIMEOUT_SECONDS=30`

## 4. 评估数据集（可选但推荐）

> 用于检索/Chat 的离线评估（不进入 v3 代码实现也可以先写方法）。

### 4.1 构建方式（轻量）
- 从你日常使用中抽取 30-50 个真实问题（中文/英文混合皆可）
- 每条记录：
  - `query`
  - `time_range`（可选）
  - `expected_timestamp`（至少 1 个“正确答案”时间点）
  - `notes`（为什么这是正确答案）

### 4.2 输出指标（建议）
- `MRR@10`（如果能标注唯一/少量正确答案）
- `Recall@50`（正确答案是否出现在前 50）
- `Chat citation coverage`（回答是否引用到包含正确答案的时间点）

## 5. 基线环境（写入评估报告时必须注明）
- OS / CPU / RAM
- `OPENRECALL_ROLE`（server/client/combined）
- `OPENRECALL_SERVER_DATA_DIR` / `OPENRECALL_CLIENT_DATA_DIR`
- `OPENRECALL_CAPTURE_INTERVAL`
- 是否仅主屏 `OPENRECALL_PRIMARY_MONITOR_ONLY`
- AI provider（local/openai/dashscope）
- `OPENRECALL_DEVICE`（cpu/cuda/mps）
- 数据规模：entries 数量、时间跨度

## 6. 产出物（建议）
- 每次评估产出一份报告（可放 `MyRecall/docs/plan/` 或 `docs/archive/`）：
  - 当次配置、数据规模、Scorecard、问题清单、下一步建议
