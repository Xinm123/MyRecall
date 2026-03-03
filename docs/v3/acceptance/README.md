# MyRecall-v3 验收记录归档

- 规则：每个阶段/子阶段在 Gate 判定前，必须先完成对应 Markdown 验收记录。
- 目录：`MyRecall/docs/v3/acceptance/`
- 记录模板：[`TEMPLATE.md`](./TEMPLATE.md)
- 指标口径 SSOT：[`../gate_baseline.md`](../gate_baseline.md)

## 强制要求（新增）

1. 每份验收文档开头必须声明"规范引用 IDs"。
2. 验收文档只能引用 `DEC-* / DB-* / API-* / GATE-*`，不得重新定义规范。
3. 若记录 Soft KPI（如引用覆盖率），必须标注 `non-blocking` 并附整改动作。
4. **模板使用验证**：每份验收文档必须包含 TEMPLATE.md 中的所有必填章节：
   - 章节 0：规范引用 IDs（必填）
   - 章节 1：范围与目标
   - 章节 2：环境与输入（含 2.1 指标口径说明）
   - 章节 3：验收步骤
   - 章节 4：结果与指标（含 4.1 数值指标、4.2 功能完成度、4.3 完善度、4.4 UI 验收）
   - 章节 5：结论
   - 章节 6：风险与后续动作

## 0. 规范引用 IDs

- 决策：N/A（目录说明文件）
- 数据：N/A（目录说明文件）
- API：N/A（目录说明文件）
- Gate：N/A（目录说明文件）
- 链接：`../decisions.md` / `../data_model.md` / `../api_contract.md` / `../gate_baseline.md`

## 文件清单

- `phase1/p1-s1.md`
- `phase1/p1-s2.md`
- `phase1/p1-s3.md`
- `phase1/p1-s4.md`
- `phase1/p1-s5.md`
- `phase1/p1-s6.md`
- `phase1/p1-s7.md`
- `phase2/phase2-lan-validation.md`
- `phase3/phase3-debian-production.md`
