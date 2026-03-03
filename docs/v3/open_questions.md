# MyRecall-v3 待决问题（仅未决）

- 版本：v1.0
- 日期：2026-03-03
- 说明：本文件仅保留未决问题；已决项统一维护于 [`decisions.md`](./decisions.md)。

## 编号规则

- **ID 格式**：`OQ-XXX`，连续编号（从头开始，不重复使用）
- **级别定义**：
  - `P1`：必须在当前 Phase 完成拍板，否则阻塞阶段验收
  - `P2`：可在后续 Phase 拍板，不阻塞当前阶段
- **编号原则**：新增问题时使用当前最大编号 + 1，保持连续性

## 当前未决项

| ID | 级别 | 问题 | 选项 | 建议 | 依据 | 风险 | 截止 |
|---|---|---|---|---|---|---|---|
| OQ-027 | P1 | 是否在 P2 启动 keyset cursor 分页替代 `offset`（降低 `search_all` 过量拉取） | A. 继续 offset；B. P2 引入 keyset（`before_timestamp`）；C. P3 再评估 | B | `content_type=all` 当前为 `limit+offset` 过量拉取；规模增长后内存成本升高 | 若继续 offset，长窗口查询可能恶化 | 2026-04-10 |
| OQ-028 | P1 | 是否在 P1-S7 后启动 DA-8B（结构化 citation 后处理） | A. 保持 DA-8A；B. 启动 DA-8B；C. P2 再评估 | 取决于 S7 覆盖率结果（默认 B） | gate_baseline 对引用覆盖率仅 soft KPI；若长期低于 92% 需收敛质量 | 引用可点击但结构化检索追踪能力不足 | 2026-03-22 |
| OQ-029 | P2 | P2 是否引入 Power Profile（动态采样频率） | A. 不引入；B. 引入并重定义 SLO；C. 仅实验不入主线 | A（当前） | `gate_baseline.md` 已声明若引入必须重定义 TTS/丢失率阈值 | 未重定义口径会导致 Gate 判定失真 | 2026-04-15 |
| OQ-030 | P2 | accessibility 独立 walker（非 paired_capture）是否进入 P2 范围 | A. 不进入；B. 进入并补性能评估；C. Post-P3 | A（当前） | DEC-025A 已支持 schema，但 P1 目标是 paired_capture 闭环 | 提前引入会扩大 P2 范围，冲击功能冻结策略 | 2026-04-20 |

## 需实验 / 需查证（未形成拍板）

1. AX-first 在多应用场景下对检索召回质量的净收益区间。
2. 多显示器高频事件触发下 Host CPU 上限与误触发率。
3. Debian 上 RapidOCR 与候选本地 VL 模型组合的长期稳定性。

## 维护规则

- 任何问题一旦拍板，必须迁移到 `decisions.md` 并从本文件移除。
- 本文件禁止追加“已决结论”长清单。
