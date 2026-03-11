## Implementation Tasks

### 1. Client 事件触发基础设施

- [x] 1.1 在 `openrecall/shared/config.py` 中补齐 P1-S2a Host 侧参数：`min_capture_interval_ms=1000`、`idle_capture_interval_ms=30000`、`permission_poll_interval_sec=10`、触发通道容量（默认 64），并保留 `OPENRECALL_CAPTURE_INTERVAL -> idle_capture_interval_ms` 的兼容映射；确保 ASCII Anchors `capture_trigger`、`idle`、`app_switch`、`manual`、`click` 在配置/注释/默认值中保持字面一致
- [x] 1.2 新增 `openrecall/client/events/base.py`（必要时补 `openrecall/client/events/__init__.py`），定义 `CaptureTrigger`/trigger event 数据结构、`TriggerDebouncer`、`device_name` 归一化与统一时间戳辅助，落实 per-monitor 去抖口径（SSOT: `docs/v3/spec.md`、`docs/v3/data-model.md`）
- [x] 1.3 在 `openrecall/client/events/base.py` 中封装有界 `trigger_event_queue`（容量 64）与折叠逻辑：首次 `put_nowait()` 失败时弹出最老事件再重试；成功折叠递增 `collapse_trigger_count`，最终无法入队才递增 `overflow_drop_count`
- [x] 1.4 新增 `openrecall/client/events/macos.py`，通过 pyobjc/Quartz CGEventTap 监听 click 与 app_switch，把事件转换成携带 `capture_trigger`、`event_ts`、`device_name` 的 trigger event；禁止把固定频率轮询作为主触发源
- [x] 1.5 新增 `openrecall/client/events/permissions.py`，实现 `granted`/`transient_failure`/`denied_or_revoked`/`recovering` 四态权限状态机，固定阈值 `REQUIRED_CONSECUTIVE_FAILURES=2`、`REQUIRED_CONSECUTIVE_SUCCESSES=3`、`EMIT_COOLDOWN_SEC=300`、`permission_poll_interval_sec=10`
- [x] 1.6 在事件源与截图源之间落实 `device_name` 强绑定：`device_name` 必须来源于稳定 OS monitor 标识（非截图数组下标），并覆盖 hot-plug/reorder 场景（稳定标识不变时 `device_name` 不变；变化时记录可审计日志并重建分区状态）；禁止跨设备事件-截图配对写入

### 2. Recorder 主循环改造与 manual/idle 触发接入

- [x] 2.1 重构 `openrecall/client/recorder.py` 的 `ScreenRecorder.run_capture_loop()`：保留 spool/uploader 生命周期，但把主触发机制从 `time.sleep(settings.capture_interval)` + MSSIM 轮询改为 `trigger_event_queue.get(timeout=idle_capture_interval_ms)` 事件驱动循环
- [x] 2.2 在 `openrecall/client/recorder.py` 中移除 P1-S2a 主路径上的 `is_user_active()` 依赖与“无变化跳过 capture”主判定，确保 `idle` fallback 只由超时条件触发，不依赖用户活跃判定
- [x] 2.3 在 `openrecall/client/recorder.py` 中实现 `emit_manual_trigger()`（或同等 Host 本地入口），让 manual 与 click/app_switch/idle 共用同一 `trigger_event_queue`、去抖规则与计数口径；验收脚本后续必须能通过该入口稳定构造 `manual >= 20` 样本
- [x] 2.4 更新截图元数据写入逻辑：`self._spool.enqueue()` 前必须为每次 capture 写入 `capture_trigger`、`device_name`、`event_ts`、`active_app`、`active_window`，并保证 `capture_trigger` 对新上报样本 100% 覆盖（`trigger_coverage = 100%` 的前提）
- [x] 2.5 在 `openrecall/client/recorder.py` 中保留现有 blank-frame warning，但将 Screen Recording/Input Monitoring 异常与 `permissions.py` 的状态机结果联动，避免只打日志而无状态上报

### 3. Host 状态上报与 Edge 观测镜像

