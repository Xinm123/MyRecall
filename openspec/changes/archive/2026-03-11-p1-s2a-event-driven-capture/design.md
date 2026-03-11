## Context

P1-S1 已交付基础 ingest 链路：Host spool → Edge 入队 → 状态机骨架（`processing_mode=noop`）。当前 Client 的 `ScreenRecorder.run_capture_loop()` 使用固定 `time.sleep(settings.capture_interval)` 轮询，通过 MSSIM 相似度比较决定是否入队。这一机制存在以下问题：

1. **无触发语义**：`frames.capture_trigger` 列在 DDL 中已存在，但 Host 从不赋值——等于浪费了 screenpipe 事件驱动的核心能力。
2. **静态屏幕资源浪费**：轮询模式在用户不活跃时仍周期截图 + MSSIM 对比，CPU 开销非零。
3. **无背压保护**：`spool.enqueue()` 不限速，高频截图可能拖垮 spool → uploader → Edge ingest 链路。
4. **权限不可观测**：当前仅在截图全黑时打 warning 日志，无状态机、无 health 暴露。

screenpipe 的对应方案（`crates/screenpipe-server/src/event_driven_capture.rs`）是 CGEventTap 事件驱动 + 全局最小间隔去抖（默认 200ms）+ idle fallback（默认 30s）+ per-monitor 执行循环。P1-S2a 在 Python + pyobjc 技术栈下重新实现此架构的核心子集。

**继承自 P1-S1（frozen）**：`/v1/ingest` 基础链路、queue-observability、frame-serving、legacy `/api/*` 301/410。

## Goals / Non-Goals

**Goals:**
- G1：实现 macOS CGEventTap 事件监听（click, app_switch），替代固定轮询作为主触发源。
- G2：每条 capture 必须赋值 `capture_trigger`（P1 枚举：`idle/app_switch/manual/click`），满足 `trigger_coverage = 100%`。
- G3：全触发共享去抖门控，`min_capture_interval_ms=1000`（1 Hz），去抖违规数 = 0。
- G4：idle fallback（`idle_capture_interval_ms=30000`），采用超时触发语义（不依赖用户活跃判定）。
- G5：有界触发通道 + lag 折叠策略，满足 `queue_saturation_ratio <= 10%`、`collapse_trigger_count >= 1`、`overflow_drop_count = 0`。
- G6：权限状态机（`granted/transient_failure/denied_or_revoked/recovering`），`/v1/health` 暴露 `capture_permission_status/reason/check_ts`。
- G7：`capture_latency_p95` 强制观测记录（non-blocking，不参与 Gate Pass/Fail）。
- G8：`POST /v1/ingest` 对 `capture_trigger` 执行枚举校验生效。

**Non-Goals:**
- AX 文本采集（P1-S2b）
- `content_hash` 计算与去重（P1-S2b）
- typing_pause / scroll_stop / window_focus 触发类型（P2）
- Windows / Linux 事件监听（P2）
- 高于 1 Hz 的采集频率

## Decisions

### D1：事件监听技术选型 — pyobjc CGEventTap

**选择**：`Quartz.CGEventTapCreate` via pyobjc。

**理由**：
- screenpipe 使用 cidre 封装的 `CGEventTapCreate`（`screenpipe-events` crate），行为验证充分。
- pyobjc 是 Python 生态中唯一提供 Quartz CG EventTap FFI 的生产级库。
- 不使用 pynput/keyboard 等高层库：它们隐藏底层 mask 配置，无法精确区分 click vs typing_pause。

**screenpipe 对齐**：aligned — 同为 CGEventTap，仅语言从 Rust 改为 Python。

**备选方案**：
- `pynput`：高层封装，无法获取 app_switch 事件、无法控制 event mask。❌ 放弃。
- `pyautogui`：无事件监听能力。❌ 放弃。

**实现路径**：新模块 `openrecall/client/events/macos.py`，封装为类：

