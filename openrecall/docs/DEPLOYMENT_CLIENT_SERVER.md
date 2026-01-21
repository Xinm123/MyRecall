# Client/Server 分离部署：配置规范与数据流

每次运行任何 OpenRecall 的代码/命令前，都先执行 `conda activate MyRecall`。

如你只需要在 Debian 上部署 Server 端（不涉及 macOS Client），请参考：[DEPLOYMENT_DEBIAN_SERVER_GUIDE.md](DEPLOYMENT_DEBIAN_SERVER_GUIDE.md)。

## 目标

- Client（macOS）只负责：截屏 → 本地缓冲（可选本地留档）→ 上传到 Server
- Server（Debian）只负责：接收上传 → 保存 PNG → 写库 → 后台 OCR/AI/Embedding → Web UI 展示与检索
- 两端不共享磁盘；Server UI 展示的截图只来自 Server 保存的 PNG

## 实现概览（与代码对齐）

### 入口

- Server：`python -m openrecall.server`
- Client：`python -m openrecall.client`

### 关键请求路径

- Client → Server 健康检查：`GET /api/health`
- Client → Server 上传截图：`POST /api/upload`（Server 保存 PNG + 入库 PENDING）
- Client → Server 心跳：`POST /api/heartbeat`（Client 拉取开关：`recording_enabled/upload_enabled`）
- Web UI：`GET /`、`/search`、`/timeline`（读取 Server SQLite + 读取 Server PNG）
- 状态排查：`GET /api/queue/status`、`GET /api/config`

### 端口与访问方式（推荐）

- Debian 上让 Python 服务只对本机监听（默认行为），由 Nginx 统一对外提供 `80/443`
- Client 通过域名访问：`OPENRECALL_API_URL=https://<domain>/api`

## Debian 服务器环境准备（建议）

### 1) 部署用户与目录规划

- 建议使用专用用户运行服务（如 `openrecall`），避免用 root 直接跑
- 建议代码与数据分离
  - 代码：`/opt/openrecall`（只读为主）
  - 数据：`/var/lib/openrecall`（持久化读写）
- 数据目录建议结构
  - `/var/lib/openrecall/db`：SQLite（`recall.db`）
  - `/var/lib/openrecall/screenshots`：Server 保存的 PNG
  - `/var/lib/openrecall/cache`：模型与推理缓存（可选）
- 典型权限设置（示例）

```bash
sudo useradd --system --create-home --home-dir /var/lib/openrecall --shell /usr/sbin/nologin openrecall
sudo install -d -o openrecall -g openrecall -m 0750 /opt/openrecall /var/lib/openrecall
sudo install -d -o openrecall -g openrecall -m 0750 /var/lib/openrecall/{db,screenshots,cache}
```

### 2) 运行环境

- 与本地一致的 conda 环境：`conda activate MyRecall`
- 或使用 venv/系统 Python，但需确保依赖版本一致（OCR/AI 依赖较重）
- 如果启用 GPU：需要提前安装匹配 CUDA/驱动/依赖（并将 `OPENRECALL_DEVICE=cuda`）

### 3) 反向代理与防火墙

- 推荐 Nginx 负责 HTTPS 与对外端口：80/443
- Python 服务端口（默认 8083）只对本机开放（`127.0.0.1:8083`），不要直接暴露公网
- 防火墙策略：只放行 80/443；如必须直连 8083，仅允许可信 IP 段（内网或本机）

## 关键目录与“谁写谁读”

### Client 侧

- buffer（必需）：`OPENRECALL_DATA_DIR/buffer`
  - 写入：Client Producer
  - 读取/删除：Client Consumer（上传成功才 commit 删除）
- client screenshots（可选）：`OPENRECALL_CLIENT_SCREENSHOTS_DIR` 或默认 `OPENRECALL_DATA_DIR/screenshots`
  - 写入：Client Producer（本地留档 WebP）
  - 用途：本地查看/调试；与 Server UI 无关

### Server 侧

- server screenshots（必需）：`OPENRECALL_DATA_DIR/screenshots`
  - 写入：Server `/api/upload` 保存 `timestamp.png`
  - 读取：Web UI `/screenshots/<timestamp>.png` 与后台 worker
- db：`OPENRECALL_DATA_DIR/db/recall.db`
  - 写入：Server（插入 PENDING 与更新处理结果）
  - 读取：Server Web UI / API

## 推荐环境变量（分离部署）

### Server（Debian）推荐

- `OPENRECALL_PORT=8083`
- `OPENRECALL_DEBUG=false`
- `OPENRECALL_API_URL=http://127.0.0.1:8083/api`（仅用于内部一致性；对外访问走 Nginx 域名）
- `OPENRECALL_DATA_DIR=/var/lib/openrecall`（建议持久化路径）
- `OPENRECALL_CACHE_DIR=/var/lib/openrecall/cache`（可选；让 HF/Doctr/Torch 缓存也可一键清理）
- `OPENRECALL_PRELOAD_MODELS=true|false`（看机器性能；低配可先 false）
- `OPENRECALL_DEVICE=cpu|cuda`
- `OPENRECALL_AI_PROVIDER=<local|openai|...>`
- `OPENRECALL_AI_API_KEY=<key>`（如使用云端 provider）

