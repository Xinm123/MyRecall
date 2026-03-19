# MyRecall-v3 验收记录归档

- 规则：每个阶段/子阶段在 Gate 判定前，必须先完成对应 Markdown 验收记录。
- 目录：`./`（本目录）
- 记录模板：`TEMPLATE.md`
- 记录要求：除性能数值外，必须填写功能完成度与完善度指标。
- 强制项：每份验收记录必须包含 `2.1 指标口径与样本说明（必填）`（口径基线版本、指标样本数、统计时间窗、百分位算法四项齐全）。
- 判定约束：若缺失 `2.1` 段或未说明最小样本数符合性，该阶段不得给出 `Pass` 结论。
- 若记录 Soft KPI（如引用覆盖率），必须标注 `non-blocking` 并附整改动作。
- 指标口径 SSOT：`../gate_baseline.md`（公式、样本数、时间窗、判定规则）。

## 文件清单

- `phase1/p1-s1.md`
- `phase1/p1-s2a.md`（事件驱动）
- `phase1/p1-s2b.md`（Capture Completion / Monitor-Aware Coordination）
- `phase1/archive/p1-s2.md`（历史参考，已被 S2a/S2b 取代，不用于当前 Gate 判定）
- `phase1/p1-s3.md`
- `phase1/p1-s4.md`
- `phase1/p1-s5.md`
- `phase1/p1-s6.md`
- `phase1/p1-s7.md`
- `phase2/phase2-lan-validation.md`
- `phase3/phase3-debian-production.md`
