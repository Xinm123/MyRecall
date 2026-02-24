# MyRecall vs screenpipe：项目对比分析报告

> **Historical Baseline**: This document is retained as a historical comparison snapshot (2026-02-04).  
> It is not the authoritative source for current vision-only roadmap decisions.  
> For current alignment decisions, see `v3/references/myrecall-vs-screenpipe-alignment-current.md`.

> 生成日期：2026-02-04  
> 目标读者：希望在“本地数字记忆（capture → index → search → timeline/chat）”方向做取舍、集成或二次开发的维护者/开发者  
> 结论先行：两者都走 **local-first**，但 MyRecall 更偏“**截图 + Web UI + 强混合检索（含 rerank）**”，screenpipe 更偏“**桌面端产品化 + 视觉/音频/事件全量采集 + 时间轴流式体验 + Agent/插件生态**”。

---

## 1. 一句话定位（What/Why）

### MyRecall（OpenRecall fork）

- **定位**：隐私优先的本地“屏幕回忆”系统，核心是 **定时截屏 → OCR/VLM/Embedding → 混合检索 → Web UI**。
- **关键特点**：
  - Client/Server 解耦：Client 只负责采集+落盘队列+上传；Server 负责异步 AI 处理与检索。
  - 搜索链路更“搜索引擎化”：**向量召回（LanceDB）+ 关键词召回（FTS5）+ 线性融合 + Cross-Encoder rerank**。
  - 提供“把数据放到加密盘”的操作指南（BitLocker / Disk Image / LUKS）。

### screenpipe

- **定位**：桌面的 24/7 记忆层（开源版 rewind），强调“**录屏+音频+可选 UI events → 本地存储 → AI 搜索/时间轴/聊天工具调用**”。
- **关键特点**：
  - Rust 后端一体化采集与服务：视觉采集、视频分片写盘、OCR 批量写库、API/WS、时间轴 streaming。
  - 数据形态更“产品化”：视频 chunk + 抽帧（按需）+ SQLite 索引；内建 Desktop App（Tauri + Next.js）。
  - 生态与集成更积极：JS SDK、CLI、（Claude）MCP 扩展、可选 cloud sync/remote agent 的路线。

---

## 2. 快速对比表（核心维度）

| 维度 | MyRecall | screenpipe |
|---|---|---|
| 主语言/栈 | Python（Flask + worker 线程），本地模型/外部 API 可选 | Rust（server/capture/db/vision/audio/events），桌面端 Tauri + Next.js |
| 捕获形态 | **截图**（PNG/WEBP）按间隔采集；MSSIM 去重 + idle 检测 | **录屏分片**（mp4）+ OCR 结果；帧差/哈希跳帧降载；多窗口裁剪 |
| 音频 | 目前文档主线是屏幕截图（可扩展） | **一等公民**：多设备录音 → 分段 → STT → 去重/重叠清理 → 入库 |
| UI Events | 未见完整链路（偏截图+元数据） | **可选**：Accessibility/Input 事件采集（权限与隐私开关强约束） |
| 存储结构 | `screenshots/*.png` + `recall.db` + `fts.db` + `lancedb/` | `~/.screenpipe/db.sqlite` + `video/audio chunks`（DB 存 file_path + offset） |
| 向量检索 | LanceDB（独立向量库） | SQLite 扩展（sqlite-vec/embedding 表） |
| 关键词检索 | SQLite FTS5（独立 `fts.db`） | SQLite FTS（在同一 `db.sqlite` 里迁移/触发器维护） |
| 排序质量 | **Top30 Cross-Encoder rerank**（显著提升精排） | 语义检索 + 关键词检索（未见 cross-encoder rerank 描述） |
| API 形态 | REST + Web UI（浏览器） | REST + WebSocket（时间轴/事件流）+ Desktop App UI |
| 运行时控制面 | `/api/config` + Client `/api/heartbeat` 同步开关；Server worker 可取消/降级 | CLI/设置驱动；服务端含缓存、抽帧、PII 打码开关；事件总线 |
| 资源开销侧重点 | AI 处理主要在 Server；截图频率决定 IO/体积 | 编码/录音/OCR 长期运行；官方给出 CPU/RAM/存储月增量经验值 |
| 隐私/安全 | 强调“数据可离线、可放加密盘”；数据本地可控 | 强调“100% local”；提供可选 PII redaction；UI events/键盘/剪贴板更敏感 |
| 许可证 | **AGPLv3**（网络服务强 copyleft） | **MIT**（宽松，商用友好） |

