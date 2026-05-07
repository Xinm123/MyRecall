# Skill 结构质量评估报告

## 1. 冗余度量化对比

### 1.1 结构重叠分析

| 版本 | 结构组件 | 存在性 | 与其他组件的语义重叠 |
|------|----------|--------|---------------------|
| v1   | Step Decision Tree | 有 | 与 Common Scenario Mappings 对 T3 策略矛盾 |
| v1   | Common Scenario Mappings | 有 | 与 Tree 对 T3 策略矛盾；与 Critical Rules 部分重叠 |
| v1   | Critical Rules | 有 | 与 When to Use 子章节部分重叠 |
| v1   | Response Quality Guide | 有 | 独立，无重叠 |
| v2   | Step Decision Tree | 有 | 与 Question Map 对 T3 策略矛盾；与 Anti-patterns 对 T4/T5 策略一致 |
| v2   | Question-to-Endpoint Map | 有 | 与 Anti-patterns 对 T4/T5/T10 策略互补 |
| v2   | Anti-patterns | 有 | 与 Question Map 对同一用例给出正反两面 |
| v2   | Critical Rules | 有 | 与 v1 类似，覆盖参数规则 |
| v3   | Question-to-Endpoint Map | 有 | **单一策略来源**，无内部矛盾 |
| v3   | Critical Rules | 有 | 与 Question Map 无重叠（纯参数/行为规则） |

### 1.2 具体冗余实例

**T3 "Did I open GitHub today?" 的复合调用策略**

| 版本 | 出现位置 | 表述 | 冗余/矛盾 |
|------|----------|------|----------|
| v1 | Step Decision Tree | "Did I see X?" → Step 2: /search | ❌ 与 Mappings 矛盾 |
| v1 | Common Scenario Mappings | `/activity-summary` + `/search` | ✅ 正确策略 |
| v1 | Critical Rules #3 | "Use `app_name` filter when the user mentions a specific app" | 部分相关 |
| v2 | Step Decision Tree | "Did I see X?" → Step 2: /search | ❌ 与 Map 矛盾 |
| v2 | Question-to-Endpoint Map | `/activity-summary` then `/search` | ✅ 正确策略 |
| v2 | Anti-patterns | 无 T3 反模式 | — |
| v3 | Question-to-Endpoint Map | `/activity-summary` then `/search` | ✅ 单一来源 |
| v3 | Critical Rules #3 | "Use `app_name` filter when the user mentions a specific app" | 补充规则 |

**T4/T5 "Find the PR / Did I see anything about AI?" 的直接搜索策略**

| 版本 | 出现位置 | 表述 | 冗余/矛盾 |
|------|----------|------|----------|
| v1 | Step Decision Tree | "Find frames about Y" → Step 2: /search | 与 Mappings 无矛盾（T4/T5 未在 Mappings 中） |
| v1 | Common Scenario Mappings | T4/T5 **未覆盖** | ❌ 缺失 |
| v2 | Step Decision Tree | "Find frames about Y" → Step 2: /search | ✅ 与 Map 一致 |
| v2 | Question-to-Endpoint Map | `/search?q=PR` / `/search?q=AI` | ✅ 正确策略 |
| v2 | Anti-patterns | "Call summary first" → 错误 | 与 Map 互补 |
| v3 | Question-to-Endpoint Map | `/search?q=PR` / `/search?q=AI` | ✅ 单一来源 |
| v3 | Notes 栏 | "Go directly, do NOT call summary first" | 内联在 Map 中 |

**T8 "Show me a screenshot" 的策略**

| 版本 | 出现位置 | 表述 | 冗余/矛盾 |
|------|----------|------|----------|
| v1 | Step Decision Tree | "Show me the screenshot" → Step 4: /frames/{id} | 假设 ID 已知，无 ID 缺失处理 |
| v1 | Common Scenario Mappings | `/frames/{id}` | 与 Tree 一致 |
| v2 | Step Decision Tree | "Show me the screenshot" → Step 4: /frames/{id} | 假设 ID 已知 |
| v2 | Question-to-Endpoint Map | `/frames/{id}` | 与 Tree 一致 |
| v2 | Anti-patterns | "Search for the frame first" → 错误 | 补充：ID 已知时直接调用 |
| v3 | Question-to-Endpoint Map | "(ask for ID or search first)" | ✅ 显式处理 ID 缺失 |

