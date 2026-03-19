# Chat 功能前置需求分析（导航）

- 旧文档路径：`docs/v3/chat-prerequisites.md`
- 当前状态：已拆分，不再维护详细结论
- 说明：原文档混合了承载 Gate、能力对齐、隐私策略、实现细节和 Chat 架构的问题；现已按职责拆分

---

## 新文档入口

### 1. 前置门槛

- `docs/v3/chat/prerequisites.md`
- 作用：定义 `Entry Gate / Parity Gate / P0-core / P0-support`

### 2. 能力对齐

- `docs/v3/chat/capability-alignment.md`
- 作用：记录 MyRecall 与 screenpipe 实际实现之间的能力面对齐关系、当前偏离点与阶段性策略

### 3. Chat 架构

- `docs/v3/chat/architecture.md`
- 作用：记录 Host / Edge / Agent / UI / provider 等运行架构议题

### 4. screenpipe Chat 事实基线

- `docs/v3/baselines/chat/chat_baseline_screenpipe.md`
- 作用：只作为 screenpipe Chat 侧的事实基线，不直接定义 MyRecall Gate

---

## 迁移说明

以下内容不再以本文件为 SSOT：

- Chat 前置能力清单
- 与 screenpipe 的能力对齐分析
- 隐私/采集策略决策
- Host / Edge Chat 架构决策

后续讨论和更新请直接落到 `docs/v3/chat/` 下对应文档。