### Client（macOS）推荐

- `OPENRECALL_API_URL=https://<domain>/api`
- `OPENRECALL_UPLOAD_TIMEOUT=180`（CPU 推理时可更大）
- `OPENRECALL_CAPTURE_INTERVAL=10`
- `OPENRECALL_PRIMARY_MONITOR_ONLY=true`
- `OPENRECALL_DATA_DIR=~/.myrecall_client`（与 Server 完全隔离）
- `OPENRECALL_CLIENT_SCREENSHOTS_DIR=~/.myrecall_client/screenshots`（可选；更明确）
- `OPENRECALL_CLIENT_SAVE_LOCAL_SCREENSHOTS=false`（可选；分离部署时通常不需要本地留档）
- `OPENRECALL_CACHE_DIR=~/.myrecall_client/cache`（可选；让 HF/Doctr/Torch 缓存也可一键清理）

## 开关（Control Center）对数据流的影响

- `recording_enabled=false`
  - Client Producer 停止截图：不会产生新的 buffer 项，也不会产生本地留档
- `upload_enabled=false`
  - Client Producer：仍会持续采集并写入本地 buffer（保证断网/断电不丢）
  - Client Consumer：即便 buffer 里已有积压也会暂停上传，恢复后继续
- `ai_processing_enabled=false`
  - Server Worker 跳过 AI/OCR/embedding 等处理（仅保留入库的 PENDING/原始截图）
- `ui_show_ai=false`
  - 仅影响 UI 展示，不影响是否入库/是否保存截图

## 典型启动方式

### Server（Debian）

```bash
conda activate MyRecall
export OPENRECALL_PORT=8083
export OPENRECALL_DEBUG=false
export OPENRECALL_DATA_DIR=/var/lib/openrecall
export OPENRECALL_PRELOAD_MODELS=false
python -m openrecall.server
```

### Client（macOS）

```bash
conda activate MyRecall
export OPENRECALL_API_URL=https://<domain>/api
export OPENRECALL_DATA_DIR=$HOME/.myrecall_client
export OPENRECALL_CLIENT_SCREENSHOTS_DIR=$HOME/.myrecall_client/screenshots
export OPENRECALL_CLIENT_SAVE_LOCAL_SCREENSHOTS=false
python -m openrecall.client
```

## Client 本地守护运行（macOS）

### 1) 推荐本地环境变量模板

可以准备一个本地 env 文件（示例：`$HOME/.myrecall_client/openrecall.env`）：

```bash
OPENRECALL_API_URL=https://<domain>/api
OPENRECALL_DATA_DIR=$HOME/.myrecall_client
OPENRECALL_CLIENT_SCREENSHOTS_DIR=$HOME/.myrecall_client/screenshots
OPENRECALL_CLIENT_SAVE_LOCAL_SCREENSHOTS=false
OPENRECALL_CAPTURE_INTERVAL=10
OPENRECALL_UPLOAD_TIMEOUT=180
OPENRECALL_PRIMARY_MONITOR_ONLY=true
```

### 2) LaunchAgent（示例）

创建 `~/Library/LaunchAgents/com.openrecall.client.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.openrecall.client</string>

  <key>ProgramArguments</key>
  <array>
    <string>/path/to/MyRecall/python</string>
    <string>-m</string>
    <string>openrecall.client</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>OPENRECALL_API_URL</key>
    <string>https://&lt;domain&gt;/api</string>
    <key>OPENRECALL_DATA_DIR</key>
    <string>$HOME/.myrecall_client</string>
    <key>OPENRECALL_CLIENT_SCREENSHOTS_DIR</key>
    <string>$HOME/.myrecall_client/screenshots</string>
    <key>OPENRECALL_CLIENT_SAVE_LOCAL_SCREENSHOTS</key>
    <string>false</string>
    <key>OPENRECALL_CAPTURE_INTERVAL</key>
    <string>10</string>
    <key>OPENRECALL_UPLOAD_TIMEOUT</key>
    <string>180</string>
    <key>OPENRECALL_PRIMARY_MONITOR_ONLY</key>
    <string>true</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>$HOME/.myrecall_client/logs/client.out.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.myrecall_client/logs/client.err.log</string>
</dict>
</plist>
```

`/path/to/MyRecall/python` 需要替换为你本机 conda 环境内 python 的绝对路径，例如：

- `/opt/miniconda3/envs/MyRecall/bin/python`
- `/Users/<user>/miniconda3/envs/MyRecall/bin/python`

## Server 生产运行（systemd）

### 1) 环境变量文件（示例）

创建 `/etc/openrecall/openrecall.env`：

```bash
OPENRECALL_DEBUG=false
OPENRECALL_PORT=8083
OPENRECALL_API_URL=http://127.0.0.1:8083/api
OPENRECALL_DATA_DIR=/var/lib/openrecall
OPENRECALL_CACHE_DIR=/var/lib/openrecall/cache
OPENRECALL_PRELOAD_MODELS=false
OPENRECALL_DEVICE=cpu
OPENRECALL_AI_PROVIDER=local
```