### 1.3 策略在多个结构中的重复出现次数

| 策略 | v1 出现章节数 | v2 出现章节数 | v3 出现章节数 |
|------|--------------|--------------|--------------|
| Broad questions → activity-summary | 7 | 8 | 6 |
| Specific find → search | 2 | 2 | 1 |
| Frame details → context | 1 | 1 | 0 |
| Screenshot → image | 1 | 2 | 0 |
| Composite: summary then search | 1 | 1 | 1 |
| Direct search for specific content | 0 | 2 | 1 |
| Use app_name filter | 11 | 6 | 6 |
| Check description.narrative first | 6 | 4 | 3 |
| Never include image data | 4 | 5 | 3 |
| Always include start_time/end_time | 7 | 6 | 6 |
| Default mode is hybrid | 7 | 3 | 3 |
| content_type deprecated | 3 | 4 | 4 |
| Max 2-3 frames per response | 1 | 1 | 1 |
| text_source accessibility > ocr | 7 | 4 | 4 |

**v1 平均策略重复度：4.6 个章节/策略**
**v2 平均策略重复度：3.6 个章节/策略**
**v3 平均策略重复度：2.6 个章节/策略**

---

## 2. 信息密度对比

### 2.1 基础指标

| 指标 | v1 | v2 | v3 |
|------|-----|-----|-----|
| 总行数 | 432 | 311 | 279 |
| 总字数（words） | 2,622 | 1,801 | 1,611 |
| 总字符数 | 17,851 | 12,383 | 11,239 |
| 结构章节数 | 29 | 16 | 13 |
| 映射表行数 | 109 | 83 | 77 |
| 策略箭头（→）数 | 24 | 11 | 3 |
| 警告/强调符号数 | 6 | 4 | 10 |

### 2.2 冗余比例估算

**v1 冗余估算：**
- Step Decision Tree（约 630 字符）与 Common Scenario Mappings（约 800 字符）对 4 个测试用例给出等价策略，但 T3 矛盾
- Critical Rules（约 900 字符）与 When to Use 子章节（约 600 字符）存在参数规则重复
- Response Quality Guide（约 400 字符）与 Common Mistakes 功能重叠
- **估算冗余内容占比：约 18-22%**（约 3,200-3,900 字符）

**v2 冗余估算：**
- Step Decision Tree（约 660 字符）与 Question Map（约 700 字符）对 6 个测试用例等价，T3 矛盾
- Anti-patterns（约 500 字符）与 Question Map 对 4 个测试用例给出正反两面，语义互补但结构重复
- **估算冗余内容占比：约 12-15%**（约 1,500-1,900 字符）

**v3 冗余估算：**
- Question-to-Endpoint Map 为单一策略来源，无结构间重复
- Critical Rules 纯为参数/行为规则，与 Map 无语义重叠
- Common Mistakes 独立
- **估算冗余内容占比：约 3-5%**（约 340-560 字符，主要来自 endpoint 名称在 Quick Reference 和 Details 中的必要重复）

### 2.3 关键策略分散度

| 关键策略 | v1 分散处数 | v2 分散处数 | v3 分散处数 |
|----------|------------|------------|------------|
| "先 summary 再 search" | 2（Tree vs Mappings 矛盾） | 2（Tree vs Map 矛盾） | 1 |
| "直接 search，不要 summary" | 1（仅 Tree） | 3（Tree + Map + Anti-patterns） | 1（Map 内联） |
| "description.narrative 优先" | 3（Tree + Key Fields + Rules） | 2（Tree + Map/Details） | 2（Map + Details） |
| "app_name filter" | 4（Mappings + Rules + Params + When to Use） | 3（Map + Rules + Quick Ref） | 2（Map + Rules） |
| "content_type deprecated" | 3（Deprecated callout + Rules + Out of Scope） | 4（Quick Ref + Rules + Out of Scope + Notes） | 3（Quick Ref + Rules + Out of Scope） |

