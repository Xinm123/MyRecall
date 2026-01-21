# Client/Server 分离部署：配置规范与数据流

每次运行任何 OpenRecall 的代码/命令前，都先执行 `conda activate MyRecall`。

## 目标

- Client（macOS）只负责：截屏 → 本地缓冲（可选本地留档）→ 上传到 Server
- Server（Debian）只负责：接收上传 → 保存 PNG → 写库 → 后台 OCR/AI/Embedding → Web UI 展示与检索
- 两端不共享磁盘；Server UI 展示的截图只来自 Server 保存的 PNG

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
- `OPENRECALL_API_URL=http://0.0.0.0:8083/api`（仅用于日志/内部一致性；外部访问走域名或内网 IP）
- `OPENRECALL_DATA_DIR=/var/lib/openrecall`（建议持久化路径）
- `OPENRECALL_CACHE_DIR=/var/lib/openrecall/cache`（可选；让 HF/Doctr/Torch 缓存也可一键清理）
- `OPENRECALL_PRELOAD_MODELS=true|false`（看机器性能；低配可先 false）
- `OPENRECALL_DEVICE=cpu|cuda`

### Client（macOS）推荐

- `OPENRECALL_API_URL=http://<debian-ip-or-domain>:8083/api`
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
export OPENRECALL_DATA_DIR=/var/lib/openrecall
export OPENRECALL_PRELOAD_MODELS=false
python -m openrecall.server
```

### Client（macOS）

```bash
conda activate MyRecall
export OPENRECALL_API_URL=http://<debian-ip-or-domain>:8083/api
export OPENRECALL_DATA_DIR=$HOME/.myrecall_client
export OPENRECALL_CLIENT_SCREENSHOTS_DIR=$HOME/.myrecall_client/screenshots
export OPENRECALL_CLIENT_SAVE_LOCAL_SCREENSHOTS=false
python -m openrecall.client
```

## 常见误区

- “Client 保存的 WebP 会出现在 Server UI”：不会。Server UI 只展示 Server 侧保存的 PNG（`/screenshots/*.png`）。
- “同一个 OPENRECALL_DATA_DIR 同时给 client/server 用”：分离部署时不要这样配置，否则会混淆归属与权限问题。