---

## 2.1 安装、运行与配置（Developer/Operator 视角）

> 这一节的重点不是“怎么跑起来”，而是对比两者的 **运行形态**：一个更像“可拆分的本地服务（含采集端）”，一个更像“桌面产品（含服务端能力）”。

### MyRecall：Python 服务 + 可拆分 Client/Server

- 常见安装/运行路径
  - 安装（可编辑）：`cd MyRecall && python -m pip install -e ".[test]"`
  - 运行（combined）：`python -m openrecall.main`
  - 运行（split）：`python -m openrecall.server` + `python -m openrecall.client`
  - 使用 env 文件：`./run_server.sh --env=myrecall_server.env`、`./run_client.sh --env=myrecall_client.env`
- 默认端口/目录（来自当前代码与文档）
  - Web 端口：`OPENRECALL_PORT` 默认 `8083`
  - Server 数据目录：`OPENRECALL_SERVER_DATA_DIR` 默认 `~/MRS`
  - Client 数据目录：`OPENRECALL_CLIENT_DATA_DIR` 默认 `~/MRC`
- 配置面（环境变量体系很完整）
  - 采集：`OPENRECALL_CAPTURE_INTERVAL`、`OPENRECALL_PRIMARY_MONITOR_ONLY`
  - AI/推理：`OPENRECALL_DEVICE`（cpu/cuda/mps）、`OPENRECALL_AI_PROVIDER` 以及 OCR/Vision/Embedding 的 provider/model/api_base/api_key 细分开关
  - 网络：`OPENRECALL_API_URL`、`OPENRECALL_UPLOAD_TIMEOUT`

**解读**
- MyRecall 更偏“服务架构”：你可以把采集端放在一台机器、处理/检索端放在另一台机器（当然也可本机）。
- 与此同时，AI 依赖具备可插拔性：既可全离线（本地模型），也可走 OpenAI-compatible 代理或云服务。

### screenpipe：Rust 常驻进程 + Desktop App

- 常见安装/运行路径
  - 安装（CLI）：`curl -fsSL get.screenpi.pe/cli | sh` → `screenpipe`
  - 源码构建：`cd screenpipe && cargo build --release --features metal`
  - Desktop App：`cd apps/screenpipe-app-tauri && bun install && bun run dev`（或 `bun run tauri dev`）
- 默认端口/目录（来自 CLI 与文档）
  - API 端口：CLI `-p/--port` 默认 `3030`
  - 数据目录（默认 base）：`~/.screenpipe/`（包含 `db.sqlite`、video/audio chunks 等）
- 平台权限（尤其 macOS）
  - Screen Recording、Microphone、Accessibility/Input monitoring（UI events 属于 opt-in 且敏感）

**解读**
- screenpipe 更偏“桌面产品化”：服务端能力（API/WS/抽帧/缓存）是为了支撑 Desktop App 的时间轴与交互体验。
- 同时它也为外部集成预留了 API/SDK（例如 `/search`、JS SDK、MCP 扩展），更像“本地记忆基础设施”。

---

## 2.2 测试与质量门槛（对维护者很关键）

### MyRecall