```python
class MacOSEventTap:
    """macOS CGEventTap 封装，监听鼠标点击事件并转换为 TriggerEvent 回调。"""
    
    def __init__(
        self,
        callback: Callable[[TriggerEvent], None],
        monitor_lookup: Callable[[float, float], MonitorDescriptor | None],
    ) -> None:
        """初始化事件监听器。
        
        Args:
            callback: 事件回调函数，接收 TriggerEvent 参数
            monitor_lookup: 根据屏幕坐标查找对应 monitor 的函数
        """
    
    def start(self) -> None:
        """启动 CGEventTap 监听（在独立线程中运行 CFRunLoop）。"""
```

### D2：触发通道架构 — 有界 trigger_event_queue + 折叠

**选择**：`queue.Queue(maxsize=64)` 作为 Host 侧 `trigger_event_queue`；overflow 策略为 lag 折叠（优先合并落后事件），而非阻塞 event tap 线程。

**理由**：
- screenpipe 当前触发通道使用 `tokio::sync::broadcast::channel(64)`（`crates/screenpipe-server/src/event_driven_capture.rs`）；接收端 lag 时通过 `Lagged(n)` 做折叠式恢复。
- Python GIL 下使用 `queue.Queue` 天然线程安全，无需额外 lock。
- **有意偏离 screenpipe**：overflow 时不阻塞 event tap 线程（会导致系统级事件延迟），而是折叠——将旧 pending 事件合并为一个最新事件，记录 `collapse_trigger_count`。
- `overflow_drop_count` 语义：仅当通道完全满且无法完成一次折叠后重入队时才递增（正常运行下应 = 0）。

**折叠算法（锁定）**：
1. `put_nowait(trigger_event)` 成功则直接返回。
2. 若 `Full`：执行一次 `get_nowait()` 弹出最老事件（FIFO 头）。
3. 立即重试一次 `put_nowait(trigger_event)`：
   - 成功：`collapse_trigger_count += 1`
   - 再次失败：`overflow_drop_count += 1`，丢弃当前新事件。

**计数口径（锁定）**：
- `collapse_trigger_count` 按“成功折叠次数”计数（每次弹出并重入队成功记 1）。
- `overflow_drop_count` 按“新事件最终无法入队次数”计数（每次记 1）。

**观测源（锁定）**：
- `queue_depth/queue_capacity/collapse_trigger_count/overflow_drop_count` 属于 Host `trigger_event_queue` 指标。
- Client 通过状态上报通道以 **1Hz** 上报上述指标；Server 保留最近 5 分钟原始样本环形缓冲（用于 Gate 采样）。
- Edge 必须通过统一读口径暴露该镜像计数器与采样窗口统计（供 `queue_saturation_ratio`、`collapse_trigger_count`、`overflow_drop_count` 验收读取）。

**screenpipe 对齐**：intentionally different — screenpipe 使用 broadcast 通道 + lag 恢复，MyRecall 使用非阻塞折叠（保护 event tap 线程）。

**maxsize=64 依据**：1 Hz 频率下 64 秒缓冲，远超正常处理延迟；与 screenpipe 当前触发通道容量（64）一致量级。

### D3：去抖实现 — 单一全局 debouncer

**选择**：所有触发类型共享 `min_capture_interval_ms=1000` 去抖。第一个事件立即触发，后续事件在窗口内被抑制。

**理由**：
- screenpipe 当前实现使用全局 `min_capture_interval_ms` 去抖（默认 200ms），并对 typing/scroll 使用独立延迟参数（`typing_pause_delay_ms=500`、`scroll_stop_delay_ms=300`）。
- P1 简化为单一全局计时器——1 Hz 安全起点，Python 实现下无需精细区分。
- 去抖以 `device_name` 分区（多 monitor 独立计时），对齐 p1-s2a.md §3 验收的 SQL 分区逻辑。

**screenpipe 对齐**：intentionally different — screenpipe 全局 200ms 去抖（含 typing/scroll 独立延迟） vs MyRecall 全局 1000ms。P2 可按需拆分。

**实现入口**：`openrecall/client/events/base.py`。

```python
class TriggerDebouncer:
    """全触发去抖器，per-device 分区。"""
    def should_fire(self, device_name: str, now_ms: int) -> bool: ...
```

**device_name 约束（锁定）**：
- 事件在 Host 侧必须解析并携带 `device_name`（格式 `monitor_{id}`）。
- 去抖、trigger_coverage、背压计数均按 `device_name` 分区。
- `metadata` 入队时必须同时包含 `capture_trigger` 与 `device_name`。

