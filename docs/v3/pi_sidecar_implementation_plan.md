# Pi Sidecar 实现路线图

- 版本：v1.0
- 日期：2026-03-01
- 依赖决策：DA-2（修订）、DA-3、DA-5、DA-7=A、DA-8=A→B、DA-9=C
- 依赖决策点：DP-1=A（Flask + threading）、DP-2=A（Edge 数据目录）、DP-3=A（Manager 始终从 chat_messages 注入历史）
- 关联文档：`ADR-0004`、`spec.md` §3.6、`roadmap.md` P1-S5/S6/S7、`chat_baseline_myrecall.md`

---

## 0. 架构总览

```
Frontend (Alpine.js + EventSource)
  │  POST /v1/chat {message, session_id, images?}
  ▼
Edge Python (Flask + threading, DP-1=A)
  ├─ /v1/chat endpoint (api.py)
  │    → PiManager.send_prompt()
  │    → SSE stream_with_context(generator)
  │
  ├─ chat/manager.py — PiManager (singleton)
  │    ├─ start/stop Pi subprocess
  │    ├─ send_prompt / abort / new_session
  │    ├─ session history injection (DP-3=A: 始终从 chat_messages 注入)
  │    └─ watchdog (idle timeout / crash restart)
  │
  ├─ chat/process.py — PiProcess (subprocess.Popen wrapper)
  │    ├─ spawn: bun ~/.bun/bin/pi --mode rpc --provider <p> --model <m>
  │    ├─ stdin write (JSON Lines)
  │    └─ stdout readline (JSON Lines → PiEvent)
  │
  ├─ chat/protocol.py — Pi JSON Lines ↔ SSE 桥接
  │    ├─ parse_pi_event(line) → PiEvent dataclass
  │    └─ pi_event_to_sse(event) → SSE formatted string
  │
  ├─ chat/persistence.py — chat_messages CRUD
  │    ├─ save_message(session_id, role, content, ...)
  │    ├─ get_session_history(session_id, limit=N)
  │    └─ list_sessions()
  │
  └─ chat/config.py — Pi 配置管理
       ├─ detect bun/pi availability
       ├─ models.json read/write
       └─ skills injection (copy SKILL.md → Pi workdir)

Pi Sidecar (bun process, --mode rpc)
  ├─ stdin: {type:"prompt", message:"...", id:"req_N"}
  ├─ stdout: JSON Lines events (11 types)
  ├─ LLM Provider (via --provider/--model)
  └─ curl Edge /v1/search (via myrecall-search SKILL.md)
```

### Pi 工作目录（DP-2=A）

```
$OPENRECALL_SERVER_DATA_DIR/     # 例如 ~/MRS/
  .pi/
    skills/
      myrecall-search/
        SKILL.md                 # Manager 启动时从 openrecall/server/skills/ 复制
    agent/
      models.json                # Provider/model 配置
      auth.json                  # API tokens（由用户配置）
```

- 路径不变量：`get_pi_workdir()` 始终返回 `$OPENRECALL_SERVER_DATA_DIR/.pi`。在 `pi_workdir` 下直接拼接 `skills/...`、`agent/...`，不得再次追加 `/.pi` 层级。

---

## 1. 新增文件结构

```
openrecall/server/
  chat/                          # 新增 package
    __init__.py                  # (~5 lines)
    manager.py                   # PiManager class (~400 lines)
    process.py                   # PiProcess subprocess wrapper (~150 lines)
    protocol.py                  # Pi JSON Lines parsing + SSE serialization (~100 lines)
    persistence.py               # chat_messages CRUD (~80 lines)
    config.py                    # Pi config management (~60 lines)
  skills/                        # 新增目录
    myrecall-search/
      SKILL.md                   # P1-S5 唯一 Skill (~200 lines)
  api.py                         # 修改：新增 /v1/chat endpoint (SSE streaming)
  templates/
    chat.html                    # 新增：Chat UI minimal (Alpine.js + EventSource)

scripts/
  install_pi.sh                  # 新增：bun + Pi installer (~60 lines)

tests/
  test_chat_manager.py           # 新增
  test_chat_protocol.py          # 新增
  test_chat_persistence.py       # 新增
```