- pytest 为主，默认排除 `e2e/perf/security/model/manual` 等重测试；可启用覆盖率门槛（>=80%）。
- 安全检查路径明确：Bandit + pip-audit（需要额外依赖组）。
- 具备 Playwright E2E 测试通道（但默认不跑，避免 CI/本地被拖慢）。

### screenpipe

- Rust：`cargo test`，并鼓励 `cargo fmt` + `cargo clippy --all-targets --all-features`。
- UI：Vitest（`bun run test`），另外有较完整的手工测试清单（面向发布前验证）。

**解读**
- MyRecall 的“测试门槛”更偏后端服务工程（覆盖率、分层 markers、可选安全扫描）。
- screenpipe 的“测试门槛”更偏跨平台桌面产品工程（权限、设备、长时间运行、资源曲线、手工回归更重要）。

---

## 3. 架构与数据流对比（从 capture 到 search）

### 3.1 MyRecall：Client/Server 解耦 + 异步处理流水线

**主链路（概念）**

1. Client：`ScreenRecorder` 定时截图 → 去重/idle → 写入磁盘队列（`~/MRC/buffer/*.webp + *.json`）
2. Client：`UploaderConsumer` FIFO 消费队列 → `multipart/form-data` 上传 `POST /api/upload`
3. Server：`/api/upload` 快路径落盘 `screenshots/{timestamp}.png` + `recall.db entries(status=PENDING)`，立即返回 `202`
4. Server：后台 `ProcessingWorker` 拉取队列任务 → OCR → VLM caption/scene/action → keywords → fusion text → embedding
5. Server：写入三层索引/存储：
   - `recall.db`：任务状态与 legacy 字段
   - `fts.db`（FTS5）：OCR/caption/keywords 全文索引
   - `lancedb/`：`SemanticSnapshot` 向量检索主存储
6. Search：QueryParser（时间/必含关键词）→ 向量 + 关键词双召回 → 线性融合 → **rerank Top30**

**优势**
- 断网不丢：磁盘队列天然容错；上传成功才删本地队列。
- 采集端负担轻：Client 不做重 AI（更接近“采集 agent”）。
- 检索质量上限高：有 rerank，且索引层次清晰（FTS 与向量库分工明确）。

**代价**
- 组件较多（Client/Server/多 DB/向量库），运维/迁移复杂度更高。
- Web UI 体验受限于“浏览器 + 请求-响应”，时间轴流式体验需要额外工作。

### 3.2 screenpipe：一体化采集 + SQLite 索引 + 时间轴 Streaming

**视觉链路（概念）**

1. `screenpipe-vision::continuous_capture`：截屏/裁剪/ OCR，并做 frame diff 跳帧降载
2. `VideoCapture`：分别把“视频帧”和“OCR 帧”推进队列
3. ffmpeg 写视频分片（chunk），`FrameWriteTracker` 记录 **真实 offset**（解决丢帧导致的“帧号≠视频位置”问题）
4. OCR 批量入库：用 `FrameWriteTracker` 修正 offset → `insert_frames_with_ocr_batch(...)`
5. Retrieval：
   - `/search`：统一检索入口（OCR/Audio/UI/Input union + 多维过滤）
   - `/frames/:id`：按需抽帧（带缓存；可选 `redact_pii`）
   - `/stream/frames`：WS 时间轴（initial bulk + live polling 推送）
   - `/ws/events`：事件总线（可用于跨组件联动）

**音频链路（概念）**

- 多设备录音 → 分段（overlap）→ STT → overlap cleanup（同设备）→ cross-device dedup（避免系统输出+麦克风重复）→ speaker embedding 归一 → 入库与可检索

**优势**
- 用户体验强：Desktop App + WS 时间轴更贴近“rewind”类产品。
- 数据形态更完整：视频/音频/事件构成“连续历史”，比单纯截图更适合回放与复盘。
- 系统工程扎实：SQLite WAL/锁竞争策略、批量入库、抽帧缓存、offset 纠偏等偏工程型优化。