**monitor 映射规则（锁定）**：
- `device_name` 必须来源于 OS 稳定标识（非 mss 列表下标）；禁止把截图数组位置直接当作设备身份。
- 热插拔/重排后，若 OS 稳定标识不变，则 `device_name` 不得变化；若稳定标识变化，必须产生日志事件并重建分区状态。
- 事件源与截图源必须通过同一 `device_name` 关联，禁止跨设备配对写入。

### D4：idle fallback — 超时触发 + 阻塞队列

**选择**：在事件驱动主线程中，使用 `queue.Queue.get(timeout=idle_capture_interval_ms/1000)` 阻塞等待触发事件。当超时抛出 `queue.Empty` 异常时，生成 `capture_trigger=idle` 的触发事件并重新入队。

**理由**：
- screenpipe 的 idle fallback 与事件循环集成（当前实现默认 `idle_capture_interval_ms=30000`），触发条件基于超时窗口。
- MyRecall idle 间隔 30s（对齐 screenpipe 当前默认值），作为无事件时的保底采集。
- 去除用户活跃判定可避免语义分叉，确保 Gate 样本可重复构造。
- 使用 `queue.Queue.get(timeout)` 的阻塞超时机制，比主动维护 `_last_trigger_time` 计时器更简洁，且天然与事件驱动架构集成。

**实现路径**（`recorder.py`）：

```python
def _wait_for_trigger(self, timeout_seconds: float, fallback_device_name: str) -> TriggerEvent:
    while True:
        try:
            return self._trigger_channel.get(timeout=timeout_seconds)
        except queue.Empty:
            # 超时后生成 idle 触发事件
            idle_event = TriggerEvent(
                capture_trigger=CaptureTrigger.IDLE,
                device_name=fallback_device_name,
                event_ts=utc_now_iso(),
            )
            # 重新入队（经过去抖门控）
            _ = self._emit_trigger(idle_event)
            continue
```

**语义边界（锁定）**：
- P1-S2a 的 idle 触发采用"**无触发超时优先**"语义：只要超过 `idle_capture_interval_ms` 且未发生其他触发，就应产生 `capture_trigger=idle`。
- S2a 不引入 `is_user_active()` 分支；idle fallback 不得依赖任何用户活跃判定。

**screenpipe 对齐**：aligned — 同为 idle timer fallback，默认间隔对齐（30s）。

### D5：权限状态机 — 四态 FSM + pyobjc 检测

**选择**：`granted/transient_failure/denied_or_revoked/recovering` 四态状态机，轮询周期 `permission_poll_interval_sec=10`。

**参数（锁定）**：
- `REQUIRED_CONSECUTIVE_FAILURES = 2`
- `REQUIRED_CONSECUTIVE_SUCCESSES = 3`
- `EMIT_COOLDOWN_SEC = 300`

**理由**：
- 借鉴 screenpipe 权限检测入口与健康态判定思想，并在 MyRecall 侧扩展为四态 FSM（`granted/transient_failure/denied_or_revoked/recovering`）。
- pyobjc 可调用 `AXIsProcessTrusted()` 检测 Accessibility 权限、`CGPreflightScreenCaptureAccess()` 检测 Screen Recording 权限。
- 连续 2 次失败才触发（防 TCC 数据库瞬态抖动误判），连续 3 次成功才恢复，5 分钟冷却期防弹窗风暴。

**权限检测范围（P1 vs P2）**：

| 权限 | 检测方法 | P1 状态 | 说明 |
|------|---------|---------|------|
| Accessibility | `AXIsProcessTrusted()` | ✅ 已实现 | 读取 UI 元素结构 |
| Screen Recording | `CGPreflightScreenCaptureAccess()` | ✅ 已实现 | 截图、屏幕内容捕获 |
| Input Monitoring | `CGEventTapCreate()` 返回值 | 🔜 P2 实现 | 监听键盘/鼠标事件（click 触发依赖） |

