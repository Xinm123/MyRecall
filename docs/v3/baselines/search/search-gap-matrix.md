# Search 差异矩阵

> 生成日期：2026-03-02
> 比较对象：screenpipe（仅屏幕链路）↔ MyRecall-v3（设计 + 实现）
> 决策记录：D1=B, D2=A, D3=A, TBD-01=A, TBD-02=关闭, D4=Scheme C（025A）
> 证据编号映射：`E-01..E-11/E-25` 来自 `screenpipe-search-fact-baseline-screen-only.md`；`E-12..E-17` 来自 `myrecall-v3-search-current-baseline.md`。

## 1. 设计层差异（v3 spec vs screenpipe）

对齐判定：**部分对齐（~92%）**


| #    | 维度                     | screenpipe                                | v3 设计                             | 对齐      | 证据           | 处置              |
| ---- | ---------------------- | ----------------------------------------- | --------------------------------- | ------- | ------------ | --------------- |
| G-01 | content_type 参数        | 有（all/ocr/audio/input/accessibility）      | 有（all/ocr/accessibility，025A）       | 100% 对齐  | [E-01][E-25] | Scheme C 引入三路径分发，content_type 参数已对齐 |
| G-02 | frame_name 参数          | 有（零实际使用）                                  | 无                                 | 有意忽略    | [E-01][E-13] | TBD-02 已关闭，安全忽略 |
| G-03 | /search/keyword 独立端点   | 有                                         | 合并入 /v1/search                    | 有意合并    | [E-03][E-13] | P1 不暴露独立端点      |
| G-04 | browser_url 匹配语义       | FTS token 序列匹配                            | ~~前缀匹配~~ → FTS token 序列（TBD-01=A） | 100%    | [E-01][E-13] | spec 措辞已修正      |
| G-05 | FTS query sanitization | sanitize_fts5_query + expand_search_query | ~~未规定~~ → P1 两个都实现（D1=B）          | 100%    | [E-08]       | data-model.md §3.0.3（FTS 查询规范化） |
| G-06 | COUNT 查询               | 独立 count_search_results()                 | ~~未规定~~ → 独立 COUNT（D3=A）          | 100%    | [E-09]       | data-model.md §3.0.3（COUNT 查询） |
| G-07 | 搜索缓存                   | LRU cache（全参数哈希）                          | P1 不实现（D2=A），P2 补                 | P2 对齐   | [E-02]       | 无阻塞             |
| G-08 | 结果聚类/分组                | cluster_search_matches()                  | P1 不实现，P2+                        | P2+ 对齐  | [E-09]       | 无阻塞             |
| G-09 | text_positions/bbox    | search_with_text_positions()              | P1 预留 text_json，不暴露 API           | P2+ 对齐  | [E-09]       | 无阻塞             |
| G-10 | elements 表             | 有（OCR/AX 层级双写）                            | P1 不建                             | P2+ 对齐  | [E-04]       | 无阻塞             |
| G-11 | 自过滤（排除自身 app）          | 排除 app_name=screenpipe                    | 待实现（排除 MyRecall 自身）               | 待实现     | [E-09]       | P1-S4 实现        |
| G-12 | frame_url 字段           | 无                                         | 有（/v1/frames/:frame_id）           | v3 独有新增 | [E-13]       | 正确              |
| G-13 | capture_id 字段          | 无                                         | 有（UUID v7 幂等键）                    | v3 独有新增 | [E-14]       | 正确              |
| G-14 | offset_index 字段        | 有（视频帧偏移）                                  | 无（无视频 chunk）                      | 有意忽略    | [E-01]       | v3 无视频录制        |
| G-15 | DB 运行时配置               | WAL/64MB cache/256MB mmap/pool 30         | 待规定                               | 待规定     | [E-10]       | P1-S4 参考但按实际调优  |
| G-16 | focused → accessibility 搜索 | focused/browser_url → 强制 content_type=ocr（limitation） | focused 列直接在 accessibility 表，search_accessibility 支持过滤 | v3 改进    | [E-25]       | P0 修复 screenpipe db.rs:1870-1872 限制 |
| G-17 | accessibility.frame_id    | 无（±1s time window LEFT JOIN frames）         | frame_id DEFAULT NULL 精确关联          | v3 改进    | [E-25]       | paired_capture 填入，独立 walker 留 NULL |


