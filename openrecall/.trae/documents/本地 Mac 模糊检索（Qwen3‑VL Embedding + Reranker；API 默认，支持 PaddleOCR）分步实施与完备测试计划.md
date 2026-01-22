## 总体原则
- 运行前统一：conda activate MyRecall；server/client 均在本地 mac，端口用 8083。
- Qwen3‑VL‑Embedding/Reranker：默认走 API；当需要真实 API 测试时我会提示你提供 api‑key；始终保留本地模型选项作为备用与离线模式。
- OCR：保留 doctr，同时新增 PaddleOCR（可选切换）。
- 每一步独立完成、带完备测试，不影响其他功能；能启动 server 做端到端验证。

## Pipeline 概览（模型与数据流）
- Ingest：Client 截图 → Server 落盘 PNG + 写 SQLite PENDING
- Index（Worker）：OCR(doctr/Paddle)、Vision 描述(Qwen3‑VL 本地/API)、Qwen3‑VL‑Embedding 生成 image_embedding → 写 DB → 建 FTS →（可选）建向量索引（sqlite‑vss）
- Query：解析时间（dateparser/jionlp）→ Hard Filter → 向量召回（text→image）+ FTS 召回 → RRF 融合 → Qwen3‑VL‑Reranker 重排 → UI 展示并标注来源/证据

## 阶段化实施（功能/效果/测试）

### Phase 0：配置与 Provider 框架
- 功能：
  - 新增 provider 选择与开关（默认 API）：
    - MM_EMBEDDING_PROVIDER=api|local，MM_EMBEDDING_MODEL_NAME
    - RERANK_PROVIDER=api|local，RERANK_MODEL_NAME，RERANK_ENABLED，RERANK_TOPK
    - OCR_PROVIDER=doctr|paddleocr|dashscope|openai，VISION_PROVIDER=local|dashscope|openai
    - VECTOR_BACKEND=cache|sqlite_vss，HARD_LIMIT_RECENT_N
  - 工厂扩展：在 [factory.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/factory.py) 新增 get_mm_embedding_provider()/get_reranker_provider()
- 效果：一套可插拔架构，默认 API，随时切到本地；无 key 时不崩溃（mock/降级）。
- 测试：
  - 单测：配置默认值与环境覆盖；Provider 接口契约（空输入、异常路径、返回类型）。

### Phase 1：DB Schema + FTS
- 功能：
  - entries 新增列 image_embedding BLOB；
  - 新建 FTS5 虚表 entries_fts，索引 text/description/title/app。
- 效果：同时支持跨模态向量检索与关键词召回。
- 测试：
  - 单测：schema 存在性、BLOB 读写；FTS 查询能命中最小样本。
  - 回退：FTS 不可用时降级不崩溃。

### Phase 2：PaddleOCR Provider（新增）
- 功能：
  - 在 ai/providers.py 增加 PaddleOCRProvider；工厂支持 OCR_PROVIDER=paddleocr。
- 效果：中文/截图 OCR 更强可选项。
- 测试：
  - 单测：加载失败/CPU 环境提示；小样例图片能返回文本；与 doctr 行为对比。

### Phase 3：Qwen3‑VL‑Embedding（API 默认，本地可选）
- 功能：
  - 新增 MultimodalEmbeddingProvider：embed_text()/embed_image()；
  - API 版本：OpenAI‑compatible/DashScope 多模态 embedding 封装；本地版本：transformers 取 EOS hidden state 并 L2 normalize（参考官方）。
  - Worker 写入 image_embedding；完成时 upsert FTS。
- 效果：实现真正 text→image 召回；入库即具备跨模态向量。
- 测试：
  - 单测（mock provider）：shape/dtype/归一化；异常路径。
  - 慢测（本地/标记 model）：同图重复 embed 相似度≈1。
  - API 合约测试：mock HTTP；当需要真实连通性测试时，我会提示你提供 api‑key。