**P1 有意简化**：
- Input Monitoring 权限缺失时，click 触发静默失效（`CGEventTapCreate` 返回 `NULL`），不影响 idle/app_switch/manual 触发。
- 用户可通过 `/v1/health` 看到的 `capture_permission_status` 仅反映 Accessibility + Screen Recording 状态。
- P2 将引入完整的 Input Monitoring 检测与 `input_monitoring_denied` 原因码，并通过回调机制将 `MacOSEventTap` 的创建失败状态同步到权限状态机。

**阈值来源（锁定）**：
- `REQUIRED_CONSECUTIVE_FAILURES=2`、`REQUIRED_CONSECUTIVE_SUCCESSES=3`、`EMIT_COOLDOWN_SEC=300` 为 MyRecall 的工程化阈值选择，不宣称与 screenpipe 一一对应。

**screenpipe 对齐**：partially aligned — 复用相同权限检测入口与健康态约束方向；四态 FSM 与阈值策略为 MyRecall 扩展；Input Monitoring 检测推迟 P2。

**状态转移（锁定）**：
- `granted -> transient_failure`：单次检测失败。
- `transient_failure -> denied_or_revoked`：连续失败达到 `REQUIRED_CONSECUTIVE_FAILURES`。
- `denied_or_revoked -> recovering`：首次检测成功。
- `recovering -> granted`：连续成功达到 `REQUIRED_CONSECUTIVE_SUCCESSES`。

**健康字段（锁定）**：
- `/v1/health` 除 `capture_permission_status` 外，必须返回：
  - `capture_permission_reason`
  - `last_permission_check_ts`

**实现入口**：`openrecall/client/events/permissions.py`。

### D6：capture 管线改造 — ScreenRecorder → EventDrivenRecorder

**选择**：保留 `ScreenRecorder` 类但重构 `run_capture_loop()` 为事件驱动，不再使用固定 `time.sleep()`。

**理由**：
- 当前 `ScreenRecorder` 与 `SpoolQueue/SpoolUploader` 的 Producer-Consumer 架构已验证稳定，事件驱动仅改变"何时触发 capture"而非"如何入队"。
- `self._spool.enqueue(image, metadata)` 路径保持不变；变化点：
  1. 触发源从 `time.sleep` 换为 `trigger_queue.get(timeout=idle_interval)`
  2. 移除 MSSIM 相似度检测（事件驱动不需要像素级变化检测）
  3. metadata 增加 `capture_trigger` 与 `device_name` 字段
- spool 和上传逻辑（`spool.py`, `v3_uploader.py`）不做变更。

**manual 触发入口（锁定）**：
- 新增 Host 本地可调用入口 `emit_manual_trigger()`（不新增对外 HTTP 端点）。
- UI/脚本触发 manual 时，统一通过该入口写入 `trigger_event_queue`，并参与同一去抖与计数口径。
- 验收脚本需使用该入口构造 `manual >= 20` 样本，禁止人工点击作为唯一证据来源。

**screenpipe 对齐**：aligned — screenpipe Step 4 也是替换 `continuous_capture()` 循环为事件驱动循环。

### D7：`POST /v1/ingest` capture_trigger 校验 — 服务端枚举校验生效

**选择**：在 `api_v1.py` 的 ingest 端点对 `capture_trigger` 新增枚举校验，P1-S2a 起生效。

**理由**：
- `frames_store.py:124` 已从 metadata 中读取 `capture_trigger` 并写入 DB，但无校验。
- S2a 起 `capture_trigger` 在 API 语义层视为必需，枚举值限定为 `idle/app_switch/manual/click`。
- 非法值返回 `400 INVALID_PARAMS`。

**兼容性**：P1-S1 的 legacy capture（无 `capture_trigger` 字段）在 S2a 起将被拒绝。这是有意的——S2a 要求 Host 必须升级到事件驱动采集。

### D8：`/v1/health` 权限状态暴露

**选择**：`GET /v1/health` 响应增加 `capture_permission_status` 字段。

**规则（对齐 p1-s2a.md §3.11）**：
- 当权限状态为 `denied_or_revoked` 或 `recovering` 时，`status` 不得返回 `ok`。
- `capture_permission_status` 值与权限状态机状态一一对应。
- `capture_permission_reason` 与 `last_permission_check_ts` 必须与最近一次权限轮询结果一致。

