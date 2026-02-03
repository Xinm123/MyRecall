# Phase 8.2 测试运行指南

## 🚀 快速开始（推荐）

### 一键测试
```bash
bash run_phase8_2_tests.sh
```

这个脚本会自动:
1. 启动 OpenRecall 服务器
2. 等待服务器就绪（最多 30 秒）
3. 运行 9 个集成测试
4. 显示测试结果
5. 清理服务器进程

**预期输出**:
```
✓ Get config
✓ Disable AI
✓ Verify state
✓ Disable recording
✓ Disable upload
✓ Heartbeat
✓ Re-enable all
✓ Recorder features
✓ Worker features

9/9 tests passed

🎉 All Phase 8.2 tests passed!
```

---

## 📖 详细测试步骤

### 步骤 1: 启动服务器

**在终端1中**:
```bash
python -m openrecall.server
```

等待看到:
```
 * Running on http://127.0.0.1:8083
```

### 步骤 2: 运行集成测试

**在终端2中**:
```bash
python tests/test_phase8_2_with_requests.py
```

### 步骤 3: 验证结果

应该看到 9/9 测试通过。

---

## 🧪 单独运行各个测试

### 仅运行单元测试（无需服务器）
```bash
python -m pytest tests/test_phase8_2_logic_integration.py -v
```

**优点**:
- 快速（< 30 秒）
- 无需运行系统
- 可测试错误处理和边界情况

### 运行集成测试（需要服务器）
```bash
# 启动服务器
python -m openrecall.server &
sleep 5

# 运行测试
python tests/test_phase8_2_with_requests.py

# 杀死服务器
pkill -f "openrecall.server"
```

---

## 🔍 手动 API 测试

### 测试 1: 查看当前配置
```bash
curl http://localhost:8083/api/config
```

**响应**:
```json
{
  "ai_processing_enabled": true,
  "recording_enabled": true,
  "upload_enabled": true,
  "ui_show_ai": true,
  "last_heartbeat": 1768903258.64,
  "client_online": false
}
```

### 测试 2: 禁用 AI 处理
```bash
curl -X POST http://localhost:8083/api/config \
  -H "Content-Type: application/json" \
  -d '{"ai_processing_enabled": false}'
```

**响应** (应该显示 ai_processing_enabled: false):
```json
{
  "ai_processing_enabled": false,
  ...
}
```

### 测试 3: 禁用录制
```bash
curl -X POST http://localhost:8083/api/config \
  -H "Content-Type: application/json" \
  -d '{"recording_enabled": false}'
```

### 测试 4: 禁用上传
```bash
curl -X POST http://localhost:8083/api/config \
  -H "Content-Type: application/json" \
  -d '{"upload_enabled": false}'
```

### 测试 5: 客户端心跳
```bash
curl -X POST http://localhost:8083/api/heartbeat
```

**响应** (包含 config 和 client_online):
```json
{
  "status": "ok",
  "config": {
    "ai_processing_enabled": false,
    "recording_enabled": false,
    "upload_enabled": false,
    ...
  },
  "client_online": true
}
```

### 测试 6: 重新启用所有
```bash
curl -X POST http://localhost:8083/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "ai_processing_enabled": true,
    "recording_enabled": true,
    "upload_enabled": true
  }'
```

### 测试 7: 验证重新启用
```bash
curl http://localhost:8083/api/config
```

所有值应该都是 `true`。

---

## 🐛 故障排除

### 问题 1: "Connection refused"
**原因**: 服务器没有运行
**解决**: 
```bash
python -m openrecall.server
```

### 问题 2: "502 Bad Gateway"
**原因**: 服务器正在加载模型（首次启动）
**解决**: 等待 20-30 秒，服务器加载完成后重试

### 问题 3: 测试失败
**调试**:
1. 检查服务器日志是否有错误
2. 运行单个手动 curl 测试来隔离问题
3. 检查服务器是否仍在运行: `lsof -i :8083`

### 问题 4: 端口 8083 被占用
**解决**:
```bash
# 找出占用端口的进程
lsof -i :8083

# 杀死进程
kill -9 <PID>

# 或者使用不同的端口（修改 config.py）
OPENRECALL_PORT=8084 python -m openrecall.server
```

---

## 📊 测试执行时间

| 测试类型 | 时间 | 备注 |
|---------|------|------|
| 单元测试 | ~30s | 无需服务器 |
| 集成测试 | ~20s | 需要启动的服务器 |
| 完整测试 (含启动) | ~60s | 包括服务器启动时间 |
| 一键测试脚本 | ~30-40s | 最快的方式 |

---

## ✅ 测试清单

### 功能测试
- [x] API 端点可访问
- [x] 设置可更新
- [x] 心跳可同步
- [x] 状态正确反映
- [x] 错误处理正确

### 集成测试
- [x] Worker 可读取 ai_processing_enabled
- [x] Recorder 可读取 recording_enabled
- [x] Recorder 可读取 upload_enabled
- [x] Recorder 有 _send_heartbeat 方法
- [x] 所有导入正确

### 边界情况
- [x] 网络超时
- [x] 缺失字段
- [x] 无效 JSON
- [x] 快速启用/禁用循环

---

## 📝 日志示例

### 服务器启动日志
```
17:57:50 | INFO    | openrecall.server | ==================================================
17:57:50 | INFO    | openrecall.server | OpenRecall Server Starting
17:57:50 | INFO    | openrecall.server | ==================================================
...
17:57:50 | INFO    | openrecall.server.worker | 🚀 ProcessingWorker started
17:57:50 | INFO    | werkzeug | Running on http://127.0.0.1:8083
```

### 禁用 AI 处理的日志
```
17:57:51 | INFO    | werkzeug | 127.0.0.1 - - [20/Jan/2026 17:57:51] "POST /api/config HTTP/1.1" 200 -
```

### Recorder 心跳日志（调试模式）
```
17:57:55 | DEBUG   | openrecall.client.recorder | Heartbeat synced: recording=False, upload=False
```

---

## 💡 高级用法

### 在测试中修改端口
```bash
OPENRECALL_PORT=8084 python -m openrecall.server
```

然后在测试中:
```python
base_url = "http://localhost:8084"
```

### 仅运行特定测试
```bash
# 运行单个单元测试
python -m pytest tests/test_phase8_2_logic_integration.py::TestWorkerPhase82 -v

# 运行单个集成测试
python -c "
import tests.test_phase8_2_with_requests as t
t.test_with_requests()
"
```

### 运行带详细输出的测试
```bash
# 显示所有 print 输出
python -m pytest tests/test_phase8_2_logic_integration.py -v -s

# 显示断言细节
python -m pytest tests/test_phase8_2_logic_integration.py -vv
```

---

## 🎯 预期结果

成功的测试运行会显示:
- ✓ 所有 9 个测试通过
- 0 个失败
- 0 个错误
- "🎉 All Phase 8.2 tests passed!" 消息

---

## 📞 支持

如果测试失败:
1. 查看 `PHASE_8.2_IMPLEMENTATION.md` 了解实现细节
2. 查看 `PHASE_8.2_TEST_RESULTS.md` 了解详细测试结果
3. 检查 `openrecall/server/api.py` 中的 API 实现
4. 检查 `openrecall/server/worker.py` 和 `openrecall/client/recorder.py` 中的逻辑

---

**Happy Testing! 🎉**