### Phase 4：Query Parsing（dateparser/jionlp）+ Hard Filter
- 功能：
  - 解析“昨天/上周三/下午”等 → (start_ts,end_ts)；从 q 剥离时间片段得到 q_semantic/q_keywords。
  - 在 SQLite 先做硬过滤（时间窗/状态）。
- 效果：候选集显著缩小，性能与准确性提升。
- 测试：
  - 单测：冻结 now，覆盖 20+ 中文表达；
  - 集成：跨天数据仅返回窗口内截图。

### Phase 5：向量检索后端（先保底，再规模化）
- 功能：
  - cache 模式：维护内存 id→embedding 映射，仅针对硬过滤后的集合；
  - sqlite‑vss 模式（推荐）：建 HNSW 索引，支持 ANN topK。
- 效果：避免“Python 全量扫描”陷阱；10 万级仍可交互。
- 测试：
  - 性能基准：同一查询二次请求命中缓存更快；随机向量 1–5 万条下 ANN 耗时符合预期。

### Phase 6：FTS 召回（关键词通道）
- 功能：FTS(BM25) topK；输出候选 id 与 rank。
- 效果：错误码/函数名/日志关键词的 precision 明显提高。
- 测试：
  - 单测：构造 npm ERR!/TypeError/函数名样本，命中与排序正确。

### Phase 7：融合（RRF 替代线性加权）
- 功能：RRF：rrf(doc)=Σ 1/(k+rank_i)，k=60；融合向量与 FTS 两路排名。
- 效果：排序稳健，无需分数归一化与魔法权重。
- 测试：
  - 单测：两路冲突样本输出符合直觉；边界（单路为空/重复）。

### Phase 8：Qwen3‑VL‑Reranker（二阶段重排；API 默认，本地可选）
- 功能：
  - RerankerProvider：对 RRF 后 topN（默认 50）输出相关性分数；
  - API 版本：OpenAI‑compatible/DashScope；本地版本：transformers，按官方 yes/no 概率取分。
- 效果：Top 结果更贴近“正在调 BUG/修复失败”等真实意图。
- 测试：
  - 单测：mock 分数验证重排正确与 topN 截断；
  - 慢测：真实模型对少量候选稳定输出；
  - API 合约：mock HTTP；当需要真实连通测试时，我会提示你提供 api‑key。

### Phase 9：UI 可解释性（Why this result）
- 功能：
  - 卡片角标：关键词命中 / 语义匹配；
  - 高亮 FTS 命中片段；可选显示 rerank/vec 分数。
- 效果：用户一眼看懂“这是搜到的还是模型看出来的”。
- 测试：
  - E2E：分别触发关键词与纯语义查询，断言角标与高亮存在。

### Phase 10：端到端验收（启动 server）
- 功能：
  - 启动 server（8083）、录入 20 张包含 IDE/终端/报错截图；
  - 查询：“我昨天下午修改的代码BUG”。
- 效果：Top10 至少 1–3 张强相关；启用 rerank 后 Top3 进一步提升。
- 测试：
  - 脚本导出 top10（timestamp+来源标签+分数）；对比 rerank 前后差异。

## 代码改动落点（主要文件）
- [factory.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai/factory.py)：新增多模态 embedding/reranker 的 provider 选择；OCR 加 Paddle。
- ai/providers.py：新增 PaddleOCRProvider、MultimodalEmbeddingProvider(API/Local)、RerankerProvider(API/Local)。
- server/worker.py：写入 image_embedding、upsert FTS；保留 text/description。
- server/app.py：引入 Query Parsing、RRF 融合、rerank 调用；
- server/database.py：schema 迁移 + FTS 建表/查询；（可选）sqlite‑vss 封装。
- templates/search.html：来源角标与证据高亮。
- tests/：为每步新增针对性与完备用例（含 mock 与慢测）。

## API‑Key 提示策略
- 当配置为 API 且检测到缺少/不可用 key 时，测试输出清晰提示“请提供 api‑key 进行连通性验证”；我会在那一步询问你输入 api‑key。