**实现**：
- 需要 Client → Server 通信通道，但与 uploader 流量解耦。
- 设计选择：
  - 状态上报入口固定为 `POST /heartbeat`（内部端点，非新增对外 `/v1/*` 契约）；
  - 权限状态（`status/reason/check_ts`）以 5s 周期上报；
  - trigger queue 指标以 1Hz 周期上报；
  - 二者共享同一状态上报 payload，采样频率独立配置，不允许“或等价入口”多实现分叉。
- Server 缓存最近权限状态并在 `/v1/health` 返回，同时保存 trigger queue 原始样本用于 Gate 统计读取。
- 若状态快照超过 TTL（默认 60s）未更新，`/v1/health` 必须降级为 `degraded`，并标记 `capture_permission_reason=stale_permission_state`。

### D9：手动触发与验收可重复性

**选择**：将 `manual` 触发定义为一等触发类型，具备明确入口与可脚本化注入能力。

**理由**：
- `trigger_coverage` Gate 要求四类触发都命中且 `manual >= 20`，必须有稳定注入路径。
- 避免把人工交互作为唯一采样来源，降低 Gate 复现波动。

**约束**：
- `manual` 与 `app_switch/click/idle` 共用同一事件通道、去抖策略与指标口径。
- `manual` 触发生成的 capture 必须写入 `capture_trigger=manual`。
- 测试环境中可通过脚本触发，生产路径可绑定 UI 按钮/快捷键，但二者最终都调用同一入口。

### D10：`capture_latency_p95` 观测链路（锁定）

**选择**：将 `capture_latency_ms = (frames.ingested_at - event_ts) * 1000` 作为唯一计算口径，`event_ts` 由 Host 在触发产生时写入 metadata 并随 capture 上报。

**字段契约**：
- `event_ts`：Host 触发时刻（UTC ISO8601）。
- `ingested_at`：Edge 完成 DB commit 时刻（现有字段）。
- `capture_latency_ms`：由 Edge 在同一 capture 上按上述公式计算并进入样本分布。

**实现约束**：
- `event_ts` 必须早于或等于 capture 入库时间；缺失/非法 `event_ts` 的样本不得参与 `capture_latency_p95` 统计，并计入观测异常计数。
- Edge 必须暴露 `capture_latency_p95` 与样本数（窗口口径同 Gate 文档），用于 S2a 强制观测记录。

**理由**：
- 对齐 `docs/v3/gate_baseline.md` 与 `docs/v3/acceptance/phase1/p1-s2a.md` 的统一口径，避免使用截图时间替代触发时间导致指标失真。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| CGEventTap 在 Terminal 继承 TCC 身份 | Dev 模式下权限状态机误判，导致测试不稳定 | Dev 模式检测 Terminal 父进程，状态机日志标注 `dev_inherited_identity` |
| pyobjc CGEventTap 回调在 CFRunLoop 线程执行 | 回调内阻塞操作可能冻结系统事件 | 回调仅做 `queue.put_nowait()`，所有重操作在 consumer 线程 |
| 1 Hz 全局去抖可能导致快速 app_switch 丢信息 | 用户在 1s 内切换多个窗口只捕获一次 | P1 可接受——后续 P2 可拆分 per-type debounce 降低至 300ms |
| idle fallback 30s 空窗内的被动屏幕变化无法捕获 | 通知弹窗/自动播放等场景可能遗漏 | 对齐 screenpipe idle 语义；P2 可引入 visual_change 触发类型 |
| 权限状态同步依赖上报通道新鲜度 | 心跳中断时 Server 可能读取到陈旧权限状态 | 增加 TTL：状态快照超过 60s 未更新时 health 降级，并返回 `stale_permission_state` 原因 |
| P1-S1 无 `capture_trigger` 的历史帧无法通过 S2a 校验 | 仅影响 S2a 开发期间的过渡 | DDL 列 `DEFAULT NULL` 保持向后兼容，校验仅在 ingest API 层生效（不追溯历史数据）|
| 多显示器下 device_name 映射错误 | 去抖与触发覆盖统计失真，Gate 误判 | 统一 `monitor_{id}` 规则，事件源与截图元数据强制携带同一 `device_name` |