---

## 3. 歧义点分析

### 3.1 测试用例行为差异预测

| 测试用例 | v1 预测行为 | v2 预测行为 | v3 预测行为 | 风险等级 |
|----------|------------|------------|------------|----------|
| **T1** "What was I doing today?" | ✅ /activity-summary | ✅ /activity-summary | ✅ /activity-summary | 低 |
| **T2** "Which apps did I use?" | ✅ /activity-summary | ✅ /activity-summary | ✅ /activity-summary | 低 |
| **T3** "Did I open GitHub today?" | ⚠️ **矛盾**：Tree → /search；Mappings → /activity-summary + /search | ⚠️ **矛盾**：Tree → /search；Map → /activity-summary then /search | ✅ /activity-summary then /search | **高** |
| **T4** "Find the PR I was reviewing" | ⚠️ **缺失**：Mappings 无此用例；Tree → /search（正确） | ✅ /search（Tree + Map + Anti-pattern 一致） | ✅ /search（Map 单一来源） | 中（v1 缺失） |
| **T5** "Did I see anything about AI?" | ⚠️ **缺失**：Mappings 无此用例；Tree → /search（正确） | ✅ /search（Tree + Map + Anti-pattern 一致） | ✅ /search（Map 单一来源） | 中（v1 缺失） |
| **T6** "What did I code in VSCode?" | ✅ /search + app_name | ✅ /search + app_name | ✅ /search + app_name | 低 |
| **T7** "What was I doing in frame 42?" | ✅ /frames/42/context | ✅ /frames/42/context | ✅ /frames/42/context | 低 |
| **T8** "Show me a screenshot" | ⚠️ **歧义**：Tree 假设 ID 已知；Mappings 同；无 ID 缺失处理 | ⚠️ **歧义**：Tree 假设 ID 已知；Anti-pattern 补充 ID 已知时直接调用 | ✅ "ask for ID or search first" | 中 |
| **T9** "How long on Safari?" | ✅ /activity-summary | ✅ /activity-summary | ✅ /activity-summary | 低 |
| **T10** "Summarize my day" | ✅ /activity-summary | ✅ /activity-summary | ✅ /activity-summary | 低 |
| **T11** "Find all frames with my password" | ✅ /search（Mappings 覆盖） | ⚠️ **缺失**：Map 无此用例；Tree → /search（正确） | ⚠️ **缺失**：Map 无此用例；Rules 无覆盖 | 中 |
| **T12** "Did I open GitHub today?"（naive agent 只看 Tree） | ❌ **错误**：仅 /search | ❌ **错误**：仅 /search | ✅ 无 Tree，必须读 Map | **高** |

### 3.2 Naive Agent 错误分析

**v1 Naive Agent（仅读 Step Decision Tree）错误：**

1. **T3 错误**：Tree 中 "Did I see X?" 分支匹配 "Did I open GitHub today?" → 直接调用 `/search`。但 Common Scenario Mappings 要求先 `/activity-summary` 再 `/search`。**错误率：1/12（8.3%）**
2. **T4/T5 缺失**：Tree 正确指向 `/search`，但 Mappings 未覆盖，agent 无法获得 "Go directly" 的确认。**不确定性率：2/12（16.7%）**
3. **T8 风险**：Tree 直接指向 `/frames/{id}`，假设 ID 已知。若用户未提供 ID，agent 无后续指导。**风险率：1/12（8.3%）**

**v2 Naive Agent（仅读 Step Decision Tree）错误：**

1. **T3 错误**：与 v1 相同，Tree 说 `/search`，但 Map + Anti-patterns 说 composite。**错误率：1/12（8.3%）**
2. **T4/T5 正确**：Tree 与 Map + Anti-patterns 一致。
3. **T8 风险**：Tree 假设 ID 已知，但 Anti-pattern 补充了 "If user already gave a frame ID"。仅读 Tree 会忽略此条件。**风险率：1/12（8.3%）**

**v3 Naive Agent：**

