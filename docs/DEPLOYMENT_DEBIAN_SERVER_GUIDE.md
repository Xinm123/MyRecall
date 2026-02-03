# Debian Server 部署参考指南（OpenRecall）

本文只面向 Debian 服务器部署 OpenRecall 的 Server 端（Web UI + `/api` + 后台 worker），不包含 macOS Client 的采集侧。

## 适用范围与工作方式

- Server 入口：`python -m openrecall.server`
- 默认端口：`8083`（`OPENRECALL_PORT`）
- 持久化数据
  - SQLite：`OPENRECALL_DATA_DIR/db/recall.db`
  - 截图 PNG：`OPENRECALL_DATA_DIR/screenshots/<timestamp>.png`
- 推荐对外访问方式：Nginx 对外 `80/443`，反代到 `127.0.0.1:8083`，不要把 `8083` 直接暴露到公网

## 目录与权限规划（推荐）

- 代码目录：`/opt/openrecall`
- 数据目录：`/var/lib/openrecall`
  - `db/`：SQLite
  - `screenshots/`：Server 侧 PNG
  - `cache/`：模型/推理缓存（可选，但强烈建议单独放，便于清理与迁移）

创建专用用户与目录（示例）：

```bash
sudo useradd --system --create-home --home-dir /var/lib/openrecall --shell /usr/sbin/nologin openrecall
sudo install -d -o openrecall -g openrecall -m 0750 /opt/openrecall /var/lib/openrecall
sudo install -d -o openrecall -g openrecall -m 0750 /var/lib/openrecall/{db,screenshots,cache}
```

## 系统依赖与运行环境

### 1) OS 包（建议最小集合）

```bash
sudo apt update
sudo apt install -y nginx sqlite3 ca-certificates curl git
```

如你使用 Let’s Encrypt：

```bash
sudo apt install -y certbot python3-certbot-nginx
```

如遇到 Python 依赖安装/运行时提示缺少动态库（常见于 Torch/图像相关依赖），再补装：

```bash
sudo apt install -y libglib2.0-0 libgl1
```

### 2) Python 环境（两种方式二选一）

#### 方案 A：conda（推荐与本地一致）

- 在服务器准备与本地一致的 conda 环境（例如 `MyRecall`）
- 后续 systemd `ExecStart` 指向该环境内 python 的绝对路径

#### 方案 B：venv（更轻量）

```bash
sudo apt install -y python3 python3-venv python3-pip
sudo -u openrecall python3 -m venv /opt/openrecall/venv
sudo -u openrecall /opt/openrecall/venv/bin/pip install -U pip
```

## 部署代码与安装依赖

### 1) 放置代码

- 推荐将仓库放到 `/opt/openrecall`
- 目录归属建议：root 拥有，openrecall 可读；或直接 openrecall 拥有（取决于你的更新流程）

示例（直接由 openrecall 用户拉取）：

```bash
sudo -u openrecall git clone <your_repo_url> /opt/openrecall
```

### 2) 安装 Python 依赖

以 conda 环境为例：

```bash
conda activate MyRecall
cd /opt/openrecall
pip install -e .
```

以 venv 为例：

```bash
sudo -u openrecall /opt/openrecall/venv/bin/pip install -e /opt/openrecall
```

## 生产环境变量（Server）

创建目录与 env 文件：

```bash
sudo install -d -m 0750 /etc/openrecall
sudo touch /etc/openrecall/openrecall.env
sudo chown root:openrecall /etc/openrecall/openrecall.env
sudo chmod 0640 /etc/openrecall/openrecall.env
```

`/etc/openrecall/openrecall.env`（示例）：

```bash
OPENRECALL_DEBUG=false
OPENRECALL_PORT=8083
OPENRECALL_API_URL=http://127.0.0.1:8083/api
OPENRECALL_DATA_DIR=/var/lib/openrecall
OPENRECALL_CACHE_DIR=/var/lib/openrecall/cache
OPENRECALL_PRELOAD_MODELS=false
OPENRECALL_DEVICE=cpu

OPENRECALL_AI_PROVIDER=local
OPENRECALL_AI_API_KEY=
OPENRECALL_AI_API_BASE=
```

