# P1-S2b+ 验收记录（感知哈希辅助检测）

- 阶段：P1-S2b+
- 日期：2026-03-14（P1-S2b+ 感知哈希实现）
- 负责人：pyw
- 状态：`Planned`
- 依赖：P1-S2b Pass
- 角色：**可选增强阶段**；若执行，阶段内自洽验收，但不构成 S3 Entry Gate

## 0. 阶段定位

- **可选增强阶段**：本阶段为功能增强阶段，可在不影响 OCR-only 主线的前提下补充感知哈希能力
- **目的**：实现 simhash 计算能力，为内容相似度观测和后续工具能力提供技术基础
- **边界**：在 S2b 已冻结的 capture completion 基础上，增加内容感知能力
- **平台策略**：macOS-only（P1 仅实现 macOS；Windows/Linux 推迟 P2）

## 0.1 Entry Gate vs Exit Gate

- Entry Gate（允许进入 P1-S2b+）：
  - P1-S2b Pass（所有 Hard Gate 指标达标）
  - 本文档与相关 SSOT（roadmap/gate_baseline/spec）口径一致
- Exit Gate（阶段内完成条件）：
  - 本文档 §4 Gate 结论为 `Pass`
  - 所有 Hard Gate 指标达标（见 §3）
  - 验收证据齐全

## 1. 范围与目标

- 范围：感知哈希（simhash）计算实现、spool 集成、`simhash` 字段写入、相似帧查询工具
- 目标：实现内容感知能力，为相似帧观测和后续工具能力提供技术基础
- 对应 Hard Gate：
  - simhash 计算实现率 = 100%
  - spool 集成成功率 = 100%
  - 相似帧检测准确率 >= 95%
  - 计算性能达标（P95 <= 10ms）

### 1.0 In-scope outcomes（本阶段必须交付）

- 感知哈希计算实现（DHash 或其他轻量算法）
- Spool 层集成：capture 入队时计算 simhash，失败时阻断并记录错误
- `frames.simhash` 字段写入（schema 已预留）
- 相似帧检测逻辑：基于汉明距离的重复判定
- 性能基线：计算耗时 P95 <= 10ms

### 1.0b Out-of-scope（本阶段明确不做）

- **不修改 S2b 已冻结语义**：routing、device_name binding、topology 等核心逻辑不变
- **不替代 capture_id 幂等**：`capture_id` 仍是主去重键，simhash 为内容级辅助
- **不引入新依赖**：仅用 Pillow，不引入 SciPy 或其他重型库
- **仅支持 DHash 或等效轻量算法**：不实现复杂算法（如 WHash）

### 1.0c 与 S2b / S3 的分工边界

| 验证项 | S2b | S2b+ | S3 |
|---|---|---|---|
| trigger routing correctness | 负责 | 继承 | 继承 |
| device_name binding | 负责 | 继承 | 继承 |
| single_monitor_duplicate_capture_rate | 负责定义并关闭 | 可复用结果做观测 | 继承使用 |
| simhash 计算 | N/A | **Hard Gate 负责** | 继承使用 |
| 内容相似度检测 | N/A | **Hard Gate 负责** | 可选增强 |
| OCR processing | N/A | N/A | 负责 |

## 2. 环境与输入

- 运行环境：macOS（P1-S2b+ 仅验证 macOS）
- 配置与数据集：
  - 已生成的 capture 样本（来自 S2b 验收）
  - simhash 计算性能基线
  - 相似帧测试数据集（构造已知相似/不相似的 capture 对）
- 依赖版本：Pillow（Python 图像处理）

### 2.1 性能基线（Hard Gate）

| 指标 | 目标 | Gate 类型 |
|---|---|---|
| simhash 计算耗时 P95 | <= 10ms | Hard Gate |
| 内存占用增加 | <= 5MB | Soft KPI |
| capture latency 增加 | <= 5ms | Soft KPI |

## 3. Hard Gate 验证准则

### 3.1 simhash 计算正确性（Hard Gate）