---

## 2. P1-S5 交付清单（Grounding 与引用）

| # | 交付物 | 文件 | 估算行数 | 说明 |
|---|--------|------|---------|------|
| S5-1 | bun + Pi 安装脚本 | `scripts/install_pi.sh` | ~60 | 检测 bun 是否已安装 → 安装 bun → 安装 Pi（`bun add -g @mariozechner/pi-coding-agent@<pinned-version>`，对齐 screenpipe）→ 验证 `pi --version` |
| S5-2 | PiProcess | `chat/process.py` | ~150 | `subprocess.Popen` wrapper；spawn Pi with `--mode rpc --provider --model`；stdin write JSON Lines；stdout readline loop（daemon thread）；graceful shutdown（SIGTERM → 3s → SIGKILL）；startup wait 1.5s |
| S5-3 | PiManager | `chat/manager.py` | ~400 | Singleton；`start()`/`stop()`/`send_prompt(message, session_id, images?)`/`abort(req_id)`/`new_session()`；Session history injection（DP-3=A：每次 `send_prompt` 前从 `chat_messages` 读取最近 N 条，构造 `<conversation_history>` XML block 拼入 prompt）；Event queue（`queue.Queue`）供 SSE generator 消费 |
| S5-4 | Protocol 桥接 | `chat/protocol.py` | ~100 | `parse_pi_event(json_line) → PiEvent`（dataclass：type, data, id）；`pi_event_to_sse(event) → str`（`data: {json}\n\n`）；处理 11 种 Pi 事件类型；stream end 判定：`response` 事件（success 或 error） |
| S5-5 | myrecall-search Skill | `skills/myrecall-search/SKILL.md` | ~200 | 对标 `screenpipe-search/SKILL.md`（255 行）；定义 `curl http://localhost:{port}/v1/search` 调用方式；包含参数说明（query, app_name, start_time, end_time, limit）；包含返回格式说明和引用格式指引（提示 Pi 在回答中内嵌 timestamp/关键词） |
| S5-6 | Skills 注入 | `chat/config.py` | ~60 | `inject_skills(pi_workdir)`：将 `openrecall/server/skills/*/SKILL.md` 复制到 `{pi_workdir}/skills/{name}/SKILL.md`；`detect_bun()`/`detect_pi()`：检查可执行文件可用性；`get_pi_workdir() → Path`：返回 `$OPENRECALL_SERVER_DATA_DIR/.pi`（DP-2=A） |
| S5-7 | /v1/chat endpoint | `api.py`（修改） | ~80 | `POST /v1/chat`：解析 `{message, session_id, images?}`；调用 `PiManager.send_prompt()`；返回 `Response(stream_with_context(sse_generator()), mimetype='text/event-stream')`（DP-1=A：Flask + threading） |
| S5-8 | 持久化 | `chat/persistence.py` | ~80 | `save_message(session_id, role, content, citations, tool_calls, model, latency_ms)`；`get_session_history(session_id, limit=20) → list[dict]`；`list_sessions() → list[dict]`；使用 `chat_messages` 表（schema per `spec.md` §3.0.3 Table 5）；stream end 后由 Manager 调用保存 user + assistant 消息 |
| S5-9 | Chat UI minimal | `templates/chat.html` | ~200 | Alpine.js + EventSource；消息列表（user/assistant 交替）；输入框 + 发送按钮；SSE 连接处理（`onmessage` 按事件类型更新 UI）；`message_update` → 追加 text delta；`tool_execution_*` → 显示工具调用状态；`response` → 流结束；错误状态展示 |

**P1-S5 小计：~1330 行**

### S5 验收对照