- [x] 3.1 扩展 `openrecall/server/config_runtime.py`，为最近一次权限快照与 `trigger_channel` 原始采样建立线程安全存储：至少包含 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`、`queue_depth`、`queue_capacity`、`collapse_trigger_count`、`overflow_drop_count`，并保留最近 5 分钟窗口
- [x] 3.2 扩展 `openrecall/server/api.py` 的固定内部端点 `POST /heartbeat` 与 `openrecall/client/recorder.py` 的 `_send_heartbeat()`，让 Client 以 5s 周期上报权限快照、以 1Hz 周期上报 `trigger_channel` 指标，同时继续同步 `recording_enabled`/`upload_enabled` 等运行时开关；MUST NOT 引入“等价入口”并行实现
- [x] 3.3 在服务端状态镜像中实现 TTL 规则：权限快照超过 60s 未更新必须视为 `stale_permission_state`，供 `/v1/health` 降级；窗口外的 `trigger_channel` 采样不得进入 `queue_saturation_ratio` 分母
- [x] 3.4 在 `openrecall/server/api_v1.py` 与对应存储/辅助逻辑中补齐 `capture_latency_p95` 观测链路：使用 `event_ts` 与 `frames.ingested_at` 计算延迟分布（P50/P90/P95/P99），缺失/非法 `event_ts` 的样本不得进入分位统计，但必须计入观测异常计数
- [x] 3.5 补齐 `capture_latency` 统一读取口径（供验收脚本与证据包复用）：至少可读取 `capture_latency_p95`、`capture_latency_sample_count`、`capture_latency_anomaly_count`，并与同一统计窗口元信息（如 `window_id`/`edge_pid`/`broken_window`）一并导出

### 4. v1 ingest / queue / health 契约升级

- [x] 4.1 修改 `openrecall/server/api_v1.py` 的 `POST /v1/ingest`：自 P1-S2a 起强制校验 `capture_trigger` 为 `idle`/`app_switch`/`manual`/`click`；字段缺失、`null` 或非法值返回 `400 INVALID_PARAMS`，且 MUST NOT 创建或修改任何 `frames` 记录
- [x] 4.2 在 `openrecall/server/api_v1.py` 中补齐 `event_ts` 观测契约：当 `event_ts` 缺失、格式非法或晚于入库时刻（会导致负延迟）时 ingest 可继续成功，但样本必须被排除出 `capture_latency_p95` 统计，并留下可读的观测异常计数/日志锚点
- [x] 4.3 调整 `openrecall/server/database/frames_store.py` 的 metadata 读写与查询辅助，确保 `capture_trigger`、`event_ts`、`device_name` 相关字段在存储层保持可验证；同时补齐读取 `trigger_channel` 镜像与窗口统计所需的辅助方法
- [x] 4.4 升级 `GET /v1/ingest/queue/status`：在现有 `pending/processing/completed/failed/capacity` 之外，返回统一 `trigger_channel` 口径（`queue_depth`、`queue_capacity`、`collapse_trigger_count`、`overflow_drop_count`），并为 `queue_saturation_ratio` 验收提供 1Hz、5 分钟窗口统计基础
- [x] 4.5 升级 `GET /v1/health`：返回 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`；当权限为 `denied_or_revoked` 或 `recovering` 时 `status` 不得为 `ok`；当快照超时 >60s 时返回非 ok 且 `capture_permission_reason=stale_permission_state`

### 5. WebUI 与读路径对齐

- [x] 5.1 更新 `openrecall/server/templates/layout.html` 的 `#mr-health` 轮询逻辑，使 `data-state` 与新 `/v1/health` 权限语义一致：权限失效/恢复中必须显示 `degraded`，不能误报 `healthy`；保留 `healthy`/`unreachable`/`degraded` 三态锚点不变
- [x] 5.2 根据新的 health payload 细化文案判定：`服务健康/队列正常`、`等待首帧`、`Edge 不可达` 继续保留；新增权限异常/陈旧快照时的降级文案必须与 `capture_permission_status`/`capture_permission_reason` 对齐
- [x] 5.3 复查 `openrecall/server/app.py`、`openrecall/server/database/frames_store.py`、`openrecall/server/templates/timeline.html` 与 grid 读路径，确保事件驱动新帧仍通过 `/v1/frames/:frame_id` 可见，且页面能展示当前上传/入队状态而不退回 legacy `screenshots/*.png` 依赖
- [x] 5.4 补齐 Grid 状态同步收敛口径（`pending -> completed`）并提供可复核读口径，确保可支撑 `P95 <= 8s` 的 UI 状态同步验收判定；Timeline 仅承担新帧可见与时间定位验证

