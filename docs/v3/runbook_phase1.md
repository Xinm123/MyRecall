# Phase 1 Runbook (Host + Edge)

- Status: Draft
- Scope: P1-S1 ~ P1-S7
- Topology: Two processes on one machine; single inbound port on Edge

This document is the single source of truth (SSOT) for how to start/stop and validate the
Phase 1 local dev environment.

## 1. Goals

- Keep Phase 1 operationally simple: two terminals, two processes.
- Validate Host->Edge boundaries (HTTP ingest + retries + idempotency) with process isolation.
- Keep inbound network surface minimal in Phase 1: Edge is the only HTTP server.

## 2. Component Mapping

- Edge (server process): `python -m openrecall.server`
- Host (client process): `python -m openrecall.client`

Wrappers (recommended):
- Edge: `MyRecall/run_server.sh`
- Host: `MyRecall/run_client.sh`

## 3. Configuration Files

- Edge env (default): `MyRecall/myrecall_server.env`
  - Edge port: `OPENRECALL_PORT` (currently `8083`)
  - Edge data dir: `OPENRECALL_SERVER_DATA_DIR` (default `~/MRS`)
- Host env (default): `MyRecall/myrecall_client.env`
  - Host data dir: `OPENRECALL_CLIENT_DATA_DIR` (default `~/MRC`)
  - Host API base: `OPENRECALL_API_URL` (must point to Edge)

Security note:
- Do not paste API keys or secret values into acceptance records or issue comments.

## 4. Start (Recommended)

Phase 1 uses two terminals.

### Terminal 1: Start Edge

```bash
./run_server.sh --debug
```

Notes:
- Loads env from `myrecall_server.env` by default.
- `--debug` exports `OPENRECALL_DEBUG=true`.
- Override env file:
  - `./run_server.sh --debug --env=/abs/path/to/myrecall_server.env`

### Terminal 2: Start Host

Start Edge first, then Host.

```bash
./run_client.sh --debug
```

Notes:
- Loads env from `myrecall_client.env` by default.
- Override env file:
  - `./run_client.sh --debug --env=/abs/path/to/myrecall_client.env`

## 5. Logs (Evidence-Friendly)

Acceptance text expects Host/Edge logs to be independently inspectable. If file-based logging
is not implemented yet, capture stdout/stderr via `tee`.

### Edge logs

```bash
mkdir -p "${OPENRECALL_SERVER_DATA_DIR:-$HOME/MRS}/logs"
./run_server.sh --debug 2>&1 | tee "${OPENRECALL_SERVER_DATA_DIR:-$HOME/MRS}/logs/edge.$(date +%F_%H%M%S).log"
```

### Host logs

```bash
mkdir -p "${OPENRECALL_CLIENT_DATA_DIR:-$HOME/MRC}/logs"
./run_client.sh --debug 2>&1 | tee "${OPENRECALL_CLIENT_DATA_DIR:-$HOME/MRC}/logs/host.$(date +%F_%H%M%S).log"
```

## 6. Sanity Checks (Before Any P1 Substage)

Assume Edge port is `$OPENRECALL_PORT` (default `8083`).

1) Edge health:

```bash
curl -sS "http://localhost:${OPENRECALL_PORT:-8083}/v1/health"
```

2) UI routes reachable (P1-S1 requires `/`, `/search`, `/timeline`):

- `http://localhost:${OPENRECALL_PORT:-8083}/`
- `http://localhost:${OPENRECALL_PORT:-8083}/search`
- `http://localhost:${OPENRECALL_PORT:-8083}/timeline`

3) Legacy namespace behavior (transitional):

P1-S1 ~ P1-S3 expects the following legacy endpoints to return transitional redirects to their `/v1/*` replacements plus `[DEPRECATED]` logs (P1 Gate scope):

- `POST /api/upload`  -> `308` -> `POST /v1/ingest`
- `GET  /api/search`  -> `GET  /v1/search`
- `GET  /api/queue/status` -> `GET  /v1/ingest/queue/status`
- `GET  /api/health`  -> `GET  /v1/health`

Note: other `/api/*` routes (if any) are out of P1 Gate scope; do not implement a catch-all `/api/*` redirect.

```bash
curl -i "http://localhost:${OPENRECALL_PORT:-8083}/api/health"
```

Expected:
- HTTP status `301`（GET legacy）或 `308`（`POST /api/upload`）
- `Location: /v1/health`

4) OCR runtime policy (P1-S3+):

- Verify Edge OCR runtime is RapidOCR (`ocr_provider=rapidocr` or equivalent runtime evidence in Edge logs).
- P1 does not require or validate multi-engine OCR switching.

## 6.1 Fault Injection: Host -> Edge disconnect (P1-S1)

P1-S1 acceptance requires a full disconnect window (e.g. 3 minutes) while Host continues to
produce captures into the local spool/buffer.

Recommended (simple, reproducible): stop Edge process temporarily

