## Context

P1-S2b 交付了完整的 capture baseline：事件驱动截图 → spool → `/v1/ingest` → `frames` 表 → `NoopQueueDriver`（`pending → completed`）。当前 `processing_mode=noop`，帧入库后无文本提取，无法支撑 S4 检索。

**现有关键组件**：

| 组件 | 位置 | 状态 |
|------|------|------|
| `NoopQueueDriver` | `openrecall/server/queue_driver.py` | ✅ 活跃（poll-loop + 状态机模式） |
| `RapidOCRBackend` | `openrecall/server/ocr/rapid_backend.py` | ✅ 活跃（singleton，`extract_text()` → `str`） |
| `FramesStore` | `openrecall/server/database/frames_store.py` | ✅ 活跃（`advance_frame_status`/`mark_failed`/`get_recent_memories`） |
| `__main__.py` | `openrecall/server/__main__.py` | 有 `noop` 分支，无 `ocr` 分支 |
| 旧 `worker.py` | `openrecall/server/worker.py` | 遗留（含 AI 增强逻辑），v3 主线不调用 |

**约束**：
- spec.md §4.3: OCR-only 处理契约（不生成 caption/keywords/fusion/embedding）
- spec.md §4.7: `processing_mode` 三路分支（noop/ocr/legacy）
- data-model.md Table 2: `ocr_text` 列要求含 `app_name/window_name`（对齐 screenpipe）
- p1-s3.md §2.1: OCR 失败不重试，空文本 `""` 归为 failed

## Goals / Non-Goals

**Goals:**
- 在 `processing_mode=ocr` 下，对 `pending` 帧执行 RapidOCR 并持久化到 `ocr_text`
- 正确标记 `frames.text_source='ocr'` 和 `frames.status`（completed/failed）
- `capture_trigger` 前置校验（fail-loud）
- 幂等防御防止重复处理
- Grid `/` UI 展示 OCR 处理状态与文本预览
- 与 `NoopQueueDriver` 共存，通过 `processing_mode` 配置切换

**Non-Goals:**
- 多 OCR 引擎切换（P1 固定 RapidOCR）
- OCR 失败重试（`retry_count` 保持 0）
- AX/accessibility 路径
- Embedding 表构建
- 旧 `worker.py` 重构

## Decisions

### D1: V3ProcessingWorker 采用 NoopQueueDriver 相同的 poll-loop 模式

**决策**：`V3ProcessingWorker` 继承 `NoopQueueDriver` 的线程架构：daemon thread + `_stop_event` + poll interval + atomic frame advancement。

**理由**：
- `NoopQueueDriver` 的模式已经过 P1-S1/S2 验证，是项目中已有的、可工作的队列驱动模式
- 相同的 `start()`/`stop()`/`join()` 接口使 `__main__.py` 的 shutdown 逻辑可复用
- screenpipe: **intentional divergence** — screenpipe 使用 Rust async channel (`tokio::mpsc`)，v3 采用 Python threading + SQLite poll（Edge-Centric 架构下符合 Python 惯例）

**替代方案**：
- 异步 asyncio 驱动 → 否决：Flask 同步框架，引入 asyncio 增加复杂度但无性能瓶颈需要解决
- 从 `NoopQueueDriver` 继承 → 否决：逻辑差异大（OCR 执行 vs noop 直推），继承带来的耦合风险大于复用收益；采用独立类、复用接口模式

### D2: `extract_text()` 返回值分类与 `failed` 语义

**决策**：基于 `RapidOCRBackend.extract_text()` 的实际返回值行为定义 failed 分类：

| 返回情况 | 分类 | 行为 |
|----------|------|------|
| 抛异常 | `failed` | `error_message='OCR_FAILED: {异常信息}'` |
| 返回 `None` | `failed` | `error_message='OCR_FAILED: null_result'` |
| 返回 `""` 空字符串 | `failed` | `error_message='OCR_EMPTY_TEXT'` |
| 返回非空文本 | `completed` | 写 `ocr_text` + `text_source='ocr'` |

