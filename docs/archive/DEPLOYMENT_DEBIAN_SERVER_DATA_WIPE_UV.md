# Debian 部署指南：/data 落盘 + uv + 数据一键清空（OpenRecall Server）

本文面向 Debian 服务器，仅部署 OpenRecall 的 Server 端（Web UI + `/api` + 后台 worker）。重点目标：

- 所有“可丢弃数据”集中在 `/data/openrecall`，需要清空时可直接 `rm -rf /data/openrecall`
- 源码、venv、uv 缓存、密钥配置不放在 `/data/openrecall`，避免误删
- 推理方案以“API 方案 + CPU”为默认（OCR 本地，Vision/Embedding 走 OpenAI 兼容 API）

入口命令：`python -m openrecall.server`

## 0) 先确认 /data 是否允许执行

如果你计划把 venv 放到 `/data`，先确认 `/data` 的挂载参数没有 `noexec`：

```bash
findmnt -no TARGET,OPTIONS /data
```

输出包含 `noexec` 表示不能从 `/data` 执行二进制/脚本，需要把 venv 放到 `/opt` 或家目录；不包含 `noexec` 则可以把 venv 放到 `/data`。

## 1) 推荐目录布局（支持一键清空数据）

- 可随时删除的数据（只放这里）：`/data/openrecall`
  - SQLite：`/data/openrecall/db/recall.db`
  - 截图 PNG：`/data/openrecall/screenshots/*.png`
  - 模型/推理缓存：`/data/openrecall/cache`（HF/Transformers/Doctr/Torch/SentenceTransformers）
- 源码（不要放进 `/data/openrecall`）：`/data/apps/MyRecall/openrecall`
- venv（不要放进 `/data/openrecall`）：`/data/venvs/openrecall`
- uv 缓存（不要放进 `/data/openrecall`）：`/data/.cache/uv/openrecall`
- env 文件（不要放进 `/data/openrecall`）：测试可先放源码目录 `./openrecall.env`，生产再放 `/etc/openrecall/openrecall.env`

## 2) OS 依赖

建议最小集合：

```bash
sudo apt update
sudo apt install -y ca-certificates curl git sqlite3
```

如需要对外提供 HTTPS 访问，再安装：

```bash
sudo apt install -y nginx
```

如遇 Torch/图像依赖报缺库，再补：

```bash
sudo apt install -y libglib2.0-0 libgl1
```

### apt 报 “Read-only file system” 怎么办

如果你在安装/升级 OS 包时看到类似报错：

- `unable to create '/usr/...': Read-only file system`
- 或 `errors=remount-ro` 相关提示

通常表示根分区因为检测到 I/O 或文件系统错误，被内核自动 remount 成只读（`ro`），导致 dpkg 无法写入 `/usr`。

排查与处理（按顺序）：

1) 确认根分区是否只读

```bash
findmnt -no TARGET,OPTIONS /
```

如果输出里包含 `ro`，就是只读。

2) 看内核日志是否有 ext4/nvme 错误

```bash
dmesg -T | tail -n 200
```

3) 临时尝试 remount 回可写（只用于救急；若底层有错可能很快又变回只读）

```bash
sudo mount -o remount,rw /
```

4) 建议做一次 fsck 修复（需要在根分区未挂载时执行）

- 最简单方式：安排下次重启时强制检查

```bash
sudo touch /forcefsck
sudo reboot
```

如果当前 `/` 已经是只读且无法 remount 为 rw，可能无法创建 `/forcefsck`。这时可在重启时通过 GRUB 临时追加内核参数来强制 fsck：

- 在 GRUB 菜单选中当前启动项，按 `e` 编辑
- 在以 `linux` 开头的那一行末尾追加：
  - `fsck.mode=force fsck.repair=yes`
- 按 `Ctrl+X` 或 `F10` 启动

重启后若系统进入 fsck 流程，待其完成。

5) 恢复包管理状态（fsck/重启后）

```bash
sudo dpkg --configure -a
sudo apt -f install
```

## 3) 创建目录与权限（使用现有普通用户跑服务）

把下面的 `<user>` 替换为你运行服务的普通用户（例如 `cix`）：

```bash
sudo install -d -m 0750 -o <user> -g <user> /data/openrecall
sudo install -d -m 0750 -o <user> -g <user> /data/openrecall/{db,screenshots,cache}

sudo install -d -m 0750 -o <user> -g <user> /data/apps/MyRecall/openrecall
sudo install -d -m 0750 -o <user> -g <user> /data/venvs/openrecall
sudo install -d -m 0750 -o <user> -g <user> /data/.cache/uv/openrecall
```

## 4) 确认源码在 /data/apps/MyRecall/openrecall（已 clone 可跳过）