1) Keep Host running.
2) Stop Edge (Ctrl+C) and keep it down for 3 minutes.
3) During this window, continue generating captures on Host (they must remain on disk in the spool).
4) Start Edge again.
5) Verify Host uploader automatically resumes and drains the spool until all buffered captures are accepted.

Note:
- Queue/status 计数口径以 DB 实时状态为准（SSOT：[spec.md](./spec.md) §4.7），Edge 重启不应改变计数语义。
- 若你在断连窗口中同时切换了 Edge data dir（导致 SQLite DB 变化/清空），则计数会随 DB 一并变化；此时应以“同一 DB 实例”的证据完成验收。
- S2b 当前主线不使用 `content_hash` 作为 active dedup 语义；Host/Edge 重启会影响运行态窗口连续性，但不改变 `capture_id` 幂等与 DB 事实计数语义。

## 7. Restart Policy Across P1-S1 ~ P1-S7

Phase 1 has two supported execution modes.

### 7.1 Default mode (recommended): reuse across substages

Default: do NOT restart between substages.

Intent:
- Keep a single continuous run across P1-S1 ~ P1-S7.
- Validate long-running behavior (retries, observability, UI continuity) without port churn.

Mandatory restart triggers (stop both, then start fresh):
- You retry a substage (re-run the same substage acceptance after a failure).
- You change runtime inputs/config (env files, datasets, feature flags).
- Either process crashes or becomes unhealthy.

### 7.2 Strict isolation mode (optional; NOT a Gate)

This mode is for debugging state contamination or producing a reproducibility baseline.
It MUST NOT be used as a Gate requirement for Phase 1.

Policy:
- After completing each substage acceptance record (P1-S1, then P1-S2a/P1-S2b, ...), stop both processes and restart a fresh Host+Edge pair before moving to the next substage.

Procedure (per substage boundary):
1) Stop Host (Ctrl+C), then stop Edge (Ctrl+C).
2) Start Edge:

```bash
./run_server.sh --debug
```

3) Start Host:

```bash
./run_client.sh --debug
```

4) Re-run sanity checks (Section 6) before starting the next substage.

Caveats:
- Queue/status 计数口径以 DB 实时状态为准（SSOT：[spec.md](./spec.md) §4.7）。
- Strict isolation mode 下如果每个子阶段使用新的 data dir（新的 SQLite DB），则计数会从空 DB 开始；如果复用同一 data dir，则计数会在子阶段间延续。
- S2b capture-completion Gate 采样若跨越 Host 或 Edge 重启，需标记 `broken_window=true`，并重开新的连续窗口重测。

Restart Edge when:
- Edge API contract changes
- DB/schema/migrations change
- UI behavior changes
- Pi Manager/Sidecar integration changes (P1-S5+)

Restart Host when:
- Capture trigger or capture-completion behavior changes (P1-S2a/P1-S2b)
- Upload/retry/buffering behavior changes

## 8. Stop

- Stop Host: Ctrl+C in Host terminal
- Stop Edge: Ctrl+C in Edge terminal

## 9. Known Doc Constraint

- Phase 1 topology uses "two processes + single Edge port".
- Do not require Host to expose an inbound port in Phase 1.

## 10. Permission Fault Drill (P1-S2a prerequisite, P1-S2b inherited verification)

目标：验证权限拒绝/撤销/恢复场景在运行态可观测、可恢复、可判定。

阶段要求：本 drill 由 S2a 建立权限前提；若 S2a 验收未执行本 drill，不得长期以 `N/A` 悬置；最迟必须在 S2b Exit 前完成并补记证据。

归属说明：本 drill 的证据首先用于关闭 S2a 的 permission observability 前提；S2b 仅继承并验证 permission 状态不会阻断 capture completion 证据链；S3 不重复承担 permission capability 验收，只继承其前提状态。

### 10.1 演练参数（固定）

- `REQUIRED_CONSECUTIVE_FAILURES = 2`
- `REQUIRED_CONSECUTIVE_SUCCESSES = 3`
- `EMIT_COOLDOWN_SEC = 300`
- `permission_poll_interval_sec = 10`

### 10.2 场景步骤

1. `startup_denied`：在系统设置中关闭 Accessibility/Input Monitoring 后启动 Host+Edge。
2. `revoked_mid_run`：运行中撤销权限，保持进程不重启，观察状态变化。
3. `restored`：重新授权，确认状态从 `recovering` 回到 `granted`。

### 10.3 判定与证据

- 判定规则：权限失效期间 `/v1/health.status` 不得为 `ok`。
- 必留证据：
  - Host/Edge 日志文件（含权限状态变化时间点）
  - `/v1/health` 快照（异常中 + 恢复后）
  - UI 状态截图（引导/降级/恢复）

### 10.4 Dev vs Production 说明

- Dev（Terminal）模式允许用于调试，但可能受 Terminal TCC 身份继承影响，不能作为长期稳定性证据。
- 生产稳定性以固定签名身份运行模型为目标（P2 收敛）。
