## 目标与现状对齐（基于本仓库实现）
- Server=Flask Web UI + `/api` + 同进程后台 worker 线程（OCR/Embedding/索引）
- Client=本地截图→buffer 队列→HTTP 上传到 Server（断网会积压，恢复后继续）
- 持久化=Server 侧 SQLite + Server 侧 PNG 截图；Client 仅缓存与可选本地留档

## 1) Debian 服务器环境准备
- 准备专用用户/目录：`/opt/openrecall`（代码）与 `/var/lib/openrecall`（数据）
- 安装 Python 运行环境（推荐与本地一致的 conda `MyRecall` 或 venv）
- 规划算力与模型缓存目录（`OPENRECALL_CACHE_DIR`），必要时挂载加密盘
- 安装并配置 Nginx + TLS（Let’s Encrypt）
- 配置防火墙：仅开放 80/443；API 通过 Nginx 反代，不直接暴露 8083

## 2) Server 端部署与守护
- 上传代码到 `/opt/openrecall`，安装依赖（按 `setup.py`/requirements）
- 以环境文件管理生产配置：`OPENRECALL_DEBUG=false`、`OPENRECALL_DATA_DIR=/var/lib/openrecall`、AI Provider/Key 等
- 使用 systemd 守护 `python -m openrecall.server`，并接入 journald 日志
- Nginx 反代到 `127.0.0.1:8083`，并启用 HTTPS、压缩、合理超时

## 3) 本地 Client 配置与运行
- 本地安装依赖并保持 `MyRecall` 环境一致
- 配置 `OPENRECALL_API_URL=https://<domain>/api`、`OPENRECALL_DATA_DIR=~/.myrecall_client`、采集/上传参数
- 以 LaunchAgent/计划任务（macOS）守护 `python -m openrecall.client`

## 4) 联网与调试路径
- 服务器侧：通过 `GET /api/health` 验证服务；观察 `/api/queue/status` 与 server 日志
- 客户端侧：先健康检查，再验证上传链路（`POST /api/upload`），确认 Server 数据目录落盘
- 若需要浏览器跨域访问（非常规），再评估 CORS；默认同源 UI 不需要

## 5) 集成与性能验证
- 端到端：heartbeat 开关控制→采集/积压/恢复→Server 入库 PENDING→worker 处理 COMPLETED→UI 检索
- 性能：调整 `OPENRECALL_PRELOAD_MODELS`、`OPENRECALL_DEVICE`、上传超时与采集间隔；监控 CPU/内存/磁盘

## 6) 安全与运维加固（建议）
- 因 API 默认无鉴权：通过 Nginx allowlist/VPN/BasicAuth 做访问控制
- 数据安全：磁盘加密 + 定期备份 SQLite 与 screenshots
- 可选改造（需代码变更后再做）：API token 鉴权、生产 WSGI（gunicorn）运行、补充 CORS 配置

如果你确认此方案，我将基于上述计划进一步给出：systemd unit、nginx server block、推荐 env 文件模板、验证清单，并按你的域名/证书方式做适配。