如果你已经把仓库 clone 到目标目录（例如你当前就是在 `/data/apps/MyRecall/openrecall`），这一步不需要迁移/重新 clone。

建议只做一次权限确认（避免后续 uv/venv 安装时写入失败）：

```bash
sudo chown -R <user>:<user> /data/apps/MyRecall/openrecall
```

## 5) 安装 uv（如已安装可跳过）

```bash
uv --version
```

若提示找不到命令，可按官方方式安装（会写入你用户的 home）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装后重新开一个 shell，或确保 `$HOME/.local/bin` 在 PATH 中。

### 已完成 0–5：从这里继续（6–11）

你当前源码目录固定为：`/data/apps/MyRecall/openrecall`。后续所有 `cd ...`、systemd 的 `WorkingDirectory=...` 都以此为准。

- 继续做第 6 步：用 uv 创建 venv 并安装依赖（editable）
- 然后做第 7 步：配置 env 文件
- 再做第 8 步：先本机直跑验证
- 最后做第 9 步：systemd 托管（完成后可选做第 10 步 Nginx 反代）

## 6) 用 uv 创建 venv 并安装依赖（editable）

将 uv 缓存重定向到 `/data`：

```bash
export UV_CACHE_DIR=/data/.cache/uv/openrecall
```

创建 venv（路径可按需调整）：

```bash
uv venv /data/venvs/openrecall
```

安装依赖（不要求激活 venv）：

```bash
cd /data/apps/MyRecall/openrecall
uv pip install --python /data/venvs/openrecall/bin/python -e .
```

## 7) 配置 env 文件（不要把密钥写进命令行历史）

测试环境：直接放到源码目录（注意不要提交到 git）：

```bash
cd /data/apps/MyRecall/openrecall
touch openrecall.env
chmod 0600 openrecall.env
```

编辑 `/data/apps/MyRecall/openrecall/openrecall.env`（示例，按你的 API 方案 + CPU + 端口 18083）：

```bash
OPENRECALL_DEBUG=false
OPENRECALL_HOST=127.0.0.1
OPENRECALL_PORT=18083
OPENRECALL_API_URL=http://127.0.0.1:18083/api

OPENRECALL_DATA_DIR=/data/openrecall
OPENRECALL_CACHE_DIR=/data/openrecall/cache

OPENRECALL_DEVICE=cpu
OPENRECALL_PRELOAD_MODELS=false

OPENRECALL_OCR_PROVIDER=local

OPENRECALL_VISION_PROVIDER=openai
OPENRECALL_VISION_API_BASE=https://api-inference.modelscope.cn/v1
OPENRECALL_VISION_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
OPENRECALL_VISION_API_KEY=<YOUR_NEW_KEY>

OPENRECALL_EMBEDDING_PROVIDER=openai
OPENRECALL_EMBEDDING_API_BASE=https://api-inference.modelscope.cn/v1
OPENRECALL_EMBEDDING_MODEL_NAME=Qwen/Qwen3-Embedding-0.6B
OPENRECALL_EMBEDDING_API_KEY=<YOUR_NEW_KEY>
```

如需让局域网其他机器访问（例如 Client 跑在你的电脑上，Server 跑在 Debian 上），将 `OPENRECALL_HOST` 改为 `0.0.0.0`，并把 Client 的 `OPENRECALL_API_URL` 指向 Debian 的内网 IP（例如 `http://10.77.45.162:18083/api`）。注意：`/api/*` 默认无鉴权，仅建议在可信局域网使用，或配合防火墙/Nginx 做访问控制。

生产环境（推荐）：放到 `/etc/openrecall/openrecall.env` 并收紧权限，便于 systemd 引用且避免误提交：

```bash
sudo install -d -m 0750 /etc/openrecall
sudo touch /etc/openrecall/openrecall.env
sudo chown root:<user> /etc/openrecall/openrecall.env
sudo chmod 0640 /etc/openrecall/openrecall.env
```

安全建议：

- 如 key 曾出现在聊天/日志/历史命令里，建议立刻撤销并重新生成新 key
- 不要把 key 写入仓库、不要直接 `export ...API_KEY=...`（容易进 shell history）

## 8) 先本机直跑验证（建议先做再上 systemd）

```bash
cd /data/apps/MyRecall/openrecall
set -a
source ./openrecall.env
set +a
/data/venvs/openrecall/bin/python -m openrecall.server
```

在另一个终端验证：

```bash
curl -fsS http://127.0.0.1:18083/api/health
```

检查落盘：

```bash
ls -lah /data/openrecall/db
ls -lah /data/openrecall/screenshots | head
ls -lah /data/openrecall/cache | head
```

