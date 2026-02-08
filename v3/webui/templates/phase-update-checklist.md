# Phase 更新检查清单（WebUI）

> 用于每次 Phase 收尾时同步维护 `v3/webui` 文档。

## A. 范围识别

- [ ] 本 Phase 是否新增页面路由？
- [ ] 本 Phase 是否修改现有页面行为？
- [ ] 本 Phase 是否新增/变更页面依赖 API？
- [ ] 本 Phase 是否引入新降级路径（fallback/degradation）？

## B. 必改文件

- [ ] 更新 `v3/webui/CHANGELOG.md`（新增 Phase 条目）
- [ ] 更新受影响页面文档（`v3/webui/pages/*.md`）
- [ ] 如全局链路变化，更新 `v3/webui/DATAFLOW.md`
- [ ] 如路由/API 变化，更新 `v3/webui/ROUTE_MAP.md`
- [ ] 如对比结论变化，更新 `v3/webui/COMPARISON_V2_TO_V3.md`

## C. 结构校验

- [ ] 每个受影响页面文档包含 9 个固定章节
- [ ] 每个受影响页面文档包含页面专属 Mermaid 图
- [ ] 全局 `DATAFLOW.md` 包含主链路图
- [ ] 若涉及采集/上传改动，文档已明确 `buffer -> uploader -> upload API -> worker` 链路

## D. 追溯校验

- [ ] 每个关键结论附代码路径（route/template/api）
- [ ] 每个“前后变化”附来源（baseline + phase results）
- [ ] 验收点可映射到测试或手工验证步骤
- [ ] upload/upload status 接口变更已同步到 `ROUTE_MAP.md` 与相关页面文档

## E. 入口联动

- [ ] `v3/README.md` 中 WebUI 入口链接仍有效
- [ ] `v3/results/README.md` 维护约束仍存在

## F. 发布前确认

- [ ] 文档内容与当前代码一致（无虚构路由/接口）
- [ ] 未覆盖历史结论（追加式更新）
- [ ] 术语统一（Request/Processing/Storage/Retrieval）
