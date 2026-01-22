## 安全原则（全程遵循）
- 不执行任何破坏性操作（尤其是 `rm -rf`）除非你明确要求。
- 不在终端输出/日志中回显任何 API Key；env 文件使用最小权限（root 可写、运行用户组可读）。
- 每一步都先做“只读检查/验证”，再做“最小必要变更”，最后做“健康检查”。

## 前置只读检查（不改动系统）
1) 确认 /data 是否 `noexec`，避免 venv 放错目录导致无法启动。
2) 确认将用于运行服务的普通用户（文档中的 `<user>`），并校验该用户对目标目录具备读写权限。
3) 确认你当前 clone 的源码目录位置（用于 rsync 迁移到 /data/apps/openrecall）。

## 逐步实施（从步骤 3 开始）
1) 创建目录与权限（步骤 3）
- 只创建文档建议的目录（/data/openrecall/{db,screenshots,cache}、/data/apps/openrecall、/data/venvs/openrecall、/data/.cache/uv/openrecall）。
- 创建后立刻用 `ls -ld`/权限检查验证 owner/group/mode 是否符合预期。

2) 放置源码到 /data/apps/openrecall（步骤 4）
- 你已 clone：采用“方式 A rsync 迁移”，先同步工作树，再同步 .git。
- 迁移后用 `git status`（只读）和目录校验确认代码完整。

3) 安装 uv（步骤 5）
- 先 `uv --version` 检查是否已装。
- 若需安装，按官方脚本安装到运行用户的 home，并验证 PATH（不改系统全局）。

4) 创建 venv 并安装依赖（步骤 6）
- 显式设置 `UV_CACHE_DIR=/data/.cache/uv/openrecall`，避免缓存散落。
- 创建 venv 后只验证 python 路径与版本，再进行依赖安装。
- 安装完成后用最小导入/启动检查验证依赖无缺失。

5) 配置 env 文件（步骤 7）
- 创建 `/etc/openrecall/openrecall.env`，权限：root 拥有、运行用户组可读（0640）。
- 填写端口、数据目录、缓存目录、provider 与 API base/model；API key 只写入 env 文件，不出现在命令行历史。

6) 本机直跑验证（步骤 8，强烈建议）
- 使用 venv 的 python 启动 `python -m openrecall.server`。
- 用 `curl http://127.0.0.1:<port>/api/health` 验证。
- 检查 /data/openrecall/db、screenshots、cache 是否按预期生成文件（落盘验证）。

7) systemd 托管（步骤 9）
- 创建 `openrecall-server.service`，严格使用 `User=<user>` 和 `EnvironmentFile=/etc/openrecall/openrecall.env`。
- `systemctl status` 与 `journalctl` 验证服务稳定重启、无循环崩溃。

8) 可选：Nginx 反代（步骤 10，若需要对外访问）
- 明确提示：`/api/*` 默认无鉴权；若公网访问，必须先做 VPN / IP allowlist / BasicAuth 之一。
- 每次改 Nginx 配置后必做 `nginx -t` 再 reload。

9) 可选：数据一键清空（步骤 11）
- 仅作为“应急手册”记录，不会自动执行。
- 真要清空时：先停服务 → 确认目标路径是 `/data/openrecall` → 再清空 → 重建目录/权限 → 启动并健康检查。

## 完成判定（每一步都有可见验证点）
- `curl /api/health` 返回成功。
- systemd 服务处于 active，日志无明显报错。
- 所有可丢弃数据仅落在 `/data/openrecall`，避免误删源码/venv/env。

你确认这个“谨慎模式”流程后，我将从步骤 3 开始逐条执行，并在每一步都把验证结果对齐到文档目标。