> **实现注意**：当前 `extract_text()` 代码路径不会返回 `None`（D2.1 修复后异常向上传播，正常路径返回 `str`）。`None` 行作为防御性分类保留，`ocr_processor.py` 必须显式处理此路径。

**实现策略（已裁定）**：

**方案 A（采用）**：在 P1-S3 范围内修复 `rapid_backend.py`，让异常向上传播：

```python
# rapid_backend.py extract_text() 修改后（伪代码）
def extract_text(self, image):
    try:
        # ... OCR 执行逻辑 ...
    except Exception as e:
        logger.error(f"RapidOCR extraction failed: {e}")
        raise  # 让调用方区分异常与空文本
```

**理由**：
1. 当前 `RapidOCRBackend.extract_text()` 的错误处理行为（`rapid_backend.py:281-283`）是异常时 `return ""`，无法区分「引擎异常」和「图像无文字」
2. 在 `ocr_processor.py` 中通过包装器规避会导致双层异常处理，增加复杂度
3. 直接修复 `rapid_backend.py` 是最简洁方案，且符合 Python 惯例（异常应向上传播）

**变更范围**：
- `rapid_backend.py`：移除 `try/except` 异常吞并（tasks.md §0.1）
- `rapid_backend.py`：修复 singleton `__new__` 模式（tasks.md §0.2，见 D2.1）
- 此变更属于 S3 范围，无需单独阶段

**screenpipe 对齐**：**aligned** — screenpipe `paired_capture.rs` 也在 OCR 失败/空文本时不写 `ocr_text` 行。

### D2.1: `RapidOCRBackend` singleton `__new__` 修复

**决策**：修复 singleton 模式，确保 `_initialize()` 失败时 `_instance` 不会残留 broken 实例。

**问题**：当前 `__new__` 实现中，`super().__new__()` 已执行并赋值给 `cls._instance` 后才调用 `_initialize()`。若 `_initialize()` 抛异常，`_instance` 已为非 `None` 但没有 `engine` 属性，后续调用 `RapidOCRBackend()` 将返回 broken 实例。

**修复方案**：

```python
# rapid_backend.py __new__ 修改后
def __new__(cls):
    if cls._instance is None:
        instance = super(RapidOCRBackend, cls).__new__(cls)
        instance._initialize()  # 失败时异常自然传播，_instance 未赋值
        cls._instance = instance
    return cls._instance
```

**语义变更**：
- 修复前：`_initialize()` 失败 → `_instance` 残留 → 后续调用得到 broken 实例 → 防御性 re-init guard 尝试修复 → 仍可能 `return ""`
- 修复后：`_initialize()` 失败 → `_instance` 保持 `None` → 下次调用重新尝试初始化 → 仍失败则继续抛异常（fail-fast）
- 移除 `extract_text()` 内的防御性 re-init guard（L242-249）：`__new__` 修复后不再需要运行时重初始化

### D3: `ocr_text` 写入必须包含 `app_name/window_name`

**决策**：写入 `ocr_text` 行时，从同一帧的 `frames` 元数据取 `app_name`/`window_name` 一并写入。

**理由**：data-model.md Table 2 注释明确要求：「写入时从 CapturePayload 取值……若 frames 行后续被修正，ocr_text 不联动更新（接受 drift，对齐 screenpipe 行为）」。

**screenpipe 对齐**：**aligned** — screenpipe `db.rs` 的 `insert_ocr_text()` 同样在写入时填入 `app_name`/`window_name`。

### D3.1: `text_json` 字段处理策略

**决策**：P1-S3 **不填充 `text_json` 字段**，写入时设为 `NULL`。

**理由**：
1. `text_json` 用于存储 OCR bounding box 结构化数据，P1 搜索能力（FTS）不依赖此字段
2. RapidOCR 的 `dt_boxes` 坐标信息序列化需额外处理逻辑，增加复杂度
3. 该字段为可选增强，P2+ 可按需实现

**实现**：`ocr_text` 写入 SQL 中 `text_json` 列直接传 `NULL`：

```python
# 伪代码
INSERT INTO ocr_text (frame_id, text, text_length, text_json, ocr_engine, app_name, window_name)
VALUES (?, ?, ?, NULL, 'rapidocr', ?, ?)
```

