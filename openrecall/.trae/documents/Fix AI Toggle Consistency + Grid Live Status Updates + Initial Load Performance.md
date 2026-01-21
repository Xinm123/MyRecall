## 1) 关于日志：`Task #64: Failed to update database` 是否有问题？
- 这是“worker 处理完了，但写回 DB 时 update 没成功”的信号，不只是噪音。
- 结合当前代码，它最常见的触发链路是：你在 UI 把 **AI Processing 关掉**时，后端会把所有 `PROCESSING` 任务重置成 `PENDING`（[api.py:L259-L266](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/api.py#L259-L266)）；而 worker 写回完成结果时 SQL 只允许 `WHERE status='PROCESSING'`（[database.py:L475-L486](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py#L475-L486)），所以 rowcount=0 → 报你看到的错误（[worker.py:L165-L179](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/worker.py#L165-L179)）。
- 结果可能是：这张图实际已经算完，但 description/embedding 没写进库，条目会卡在 PENDING/PROCESSING，刷新后“看起来变了/又不对”。

## 2) Toggle 后 Grid 不变（刷新才变）的根因
- Grid 的轮询只做“拉新条目”：`/api/memories/latest?since=lastCheck`，lastCheck 基于 timestamp。
- 但同一条 entry 状态从 `PENDING/PROCESSING → COMPLETED` 时 timestamp 不变，因此不会再被增量接口返回；前端也就不会更新已有卡片的 status/description。
- 另外，Grid 页面里渲染 AI 描述的开关用的是 `settings.show_ai_description`（静态配置），而 Control Center 的 “Show AI” 是 `ui_show_ai`（运行时配置），它只是用 CSS 隐藏 `.ai-insight-text`；这块逻辑本身没问题，但它不会解决 status/description 同步。

## 3) 刷新/切页面时图片先不出来、卡顿
- 初始会触发大量图片请求与布局计算；同时我们现在用 Alpine + `x-cloak`，如果 Alpine 加载/初始化慢就会先空白。
- 另外图片缺少“占位尺寸/优先级控制”，容易出现首屏优先级不对、CLS（布局抖动）和主线程忙导致的卡顿。

---

## 最终效果（修完后你会看到什么）
- 关闭 AI Processing：
  - 不会再把正在处理的任务强行改回 PENDING（避免 worker 写回失败）。
  - 行为变成“停止领取新任务”，正在处理的那张可以正常完成并落库。
  - Grid 会在几秒内自动反映 status/description 的变化（无需刷新）。
- Grid：
  - 除了“新增截图自动 prepend”，已有卡片的 `PENDING/PROCESSING/COMPLETED` 和 description 也会自动刷新。
- 性能：
  - 首屏图片更快出现；减少首次进入/切页的卡顿与“图片一开始不显示”。

---

## 实施计划

### A. 修复 worker 写库失败的根因（后端）
1. 调整 `POST /api/config`：当 `ai_processing_enabled` 从 true → false 时，不再调用 `reset_stuck_tasks()`（避免把正在处理的任务改成 PENDING）。
2. 在 worker 中检查 `mark_task_processing(...)` 的返回值；如果未成功标记为 PROCESSING，则跳过该任务，避免无意义算一遍最后写不进去。

### B. 让 Grid 能“刷新已有条目”的状态/描述（后端 + 前端）
1. 增加一个“近期快照”接口（例如）：`GET /api/memories/recent?limit=200`
   - 返回最新 N 条 entries（id/timestamp/app/title/description/status/filename）。
2. 在 `memoryGrid()` 中新增一个轮询：每 5 秒拉一次 recent snapshot，并按 `id` merge 到 `this.entries`：
   - 如果已存在同 id：更新 `status/description/app/title`。
   - 如果不存在：当作新条目 prepend（与现有逻辑兼容）。

### C. 优化初次加载卡顿/图片延迟（前端）
1. 为首屏几张图设置更高优先级：
   - 动态绑定 `loading`（前几张 eager，其余 lazy）
   - 添加 `decoding="async"` 与 `fetchpriority`（前 1-2 张 high）
2. 降低大量卡片的渲染压力：给 `.memory-card` 增加 `content-visibility: auto` + 合理的 `contain-intrinsic-size`。

---

## Verification
- 运行前：`conda activate MyRecall`。
- 复现与验证：
  1) 打开 `/`，观察 Grid 正常渲染。
  2) 运行 client，产生新截图：新卡片自动出现在左上角。
  3) 观察某条从 PROCESSING → COMPLETED：无需刷新，卡片文案/状态自动更新。
  4) 点击 AI Processing 关闭：不再出现 “Failed to update database”，并且 Grid 状态仍能自动更新。