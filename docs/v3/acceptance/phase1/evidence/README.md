# Phase 1 验收证据归档

本目录存放 P1 各子阶段的验收证据文件。

## 证据文件命名规范

- `p1-{stage}-local-gate.log`：脚本/手测总日志
- `p1-{stage}-permission-transitions.jsonl`：权限状态变化时间线（S2a+）
- `p1-{stage}-health-snapshots.json`：各场景 `/v1/health` 快照
- `p1-{stage}-ui-proof.md`：引导/降级/恢复截图索引
- `p1-{stage}-context.json`：执行环境上下文（Terminal mode、git rev、env snapshot）

## 已完成阶段

### P1-S2a+（权限稳定性收口）

- **状态**: ✅ Pass
- **日期**: 2026-03-13
- **Git Rev**: `157eef2`
- **执行环境**: Terminal mode

**证据文件**:

| 文件 | 说明 |
|------|------|
| `p1-s2a-plus-local-gate.log` | 执行脚本总日志 |
| `p1-s2a-plus-permission-transitions.jsonl` | 权限状态机变化时间线 |
| `p1-s2a-plus-health-snapshots.json` | `/v1/health` 响应快照 |
| `p1-s2a-plus-ui-proof.md` | UI 降级/恢复证据索引 |
| `p1-s2a-plus-context.json` | 执行环境上下文 |
| `p1-s2a-plus-ui-proof.md` | S2a UI 验收证据（历史） |

**自动化测试**: `tests/test_p1_s2a_plus_permission_fsm.py` (12/12 passed)

**覆盖场景**:
- ✅ `startup_not_determined` → `transient_failure` → degraded health
- ✅ `startup_denied` → `denied_or_revoked` (2 consecutive failures)
- ✅ `revoked_mid_run` → capture stops, health degrades
- ✅ `restored_after_denied` → `recovering` (3 consecutive successes) → `granted`
- ✅ `stale_permission_state` (>60s) → degraded health
- ✅ Health contract includes permission fields

## 生成方式

```bash
# 执行验收脚本
./scripts/acceptance/p1_s2a_plus_local.sh

# 证据将生成到本目录
```

## 归档规则

1. 每个子阶段必须通过对应脚本生成最小证据集合
2. 证据文件必须包含 git rev、时间戳、执行环境
3. Terminal mode 执行的证据需显式标注（P1 已知限制）
4. 证据文件按 `p1-{stage}-{timestamp}` 格式命名