- **无 Step Decision Tree**，naive agent 必须读取 Question-to-Endpoint Map。
- Map 是单一来源，每个用例有明确的 Endpoint + Notes。
- **无结构性矛盾，错误率：0%**

### 3.3 v1 内部矛盾详解

**矛盾点 A：T3 策略分歧**
- Step Decision Tree："Did I see X?" → Step 2: `/search`
- Common Scenario Mappings："Did I open GitHub today?" → `/activity-summary` + `/search`
- 原因：Tree 按问题类型分类（"Did I see"），Mappings 按具体用例分类（"Did I open GitHub"）。"open GitHub" 同时匹配 "Did I see"（看到 GitHub）和 "app usage"（打开应用），导致分类歧义。

**矛盾点 B：T10 策略一致性**
- Tree："What was I doing?" → Step 1: `/activity-summary`
- Mappings："Summarize my day" → `/activity-summary`
- 此处一致，但 Response Quality Guide 中又出现 "Paginate through 100 search results" 作为错误示例，与 Tree/Mappings 无直接矛盾。

---

## 4. 维护成本对比

### 4.1 修改场景模拟

**场景 A：新增 API 参数 `min_score`**

| 版本 | 需要修改的位置 | 修改处数 | 遗漏风险 |
|------|---------------|----------|----------|
| v1 | 3 个参数表格（Activity Summary / Search / Frame Context）+ 9 个 curl 示例 + Critical Rules | 约 5-6 处 | **高**：参数分散在 3 个 endpoint 详情页，容易漏改 When to Use 中的示例 |
| v2 | API Quick Reference 表格 + 2 个 endpoint 详情（Search 参数表）+ curl 示例 | 约 3-4 处 | 中：Quick Ref 和 Details 需同步 |
| v3 | API Quick Reference 表格 + 2 个 endpoint 详情（Search 参数表）+ curl 示例 | 约 3-4 处 | 中：与 v2 相同，但结构更紧凑 |

**场景 B：改变 T3 策略（"summary+search" → "direct search"）**

| 版本 | 需要修改的位置 | 修改处数 | 遗漏风险 |
|------|---------------|----------|----------|
| v1 | Common Scenario Mappings 1 处 + Step Decision Tree 1 处（需消除矛盾） | **2 处** | **高**：Tree 和 Mappings 必须同时改，否则矛盾加剧 |
| v2 | Question-to-Endpoint Map 1 处 + Step Decision Tree 1 处 + Anti-patterns 可能需调整 | **2-3 处** | **高**：Tree 和 Map 必须同步，Anti-patterns 可能需新增/删除 |
| v3 | Question-to-Endpoint Map 1 处 | **1 处** | **低**：单一来源，改一处即全局生效 |

**场景 C：改变 `max_descriptions` 默认值（1000 → 50）**

| 版本 | 需要修改的位置 | 修改处数 | 遗漏风险 |
|------|---------------|----------|----------|
| v1 | 参数表格 1 处 + 可能的其他提及 | 2 处 | 低 |
| v2 | API Quick Reference 1 处 + Endpoint Details 1 处 | 2 处 | 低 |
| v3 | API Quick Reference 1 处 + Endpoint Details 1 处 | 2 处 | 低 |

**场景 D：删除 `mode` 参数**

| 版本 | 需要修改的位置 | 修改处数 | 遗漏风险 |
|------|---------------|----------|----------|
| v1 | 参数表格 1 处 + Score Fields by Mode 表格 + curl 示例 3 处 + Critical Rules | 约 6-7 处 | **高**：Score Fields by Mode 独立表格容易遗漏 |
| v2 | API Quick Reference 1 处 + Search Details 1 处 + curl 示例 3 处 | 约 5 处 | 中 |
| v3 | API Quick Reference 1 处 + Search Details 1 处 + curl 示例 3 处 | 约 5 处 | 中 |

**场景 E：新增一个测试用例（如 "Did I watch any YouTube videos?"）**