**代价**
- 长期资源占用更显著：编码/录音/转写/OCR 会带来稳定 CPU/RAM/磁盘增长。
- 权限与隐私面更大：音频、Accessibility、键盘/剪贴板属于高敏采集，需要更强的默认策略与合规姿势。

---

## 4. 检索与“结果质量”对比（为什么 MyRecall 的 rerank 很关键）

### MyRecall：三段式检索更像“搜索引擎”

- Stage1：向量召回（LanceDB）+ 关键词召回（FTS5）
- Stage2：线性融合（base + boost）+ FTS-only rescue（base=0.2）
- Stage3：**Cross-Encoder rerank Top30**（若分数非全零则覆盖 Stage2 排序）

这意味着：当“用户 query 很短/含歧义/需要精排理解”时，MyRecall 更容易把真正相关的结果排到前面（尤其是 OCR 噪声较大时）。

### screenpipe：更强调“检索 + 体验”

- `/search` 强过滤（time/app/window/url/speaker）+ 内容 union（OCR/Audio/UI/Input）
- `/search/keyword` 给 `text_positions`，用于 UI 高亮/定位
- `/semantic-search` 基于 embeddings 的相似搜索

从文档描述来看，它更像“产品化检索 API”，在体验层（timeline/抽帧/缓存/WS）上投入更多；精排模型（cross-encoder）不是主线叙事的一部分。

**建议**
- 若你在 screenpipe 侧遇到“搜索结果相关性不够”的反馈，引入 MyRecall 同款“TopK rerank”是最直接的质量提升杠杆。
- 若你在 MyRecall 侧遇到“找得到但不好用/不顺滑”的反馈，screenpipe 的 WS timeline + 抽帧缓存 + Desktop App 信息架构是更高 ROI 的体验方向。

---

## 5. 隐私、安全与许可证（容易被忽略但决定路线）

### 5.1 隐私面差异

- MyRecall 的敏感面主要集中在“屏幕截图内容”，并通过“建议用户把数据目录放到加密卷”来解决设备丢失/被拷贝风险。
- screenpipe 在此基础上还引入：
  - 音频（可能包含会议隐私）
  - UI events（键入/剪贴板/窗口切换等）
  - 可选 PII 打码（抽帧时 redaction）

因此 screenpipe 更需要：
- 默认最小采集（opt-in + 白名单/黑名单）
- 可解释的隐私开关与可审计的数据落盘策略
- 清晰的“敏感数据不会离开本机”的边界（尤其当引入 cloud sync/remote agent 时）

### 5.2 许可证对商业化/集成的影响

- MyRecall：AGPLv3  
  - 如果你把它改造成对外提供的网络服务（SaaS），AGPL 会要求提供对应源代码给服务用户。
- screenpipe：MIT  
  - 更宽松，适合做商业发行与闭源增值层。

**集成提示（非常现实）**
- 把 MIT 代码引入 AGPL 项目一般没问题（MIT 兼容性好），但反过来把 AGPL 代码引入 MIT 项目会“传染”到整体分发/服务策略，影响商业路线。

---

## 6. 选择建议（按目标场景）

### 更适合选 MyRecall 的场景

- 你要的是“隐私优先 + 可控 + 轻量采集 + 强检索质量”，并接受 Web UI。
- 你想在 Python 生态里快速迭代 OCR/VLM/embedding/rerank，或对模型/供应商切换有强需求。
- 你更关注“把信息检索出来”而不是“连续回放体验”。

### 更适合选 screenpipe 的场景

- 你更看重“桌面产品体验”：时间轴滚动、抽帧预览、流式更新、聊天工具调用。
- 你需要音频转写/说话人/跨设备去重，或者希望把“屏幕+音频+事件”统一检索。
- 你希望通过 SDK/MCP/插件（pipes）把记忆层接入更大的自动化生态。

---

## 7. 互补与潜在融合方向（给维护者的路线图）