常见坑：

- 如果你运行任意 Python/脚本时忘了先 `source ./openrecall.env`，`OPENRECALL_DATA_DIR` 会回退到默认 `~/.myrecall_data`，你会看到 `HF_HOME` 等缓存路径也跟着跑到家目录下。这不是服务“坏了”，只是当前进程没加载 env。
- systemd 托管时以 `EnvironmentFile=...` 为准，不会出现上述“忘记 source 导致回退默认值”的问题。

## 9) systemd 托管（用现有普通用户）

说明：

- 你可以在仓库目录（`/data/apps/MyRecall/openrecall`）先写/改 unit 当草稿，但 **系统级 systemd 最终必须安装到** `/etc/systemd/system/openrecall-server.service` 才会生效。
- 不建议在 `/etc/systemd/system/` 下用 symlink/link 指向仓库目录（仓库目录通常用户可写，存在安全与维护风险）。

在仓库目录创建一个 unit 草稿文件：

```bash
cd /data/apps/MyRecall/openrecall
cat > openrecall-server.service <<'EOF'
[Unit]
Description=OpenRecall Server
After=network.target

[Service]
Type=simple
User=<user>
Group=<user>
WorkingDirectory=/data/apps/MyRecall/openrecall
EnvironmentFile=/data/apps/MyRecall/openrecall/openrecall.env
Environment=UV_CACHE_DIR=/data/.cache/uv/openrecall
ExecStart=/data/venvs/openrecall/bin/python -m openrecall.server
Restart=always
RestartSec=5
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
EOF
```

安装到系统目录（推荐用 install 固定属主与权限）：

```bash
sudo install -m 0644 -o root -g root /data/apps/MyRecall/openrecall/openrecall-server.service /etc/systemd/system/openrecall-server.service
```

如果你不想在仓库里留 unit 草稿文件，也可以直接用编辑器创建 `/etc/systemd/system/openrecall-server.service`，内容如下：


```ini
[Unit]
Description=OpenRecall Server
After=network.target

[Service]
Type=simple
User=<user>
Group=<user>
WorkingDirectory=/data/apps/MyRecall/openrecall
EnvironmentFile=/data/apps/MyRecall/openrecall/openrecall.env
Environment=UV_CACHE_DIR=/data/.cache/uv/openrecall
ExecStart=/data/venvs/openrecall/bin/python -m openrecall.server
Restart=always
RestartSec=5
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
```

启用与启动：

```bash
如果你第 8 步还在前台跑着服务，先在那个终端按 Ctrl+C 停掉（避免端口占用）。
sudo systemctl stop openrecall-server || true
sudo systemctl daemon-reload
sudo systemctl enable --now openrecall-server
sudo systemctl status openrecall-server --no-pager
```

查看日志：

```bash
sudo journalctl -u openrecall-server -n 200 --no-pager
```

## 10) Nginx 反代（可选但推荐）

注意：OpenRecall 的 `/api/*` 默认无鉴权。如需公网访问，务必增加 VPN / IP allowlist / BasicAuth 之一，并确保只暴露 80/443。

### 访问控制（推荐至少做一种）

IP allowlist（示例，只允许内网与单个公网 IP）：

```nginx
location / {
  allow 10.0.0.0/8;
  allow 192.168.0.0/16;
  allow <your_public_ip>;
  deny all;

  proxy_pass http://127.0.0.1:18083;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

BasicAuth（示例，最易落地）：

```bash
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd <user>
```

```nginx
location / {
  auth_basic "OpenRecall";
  auth_basic_user_file /etc/nginx/.htpasswd;

  proxy_pass http://127.0.0.1:18083;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

### HTTPS（建议）

如需 HTTPS，建议用 certbot（Nginx 插件）生成证书后再改为 443 监听。

创建 `/etc/nginx/sites-available/openrecall.conf`（反代到 127.0.0.1:18083）：

```nginx
server {
  listen 80;
  server_name <domain>;

  location / {
    proxy_pass http://127.0.0.1:18083;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/openrecall.conf /etc/nginx/sites-enabled/openrecall.conf
sudo nginx -t
sudo systemctl reload nginx
```

## 11) 数据一键清空与恢复（rm -rf /data/openrecall）

清空前先停服务：

```bash
sudo systemctl stop openrecall-server
```

清空数据：

```bash
sudo rm -rf /data/openrecall
```

重建目录并恢复权限：

```bash
sudo install -d -m 0750 -o <user> -g <user> /data/openrecall
sudo install -d -m 0750 -o <user> -g <user> /data/openrecall/{db,screenshots,cache}
```

启动服务：

```bash
sudo systemctl start openrecall-server
```