- Chat 工具能力清单完成率 = 100%（search/frame lookup/time range expansion 均通过 myrecall-search Skill 覆盖）
- Chat 引用点击回溯成功率 >= 95%（通过 Skill 提示词引导 Pi 内嵌 timestamp，UI 中可点击跳转 timeline）
- 观测 KPI：Chat 引用覆盖率目标 >= 85%（non-blocking）

---

## 3. P1-S6 交付清单（路由与流式）

| # | 交付物 | 文件 | 估算行数 | 说明 |
|---|--------|------|---------|------|
| S6-1 | models.json 配置 UI | `templates/settings.html`（修改）+ `chat/config.py`（扩展） | ~100 | Provider/model 选择下拉；保存时写入 `{pi_workdir}/agent/models.json`；Manager 检测配置变更 → 重启 Pi 进程 |
| S6-2 | Watchdog | `chat/manager.py`（扩展） | ~80 | 5 min idle timeout → 优雅关闭 Pi 进程；crash auto-restart（max 3 in 60s，超限则报告 fatal）；orphan cleanup（启动时读取 `{pi_workdir}/manager.pid`，验证 cmdline 匹配后 kill 该 PID；不使用 `pkill -f` 以避免误杀其他实例的 Pi 进程） |
| S6-3 | Error event 处理 | `chat/protocol.py` + `chat/manager.py`（扩展） | ~60 | `response.success=false` → SSE error event frame；Pi crash（stdout EOF）→ SSE interrupt frame + 错误描述；Manager 日志记录错误上下文 |
| S6-4 | Streaming 协议测试 | `tests/test_chat_protocol.py` | ~150 | Event ordering 验证（message_start → message_update* → message_end）；嵌套验证（turn_start 包含 agent_start/end）；termination 验证（response 事件必须是最后一个）；error frame 格式验证 |
| S6-5 | Provider timeout | `chat/manager.py`（扩展） | ~40 | First-token timeout >15s → abort 当前请求 → 返回 timeout error event；**不做自动 fallback**（DA-5，对齐 screenpipe）；日志记录 timeout 上下文 |
| S6-6 | UI 路由状态 | `templates/chat.html`（扩展） | ~70 | Provider/model badge 显示当前配置；error/timeout notification（toast 或 inline 消息）；Pi 进程健康状态指示器（connected/disconnected/error） |

**P1-S6 小计：~500 行**

### S6 验收对照

- Chat 首 token P95 <= 3.5s
- 路由切换在故障注入下可重复通过
- 路由切换场景覆盖率 = 100%（注意：P1 不含 auto-fallback 场景，覆盖 provider 切换 + timeout 错误）
- 流式输出协议一致性用例通过率 = 100%
- 路由与超时状态可见场景覆盖率 = 100%

---

## 4. P1-S7 交付清单（E2E 验收）

| # | 交付物 | 文件 | 估算行数 | 说明 |
|---|--------|------|---------|------|
| S7-1 | E2E 测试集 | `tests/test_chat_e2e.py` | ~200 | >= 30 场景覆盖：正常问答、工具调用、引用回溯、多轮对话、session 恢复、错误处理、timeout、Pi crash 恢复 |
| S7-2 | Citation 覆盖率评估 | 评估报告（非代码） | — | 在 grounding 问题集（>= 80 条）上统计引用覆盖率；评估 DA-8=A（提示词驱动）的实际效果 |
| S7-3 | DA-8 B 阶段决策 | ADR 更新或新建 | — | 根据 S7-2 评估结果决定：是否需要结构化 citation 后处理（DA-8 B 阶段）；若需要，产出实现方案 |
| S7-4 | S1-S6 回归 | 回归报告 | — | 逐项确认 S1~S6 Gate 结果仍为 Pass |
| S7-5 | 性能基线 | 性能报告 | — | TTS P95、Chat first-token P95、Search P95 基线数据 |

**P1-S7 小计：~200 行（代码），其余为评估/报告**