**screenpipe 对齐**：**intentional divergence** — screenpipe 当前也未填充 bounding box JSON 到 `text_json`（该字段保留用于未来细粒度 UI 元素检索）。

### D4: `capture_trigger` 前置校验（fail-loud）

**决策**：OCR 处理前校验 `capture_trigger` 合法性。非法值立即 `failed`，不执行 OCR。

**合法值集合（P1）**：`{'idle', 'app_switch', 'manual', 'click'}`

**大小写语义**：`capture_trigger` 值**区分大小写**，必须为小写。上游（Host）必须确保传入小写值。大写或混合大小写（如 `IDLE`、`App_Switch`）将被视为非法值，触发 fail-loud。

**screenpipe 对齐**：**no comparable pattern** — screenpipe 的 trigger 是编译期枚举（Rust enum），不存在运行时非法值问题。v3 Python 实现需要运行时防御。

### D5: 幂等防御策略（三层检查）

**决策**：

| 层次 | 时机 | 方法 |
|------|------|------|
| 第一层 | `_fetch_pending_frames` | 只获取 `status='pending'` 的帧，跳过已处理帧 |
| 第二层 | 写入 `ocr_text` 前 | 检查该 `frame_id` 是否已存在 `ocr_text` 行；若存在则跳过并 warn |
| 第三层 | SQL 写入语句 | 使用 `INSERT OR IGNORE` + `UNIQUE(frame_id)` 约束作为最终安全网 |

**理由**：p1-s3.md §2.1 明确要求幂等防御，防止并发场景下重复处理。第三层为数据库级兜底，即使前两层均未拦截（极端竞态），也不会产生重复行。

**screenpipe 对齐**：**intentional divergence** — screenpipe 单进程 Rust 处理，无并发冲突；v3 需应对 Python 线程 + SQLite 的并发场景。

### D5.1: `ocr_text.frame_id` UNIQUE 约束

**决策**：为 `ocr_text.frame_id` 添加 UNIQUE 约束，确保每帧最多一条 OCR 结果行。写入使用 `INSERT OR IGNORE`。

**实现**：通过新增迁移文件添加 UNIQUE INDEX：

```sql
-- 新增 migration（在 initial_schema.sql 之后）
CREATE UNIQUE INDEX IF NOT EXISTS idx_ocr_text_frame_id_unique ON ocr_text(frame_id);
```

> **注**：该 UNIQUE INDEX 替代现有的 `idx_ocr_text_frame_id` 普通索引。若 `initial_schema.sql` 尚未应用到生产环境，可直接修改 DDL；否则通过增量 migration 处理。

**理由**：
1. 业务语义上每帧最多一条 OCR 结果——screenpipe `insert_ocr_text()` 也遵循每帧一行
2. `INSERT OR IGNORE` 作为 D5 幂等防御的第三层安全网
3. 数据库级约束比应用层检查更可靠

### D6: `processing_mode` 启动切换

**决策**：在 `__main__.py` 添加 `ocr` 分支，三路选择：

```python
if processing_mode == "noop":
    worker = _start_noop_mode()
elif processing_mode == "ocr":
    _preload_ocr_model()       # 仅加载 RapidOCR，不加载 VL/Embedding
    worker = _start_ocr_mode()
    logger.info("MRV3 processing_mode=ocr")
else:
    preload_ai_models()        # 旧模式（兼容保留）
    init_background_worker(app)
```

**默认值策略**：P1-S3 及后续阶段**默认值切换为 `ocr`**。

**理由**：
1. **功能可用性**：OCR 是 v3 核心价值，升级后应开箱即用
2. **验收便利**：无需额外配置即可验证 S3 功能
3. **screenpipe 对齐**：screenpipe OCR 默认开启，无模式切换

**兼容性处理**：
- 仍支持 `OPENRECALL_PROCESSING_MODE=noop` 显式禁用 OCR（用于调试或资源受限场景）
- 启动日志强制输出 `MRV3 processing_mode=ocr` 以确认当前模式

**screenpipe 对齐**：**no comparable pattern** — screenpipe 不支持运行时 processing mode 切换（编译期确定功能集）。