### 2) systemd unit（示例）

创建 `/etc/systemd/system/openrecall-server.service`：

```ini
[Unit]
Description=OpenRecall Server
After=network.target

[Service]
Type=simple
User=openrecall
Group=openrecall
WorkingDirectory=/opt/openrecall
EnvironmentFile=/etc/openrecall/openrecall.env
ExecStart=/path/to/MyRecall/python -m openrecall.server
Restart=always
RestartSec=5
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
```

`ExecStart` 推荐填 conda 环境内 python 的绝对路径，例如：

- `/opt/miniconda3/envs/MyRecall/bin/python`
- `/home/<user>/miniconda3/envs/MyRecall/bin/python`

## Nginx 反向代理与 HTTPS（模板）

### 1) 反代策略

- 对外只暴露 80/443
- Nginx 反代到 `http://127.0.0.1:8083`（Python 服务默认只本机监听即可）

### 2) Nginx server block（示例）

```nginx
server {
  listen 80;
  server_name <domain>;

  location /.well-known/acme-challenge/ {
    root /var/www/letsencrypt;
  }

  location / {
    return 301 https://$host$request_uri;
  }
}

server {
  listen 443 ssl http2;
  server_name <domain>;

  ssl_certificate     /etc/letsencrypt/live/<domain>/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/<domain>/privkey.pem;

  client_max_body_size 50m;
  proxy_read_timeout 300;

  location / {
    proxy_pass http://127.0.0.1:8083;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
}
```

### 3) 证书获取（Let’s Encrypt 方向）

- 使用 certbot 获取证书后，上述路径会自动生成到 `/etc/letsencrypt/live/<domain>/...`
- 建议开启自动续期，并在续期后 reload Nginx

## 联调与验证清单

### 1) 基础连通性

- Server：`GET https://<domain>/api/health` 返回 `{"status":"ok"}`
- Client：启动后应周期性调用 `POST https://<domain>/api/heartbeat` 并收到开关配置

### 2) 上传链路验证

- 上传成功后，Server 侧应同时出现两类落盘
  - PNG：`OPENRECALL_DATA_DIR/screenshots/<timestamp>.png`
  - SQLite：`OPENRECALL_DATA_DIR/db/recall.db` 中插入一条 `PENDING`
- 排查入口
  - `GET https://<domain>/api/queue/status`：看队列是否积压
  - `GET https://<domain>/api/memories/recent`：看最近条目与 `status` 变化（PENDING → COMPLETED）

### 3) Web UI 功能验证

- `GET https://<domain>/`：能看到最近截图（来自 Server 保存的 PNG）
- `GET https://<domain>/search?q=<keyword>`：能基于 OCR/Embedding 结果检索（取决于 `ai_processing_enabled` 是否开启）

### 4) 性能与稳定性压测方向

- 采集压力：调大 `OPENRECALL_CAPTURE_INTERVAL` 降低采集频率；或限制 `OPENRECALL_PRIMARY_MONITOR_ONLY=true`
- 推理压力：`OPENRECALL_PRELOAD_MODELS=false` 可降低启动与常驻内存；GPU 场景设置 `OPENRECALL_DEVICE=cuda`
- 网络与上传：弱网/高延迟场景适当调大 `OPENRECALL_UPLOAD_TIMEOUT`，并确保 Nginx `proxy_read_timeout` 覆盖最大推理耗时
- 磁盘与备份：截图目录增长快，需监控剩余空间并定期备份 `db/` 与 `screenshots/`

## 安全与运维加固（强烈建议）

### 1) 访问控制（因为 API 默认无鉴权）

- 不要把 `8083` 端口直接暴露到公网（即使有 HTTPS 也不够）
- 如果必须公网访问，建议至少做到其中一种
  - Nginx 侧 IP allowlist（只允许你的办公网/家庭 IP）
  - VPN 接入后再访问（推荐）
  - Nginx BasicAuth（最容易落地，但注意密码管理）
- 尤其注意：`/api/upload` 与 `/api/config` 在默认实现下都不需要登录即可访问

### 2) 密钥与配置管理

- `OPENRECALL_AI_API_KEY` 等敏感变量放在 `/etc/openrecall/openrecall.env`，权限建议 `chmod 600`
- 不要把 key 写进代码仓库，也不要写进 shell 历史（用文件或 CI secret 注入）

### 3) 数据安全与合规

- Server 会保存原始截图与 OCR/描述/Embedding；请按你的数据合规要求决定保留周期
- 推荐对 `OPENRECALL_DATA_DIR` 使用磁盘加密（LUKS/加密卷）并配置定期备份

### 4) 监控与巡检

- 定期探活：`GET /api/health`
- 重点监控：磁盘剩余空间、CPU/内存、队列积压（`/api/queue/status`）、错误日志（systemd/journald）

## 常见误区

- “Client 保存的 WebP 会出现在 Server UI”：不会。Server UI 只展示 Server 侧保存的 PNG（`/screenshots/*.png`）。
- “同一个 OPENRECALL_DATA_DIR 同时给 client/server 用”：分离部署时不要这样配置，否则会混淆归属与权限问题。