### S7 验收对照

- TTS P95 <= 12s
- S1~S6 回归全通过
- P1 功能清单完成率 = 100%
- P1 验收记录完整率 = 100%
- UI 关键路径脚本通过率 = 100%
- 观测 KPI：Chat 引用覆盖率目标 >= 92%（non-blocking）

---

## 5. 工作量汇总

| 阶段 | 新增代码 | 修改代码 | 测试代码 | 小计 |
|------|---------|---------|---------|------|
| P1-S5 | ~1130 | ~80 (api.py) | ~200 (预留) | ~1330 |
| P1-S6 | ~170 | ~330 (扩展已有文件) | ~150 | ~500 |
| P1-S7 | ~0 | ~0 | ~200 | ~200 |
| **总计** | **~1300** | **~410** | **~550** | **~2030** |

---

## 6. 确认的决策点摘要

| 决策点 | 选项 | 确认结果 | 理由 |
|--------|------|---------|------|
| DP-1 | Flask SSE 流式方案 | **A) Flask + threading** | P1 单用户场景足够；`stream_with_context` + daemon thread 读取 Pi stdout → queue → SSE generator；避免 async 迁移成本 |
| DP-2 | Pi 工作目录 | **A) Edge 数据目录** `$OPENRECALL_SERVER_DATA_DIR/.pi/` | 与 MyRecall 数据管理统一；Pi skills、models.json、auth.json 均在 Edge 数据目录下；备份/迁移时随数据目录一起 |
| DP-3 | Session 历史注入 | **A) Manager 始终注入** | 每次 `send_prompt` 前从 `chat_messages` 读取最近 N 条历史拼入 prompt；Pi 进程重启/crash 后自动恢复对话上下文；不依赖 Pi 内存状态 |

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Pi binary 不稳定或版本更新破坏 RPC 协议 | Chat 功能中断 | `install_pi.sh` 锁定 Pi 版本；protocol.py 做事件类型白名单过滤，未知事件 warn+skip |
| bun 在 Debian 受限环境安装失败 | 无法启动 Pi | `install_pi.sh` 包含 fallback 安装路径（curl script → npm global）；config.py 启动时检测并给出诊断信息 |
| Flask + threading 在高并发下阻塞 | P1 不受影响（单用户） | P1 scope 明确单用户；P2+ 若需多用户并发再评估 async 迁移（DP-1 B 方案） |
| 提示词驱动 citation（DA-8=A）覆盖率不达标 | 引用质量低 | P1-S7 评估点决定是否启动 DA-8 B 阶段；Skill 提示词持续优化；覆盖率为 non-blocking KPI |
| Session 历史注入 token 过长 | LLM 上下文窗口溢出 | 限制注入条数（默认 20 条）；按 token 估算截断；在 config 中可配置 |

---

## 8. screenpipe 参考映射

MyRecall Pi Sidecar 实现与 screenpipe 的对应关系：

| MyRecall 组件 | screenpipe 对应 | 对齐程度 |
|--------------|----------------|---------|
| `chat/process.py` (PiProcess) | `pi.rs` spawn/stdin/stdout 逻辑 | 行为对齐，语言适配（Rust → Python） |
| `chat/manager.py` (PiManager) | `pi.rs` PiManager struct | 行为对齐，增加 DP-3 历史注入 |
| `chat/protocol.py` | `pi-event-handler.ts` 11 种事件 | 完全对齐，输出从 IPC 改为 SSE |
| `chat/config.py` skills injection | `pi.rs` copy_skills_to_workdir | 完全对齐 |
| `skills/myrecall-search/SKILL.md` | `screenpipe-search/SKILL.md` | 行为对齐，API 端点适配 |
| `chat/persistence.py` | screenpipe 无独立持久化层 | 新增（screenpipe 依赖前端状态管理） |
| Flask SSE streaming | Tauri IPC events | 拓扑适配（per Decision 001A） |
