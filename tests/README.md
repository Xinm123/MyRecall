# Tests

## Quick Reference

### 默认运行（无需外部服务）

```bash
pytest
```

### 集成测试（需要运行 Edge 服务器）

```bash
# Terminal 1: 启动服务器
./run_server.sh --debug

# Terminal 2: 运行集成测试
pytest -m integration
```

### 单独运行

```bash
pytest tests/test_p1_s1_health_parsing.py -v
```

## Test Categories

| 标记 | 说明 | 运行命令 |
|------|------|---------|
| `unit` | 单元测试，无外部依赖 | `pytest -m unit` |
| `integration` | 需要 Edge 服务器 | `pytest -m integration` |
| `e2e` | 端到端测试 | `pytest -m e2e` |
| `perf` | 性能基准测试 | `pytest -m perf` |
| `security` | 安全测试 | `pytest -m security` |
| `model` | 需要模型/大资源 | `pytest -m model` |
| `manual` | 手工测试脚本 | `pytest -m manual` |

## Files

### 独立运行（无依赖）

这些测试使用 `tmp_path`、`monkeypatch` 或 `flask_client` fixture，无需外部服务：

| 文件 | 测试内容 |
|------|---------|
| `test_p1_s1_grid_data_contract.py` | Grid 数据契约 |
| `test_p1_s1_timestamp_contract.py` | 时间戳契约 |
| `test_p1_s1_spool_atomic.py` | Spool 原子写入 |
| `test_p1_s1_noop_search_engine.py` | Noop 搜索引擎 |
| `test_p1_s1_health_parsing.py` | Health 响应解析 |
| `test_p1_s2a_events.py` | 事件系统 |
| `test_p1_s2a_debounce.py` | 去抖逻辑 |
| `test_p1_s2a_device_binding.py` | 设备绑定 |
| `test_p1_s2a_trigger_coverage.py` | 触发器覆盖 |
| `test_p1_s2a_backpressure_gate.py` | 背压保护 |
| `test_p1_s2a_loss_rate_gate.py` | 丢失率计算 |
| `test_p1_s2a_recorder.py` | 录制器逻辑 |
| `test_p1_s2a_server_contracts.py` | 服务器契约 |
| `test_p1_s2a_local_script.py` | 验收脚本逻辑 |
| `test_v3_migrations_bootstrap.py` | 数据库迁移 |
| `test_timestamp_utils.py` | 时间戳工具 |
| `test_shared_utils_logging.py` | 日志工具 |
| `test_api_memories_since.py` | API 记忆查询 |
| `test_client_uploader_logging.py` | 上传器日志 |

### 需要 Edge 服务器

这些测试使用 `requests` 直接调用 `http://localhost:8083`：

| 文件 | 测试内容 | 启动命令 |
|------|---------|---------|
| `test_p1_s1_frames.py` | Frame 读取 API | `./run_server.sh --debug` |
| `test_p1_s1_ingest.py` | Ingest 管道 | `./run_server.sh --debug` |
| `test_p1_s1_startup.py` | 启动验证 | `./run_server.sh --debug` |
| `test_p1_s1_legacy.py` | Legacy API 重定向 | `./run_server.sh --debug` |
| `test_p1_s1_image_format.py` | 图片格式处理 | `./run_server.sh --debug` |
| `test_p1_s1_uploader_retry.py` | 上传重试逻辑 | `./run_server.sh --debug` |

## Fixtures

`conftest.py` 提供以下 fixture：

| Fixture | 说明 |
|---------|------|
| `flask_app` | 配置好的 Flask 应用实例 |
| `flask_client` | Flask 测试客户端 |
| `tmp_path` | 隔离的临时目录 |
| `monkeypatch` | 环境变量/mock 替换 |

## Coverage

```bash
pytest --cov=openrecall --cov-report=term-missing
```