### 6. 测试、验收脚本与 Gate 证据

- [x] 6.1 新增 `tests/test_p1_s2a_trigger_coverage.py`：基于 `capture_trigger`/`device_name`/`event_ts` 样本验证 `trigger_coverage = 100%`（`idle`、`app_switch`、`manual`、`click` 四类均命中，且每类样本 >= 20）
- [x] 6.2 新增 `tests/test_p1_s2a_debounce.py`：校验同一 `device_name` 下 `app_switch`/`click` 连续入库间隔 < `min_capture_interval_ms` 的违规数为 0，并覆盖 manual/idle 共享去抖门控
- [x] 6.3 扩展现有服务端测试（优先复用 `tests/test_p1_s1_ingest.py`、`tests/test_p1_s1_health_parsing.py`、`tests/test_p1_s1_startup.py`，必要时新增 S2a 专项文件），覆盖 `POST /v1/ingest` 的 `capture_trigger`/`event_ts` 契约（含未来时间戳/负延迟样本排除）、`GET /v1/ingest/queue/status` 的 `trigger_channel` 返回，以及 `/v1/health` 的权限/TTL 语义
- [x] 6.4 新增 `tests/test_p1_s2a_device_binding.py`（或等价专项）：覆盖 `device_name` 稳定映射、hot-plug/reorder 后分区行为与事件源-截图源同设备绑定约束
- [x] 6.5 在 S2a 回归中显式补充 P1-S1 幂等契约测试：重复 `capture_id` + 合法 S2a metadata（含 `capture_trigger`）必须返回 `200 already_exists`，且 `frames` 行数与 queue 计数不增长
- [x] 6.6 补齐 `scripts/acceptance/p1_s2a_local.sh`：不再仅输出 `null` 指标，而是实际采集并汇总 `trigger_coverage`、`capture_latency_p95`、`capture_latency_sample_count`、`capture_latency_anomaly_count`、`collapse_trigger_count`、`queue_saturation_ratio`、`overflow_drop_count`、health snapshots 与 UI 证据索引；同时固化上下文快照与最终 Pass/Fail 摘要
- [x] 6.7 更新 `tests/test_p1_s2a_local_script.py`，校验 `scripts/acceptance/p1_s2a_local.sh` 的帮助输出、证据文件骨架、窗口元信息（`window_id`/`edge_pid`/`broken_window`）与新增指标字段/占位约束，保证脚本在未连真实服务时也能被静态验证；证据骨架 MUST 包含原始 1Hz trigger_channel 序列文件（例如 `p1-s2a-trigger-channel-raw.jsonl`）

## Acceptance Verification

- [x] 验收口径约束：P1-S2a 仅覆盖事件驱动采集、`capture_trigger`、去抖、背压、权限状态与观测链路；AX 文本采集、`content_hash` 去重与 `processing_mode=ax_ocr` 均不属于本阶段范围

### 7. 启动与运行时基线验证

- [x] 7.1 启动 Edge（`./run_server.sh --debug`）与 Host（`./run_client.sh --debug`），确认 Client 不再以固定频率轮询为主触发机制，且 Edge 启动后 `GET /v1/health`/`GET /v1/ingest/queue/status` 可稳定返回 200
- [x] 7.2 验证 Host 运行参数：`min_capture_interval_ms=1000`、`idle_capture_interval_ms=30000`、触发通道容量 = 64，且 `OPENRECALL_CAPTURE_INTERVAL` 仅作为 `idle_capture_interval_ms` 兼容映射，不再定义主触发机制
- [x] 7.3 先运行受影响的 P1-S1 基线回归（至少覆盖 ingest、queue、health、startup、Grid/Timeline 读路径），确认事件驱动改造未破坏既有 `/v1/ingest`、`/v1/ingest/queue/status`、`/v1/health` 与 UI 可见性契约

### 8. Trigger 覆盖与 debounce Gate

- [x] 8.1 通过 click、app_switch、manual 入口与 idle 超时构造四类样本，确认 `frames.capture_trigger` 仅出现 `idle`/`app_switch`/`manual`/`click`，且四类样本各 >= 20，`trigger_coverage = 100%`
- [x] 8.2 对同一 `device_name` 执行高频 click/app_switch 注入，确认连续成功入库间隔 < `min_capture_interval_ms`（1000ms）的违规数 = 0；manual 与 idle 也必须经过同一去抖门控，不得绕过

