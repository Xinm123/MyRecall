## 模型选型：每个环节都提供 Local / API 两种选项

### 1) Qwen3‑VL‑Embedding（跨模态向量）
- **Local 选项（默认推荐）**：transformers 加载 `Qwen3‑VL‑Embedding-*B`，实现 `embed_text/embed_image`。
- **API 选项（可选）**：调用 OpenAI-compatible / DashScope 的 embedding 接口（前提：该服务支持多模态 embedding 输入；阿里云文档明确存在“multimodal embeddings”能力）。(https://www.alibabacloud.com/help/en/model-studio/embedding)

### 2) Qwen3‑VL‑Reranker（重排序）
- **Local 选项（默认推荐）**：transformers 加载 `Qwen3‑VL‑Reranker-*B`，对 (query, image+evidence) 输出 relevance。
- **API 选项（可选）**：通过 OpenAI-compatible chat/completions 调用托管模型，让模型输出分数/yes-no 概率（实现上会提供可插拔 provider）。

### 3) OCR（用于关键词召回与证据）
- **Local 选项 A（现有）**：doctr（已在仓库中实现 LocalOCRProvider）。
- **Local 选项 B（新增可选）**：**PaddleOCR**（可以用，但需要新增依赖 `paddleocr` + `paddlepaddle`，mac 上通常走 CPU；体积/安装复杂度更高，但中文与截图场景往往更强）。
- **API 选项**：DashScope OCR / OpenAI OCR（仓库已有对应 provider）。

### 4) Vision 描述（用于“Why this result”与 FTS 补充）
- **Local 选项**：现有 LocalProvider（Qwen3‑VL 指令生成 description）。
- **API 选项**：DashScopeProvider / OpenAIProvider（仓库已有）。

---

## 整体 Pipeline（保存的数据与用到的模型）

### Ingest / Index
1) Client（本地 mac）：截图 + app/title + timestamp → 上传
2) Server：落盘 png + SQLite 写 PENDING
3) Worker：
- OCR（doctr / PaddleOCR / API）→ `entries.text`
- Vision 描述（local/API）→ `entries.description`
- **Qwen3‑VL‑Embedding**（local/API）→ `entries.image_embedding`
- upsert FTS（text/description/title/app）
- upsert 向量索引（sqlite-vss）或更新内存缓存

### Query / Search
1) Query Parsing（dateparser/jionlp）→ time_range hard filter + q_keywords/q_semantic
2) Recall：
- 向量：`embed_text(q_semantic)` 查询向量索引（sqlite-vss）
- 关键词：FTS topK（BM25）
3) Fusion：RRF
4) **Qwen3‑VL‑Reranker**（local/API）重排 topN（默认 50）
5) UI：来源角标 + 高亮片段（Why this result）

---

## 分阶段实现（每阶段：功能/效果/测试，且“每个实现都有完备测试”）

## Phase 0：配置开关 + Provider 插拔框架（先把可测试性打牢）
**功能**
- 增加 provider 选择项：
  - `MM_EMBEDDING_PROVIDER` = local | api
  - `RERANK_PROVIDER` = local | api
  - `OCR_PROVIDER` = doctr | paddleocr | dashscope | openai
  - `VISION_PROVIDER` = local | dashscope | openai
- 增加运行开关：rerank_enabled、rerank_topk、vector_backend（sqlite-vss / cache）。

**效果**
- 同一条 pipeline 可以在不同机器/算力/成本约束下切换实现。

**测试（完备）**
- 单测：每个 provider 的“接口契约测试”（空输入、异常处理、返回类型/shape）。
- 单测：配置解析（环境变量覆盖）与默认值。

---

## Phase 1：DB Schema + FTS
**功能**
- entries 新增 `image_embedding BLOB`。
- 创建 `entries_fts`（FTS5）。

**效果**
- 数据层同时支持跨模态向量检索与关键词检索。

**测试（完备）**
- 单测：schema 存在性、写入/读取 BLOB 正确。
- 单测：FTS 查询 top1 命中（用最小样本 OCR 文本）。

---

## Phase 2：Query Parsing（dateparser/jionlp）+ Hard Filter
**功能**
- 引入 dateparser（或可选 jionlp）解析中文时间，输出 SQLite hard filter。

**效果**
- 任何查询先缩小候选集，性能与准确性都提升。

**测试（完备）**
- 单测：冻结 now，覆盖 20+ 种表达（昨天下午/上周三/本周/三天前等）。
- 集成：插入跨天数据，断言返回的截图都在时间窗口内。

---

## Phase 3：Qwen3‑VL‑Embedding Provider（Local/API 两套）
**功能**
- Local：transformers 取 EOS hidden state 向量（L2 normalize）。参考官方描述。 (https://github.com/QwenLM/Qwen3-VL-Embedding)
- API：封装 OpenAI-compatible embeddings（前提支持多模态）。(https://www.alibabacloud.com/help/en/model-studio/embedding)

**效果**
- text 与 image 同空间向量。

**测试（完备）**
- 单测（mock）：shape/dtype/norm。
- 慢测（标记 model，允许本地跳过）：真模型生成向量稳定。
- API 合约测试：mock HTTP 返回，验证解析与错误处理。

---

## Phase 4：Worker 写入 image_embedding + upsert FTS
**功能**
- worker 完成时写 `image_embedding`，并更新 FTS。

**效果**
- 从第一张截图开始就具备完整索引。

**测试（完备）**
- 集成：插入 PENDING→跑 worker 一次→断言 COMPLETED + embedding 非空 + FTS 命中。

---

## Phase 5：向量检索后端（解决你提到的 10 万级陷阱）
**功能（推荐优先做 sqlite-vss）**
- 引入 sqlite-vss(HNSW) 建向量索引，查询直接 topK entry_id。
- 保底：cache 模式（只对 hard filter 后集合做计算）。

**效果**
- 从一开始就避免未来返工；同时保留回退路径。

**测试（完备）**
- 单测：vss backend 的 create/upsert/query。
- 性能基准：随机向量 1–5 万条下 topK 查询耗时。

---

## Phase 6：FTS 召回 + RRF 融合
**功能**
- FTS topK + 向量 topK 用 RRF 融合。

**效果**
- 避免线性加权调参痛苦；排序更稳。

**测试（完备）**
- 单测：构造两路排名冲突样本，断言 RRF 排序。

---

## Phase 7：Qwen3‑VL‑Reranker（Local/API 两套）
**功能**
- 对融合后 topN（默认 50）做 rerank。

**效果**
- Top 结果更贴近人类判断，特别是“修改/修复/排查 bug”。

**测试（完备）**
- 单测：mock reranker 验证重排与截断。
- 慢测（model）：真模型对少量候选跑一次，验证输出为数值且排序稳定。
- API 合约测试：mock HTTP 返回，验证解析与异常处理。

---

## Phase 8：UI 可解释性（Why this result）
**功能**
- 角标：关键词命中 / 语义匹配。
- 高亮：FTS 命中的 OCR/description 片段。

**效果**
- 用户能理解“这是搜到的还是模型看出来的”。

**测试（完备）**
- E2E：两条查询（关键词 vs 纯语义）分别断言角标与高亮出现。

---

## 运行与测试注意事项（按你的约束）
- 所有测试/启动命令前：先 `conda activate MyRecall`。
- 本机默认端口 8083（不使用 18083）。