> 下面不是“必须做”，而是把两者的优势拆成可以落地的模块化选择。

### 方向 A：MyRecall 借鉴 screenpipe 的“体验与工程化”

1. **时间轴体验升级**：引入 WS streaming + 客户端缓存（类似 `stream_frames` 的两段式响应）
2. **媒体层演进**：从“孤立 PNG”走向“chunk + 按需抽帧”（降低 UI 预览成本，提升连续性）
3. **性能与并发策略**：参考 SQLite WAL + `BEGIN IMMEDIATE` + 批量写库的组合，减少锁竞争与写放大

### 方向 B：screenpipe 借鉴 MyRecall 的“检索质量”

1. **引入 Cross-Encoder rerank**：对 TopK 结果做精排（尤其 OCR 噪声大、query 短时）
2. **更清晰的融合策略**：把 keyword + semantic 的融合规则显式化（可解释性更强）
3. **时间语义解析**：把“today/yesterday/last week + quoted mandatory keywords”固化为 query parser 能力

### 方向 C：更“松耦合”的集成（推荐优先考虑）

- 以 **导出/导入** 或 **API 互调** 形式集成，而不是直接合并代码：
  - screenpipe 产出结构化摘要/embedding → MyRecall 做 rerank/融合检索服务
  - MyRecall 只做“强检索服务”，screenpipe 做“强体验客户端”
- 好处：减少许可证/语言栈/发布链路耦合，迭代更安全。

---

## 8. 参考索引（便于你继续深挖）

### MyRecall（source of truth）

- 架构与数据流：`MyRecall/docs/MyRecall_V2_Analysis.md`
- 加密存储指南：`MyRecall/docs/encryption.md`
- 运行时配置：`MyRecall/openrecall/shared/config.py`
- 搜索引擎实现线索：`MyRecall/openrecall/server/search/engine.py`

### screenpipe（source of truth）

- 数据流与 pipeline：`screenpipe/docs/dataflow-pipeline.zh-en.md`
- Server 入口：`screenpipe/crates/screenpipe-server/src/bin/screenpipe-server.rs`
- DB 与写入策略：`screenpipe/crates/screenpipe-db/src/db.rs`
- Desktop App 时间轴：`screenpipe/apps/screenpipe-app-tauri/components/rewind/timeline.tsx`


我已阅读并将使用 `superpowers:brainstorming` 来把“你要从 screenpipe 借鉴什么、优先级是什么”澄清到位；并用 `superpowers:writing-plans` 在你选定方向后，把借鉴落地成可执行的 MyRecall 实施路线（具体到要改哪些模块/接口/验收点）。

**基于代码的事实来源（我对齐过的入口）**
- MyRecall 端到端：`MyRecall/docs/MyRecall_V2_Analysis.md`、`MyRecall/openrecall/client/*`、`MyRecall/openrecall/server/*`
- screenpipe 端到端：`screenpipe/docs/dataflow-pipeline.zh-en.md`、`screenpipe/crates/screenpipe-server/src/*`、`screenpipe/crates/screenpipe-db/src/db.rs`、`screenpipe/apps/screenpipe-app-tauri/*`

---

# screenpipe → MyRecall 的借鉴路线 （2026-02-04）

## 1) 定位/产品形态：相同目标，不同“落地形态”

**共同点**
- 都是“本地优先的数字记忆层”：采集 → 处理 → 本地存储 → 检索 → UI 消费。
- 都强调隐私/离线与可控存储。

**差异点**
- **MyRecall（OpenRecall fork）**：Python 单仓（Client + Flask Server + Worker + Web UI），更像“可跑起来的研究/原型 + web 控制台”。核心链路是 *截图→上传→异步处理→搜索*。
- **screenpipe**：Rust workspace（capture/vision/audio/db/events/server）+ Tauri/Next.js 桌面端 + JS SDK/CLI/agents，更像“产品化的本地基础设施层”。核心链路是 *连续采集（屏幕+音频+可选事件）→统一索引→时间轴/聊天/自动化生态*。

