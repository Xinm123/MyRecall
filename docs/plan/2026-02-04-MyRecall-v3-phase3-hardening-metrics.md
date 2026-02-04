# Phase 3 (Hardening + Metrics) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 v3 变成“可持续迭代”的工程：指标可量化、回归可执行、错误处理可预期、远程暴露有最低安全线。

**Architecture:** 不引入大重构；主要做稳定性收敛（日志/错误/边界/回归清单）+ 最小评估脚本框架。

**Tech Stack:** pytest、现有 Flask/SQLite/SearchEngine、（可选）一个轻量脚本用于离线 eval

## Scope
- In:
  - Scorecard 落地（日志字段齐全，便于统计）
  - 回归清单（手工 + pytest）
  - 最小 eval set 方案（可仅文档）
  - 远程暴露最低安全线（文档 + 防呆）
- Out:
  - 完整自动化 benchmark 系统
  - 复杂 auth（除非必须）

## Deliverables
- “怎么验收 v3”的清单与阈值（以 `MyRecall/docs/plan/2026-02-04-MyRecall-v3-metrics.md` 为准）
- 4h 稳定性手工跑法（client+server）
- 关键端点日志字段齐全

---

### Task 1: 端点打点与结构化日志（为 metrics 服务）

**Files:**
- Modify: `MyRecall/openrecall/server/api_v3.py`
- Modify: `MyRecall/openrecall/server/search/engine.py`（必要时增加耗时拆分日志）

**要求**
- 每次请求至少记录：
  - `route`, `limit`, `result_count`, `total_ms`
- search 额外记录：
  - `embedding_ms`, `vector_ms`, `fts_ms`, `rerank_ms`（如果可取）

---

### Task 2: 回归清单（手工 30min + 4h endurance）

**Files:**
- (Doc only) Modify: `MyRecall/docs/plan/2026-02-04-MyRecall-v3-metrics.md`（附录）

**30min 清单**
- ingest：`/api/upload` 正常写盘 + 入队
- worker：PENDING → COMPLETED
- timeline-v3：首屏 + 滚动 + 增量
- keyword：snippet 高亮
- chat：能回答并给 citations

**4h 清单**
- “database is locked”=0
- 队列积压可恢复（停 AI 再开）

---

### Task 3: 最小 eval set（仅文档也可）

**Files:**
- (Doc only) Modify: `MyRecall/docs/plan/2026-02-04-MyRecall-v3-metrics.md`

**内容**
- 30-50 条 query 的采样与标注格式
- 如何计算 MRR@10 / Recall@50（可手工/表格）

---

### Task 4: 远程暴露最低安全线（防呆）

**Files:**
- Modify: `MyRecall/openrecall/shared/config.py`（若要加开关）
- Doc: `MyRecall/docs/archive/DEPLOYMENT_CLIENT_SERVER.md`（若要补充提醒）

**建议规则**
- 默认 host=127.0.0.1
- 若检测到非 loopback host：提示风险；可选禁用 `/api/v3/chat` 或要求 token（实现取决于你是否需要公网访问）

