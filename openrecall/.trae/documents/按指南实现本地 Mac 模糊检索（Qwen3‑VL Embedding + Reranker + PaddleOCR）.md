## 现状对齐（与指南的差异）
- 当前已具备：异步入库（PENDING/PROCESSING/COMPLETED）、OCR（三种：doctr/OpenAI/DashScope）、Vision 描述（三种：local/OpenAI/DashScope）、文本 embedding（三种：SentenceTransformer/OpenAI/DashScope）、以及“全量余弦排序”的语义检索入口（/search）。
- 当前缺失/需升级：
  - DB 中没有 `image_embedding`（跨模态 text→image 空间）与 FTS5 表。
  - Query 侧没有中文时间解析（只能靠 UI 的 start/end 参数）。
  - 没有向量检索后端（sqlite-vss / cache）与 RRF 融合。
  - 没有 Reranker（二阶段重排）。
  - 没有 PaddleOCR provider。

## Phase 0：配置与 Provider 框架扩展（保持现有风格）
- 代码改动
  - 在 [config.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/shared/config.py) 增加新配置（全部带 OPENRECALL_ 前缀，避免与现有冲突）：
    - `OPENRECALL_MM_EMBEDDING_PROVIDER`、`OPENRECALL_MM_EMBEDDING_MODEL_NAME`、`OPENRECALL_MM_EMBEDDING_API_KEY`、`OPENRECALL_MM_EMBEDDING_API_BASE`
    - `OPENRECALL_RERANK_PROVIDER`、`OPENRECALL_RERANK_MODEL_NAME`、`OPENRECALL_RERANK_ENABLED`、`OPENRECALL_RERANK_TOPK`
    - `OPENRECALL_VECTOR_BACKEND`（cache/sqlite_vss）、`OPENRECALL_HARD_LIMIT_RECENT_N`
  - 在 [base.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/base.py) 增加两个新接口：`MultimodalEmbeddingProvider(embed_text/embed_image)`、`RerankerProvider(rerank)`。
  - 在 [factory.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/factory.py) 增加 `get_mm_embedding_provider()` 与 `get_reranker_provider()`，沿用当前的“按 capability 单例缓存 + provider 字符串选择”模式。
- 降级策略
  - provider 选择为 API 但 key 缺失时：抛 `AIProviderConfigError`，上层捕获后走 fallback（返回空/零向量），保证 server/worker 不崩。
- 测试与验证
  - 新增 unit tests：配置默认值、环境变量覆盖、工厂选择分支（含 unknown provider 报错）。

## Phase 1：DB Schema + FTS5（迁移式落地）
- 代码改动
  - 在 [database.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py) 的 `_migrate_db` 增加：
    - `ALTER TABLE entries ADD COLUMN image_embedding BLOB`（若不存在）。
    - 创建 `entries_fts`（FTS5）虚表（若可用），包含 `app/title/text/description`。
    - 提供 `fts_upsert_entry(conn, entry_id, app, title, text, description)` 与 `fts_search(conn, query, topk)`；当 SQLite 不支持 FTS5 时自动降级为空结果且不报致命错。
  - 在 [models.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/shared/models.py) 扩展 `RecallEntry` 支持 `image_embedding` 反序列化（bytes→np.ndarray），并允许为空。
- 测试与验证
  - schema 单测：新列存在、BLOB 写入/读取 dtype/shape 正确。
  - FTS 单测：最小样本写入后，`fts_search` 可命中；并覆盖“FTS 不可用”降级路径。

