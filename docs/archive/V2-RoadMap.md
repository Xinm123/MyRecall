这是一个为 **Code Agent (如 Cursor, Windsurf, Devin)** 量身定制的 **OpenRecall V2 (Caption-First 架构)** 实施路线图。

我们将整个重构过程划分为 **5 个核心阶段**，共 **18 个细粒度任务**。每个任务都包含明确的 **上下文 (Context)** 和 **执行指令 (Instruction)**，你可以直接将这些指令复制给 AI 执行。

---

### 📅 Phase 1: 数据基石与存储层 (Data Foundation)
> **目标**：建立 LanceDB 向量存储，定义基于 Pydantic 的强类型 Schema，确立“文本优先”的数据结构。

*   **Task 1.1: 依赖管理**
    *   **Context**: 项目需要引入向量数据库和数据验证库。
    *   **Instruction**: "在 `pyproject.toml` (或 `requirements.txt`) 中添加 `lancedb` 和 `pydantic`。如果存在 `numpy` 用于存储的旧依赖，请标记为待移除。运行安装命令确保环境就绪。"

*   **Task 1.2: 定义 Semantic Schema (关键)**
    *   **Context**: 我们需要一个全新的数据结构来支持 Caption-First 架构。
    *   **Instruction**: "创建 `openrecall/server/schema.py`。使用 Pydantic 定义以下模型：
        1.  `Context`: 包含 `app_name`, `window_title`, `timestamp`, `time_bucket`。
        2.  `Content`: 包含 `ocr_text` (完整), `ocr_head` (前300字), `caption`, `keywords` (List[str]), `scene_tag`, `action_tag`。
        3.  `SemanticSnapshot`: 包含 `id`, `image_path`, `context`, `content`。
        4.  **注意**：在 `SemanticSnapshot` 中添加 `embedding_vector` (List[float]) 和 `embedding_model` (str, 默认 'qwen-text-v1')。"

*   **Task 1.3: 初始化 LanceDB 向量库**
    *   **Context**: 使用 LanceDB 替代原本的 SQLite BLOB 存向量。
    *   **Instruction**: "创建 `openrecall/server/database/vector.py`。
        1.  初始化 LanceDB 连接（存储在 `settings.lancedb_path`）。
        2.  定义一个 `SnapshotTable` 类。
        3.  实现 `create_table_if_not_exists`：基于 Schema 定义表结构。
        4.  实现 `add_record(snapshot: SemanticSnapshot)`：将 Pydantic 对象扁平化存入。
        5.  **注意**：LanceDB 需要 `vector` 列，确保将 `embedding_vector` 映射过去。"

*   **Task 1.4: 升级 SQLite 元数据表**
    *   **Context**: SQLite 仍用于任务队列和全文检索 (FTS)。
    *   **Instruction**: "修改 `openrecall/server/database/sql.py`。
        1.  确保 `entries` 表保留用于任务队列状态管理 (`PENDING`, `PROCESSING`)。
        2.  **新增**：启用 FTS5 扩展，创建一个虚拟表 `fts_index`，字段包括 `rowid` (对应 entries.id), `ocr_text`, `caption`, `keywords`。用于关键词倒排索引。"

---

### 🚀 Phase 2: 高效传输管道 (Ingestion Pipeline)
> **目标**：将原本低效的 JSON Base64 传输改为二进制流传输，降低内存开销。

*   **Task 2.1: 客户端上传逻辑重构**
    *   **Context**: Client 目前发送 JSON，效率低。
    *   **Instruction**: "修改 `openrecall/client/uploader.py`。
        1.  不再进行 Image -> NumPy -> JSON 的转换。
        2.  使用 `requests.post` 发送 `multipart/form-data`。
        3.  字段构造：`file` 为图片二进制流，`metadata` 为 JSON 字符串 (包含 timestamp, window info)。"

*   **Task 2.2: 服务端流式接收**
    *   **Context**: Server 需要高效接收文件并落盘。
    *   **Instruction**: "重写 `openrecall/server/api.py` 的 `/api/upload` 接口。
        1.  使用 FastAPI 的 `UploadFile` 接收流。
        2.  **关键**：直接以 `wb` 模式将流写入 `settings.screenshots_path`，不要读入内存。
        3.  解析 `metadata` JSON。
        4.  向 SQLite 写入一条 `PENDING` 记录（只存路径和元数据），返回 202 Accepted。"

---

### 🧠 Phase 3: 智能处理核心 (The Processing Brain)
> **目标**：构建 OCR -> VLM (Tags) -> Fusion -> Embedding 的流水线。

*   **Task 3.1: 关键词提取器 (Keyword Extractor)**
    *   **Context**: 需要从 OCR 文本中提取高价值关键词。
    *   **Instruction**: "创建 `openrecall/server/utils/keywords.py`。
        1.  实现 `KeywordExtractor` 类，读取配置 `KEYWORD_STRATEGY`。
        2.  实现 `local` 策略：对输入文本进行正则分词、停用词过滤、词频统计，返回 Top-10 单词。"