### D7: 后端 API 扩展（`/api/memories/*`）

**决策**：`FramesStore.get_recent_memories()` 和 `get_memories_since()` 的查询 SQL 改为 LEFT JOIN `ocr_text`，返回对象增加 OCR 相关字段。

**LEFT JOIN 而非 INNER JOIN**：Grid 视图需要显示所有状态的帧（含 pending/processing/failed），这些帧没有 `ocr_text` 行。与 Search 路径的 `INNER JOIN` 不同（data-model.md §3.0.3 明确：Search 路径对齐 screenpipe 避免 LEFT JOIN）。

**screenpipe 对齐**：**intentional divergence** — 这是 legacy 内部 API，不在 screenpipe 对齐范围内。

### D8: UI 卡片结构

**决策**：改造 `index.html` Grid 卡片为 Header + Footer 两层结构：

- **Header**：`app_name` | `window_name` | `device_name`
- **Footer**：`capture_trigger` + `timestamp` | 状态标签 | OCR info（引擎/时间/文本长度） | 文本预览（≤100 字符） | 错误信息
- **data 属性**：`data-frame-status="pending|processing|completed|failed"`（自动化测试锚点）

**screenpipe 对齐**：**no comparable pattern** — screenpipe 的 UI 是 Tauri/React 实现。

### D9: RapidOCR v3 API Migration

**决策**：迁移到 RapidOCR v3 API，使用 params dict + 枚举配置，移除本地模型路径管理。

**理由**：
1. **字典自动匹配**：v3 API 根据 `OCRVersion` 自动选择对应的字典文件，避免手动指定路径导致的乱码问题
2. **零网络依赖**：PP-OCRv4 模型随 pip 包安装，首次运行无需下载
3. **简化配置**：移除 8 个配置参数（`use_local`, `model_dir`, `det_model_path` 等）
4. **类型安全**：使用枚举替代字符串，IDE 自动补全，拼写错误会报错

**配置方式**：
```python
from rapidocr import RapidOCR, OCRVersion, ModelType

engine = RapidOCR(params={
    "Det.ocr_version": OCRVersion.PPOCRV4,  # 默认，pip 自带
    "Det.model_type": ModelType.MOBILE,
    "Rec.ocr_version": OCRVersion.PPOCRV4,
    "Rec.model_type": ModelType.MOBILE,
    # 质量参数
    "Det.limit_side_len": 960,
    "Det.box_thresh": 0.7,
    "Global.text_score": 0.6,
})
```

**保留的环境变量**：
- `OPENRECALL_OCR_RAPID_OCR_VERSION`: PP-OCRv4（默认）或 PP-OCRv5
- `OPENRECALL_OCR_RAPID_MODEL_TYPE`: mobile（默认）或 server
- 质量参数：`OPENRECALL_OCR_DET_*`, `OPENRECALL_OCR_DROP_SCORE`

**screenpipe 对齐**：**intentional divergence** — screenpipe 使用 Rust PaddleOCR binding，模型路径硬编码在编译时；v3 采用 Python pip 包管理。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|------|------|------|
| `RapidOCRBackend.extract_text()` 内部捕获异常并返回 `""` | 无法区分「引擎异常」和「图像无文字」 | **已裁定（D2）**：在 S3 范围内修复 `rapid_backend.py`，移除异常吞并，让异常向上传播 |
| 高分辨率截图 OCR 处理慢 | P95 > 10s 影响用户体验 | 观测指标（non-blocking），通过 `elapsed_ms` 结构化日志度量；P2+ 优化 |
| SQLite WAL 并发下 `ocr_text` 写入冲突 | 重复写入或死锁 | 三层幂等防御（fetch 层 + pre-write 层 + `INSERT OR IGNORE` + `UNIQUE(frame_id)`） |
| `processing_mode` 配置错误 | 启动后无 OCR 处理 | 启动日志强制输出 `MRV3 processing_mode={value}` |
| PP-OCRv5 首次运行需下载模型 | 离线环境启动失败 | 默认使用 PP-OCRv4（pip 自带）；如需 v5 需确保网络或预下载 |
