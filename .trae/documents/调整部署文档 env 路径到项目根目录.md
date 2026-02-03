## 现状对齐

* 你当前仓库根目录是 `/data/apps/MyRecall/openrecall`（含 `setup.py` 与 `openrecall/` 包），所以文档里所有 `cd /data/apps/openrecall`、`WorkingDirectory=/data/apps/openrecall`、以及“放置源码到 /data/apps/openrecall”的段落都需要改为 `/data/apps/MyRecall/openrecall`。

* 你已完成 0–5 步，因此文档应提供“从第 6 步继续”的快捷入口，避免重复执行。

## 文档修改点（只改这一份文件）

* 更新“推荐目录布局”中的源码路径：`/data/apps/openrecall` → `/data/apps/MyRecall/openrecall`。

* 更新“创建目录与权限”中的源码目录创建命令：`/data/apps/openrecall` → `/data/apps/MyRecall/openrecall`。

* 重写第 4 步为“源码已在目标目录，无需迁移/重新 clone”，并补一段可选的 ownership/权限检查命令（仍使用 `<user>` 占位，示例写 `cix`）。

* 在第 5 步后插入一个小节“已完成 0–5：从这里继续（6–11）”，把后续关键命令按你的路径重新给一遍，降低照抄出错概率。

* 更新后续所有引用源码目录的地方：

  * 第 6 步 `cd ...`

  * 第 8 步 `cd ...`

  * 第 9 步 systemd `WorkingDirectory=...`

## 一致性与可读性检查

* 全文搜索确认不再出现旧路径 `/data/apps/openrecall`。

* 确认入口命令仍为 `python -m openrecall.server`，且与仓库结构匹配。

## 交付物

* 直接提交对 [DEPLOYMENT\_DEBIAN\_SERVER\_DATA\_WIPE\_UV.md](file:///data/apps/MyRecall/openrecall/docs/DEPLOYMENT_DEBIAN_SERVER_DATA_WIPE_UV.md) 的一次性改稿（仅文档变更，不改代码）。

