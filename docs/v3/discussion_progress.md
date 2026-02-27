# MyRecall v3 架构评审与讨论进度总览

> **文档目的**：作为架构评审的 "Save Point"（存档点）。记录已收敛并落盘的议题（#1~#3），并为后续未讨论的议题（#4~#9）提供提纲与核心争议点，确保任何时候切入会话都能保持上下文连续性。

## 🟢 阶段一：已完成并落盘的议题 (Completed)

以下议题已完成深度讨论，决策已固化并同步至 `spec.md`, `roadmap.md`, `open_questions.md` 及对应 ADR。

### #1 对齐策略与核心边界 (Decisions 001A-013A)
- **核心定位**：Edge-Centric（Host 轻量采集，Edge 重负载推理/检索）。
- **对齐基准**：对齐 screenpipe 的能力与行为，但**不**完全对齐拓扑结构。
- **阶段规划**：功能开发 100% 集中在 Phase 1，按 P1-S1~S7 串行交付，P2/P3 进入功能冻结期。
- **验收标准**：Gate 双轨制（功能完成度 + 宽松数值），强制 Markdown 验收记录。

### #2 API 契约与通信协议 (Decisions 014A-020A)
- **Ingest 协议**：Host 到 Edge 采用单次幂等上传（`/v1/ingest`），边缘侧负责异步队列（`pending` -> `processing` -> `completed`）。
- **Search API**：全面放弃 v2 的混合检索（Hybrid），100% 拥抱 FTS + 元数据过滤（对齐 screenpipe）。
- **Chat API**：采用 OpenAI-Compatible 格式并支持 Tool calling schema。

### #3 数据模型与 Migration 策略 (Decisions 021A-023A)
- **表结构对齐**：`ocr_text` 补齐 `app_name`/`window_name`，接受与 `frames` 表更新时的微小 drift。
- **FTS 分工**：`ocr_text_fts` 专职处理 `text` 全文匹配，`frames_fts` 专职处理 `app_name/window_name` 等元数据过滤。
- **Search JOIN 策略**：以 `frames INNER JOIN ocr_text` 为基座，按需 LEFT/INNER JOIN FTS 虚拟表。
- **Migration**：抛弃繁重的 ORM 迁移工具，手写 SQL + `schema_migrations` 表记录，零额外依赖。

---

## 🟡 阶段二：待评审议题 (Pending Topics)

以下议题尚未进行深度讨论。下次会话可直接指定编号（如：“开始讨论 #4”）进行展开。

### #4 Chat Orchestrator 技术选型（Next In Line）
- **核心争议**：RAG 的检索编排是在 Edge 的 Python 后端做，还是下发给前端大模型直接以 Tool call 形式做？
- **需要收敛的决策**：
  - 本地模型（Ollama/Llama.cpp）与云端模型（OpenAI/Anthropic）的路由与统一封装策略。
  - Prompt 模板与上下文窗口裁剪（Context Truncation）策略。
  - 流式输出（Streaming）在前后端链路的实现细节。

### #5 Host Capture 采集器实现细节
- **核心争议**：纯 Python 实现是否能满足 macOS/Windows 的系统底层事件监听？
- **需要收敛的决策**：
  - 触发机制：轮询（Polling）vs 操作系统事件驱动（Event-driven）。
  - Spool Buffer 设计：离线状态下，Host 端的本地缓存使用 SQLite 还是 JSON Lines？
  - 重试退避算法（Exponential Backoff）与死信队列（DLQ）机制。

### #6 Edge Processing Pipeline (OCR & 索引)
- **核心争议**：多 OCR 引擎的调度与切换逻辑。
- **需要收敛的决策**：
  - macOS Apple Vision 框架与 Tesseract / Windows ML 的兼容与降级策略。
  - `ocr_preferred_apps` 的初始名单与动态学习更新机制。
  - AX-first（Accessibility 文本优先）策略下的查重与合并逻辑。

### #7 传输安全与身份验证
- **核心争议**：从 P1 到 P3 的安全渐进式演进路径。
- **需要收敛的决策**：
  - P1 阶段：Static Bearer Token + 局部 TLS 的配置化方案。
  - P2/P3 阶段：双向认证（mTLS）的证书下发与轮转机制。

### #8 可观测性与遥测 (Observability)
- **核心争议**：如何用最少的依赖监控系统健康度？
- **需要收敛的决策**：
  - 核心指标定义：Ingest Lag (延迟), Queue Depth (堆积深度), Search Latency。
  - 收集方案：写入本地 SQLite `metrics` 表，还是暴露 Prometheus `/metrics` 端点？

### #9 P1-S1~S7 各子阶段 Gate 验收自动化细节
- **核心争议**：手工验收成本过高，自动化测试边界在哪里？
- **需要收敛的决策**：
  - 哪些阶段必须挂载真实的 UI 进行 E2E 验收，哪些阶段仅通过 curl/pytest 验收契约？
  - Mock Host 注入测试数据的工程规范。

---

## 📝 如何继续？

在任意新的 Claude / AI 会话中，你可以提供此文件的内容或告知我读取此文件，然后说：
**“我是架构评审官，我们开始讨论 #[编号] 议题。”**
我将自动加载对应的上下文，继续协助你收敛和落盘方案。
