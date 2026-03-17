## Why

P1-S2b 已完成 capture baseline（截图采集 + spool + ingest + 队列状态机），但 `processing_mode` 固定为 `noop`——帧入库后仅驱动状态流转，不执行任何文本提取。要进入 P1-S4（检索能力），Edge 必须先能从截图中提取可搜索文本。

P1-S3 的目标是在 Edge 端引入 **OCR-only 处理链路**：对每一帧执行 RapidOCR，将提取结果持久化到 `ocr_text` 表，并在 UI 中展示处理状态与文本预览。这是 v3 主线从"能采集"到"能搜索"的关键桥梁。

> **Source precedence**: spec.md §4.3 (OCR-only 处理契约) > p1-s3.md (substage contract) > gate_baseline.md (Gate thresholds)

## What Changes

- **新增独立 V3ProcessingWorker** (`openrecall/server/processing/v3_worker.py`)，替代旧 worker 实现 OCR-only 处理循环
- **新增 OCR 执行封装** (`processing/ocr_processor.py`)，调用已有的 `RapidOCRBackend`
- **新增幂等防御模块** (`processing/idempotency.py`)，三层检查防止重复处理同一帧
- **`processing_mode` 切换**：从 P1-S1 的 `noop` 升级为 `ocr`，`/v1/ingest/queue/status` 响应中 `processing_mode` 语义变更
- **OCR 结果持久化**：成功帧写入 `ocr_text` 表 + 设置 `frames.text_source='ocr'`
- **失败语义**：OCR 异常/返回 None/空文本 → `frames.status='failed'` + `error_message`，不写 `ocr_text`
- **capture_trigger 校验**（fail-loud）：非法/空 trigger 立即标记 failed，不执行 OCR
- **后端 API 扩展**：`/api/memories/recent` 和 `/api/memories/latest` LEFT JOIN `ocr_text`，返回文本预览等字段
- **UI 卡片改造**：Grid `/` 的 frame 卡片展示 Header（app/window/device）+ Footer（触发信息、OCR 状态、文本预览、错误信息）
- **零 AI 增强防守**：确认不生成 caption/keywords/fusion_text/embedding，`ocr_text_embeddings` 表不存在

## Non-goals

- **不实现多引擎切换**：P1 固定 RapidOCR（single-engine policy），不做引擎对比/fallback
- **不实现 OCR 重试**：失败直接标记 `failed`，`retry_count` 保持 0，重试留给 P2+
- **不实现 AX/dual-path**：`accessibility` 表保持 v4 seam，不参与 v3 数据流
- **不实现 embedding**：`ocr_text_embeddings` 表 P1 不建
- **不改动旧 worker.py**：保留兼容但 v3 主线不调用
- **不新增对外 HTTP 端点**：仅变更 `processing_mode` 语义值（noop → ocr）

## Capabilities

### New Capabilities

- `ocr-processing`: V3ProcessingWorker OCR-only 处理循环——帧获取、trigger 校验、RapidOCR 执行、ocr_text 写入（INSERT OR IGNORE + UNIQUE(frame_id)）、text_source 标记、failed 处理、三层幂等防御
- `processing-mode-switch`: processing_mode 从 noop 升级到 ocr 的启动切换机制，含模型预加载与启动日志
- `ui-processing-cards`: Grid `/` frame 卡片的 OCR 处理状态展示——Header（app/window/device）+ Footer（trigger/status/text_preview/error）+ data 属性

### Modified Capabilities

_（无现有 openspec specs 需修改——`openspec/specs/` 目录为空）_

## Impact

### Code

| 区域 | 文件 | 变更类型 |
|------|------|----------|
| Processing 主模块 | `openrecall/server/processing/v3_worker.py` | 新增 |
| OCR 封装 | `openrecall/server/processing/ocr_processor.py` | 新增 |
| 幂等防御 | `openrecall/server/processing/idempotency.py` | 新增 |
| 包初始化 | `openrecall/server/processing/__init__.py` | 新增 |
| 启动入口 | `openrecall/server/__main__.py` | 修改（添加 ocr 分支） |
| 数据库层 | `openrecall/server/database/` | 扩展（`ocr_text` 写入方法） |
| 后端 API | `openrecall/server/api.py` | 修改（LEFT JOIN ocr_text） |
| UI 模板 | `openrecall/server/templates/index.html` | 修改（卡片结构） |
| 配置 | `openrecall/shared/config.py` | 修改（`OPENRECALL_PROCESSING_MODE` 支持 ocr） |

### APIs

- `GET /v1/ingest/queue/status`: `processing_mode` 值从固定 `"noop"` 变为 `"ocr"`
- `/api/memories/recent` 和 `/api/memories/latest`（legacy 内部 API）: 返回对象增加 OCR 相关字段

### Dependencies

- `RapidOCRBackend`（`openrecall/server/ocr/rapid_backend.py`）：已有，需修复异常传播行为（见 design.md D2）及 singleton `__new__` 模式（见 design.md D2.1）
- `SQLStore`（`openrecall/server/database/`）：需扩展 `ocr_text` 写入方法

### Gate 条件

- OCR 成功帧写入 `ocr_text` 正确率 = 100%（硬门槛）
- `frames.text_source='ocr'` 标记正确率 = 100%
- OCR 失败帧 `failed` 语义正确率 = 100%
- 索引时零 AI 增强检查通过率 = 100%
- 处理来源字段 UI 展示完整率 = 100%（硬性交付物）
