# MyRecall-v3 文档导航与治理规则

- 版本：v0.2（Draft）
- 日期：2026-02-26
- 目标：将 `spec.md` 固化为唯一事实源（SSOT），降低文档漂移与冲突。

## 1. 文档地图（谁负责什么）

| 文档 | 角色 | 必须包含 | 禁止包含 |
|---|---|---|---|
| `spec.md` | **唯一事实源（SSOT）** | 架构边界、协议契约、能力字典（`C-*`）、指标字典（`M-*`） | 排期日期、执行过程细节 |
| `roadmap.md` | 执行与里程碑视图 | 阶段时间线、入口/退出条件、`C-*`/`M-*` 引用 | 阈值定义、协议细节复制 |
| `open_questions.md` | 待决问题与决策索引 | 未决问题、已决索引（链接 ADR/Spec） | 已决问题的完整重复论述 |
| `adr/*` | 决策动机与取舍 | Context / Decision / Consequences / Risks | 可执行阈值表、阶段执行脚本 |
| `acceptance/*` | 验收证据归档 | 证据、步骤、结果、Gate 结论、阻塞项 | 指标定义（应引用 `M-*`） |

## 2. SSOT 规则（强制）

1. 所有“事实”只允许在 `spec.md` 定义。
2. 指标阈值只允许在 `spec.md` 的 `Gate Metrics Dictionary` 中定义。
3. 其他文档出现阈值时，必须改为引用 `M-*` ID。
4. 能力条目只允许在 `spec.md` 的 `Capability Dictionary` 中定义。
5. 其他文档出现功能清单时，必须改为引用 `C-*` ID。

## 3. 引用规范（`C-*` / `M-*`）

- `C-*`：能力条目（Capability），例：`C-CHT-002`。
- `M-*`：指标条目（Metric），例：`M-CHT-001`。
- 命名策略：**领域前缀**（`ING/SCH/CHT/UI/SYS/SEC/OPS`），不使用阶段前缀。
- 引用方式：在 `roadmap`、`acceptance`、`open_questions` 中直接引用 ID，并链接回 `spec.md` 对应章节。

## 4. 变更流程

1. 改“事实”（边界、契约、阈值、能力定义）
- 先改 `spec.md`。
- 再改引用方（`roadmap`/`acceptance`/`open_questions`）。

2. 改“决策”
- 新增或更新 `adr/*`。
- 在 `spec.md` 的“已决策索引”同步结论与链接。

3. 改“计划节奏”
- 只改 `roadmap.md` 和对应 `acceptance` 计划文件。
- 不得在 `roadmap` 复制 `spec` 的阈值正文。

## 5. 评审检查清单

- [ ] 是否新增了未在 `spec` 定义的指标阈值？
- [ ] 是否新增了未在 `spec` 定义的能力条目？
- [ ] `roadmap` 是否只包含执行视图而非规格正文？
- [ ] `open_questions` 是否只保留未决问题与索引？
- [ ] 验收记录是否引用 `C-*` 与 `M-*` 并给出证据路径？

## 6. 快速入口

- 规格事实源：[`spec.md`](./spec.md)
- 执行路线图：[`roadmap.md`](./roadmap.md)
- 待决问题：[`open_questions.md`](./open_questions.md)
- 决策记录：[`adr/`](./adr)
- 验收记录：[`acceptance/`](./acceptance)