## 2. 实现层差异（当前代码 vs v3 spec）

对齐判定：**不能对齐（~8%）**


| #    | 维度           | v3 设计                                      | 当前实现                          | 差距             | 证据           | 性质   |
| ---- | ------------ | ------------------------------------------ | ----------------------------- | -------------- | ------------ | ---- |
| I-01 | API 路径       | /v1/search                                 | /api/search                   | 完全不同           | [E-13][E-15] | 全新实现 |
| I-02 | 查询参数         | 13 个（含 include_frames P1 预留）              | 2 个（q, limit）                 | 11 参数缺失        | [E-13][E-15] | 全新实现 |
| I-03 | 搜索算法         | FTS5 BM25                                  | vector+FTS+rerank 3-stage     | 架构不兼容          | [E-12][E-16] | 全新实现 |
| I-04 | DB schema    | frames, ocr_text, accessibility, frames_fts, ocr_text_fts, accessibility_fts | entries, ocr_fts              | 完全不同           | [E-14][E-17] | 全新实现 |
| I-05 | FTS 索引列      | text, app_name, window_name                | ocr_text, caption, keywords   | 列不对齐           | [E-14][E-17] | 全新实现 |
| I-06 | 排序           | BM25 rank + timestamp                      | vector×0.7 + FTS×0.3 → rerank | 不同排序模型         | [E-07][E-16] | 全新实现 |
| I-07 | 分页           | limit + offset + total                     | 仅 limit                       | 无 offset/total | [E-13][E-15] | 全新实现 |
| I-08 | Response 格式  | {data, pagination}                         | flat JSON list                | 完全不同           | [E-13][E-15] | 全新实现 |
| I-09 | 空查询行为        | 返回全部 timestamp DESC                        | 返回空 []                        | 语义相反           | [E-13][E-15] | 全新实现 |
| I-10 | Embedding 依赖 | 无（P1 禁止）                                   | 必选 LanceDB                    | 违反 ADR-0005    | [E-12][E-16] | 全新实现 |
| I-11 | Reranker 依赖  | 无（P1 不用）                                   | 必选 cross-encoder              | 违反 ADR-0005    | [E-12][E-16] | 全新实现 |


**结论**：实现层无增量修改路径，需按 v3 spec 全新实现 search 模块。v2 hybrid 代码保留供过渡参考，不复用。

## 3. 决策审计链


| 决策                        | 选项                            | 日期         | 影响             |
| ------------------------- | ----------------------------- | ---------- | -------------- |
| D1 FTS Query Sanitization | B（sanitize + expand 全实现）      | 2026-03-02 | data-model.md §3.0.3（FTS 查询规范化） |
| D2 搜索缓存                   | A（P1 不实现）                     | 2026-03-02 | P2 补           |
| D3 COUNT 查询               | A（独立 COUNT）                   | 2026-03-02 | data-model.md §3.0.3（COUNT 查询） |
| TBD-01 browser_url 语义     | A（FTS token 序列，对齐 screenpipe） | 2026-03-02 | [spec.md §4.5 Search（召回与排序）](../../spec.md#45-search召回与排序) 文案修正 |
| TBD-02 frame_name         | 安全忽略                          | 2026-03-02 | 对齐映射表追加备注      |
| D4 Scheme C + focused 修复    | A（P0 建表 + focused 修复 + frame_id 方案 3） | 2026-03-02 | spec 多处修订（018A→C, 022A→C, 新增 025A） |


## 4. 未关闭项


| 编号     | 内容                                | 阶段          |
| ------ | --------------------------------- | ----------- |
| TBD-03 | COUNT(DISTINCT) 100k 行级 benchmark | P1-S4 实现后验证 |
| G-11   | 自过滤逻辑（排除 MyRecall 自身 app）         | P1-S4 实现    |
| G-15   | DB 运行时配置（WAL/cache/mmap/pool）     | P1-S4 实现时确定 |
| G-16   | focused 过滤在 search_accessibility 的正确性验证 | P1-S4 实现后验证 |