---

## 2) 端到端数据流对照（Capture → Process → Store → Retrieve → UI）

| 维度 | MyRecall | screenpipe | 对 MyRecall 的启发 |
|---|---|---|---|
| **采集位置** | Client 采集（`openrecall/client/recorder.py`），Server 不采集 | Server 自己持续采集（`screenpipe-server` + `screenpipe-vision/audio`） | 是否要继续“Client/Server 分离”？还是合并成单机常驻服务 |
| **采集形态** | 每次一张截图（buffer 用 `.webp`，Server 落 `*.png`） | 视频分片（chunk）+ 帧元数据；需要图片再抽帧（`GET /frames/:id`） | “视频分片 + 抽帧”是降存储/提性能的关键架构点 |
| **去重/降载** | MSSIM 相似度过滤（`mean_structured_similarity_index`）+ idle 检测 | capture 侧 frame diff/跳帧 + 可选 adaptive fps（doc/代码提到） | 去重建议前移到最源头，并把“丢帧/错位”纳入设计 |
| **摄入模型** | `POST /api/upload` 快路径：落盘 + 入队（`entries:PENDING`），返回 202 | capture loop 直接写媒体 + 批量写 DB（frames/ocr/audio） | MyRecall 的“快路径 + 后台重算”思路是对的；screenpipe 更强调批量写与一致性 |
| **后台处理** | Python Worker：OCR→vision→keywords→embedding→FTS+向量库 | Rust pipeline：OCR/音频转写/事件→批量入库→embedding→缓存→检索 | MyRecall 可以借鉴：批量写、缓存、统一数据模型、更多模态（audio/ui events） |
| **存储** | `recall.db`（队列/元数据）+ `fts.db`（FTS）+ `lancedb`（向量）+ screenshots 文件 | 单 SQLite（WAL/迁移/FTS/sqlite-vec）+ 视频/音频文件；DB 存 file_path+offset 索引 | “一库多表 + 迁移 + 并发策略”可显著降低锁/一致性问题 |
| **检索 API** | `GET /api/search`（返回 SemanticSnapshot 扁平字段）+ memories/timestamps 等 | `GET /search`（统一入口，多 content_type + 强过滤）+ `/search/keyword`（text positions）+ `/semantic-search` + WS | text positions（高亮/定位）和“统一检索入口”对 UI/生态很重要 |
| **时间轴 UI** | Web 模板 + slider（一次性拿 timestamps，切图 `/static/{ts}.png`） | 桌面端 Timeline WS：一次请求 + initial bulk + live polling + UI 本地缓存/去重/重连 | WS timeline + 缓冲 flush + 本地缓存，是“体验质变”的点 |
| **聊天/工具调用** | 目前无“chat + tool-call”链路（主要是 search 页面） | `GlobalChat` 用 tool-call 触发 `/search`，并做强截断/限额 | 这是把“搜索”升级为“问答/总结/工作流”的关键一层 |
| **云同步** | 偏向本地加密盘（`MyRecall/docs/encryption.md`） | 有 zero-knowledge 同步抽象（doc 里有 provider→加密→上传→synced_at） | 若 MyRecall 想做“多端/备份”，screenpipe 的 sync 抽象可直接借鉴 |

---

## 3) 工程实现层面的“可直接借鉴点”（screenpipe → MyRecall）

下面这些是“方法/实现”层面最值得抄作业的点（不等于要 1:1 复刻产品）：

1) **“视频分片 + 帧索引 + 按需抽帧”**  
- screenpipe：DB 里记录 `video_chunks.file_path` + `frames.offset_index`，需要图片时 `GET /frames/:frame_id` 用 ffmpeg 抽帧并缓存。见 `screenpipe/docs/dataflow-pipeline.zh-en.md`（Vision/Timeline/frames 章节）  
- MyRecall 当前：每次截图就是一个文件，timeline 就是切文件。  
- 借鉴价值：存储/IO/查询都更可控，后续做“滚动/预览/回放”更自然。

