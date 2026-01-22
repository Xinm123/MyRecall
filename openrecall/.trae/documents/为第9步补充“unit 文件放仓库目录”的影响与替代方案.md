## 目标
- 按你当前“仍用系统级服务 + env 放仓库根目录”的测试方式，把第 9 步落地成可照抄执行的步骤。

## 将要执行的改动（只改仓库里的文档，不改系统）
1) 更新 [DEPLOYMENT_DEBIAN_SERVER_DATA_WIPE_UV.md](file:///data/apps/MyRecall/openrecall/docs/DEPLOYMENT_DEBIAN_SERVER_DATA_WIPE_UV.md) 的第 9 步说明：
   - 明确：systemd 系统级 unit **必须安装到** `/etc/systemd/system/openrecall-server.service` 才会生效；仓库目录只能作为编辑草稿。
   - 给出推荐安装方式：`sudo install -m 0644 -o root -g root ...`（避免手误权限/属主）。
   - 明确不推荐：`/etc/systemd/system/...` 指向仓库目录的 symlink/link（解释安全与可维护性影响）。

2) 在第 8/9 步之间补一段“常见坑”：
   - 忘记 `source ./openrecall.env` 时，会回退到默认的 `~/.myrecall_data`，导致你看到 `HF_HOME` 变成家目录缓存；
   - systemd 下以 `EnvironmentFile=/data/apps/MyRecall/openrecall/openrecall.env` 为准，不会出现这个漂移。

## 你在机器上执行第 9 步的命令序列（我会写进文档）
- 在仓库里编辑一个临时 unit 文件（例如 `/data/apps/MyRecall/openrecall/openrecall-server.service`）。
- 安装到系统目录：复制/安装到 `/etc/systemd/system/openrecall-server.service`。
- `sudo systemctl daemon-reload`、`sudo systemctl enable --now openrecall-server`、`sudo systemctl status ...`。

## 验证点
- `systemctl status openrecall-server` 为 active。
- `curl -fsS http://127.0.0.1:18083/api/health` 返回 ok。

确认后我会按以上步骤更新文档内容，并把第 9 步写成你现在的测试路径（WorkingDirectory 与 EnvironmentFile 都指向 `/data/apps/MyRecall/openrecall`）。