*   **Task 3.2: 升级 Vision Provider (Prompt 工程)**
    *   **Context**: Qwen-VL 现在不仅要描述，还要打标签。
    *   **Instruction**: "修改 `openrecall/server/ai/vision.py`。
        1.  更新 System Prompt：要求模型输出 **JSON 格式**。
        2.  Prompt 内容：'Analyze this screenshot. Output JSON with: "caption" (detailed description), "scene" (e.g., coding, browsing), "action" (e.g., debugging, reading).'
        3.  添加 JSON 解析逻辑，处理模型可能返回的 Markdown 代码块。"

*   **Task 3.3: 结构化文本融合 (Fusion Logic)**
    *   **Context**: 将多模态信息拼接成单一文本，用于 Embedding。
    *   **Instruction**: "创建 `openrecall/server/utils/fusion.py`。
        1.  实现 `build_fusion_text(snapshot: SemanticSnapshot) -> str`。
        2.  **格式要求**：严格按照 `[APP] ... \n [SCENE] ... \n [ACTION] ... \n [CAPTION] ... \n [KEYWORDS] ... \n [OCR_HEAD] ...` 的格式拼接。"

*   **Task 3.4: Worker 主流程重写**
    *   **Context**: 将上述组件串联在 Worker 中。
    *   **Instruction**: "重构 `openrecall/server/worker.py` 的 `process_task` 函数：
        1.  **OCR**: 提取完整文本，并截取 `ocr_head`。
        2.  **Vision**: 调用 VLM 获取 caption, scene, action。
        3.  **Keywords**: 基于 OCR 文本提取关键词。
        4.  **Fusion**: 调用 `build_fusion_text` 生成 `dense_text`。
        5.  **Embed**: 调用 `embedding_provider.embed_text(dense_text)` (注意：只 Embed 这一次)。
        6.  **Store**: 将向量存入 LanceDB，将完整 OCR 存入 SQLite FTS。"

---

### 🔍 Phase 4: 混合检索系统 (Hybrid Search)
> **目标**：实现 FTS (关键词) + Vector (语义) 的双路召回与重排。

*   **Task 4.1: 查询意图解析**
    *   **Context**: 理解用户 Query 是搜时间、搜关键词还是搜语义。
    *   **Instruction**: "修改 `openrecall/server/search.py`。实现 `parse_query(text)`：
        1.  提取简单的时间词（昨天、上周）。
        2.  提取引号内的强制关键词（如 `"error"`）。
        3.  返回结构化对象 `ParsedQuery`。"

*   **Task 4.2: 双路召回逻辑**
    *   **Context**: 结合 LanceDB 和 SQLite FTS。
    *   **Instruction**: "在 `search.py` 中实现 `hybrid_search`：
        1.  **Vector Path**: 将 Query 转向量，LanceDB 搜索 Top-100 (Where 过滤时间/APP)。
        2.  **FTS Path**: SQLite FTS 搜索 Query 关键词，Top-50。
        3.  **Merge**: 按 Snapshot ID 合并结果。如果 ID 重复，给予加权分 (例如 Score = VectorScore * 0.7 + FTSScore * 0.3)。"

*   **Task 4.3: 搜索接口更新**
    *   **Context**: 前端需要更丰富的数据展示。
    *   **Instruction**: "更新 `/api/search`。返回的结果不仅包含图片路径，还要包含 `caption`, `scene_tag`, `keywords`，以便前端展示'为什么搜到了这张图'（可解释性）。"

---

### 🧹 Phase 5: 清理与收尾 (Cleanup)
> **目标**：移除旧代码，更新配置，准备发布。

*   **Task 5.1: 配置项更新**
    *   **Context**: 配置文件需要支持新组件。
    *   **Instruction**: "在 `openrecall/shared/config.py` 中：
        1.  添加 `LANCEDB_PATH`。
        2.  添加 `KEYWORD_STRATEGY` (默认 'local')。
        3.  添加 `EMBEDDING_MODEL_VERSION` (用于版本控制)。"

*   **Task 5.2: 遗留代码移除**
    *   **Instruction**: "删除旧的 `numpy.save` 相关代码。删除旧的基于图像相似度的暴力搜索逻辑。删除 SQLite 中旧的 `embedding` BLOB 字段读写逻辑。"

---

### 💡 给 Agent 的通用提示词 (Meta-Prompt)

在执行上述每个 Task 时，建议在 Prompt 开头加上：

> "当前我们处于 **OpenRecall V2 重构计划** 的 **Phase X - Task Y**。
> 架构核心约束：
> 1. **No Image Embeddings**: 只能使用 Text Embedding。
> 2. **Caption-First**: 依赖 VLM 生成的文本描述。
> 3. **Structured Fusion**: 使用 `[TAG]` 格式拼接文本。
> 请基于这些约束修改代码。"