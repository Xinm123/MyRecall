## 现状判断（为什么你会觉得“没解决”）
- 目前的实现是“关闭后不再领取新任务 + 协作式取消（在阶段边界检查）”。
- 但如果 worker 已经进入 `ai_engine.analyze_image(...)` 这类耗时调用，线程无法被强行中断，所以它会继续跑到该调用返回为止；在这段时间里 DB 里的 `status` 仍是 `PROCESSING`，UI 就会一直显示 Processing。

## 目标（你想要的体验）
- 你点开关从 ON → OFF 后：
  - UI 上正在 PROCESSING 的卡片应当立刻不再显示 Processing（回退到 Pending/取消中）。
  - 后台即便还在跑模型，也不能再把结果写回库（避免“关了还生成结果”）。

## 实施方案

### 1) 关掉 AI Processing 时立刻“回退所有 PROCESSING → PENDING”（后端）
- 在 `POST /api/config` 中，当 `ai_processing_enabled` 从 true→false 时：
  - 递增 `ai_processing_version`（已经有）
  - **重新调用** `reset_stuck_tasks()`，把当前所有 `PROCESSING` 直接改回 `PENDING`，让 UI 立刻反映“已取消”。
- 这样即便 worker 仍在模型调用里跑，状态也不会继续显示 PROCESSING。

### 2) worker 写库失败时识别“取消导致的 rowcount=0”，不再报错（后端）
- 在 `worker._process_task` 的 `mark_task_completed(...)` 返回 False 的分支：
  - 如果此时检测到 `ai_processing_enabled` 为 false 或 `ai_processing_version` 已变化：
    - 视为“被取消”，不再打印 `Failed to update database`
    - 尝试把该任务回退为 PENDING（如果仍是 PROCESSING）
  - 否则才保留错误日志（真 DB 问题）。
- 目的：避免你关闭开关后出现误导性的 ERROR。

### 3) 前端无需额外改动
- Grid 已经有 `/api/memories/recent` 轮询合并，所以只要 DB status 变了，界面几秒内会自动刷新。

## 验证方式
- `conda activate MyRecall` 后启动 server/client。
- 让某条任务进入 PROCESSING，然后在 UI 关闭 AI Processing：
  - 预期：该卡片在 0~5 秒内从 Processing 变回 Pending（无需刷新）。
  - server 日志不再出现 `Failed to update database`（关闭导致的那种）。

## 说明（客观限制）
- 由于模型推理函数本身不可中断，**CPU/GPU 计算可能仍会跑到本次调用结束**；但从“状态/结果落库/界面显示”角度会被视为已取消，且不会写回结果。