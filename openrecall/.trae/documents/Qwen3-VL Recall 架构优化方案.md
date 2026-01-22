# Qwen3-VL Recall 本地 MVP 增强方案

本方案将在本地 Mac 环境（Server + Client）实现基于 Qwen3-VL 的多模态检索增强，重点解决“模糊语义检索”和“自然语言时间过滤”。

**运行环境配置**
- 端口：使用 `8090` (Server) / `8091` (Client) 以避开 18083。
- 环境：所有命令前强制执行 `conda activate MyRecall`。
- 模式：本地开发模式 (Localhost)。

## Step 1: 基础设施增强 (Data Schema & Indexing)

**目标**：确保数据层支持混合检索（Hybrid Search）。

1.  **Schema 确认与补全**：
    -   确认 SQLite `entries` 表已包含 `text` (OCR结果) 和 `timestamp`。
    -   (如有缺失) 执行 DB Migration 补全字段。
2.  **引入 Keyword Index (BM25)**：
    -   安装 `rank_bm25`。
    -   在 Server 启动时，将最近 N 条（如 10,000 条）记录的 OCR 文本加载到内存构建 `BM25Okapi` 索引，用于精确/模糊关键词匹配。

## Step 2: 自然语言 Query 解析 (The Query Parser)

**目标**：让系统听懂“昨天下午”、“上周五”等时间指令。

1.  **引入时间解析库**：
    -   安装 `dateparser` (支持中文/英文自然语言时间解析)。
2.  **实现 `QueryParsingService`**：
    -   **输入**："我昨天下午改的代码 BUG"
    -   **处理**：
        -   提取时间实体 -> 转换为 Unix Timestamp Range (e.g., `1705824000` - `1705845600`)。
        -   保留剩余文本 -> "改的代码 BUG" (用于语义检索)。
    -   **输出**：`QueryObject { text: str, time_filter: (start, end) }`

## Step 3: 多路召回与混合排序 (Hybrid Recall)

**目标**：结合“语义向量”与“关键词匹配”，并强制应用“时间过滤器”。

1.  **重构 `/search` 接口逻辑**：
    -   **Filter (第一层)**：先根据 Step 2 的时间范围过滤 DB 记录（极大缩小搜索空间）。
    -   **Vector Search (第二层)**：计算 `Cosine Similarity` (基于现有的 Embedding)。
    -   **Keyword Search (第三层)**：计算 `BM25 Score` (基于 OCR 文本)。
    -   **Fusion (融合)**：`Final_Score = (Vector_Score * 0.7) + (BM25_Score * 0.3)`。
2.  **输出**：返回 Top 10-20 候选集。

## Step 4: VLM Rerank & Explanation (The Intelligence)

**目标**：使用 Qwen3-VL 进行最终判决和解释。

1.  **实现 Rerank Service**：
    -   对 Top 5 候选图，调用 `AIEngine` (Qwen3-VL)。
    -   **Prompt**: "用户正在寻找：'{query}'。这张截图是否相关？请打分 (0-10) 并简述理由。"
    -   根据 VLM 打分重新排序。
2.  **Explanation UI**：
    -   在前端展示 VLM 生成的“理由”（如：“这张图显示了 VS Code 调试界面，且包含 'Error' 字样，符合‘改 BUG’的描述”）。

## 实施计划 (Todo List)

1.  **环境准备**: 安装 `dateparser`, `rank_bm25`。
2.  **后端开发**:
    -   实现 `utils/time_parser.py`。
    -   修改 `app.py` 引入 BM25 和 Query Parser。
    -   修改 `ai_engine.py` 增加 `rerank_image(image, query)` 方法。
3.  **前端适配**: 修改 Search UI 支持显示 Rerank 后的解释。