- **功能验证**：对已知相似图像计算 simhash，汉明距离应较小（<= 5 bits）
- **功能验证**：对已知不相似图像计算 simhash，汉明距离应较大（> 10 bits）
- **错误处理**：计算失败时必须阻断 capture 流程并记录错误（非 NULL 降级）
- **实现完成率**：100%

### 3.2 Spool 集成验证（Hard Gate）

- **正常路径**：simhash 成功计算并写入 `frames.simhash`
- **失败路径**：计算失败时 capture 失败，触发 error 处理流程
- **性能路径**：计算耗时 P95 <= 10ms（Hard Gate）

### 3.3 相似帧检测准确率（Hard Gate）

- **准确率**：已知相似帧检测准确率 >= 95%
- **误报率**：已知不相似帧误报率 <= 5%
- **样本要求**：相似样本 >= 50 对，不相似样本 >= 50 对

## 4. 结果与 Hard Gate 指标

### 4.1 Hard Gate（必须达标）

| Gate 指标 | 阈值 | 状态 |
|---|---|---|
| simhash 计算实现率 | = 100% | |
| spool 集成成功率 | = 100% | |
| 相似帧检测准确率 | >= 95% | |
| 计算耗时 P95 | <= 10ms | |

### 4.2 Soft KPI（观测记录）

| 指标 | 记录值 |
|---|---|
| 计算耗时 P50/P90/P95/P99 | |
| 内存占用增加 | |
| capture latency 增加 | |

### 4.3 功能完成度指标

- 功能清单完成率（目标 100%）：
- API/Schema 契约完成率（目标 100%）：
- 错误处理覆盖率（目标 100%）：

## 5. 结论

- Gate 结论：`Pass` | `Fail`
- 依据：
- 阻塞项（若 Fail 必填）：

## 6. 风险与后续动作

- 风险：simhash 计算性能不达标，影响 capture latency
  - 缓解：采用轻量 DHash 算法，失败时快速失败（fail-fast）
- 风险：simhash 误报（不相似图像被判定为相似）
  - 缓解：调整汉明距离阈值，增加训练样本校准
- 风险：算法选择争议（DHash vs PHash vs 其他）
  - 缓解：P1 固定 DHash，P2+ 评估升级

## 7. 算法选择（P1 固定）

### 7.1 选定算法：DHash（Difference Hash）

**理由**：
- 纯 Pillow 实现，无 SciPy 依赖
- 计算快（~5ms/张），满足 P95 <= 10ms
- 对 UI 截图的边缘变化敏感
- 64-bit 输出，与 `frames.simhash` 字段兼容

**参数**：
- hash_size = 8
- 汉明距离阈值 = 5 bits（相似）/ 10 bits（不相似）

### 7.2 不考虑的算法

- **PHash**：需 SciPy，依赖重
- **WHash**：计算慢（~50ms），不满足性能要求
- **AHash**：对亮度敏感，不适合截图场景

## 8. HTTP 契约 delta（本阶段）

- 无新增 HTTP 端点
- `POST /v1/ingest` 的 payload 不新增必填字段
- `frames.simhash` 为内部字段，API 响应可选返回（不作为契约）

## 9. 文件清单（参考）

```
openrecall/client/
├── hash_utils.py          # 感知哈希计算（新增）
└── spool.py               # 集成 simhash 计算（修改）

openrecall/server/
└── database/
    └── frames_store.py    # 相似帧查询方法（新增）

tests/
├── test_p1_s2b_plus_simhash.py       # simhash 计算测试（新增）
└── test_p1_s2b_plus_integration.py   # 集成测试（新增）

scripts/acceptance/
└── p1_s2b_plus_local.sh   # 本阶段验收脚本（新增）
```

## 10. 与 S2b / S3 的衔接

- **前置依赖**：必须等待 P1-S2b Pass 后才能进入 S2b+
- **后置关系**：P1-S2b+ 不阻塞 P1-S3；若执行，应保持与 S3 OCR-only 主线兼容
- **功能增强**：S2b+ 在 S2b 的 capture completion 基础上，增加内容感知能力
- **S3 继承**：S3 可直接使用 S2b+ 实现的 simhash 能力（可选增强）