### 9. Ingest 契约与观测字段验证

- [x] 9.1 向 `POST /v1/ingest` 提交缺失 `capture_trigger`、`capture_trigger=null` 与非法枚举值样本，确认均返回 `400 INVALID_PARAMS`，且请求前后 `frames` 表总行数与 queue 计数完全不变
- [x] 9.2 提交合法 `capture_trigger` 但缺失/非法 `event_ts` 的样本，确认 ingest 仍可成功；随后验证该样本未进入 `capture_latency_p95` 分位统计，但观测异常计数已增加
- [x] 9.3 提交合法 `capture_trigger` 但 `event_ts` 晚于入库时刻（未来时间戳，导致负延迟）样本，确认 ingest 仍可成功；随后验证该样本未进入 `capture_latency_p95` 分位统计，且观测异常计数已增加

### 10. 背压与 trigger_channel 指标验证

- [x] 10.1 制造 5 分钟过载窗口（触发速率短时高于下游处理能力），确认 `GET /v1/ingest/queue/status` 可读取 `trigger_channel.queue_depth`、`trigger_channel.queue_capacity`、`trigger_channel.collapse_trigger_count`、`trigger_channel.overflow_drop_count`
- [x] 10.2 使用窗口内有效采样点计算 `queue_saturation_ratio = (queue_depth >= 0.9 * queue_capacity 的采样数 / 总采样数) * 100%`，确认结果 <= 10%，且同窗口满足 `collapse_trigger_count >= 1`、`overflow_drop_count = 0`
- [x] 10.3 导出过载窗口原始 1Hz 采样序列（至少包含 `ts`、`queue_depth`、`queue_capacity`、`collapse_trigger_count`、`overflow_drop_count`）与计算脚本/SQL，保证 `queue_saturation_ratio` 可离线复算

### 10A. Capture 丢包率 Gate 验证

- [x] 10A.1 在 `300 events/min`、持续 5 分钟压测窗口下计算 `loss_rate = (应到达 capture 数 - 成功 commit capture 数) / 应到达 capture 数`，确认 `loss_rate < 0.3%`
- [x] 10A.2 将 `loss_rate` 的分子/分母、窗口标识与计算依据写入证据包，保证 Gate 结论可追溯

### 11. 权限状态与 Health/UI 一致性验证

- [x] 11.1 制造权限连续失败直到进入 `denied_or_revoked`，确认 `/v1/health` 返回 `capture_permission_status=denied_or_revoked`，`status != ok`，`#mr-health` 的 `data-state="degraded"`
- [x] 11.2 恢复权限并观察 `recovering -> granted`，确认在达到连续成功阈值前 `/v1/health` 仍不得返回 `status=ok`；阈值达标后才允许 UI 自动恢复到 `healthy`
- [x] 11.3 停止 Host 状态上报超过 60 秒，确认 `/v1/health` 返回 `capture_permission_reason=stale_permission_state` 且维持非 ok；恢复上报后状态可自动收敛，不需要刷新页面

### 12. 本机 Gate 证据包验证

- [x] 12.1 运行 `pytest tests/test_p1_s2a_trigger_coverage.py tests/test_p1_s2a_debounce.py -q`，并补跑受影响的 ingest/health/startup/acceptance 脚本测试，确认阶段交付测试文件真实存在且通过
- [x] 12.2 运行 `scripts/acceptance/p1_s2a_local.sh`，确认生成 `p1-s2a-local-gate.log`、`p1-s2a-metrics.json`、`p1-s2a-health-snapshots.json`、`p1-s2a-ui-proof.md`、`p1-s2a-trigger-channel-raw.jsonl`，且指标文件已填入 `capture_latency_p95`、`capture_latency_sample_count`、`capture_latency_anomaly_count`、`trigger_coverage`、`collapse_trigger_count`、`queue_saturation_ratio`、`overflow_drop_count`、`loss_rate` 及窗口元信息（`window_id`/`edge_pid`/`broken_window`）
- [x] 12.3 在 `p1-s2a-ui-proof.md` 中补齐 Grid 状态可见、Timeline 新帧定位与健康锚点截图索引，保证证据包可直接支撑 `docs/v3/acceptance/phase1/p1-s2a.md` 的 Exit Gate 判定