2) **SQLite 并发与可靠写入策略（非常硬核、非常实用）**  
- screenpipe：WAL + busy_timeout + `BEGIN IMMEDIATE` + retry + 连接池上限（`screenpipe/crates/screenpipe-db/src/db.rs`）  
- MyRecall：`sqlite3.connect` 默认策略，且把 FTS/主库拆成两个 DB（`MyRecall/openrecall/server/database/sql.py`）  
- 借鉴价值：减少 “database is locked”、降低写竞争、让 timeline/search 在写入时仍稳定读。

3) **Timeline 通过 WebSocket 做“历史批量 + 当日增量”**  
- screenpipe：`WS /stream/frames`，UI 侧还有 buffer flush（150ms）、timestamp 去重、断线重连不清屏、localforage 缓存（doc Timeline 章节）  
- MyRecall：一次性 timestamps + slider；数据量一大体验会崩。  
- 借鉴价值：这套“渐进加载 + 乐观 UI”是桌面记忆产品的标准答案。

4) **Keyword 搜索返回 text positions（高亮/定位的基础设施）**  
- screenpipe：`GET /search/keyword` 返回 `SearchMatch[]` + `text_positions`（doc Retrieval 章节）  
- MyRecall：当前 search 主要返回“结果卡片”，高亮/定位能力弱。  
- 借鉴价值：让搜索结果可以“跳转到具体帧、具体位置”，体验更像“可检索的录像”。

5) **事件总线（WS /ws/events）把系统做成可扩展平台**  
- screenpipe：ocr_result / transcription / 以及 UI events 都可广播，外部也能发 event 再广播（doc /ws/events）  
- MyRecall：目前主要是 HTTP 拉取与页面渲染。  
- 借鉴价值：为后续“插件/自动化/agent”铺路。

6) **Chat 的 tool-call 设计（严格限额/截断/超时）**  
- screenpipe：chat 不直接塞库，而是“模型按需调用 search 工具”，并强约束输出长度（doc Chat 章节）  
- 借鉴价值：你可以在 MyRecall 上快速实现“问昨天做了什么/找某个报错/总结会议”等高价值能力，而不必先重构存储。

---

## 4) MyRecall 其实也有 screenpipe 值得学的点（建议保留）

- **Client 磁盘队列 buffer + 上传退避**（断网不丢）：`openrecall/client/buffer.py`、`consumer.py`  
- **Server 快路径 202 Accepted + 后台重算**（避免阻塞上传）：`openrecall/server/api.py::upload` + `worker.py`  
- **运行时开关 + 心跳同步**（控制采集/上传/AI）：`openrecall/server/config_runtime.py` + `client/recorder.py::_send_heartbeat`

这些机制和 screenpipe 的“持续采集”不是冲突关系；你可以决定继续 Client/Server 分离，或改成单机常驻服务。

---

## 5) 许可证/复用方式（你后面真要“借鉴实现”会碰到）
- MyRecall：AGPLv3（`MyRecall/README.md`）  
- screenpipe：MIT OR Apache-2.0（`screenpipe/Cargo.toml` 的 workspace license）  
一般来说，把 MIT/Apache 代码借鉴进 AGPL 项目是可行的，但要注意保留必要的版权/许可声明；如果只是“学习架构与思路”则影响更小。

---

### 为了把“借鉴路线”写成你可直接照着做的实施清单：
1) **架构/存储/性能（推荐）**：向“视频分片+统一 DB+WS timeline”靠拢  
2) **搜索体验升级**：keyword 高亮定位 + 语义/混合检索能力对齐  
3) **多模态与生态**：音频转写、UI events、chat tool-call、SDK/agent
