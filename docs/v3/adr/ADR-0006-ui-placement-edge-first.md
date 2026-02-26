# ADR-0006 UI 部署位置：P1~P3 保持 Edge 承载

- 状态：Accepted
- 日期：2026-02-26

## Context
- v3 的主目标是先收敛 Edge-Centric 视觉主链路（capture -> processing -> search -> chat）。
- 当前实现中 Flask 页面已与 server 同进程（`/`、`/search`、`/timeline`）。
- 若在 P1/P2/P3 同时推进 UI 迁移到 Host，会与链路改造并行，放大交付风险。

## Decision
- 在 P1/P2/P3 阶段，页面/UI 继续部署在 Edge。
- Host 不负责 UI，仅负责 capture、轻处理、上传、缓存与断点续传。
- UI 迁移到 Host 只作为 Post-P3 可选演进，不纳入当前里程碑承诺。

## screenpipe 参考与对齐
- screenpipe 交互面主要在本地 app 侧，搜索/推理由后端能力提供。
- 本决策与 screenpipe 在“交互与推理解耦”目标上可对齐，但在“部署拓扑”上不对齐（该差异由 Edge-Centric 约束决定）。

## Consequences
- 优点：
  - 降低阶段内并行改造复杂度，优先保证主链路可用性与可验证性。
  - 保持当前页面可用，避免 P1 初期 UI 回归风险。
- 代价：
  - Edge 同时承载 UI 与重处理，存在资源争用。
  - UI 发布节奏与 Edge 服务发布仍有耦合。

## Risks
- 高负载时 UI 响应抖动，可能影响运维可观测与问题定位效率。

## Validation
- 压测场景：处理队列高压 + 页面查询并发，观测 UI P95 与 Search/Chat P95。
- 运行期指标：CPU/内存分配、队列深度、页面错误率、API 超时率。
- Gate：若 P3 前出现持续资源争用且无法通过限流/隔离缓解，再提前触发 UI 迁移评估。
