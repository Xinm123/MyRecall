## 先解释你问的：“解析失败则回退到原句 + 规则提取”是什么意思？
这里说的“解析”指的是：我们希望让 **Vision/VL 模型返回结构化 JSON**（例如 `{app, scene, action, entities}`），然后程序把它 `json.loads(...)` 解析成字典来用。

但在真实环境里，LLM/VL 有时会：
- 输出多余的解释文字（不是纯 JSON）
- JSON 格式不严格（少引号、多逗号、混入换行）
- 某些字段缺失
这时 `json.loads()` 会失败，程序就不能直接拿到 `scene/action/entities`。

“回退到原句 + 规则提取”的意思是：
- **不让系统因为 JSON 不标准就崩掉**。
- 当 JSON 解析失败时，我们就把 vision 的输出当作“普通一句话描述”（现在现状就是一句话），然后用一些简单规则/正则尽量提取信息：
  - 从句子里抓 `app`（例如出现 VSCode/Chrome/WeChat）
  - 从句子里抓动作动词（阅读/写作/调试/搜索/会议/聊天等）
  - 从 OCR 文本里抓实体（URL/域名/文件名/错误类型/项目名等）
这样即便 vision JSON 不稳定，pipeline 仍然能产出可用的“回忆卡片”。

举个例子：
- 理想输出（可解析 JSON）：`{"app":"VSCode","scene":"debugging","action":["fixing bug"],"entities":["TypeError"]}`
- 失败输出（不可解析）：`APP: VSCode; user is debugging a Python error...`
- 回退策略：把这句当作 `description`，用规则提取出 `app=VSCode`、`action=debugging`，再从 OCR 里提取 `TypeError/traceback` 等。

---

## 全场景的核心目标（你的要求）
- 让 embedding/rerank 表达“这张截图在干什么/属于什么场景”，而不是被长 OCR（尤其代码）牵着走。
- 代码/traceback 只是众多场景之一的证据块，而且要可选、截断、降权。

## 全场景 Memory Card（结构化表示）
建议 schema：
- `[APP]` 应用/窗口标题
- `[SCENE]` 场景（阅读/沟通/写作/数据整理/调试/搜索…）
- `[ACTION]` 行为（动词标签，可多标签）
- `[ENTITIES]` 实体（人名/项目名/域名/文件名/issue号…）
- `[KEYWORDS]` 关键词（从 OCR 抽取，高信息 token）
- `[UI_TEXT]` OCR 片段（短、像标题/列表/按钮/小结的部分）
- `[CODE]`（可选，检测到代码才加，截断）
- `[TRACEBACK]`（可选，检测到错误栈才加，截断）
- `[TIME]`（时间桶，用于对齐“昨天下午”等意图）

## 计划（按风险从低到高）
### 1) 新增 Memory Card 构造器
- OCR：关键词抽取 + 实体抽取 + UI 片段选择 +（可选）code/traceback 检测截断。
- 生成固定 schema 文本并限制最大长度。

### 2) Vision 输出升级为 JSON（但必须可回退）
- 将 vision prompt 从“一句话”升级为“输出 JSON：app/scene/action/entities”。
- 若 JSON 解析失败：回退到原一句话 + 规则提取，保证稳定性。

### 3) Worker：Text Embedding 用 Memory Card（DB 仍存原始 text/description）
- 避免长 OCR 主导 embedding。

### 4) Rerank：输入 Memory Card 证据（可选带图）
- Query + candidate 的 scene/action/entities/keywords/time + snippet
- 可选 `OPENRECALL_RERANK_INCLUDE_IMAGE=true` 时 topN 带截图输入。

### 5) 测试与全场景验收
- 覆盖：浏览器阅读、聊天沟通、文档写作、表格、终端、IDE 调试等。

如果你认可这个方向，我会先落地第 1+3（构造器 + worker 使用）确保收益，再做第 2（vision JSON）和第 4（rerank 补证据）。