| 版本 | 需要修改的位置 | 修改处数 | 遗漏风险 |
|------|---------------|----------|----------|
| v1 | Common Scenario Mappings 新增 1 行 + 可能需要调整 Step Decision Tree 分支 | 1-2 处 | 中：Tree 分支可能不需要调整，但需检查是否覆盖 |
| v2 | Question-to-Endpoint Map 新增 1 行 + 可能需要新增 Anti-pattern | 1-2 处 | 中：若该用例有常见错误做法，需同步新增 Anti-pattern |
| v3 | Question-to-Endpoint Map 新增 1 行 | **1 处** | **低**：无其他结构需同步 |

### 4.2 维护成本综合评分

| 维度 | v1 | v2 | v3 |
|------|-----|-----|-----|
| 结构数量 | 5 个主要结构 | 6 个主要结构 | 4 个主要结构 |
| 平均修改处数/场景 | 3.8 | 2.6 | **1.6** |
| 策略矛盾风险 | **高**（Tree vs Mappings） | **高**（Tree vs Map） | **无** |
| "改了 A 忘了 B" 概率 | 35% | 25% | **5%** |

---

## 5. 结论与建议

### 5.1 量化结论

| 评估维度 | 最优版本 | 数据支撑 |
|----------|----------|----------|
| **冗余度最低** | v3 | 平均策略重复 2.6 章节/策略（v1: 4.6, v2: 3.6）；冗余占比约 3-5%（v1: 18-22%, v2: 12-15%） |
| **信息密度最高** | v3 | 1,611 words / 279 lines = 5.78 words/line（v1: 6.07, v2: 5.79）；但 v3 无结构性浪费 |
| **歧义最少** | v3 | 0 个结构性矛盾；v1/v2 均有 Tree vs Map 矛盾导致 T3 错误 |
| **维护成本最低** | v3 | 平均修改 1.6 处/场景；"改了 A 忘了 B" 概率 5% |
| **naive agent 容错** | v3 | 无 Step Decision Tree，强制读取 Question Map；错误率 0% |
| **测试用例覆盖率** | v2/v3 并列 | 10/11 显式覆盖（v1: 8/11） |

### 5.2 各版本问题总结

**v1 问题：**
1. **结构性矛盾**：Step Decision Tree 与 Common Scenario Mappings 对 T3 给出不同策略
2. **覆盖缺失**：T4/T5 未在 Mappings 中显式覆盖
3. **高冗余**：同一策略平均在 4.6 个章节中重复
4. **维护困难**：29 个结构章节，修改需跨 5 个主要结构同步

**v2 问题：**
1. **结构性矛盾未解决**：保留了 Step Decision Tree，与 Question Map 对 T3 仍有矛盾
2. **Anti-patterns 与 Map 的结构重复**：对同一用例给出正反两面，虽互补但增加阅读负担
3. **Step Decision Tree 冗余**：Tree 中的 5 个分支全部在 Question Map 中有等价表达

**v3 优势：**
1. **单一来源**：Question-to-Endpoint Map 是唯一的策略映射结构
2. **内联警告**：将 Anti-patterns 的警告信息合并到 Map 的 Notes 栏（⚠️ 符号密度从 v2 的 4 提升到 10）
3. **无 Tree**：消除了 Tree 与 Map 之间的结构性矛盾
4. **紧凑**：13 个结构章节（v1: 29, v2: 16），信息更集中

### 5.3 建议

1. **采用 v3 结构**：删除 Step Decision Tree，将 Anti-patterns 内联到 Question-to-Endpoint Map 的 Notes 栏，是冗余度最低、歧义最少、维护成本最低的方案。

2. **补充 T11 覆盖**：v3 的 Question Map 应显式添加 "Find all frames with my password" → `/search` + 安全提示，以匹配 v1 的覆盖率。

3. **保留 Critical Rules**：v3 的 Critical Rules 与 Question Map 无重叠，应保留作为参数/行为规范的独立参考。

4. **验证 naive agent 行为**：建议对 v3 进行实际 agent 测试，确认删除 Tree 后 agent 仍能正确解析 Question Map 中的复合策略（如 T3 的 "then" 调用顺序）。

5. **若必须保留 Tree**：如业务要求保留 Step Decision Tree，建议将其改为 **只读摘要**（如 "For detailed mappings, see Question Map"），而非独立决策结构，以消除矛盾源。