## systemd 守护运行

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
ExecStart=/path/to/python -m openrecall.server
Restart=always
RestartSec=5
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
```

`ExecStart` 建议填写绝对路径：

- conda：`/opt/miniconda3/envs/MyRecall/bin/python` 或 `/home/<user>/miniconda3/envs/MyRecall/bin/python`
- venv：`/opt/openrecall/venv/bin/python`

启用与启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now openrecall-server
sudo systemctl status openrecall-server --no-pager
```

查看日志：

```bash
sudo journalctl -u openrecall-server -n 200 --no-pager
```

## Nginx 反向代理与 HTTPS

### 1) 站点配置（HTTP → HTTPS）

创建 `/etc/nginx/sites-available/openrecall.conf`：

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

启用站点并 reload：

```bash
sudo ln -s /etc/nginx/sites-available/openrecall.conf /etc/nginx/sites-enabled/openrecall.conf
sudo nginx -t
sudo systemctl reload nginx
```

### 2) Let’s Encrypt（certbot）

```bash
sudo install -d -m 0755 /var/www/letsencrypt
sudo certbot --nginx -d <domain>
```

## 防火墙端口策略

- 推荐只开放：`80/443`
- `8083` 仅本机使用（Nginx 反代），不对公网开放

如果你使用 UFW（示例）：

```bash
sudo apt install -y ufw
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

## 验证清单（上线前后都适用）

### 1) 服务探活

```bash
curl -fsS https://<domain>/api/health
```

### 2) UI 可访问

- 打开 `https://<domain>/` 应出现 Web UI 页面

### 3) Server 落盘检查

- `ls -lah /var/lib/openrecall/db/recall.db`
- `ls -lah /var/lib/openrecall/screenshots | head`

### 4) 队列与处理状态

```bash
curl -fsS https://<domain>/api/queue/status
curl -fsS https://<domain>/api/memories/recent
```

## 备份、监控与维护

### 1) 备份建议

- 至少备份：`/var/lib/openrecall/db/` 与 `/var/lib/openrecall/screenshots/`
- 建议定期把 `db/` 单独快照（SQLite 文件体积小，恢复快）

### 2) 监控建议（最小集合）

- 磁盘空间：截图增长快，优先告警
- CPU/内存：本地推理时 CPU 占用可能很高
- 服务与错误：systemd 状态 + journald 日志
- 队列积压：`/api/queue/status`

## 安全加固（强烈建议）

### 1) 默认无鉴权风险

OpenRecall 的 `/api/*` 默认没有鉴权。不要把服务裸露到公网。

建议至少采用一种访问控制：

- VPN 后访问（推荐）
- Nginx IP allowlist（只允许可信来源）
- Nginx BasicAuth（易落地，但注意密码与审计）

### 2) 敏感配置

- `OPENRECALL_AI_API_KEY` 只放在 `/etc/openrecall/openrecall.env`，并控制权限（建议 root 可写、openrecall 可读）
- 不要把 key 写入仓库或命令行历史

### 3) 数据安全

- Server 保存原始截图与提取内容；按你的合规要求确定保留周期
- 推荐对 `/var/lib/openrecall` 做磁盘加密与离线备份

## 常见问题排查

### 1) Nginx 502 / 连接失败

- `systemctl status openrecall-server`
- `journalctl -u openrecall-server -n 200 --no-pager`
- 确认 `OPENRECALL_PORT` 与 Nginx `proxy_pass` 端口一致（默认 8083）

### 2) 上传超时或响应慢

- 适当增大 Client 侧 `OPENRECALL_UPLOAD_TIMEOUT`
- 确保 Nginx `proxy_read_timeout` 覆盖最大推理耗时
- 降低采集频率：调大 `OPENRECALL_CAPTURE_INTERVAL`

### 3) 磁盘占满

- 优先监控 `screenshots/` 的增长速度
- 如需清理，务必先备份 `db/`，并确认你的保留策略与合规要求