## Phase 2：PaddleOCR Provider（可选依赖）
- 代码改动
  - 在 [providers.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/providers.py) 增加 `PaddleOCRProvider`（延迟 import `paddleocr`，未安装时给出可读错误）。
  - 在 [factory.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/factory.py) 的 `get_ocr_provider` 增加分支：`provider == "paddleocr"`。
  - 在 [setup.py](file:///Users/tiiny/Test2/MyRecall/openrecall/setup.py) 增加 extras：`extras_require["paddleocr"] = ["paddleocr", "paddlepaddle"]`（mac 默认 CPU）。
- 测试与验证
  - 单测：未安装 paddleocr 时返回明确异常信息；安装环境下做最小图片 OCR（放在 tests 资源中或动态生成）并断言返回字符串。

## Phase 3：Qwen3‑VL‑Embedding（跨模态）Provider（API 默认，本地可选）
- 代码改动
  - 在 [providers.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/providers.py) 新增：
    - `LocalQwen3VLEmbeddingProvider`：`embed_text` 与 `embed_image` 输出同维度向量，并做 L2 normalize；维度不一致时沿用现有 `_fit_embedding_dim/_l2_normalize` 逻辑。
    - `OpenAICompatibleMMEmbeddingProvider`：走 OpenAI-compatible（以 mock 合约测试为主；真实连通需 key）。
    - `DashScopeMMEmbeddingProvider`：如 DashScope 支持 multimodal embedding，则封装；否则同样以合约 mock 为主。
  - 在 [factory.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/factory.py) 的 `get_mm_embedding_provider` 里按 provider 选择实现。
- 测试与验证
  - 单测（mock）：向量 shape/dtype、归一化、异常路径（空输入/图片不存在）。
  - 慢测（pytest.mark.model）：本地模型对同一图片多次 embed 相似度≈1（允许跳过）。
  - API 合约测试：mock HTTP 响应格式与错误码处理；若要真实验证，再单独提示你提供 key。

## Phase 4：Worker 写入 `image_embedding` + FTS upsert
- 代码改动
  - 在 [worker.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/worker.py) 处理链路中新增：
    - 在 COMPLETED 前调用 mm embedding provider：对图片生成 `image_embedding`。
    - `mark_task_completed` 扩展为同时写入 `image_embedding`（需要同步改 [database.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py) 的 update 语句）。
    - 完成后调用 `fts_upsert_entry`（保证入库即具备关键词检索）。
  - 保留现有 `embedding`（文本融合 embedding）用于回退或 UI 展示，不破坏旧功能。
- 测试与验证
  - 集成测试：插入 PENDING→模拟 worker 处理一次（mock provider）→断言 status=COMPLETED、`image_embedding` 非空、FTS 命中。

## Phase 5：向量检索后端（cache 保底 + sqlite-vss 可选）
- 代码改动
  - 新增向量检索模块（例如 `openrecall/server/vector_backend.py`）：统一接口 `upsert(entry_id, vec) / query(vec, topk, candidate_ids=None)`。
  - cache 后端：仅对 hard filter 结果集合做快速 numpy 计算；支持按时间窗候选集。
  - sqlite-vss 后端（可选依赖）：封装建表/建索引/HNSW 查询；依赖缺失时自动降级到 cache。
- 测试与验证
  - 单测：两种 backend 的基本契约；sqlite-vss 缺失时的降级路径。
  - 性能基准（pytest-benchmark 或已有 perf 体系）：随机 1–5 万向量 topK 查询耗时不退化。

## Phase 6：Query Parsing（中文时间）+ Hard Filter
- 代码改动
  - 新增 `openrecall/server/query_parsing.py`：
    - `parse_time_range(q, now)`：从中文表达抽取 (start_ts,end_ts)；优先 dateparser，jionlp 作为可选增强；两者缺失则只返回 None。
    - `split_query(q)`：得到 `q_semantic/q_keywords`（时间片段剥离）。
  - 在 [app.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/app.py) 的 `/search`：
    - 若用户没填 start/end，则尝试从 q 中解析；先做 hard filter（时间窗 + status）。
- 测试与验证
  - 单测：冻结 now，覆盖 20+ 中文表达（昨天下午/上周三/三天前/本周等）。
  - 集成：构造跨天 entries，断言返回全部在窗口内。

## Phase 7：两路召回 + RRF 融合
- 代码改动
  - 在搜索流程中实现：
    - 向量召回：`mm_embed_text(q_semantic)` → vector backend topK。
    - 关键词召回：FTS BM25 topK。
    - 融合：RRF（k=60），输出 fused candidates。
- 测试与验证
  - 单测：两路排名冲突/单路为空/重复 id 等边界；验证 RRF 输出稳定。

## Phase 8：Qwen3‑VL‑Reranker（二阶段重排）
- 代码改动
  - 在 [providers.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/providers.py) 增加 `LocalRerankerProvider` 与 API 版本（OpenAI-compatible/DashScope）。
  - 在 `/search` 融合后对 topN（默认 50）调用 rerank（可通过 `OPENRECALL_RERANK_ENABLED` 关闭）。
- 测试与验证
  - 单测：mock 分数→断言重排正确与 topN 截断。
  - 慢测（model）：少量候选做真实 rerank（可跳过）。
  - API 合约：mock HTTP。

## Phase 9：UI 可解释性（Why this result）
- 代码改动
  - 在 [search.html](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/templates/search.html) 增加：来源角标（关键词/语义/融合）、FTS 命中高亮片段（只显示必要片段），并可选展示分数。
- 测试与验证
  - E2E（沿用现有 Playwright 体系）：关键词查询与纯语义查询各跑一次，断言角标与高亮存在。

## Phase 10：端到端验收（本地 server）
- 验收方式
  - 启动 server（默认 8083；如你已有 18083 习惯，也会保持 env 可覆盖，不让测试依赖端口）。
  - 录入若干张包含 IDE/终端/报错的截图。
  - 查询“我昨天下午修改的代码 BUG”，导出 top10（timestamp+来源+分数），对比 rerank 前后 Top3 改善。

## 交付与执行节奏（严格按你要求“每步完备测试/验证”）
- 我会按 Phase 0→10 顺序逐步实现；每完成一个 Phase：先补齐单测/集成/E2E（该 phase 需要什么就做什么），跑通后再进入下一步；任何一步失败会先修到全绿再继续。