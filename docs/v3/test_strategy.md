# MyRecall-v3 测试策略

- 版本：v1.0
- 日期：2026-03-05
- 状态：已锁定
- 关联决策：016A（v3 全新数据起点）

---

## 1. 核心决策

**v3 全部使用全新测试，不复用 v2 现有测试。**

现有测试文件保留在 `tests/` 目录下，仅作为实现参考，不计入 v3 验收。

---

## 2. 决策理由

| 维度 | v2 | v3 | 结论 |
|------|-----|-----|------|
| 架构 | 单机闭环 | Host/Edge 分离 | 不兼容 |
| 数据模型 | LanceDB + FTS | SQLite Scheme C | 不兼容 |
| API | `/api/*` | `/v1/*` | 契约变更 |
| Capture | 定时轮询 | 事件驱动 | 逻辑重写 |
| Chat | 无 | Pi Sidecar + SSE | 全新 |

v3 是全新起点（决策 016A），架构与 v2 根本不同，复用测试的成本 > 全部重写。

---

## 3. 测试分层结构

```
tests/
├── host/                          # Host 端测试（全新）
│   ├── test_capture_trigger.py    # 事件驱动 capture
│   ├── test_host_uploader.py      # 幂等上传协议
│   └── test_spool_buffer.py       # Host spool
│
├── edge/                          # Edge 端测试（全新）
│   ├── test_ingest_api.py         # /v1/ingest 端点
│   ├── test_ax_ocr_pipeline.py   # AX-first + OCR-fallback
│   ├── test_search_api.py        # /v1/search 端点
│   ├── test_frames_api.py        # /v1/frames/* 端点
│   └── test_health_api.py        # /v1/health 端点
│
├── chat/                          # Chat 测试（全新）
│   ├── test_chat_manager.py
│   ├── test_chat_protocol.py
│   ├── test_chat_persistence.py
│   └── test_chat_e2e.py
│
└── e2e/                          # 端到端测试（全新）
    └── test_host_edge_integration.py
```

---

## 4. 各阶段测试覆盖

### P1-S1（基础链路）
- `test_ingest_api.py` — 幂等上传、队列状态
- `test_frames_api.py` — 图像获取、metadata
- `test_health_api.py` — 健康检查

### P1-S2（采集）
- `test_capture_trigger.py` — 事件驱动、去抖、去重
- `test_host_uploader.py` — 断点续传、重试策略

### P1-S3（处理）
- `test_ax_ocr_pipeline.py` — AX-first/OCR-fallback 决策、分表写入

### P1-S4（检索）
- `test_search_api.py` — FTS、过滤参数、`content_type` 路由

### P1-S5~S6（Chat）
- `test_chat_manager.py` — Pi 进程管理
- `test_chat_protocol.py` — 事件流协议
- `test_chat_persistence.py` — 会话持久化

### P1-S7（验收）
- `test_chat_e2e.py` — E2E 场景覆盖 >= 30
- `test_host_edge_integration.py` — 完整链路

---

## 5. 标记规范

所有 v3 测试使用以下 pytest 标记：

```python
pytestmark = pytest.mark.unit  # 或 integration
```

- **unit**: 单元测试，无外部依赖（mock）
- **integration**: 集成测试，需要真实组件（Flask app、SQLite）
- **e2e**: 端到端测试，不在默认套件中运行

---

## 6. 现有测试处理

| 文件 | 处理方式 |
|------|---------|
| `test_phase*.py` | 保留，不运行，仅作参考 |
| `test_nlp*.py` | 保留，不运行，仅作参考 |
| `test_ai_*.py` | 保留，不运行，仅作参考 |
| `test_api_*.py` | 保留，不运行，仅作参考 |

---

## 7. 工作量估算

| 模块 | 预估行数 |
|------|---------|
| Host | ~500 |
| Edge API | ~500 |
| Edge Processing | ~250 |
| Chat | ~550 |
| E2E | ~200 |
| **总计** | **~2000** |

---

## 8. 验收标准

- 每个 P1 子阶段的 Gate 对应测试用例必须通过
- 测试覆盖率不设硬性指标，但关键路径必须覆盖
- E2E 测试场景数 >= 30
