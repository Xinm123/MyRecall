# Runtime Configuration API 测试清单

## 快速测试指南

按照下面的命令逐个执行，验证所有功能是否正常工作。

### 1. 读取配置 (GET /api/config)

```bash
curl -s http://localhost:8083/api/config | python3 -m json.tool
```

**预期结果:**
- HTTP 200
- JSON包含以下字段：
  - `recording_enabled`: boolean
  - `upload_enabled`: boolean
  - `ai_processing_enabled`: boolean
  - `ui_show_ai`: boolean
  - `last_heartbeat`: float (Unix时间戳)
  - `client_online`: boolean

**示例输出:**
```json
{
    "ai_processing_enabled": true,
    "client_online": false,
    "last_heartbeat": 1768899751.165005,
    "recording_enabled": true,
    "ui_show_ai": true,
    "upload_enabled": true
}
```

---

### 2. 更新单个字段 (POST /api/config)

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"recording_enabled": false}' \
  http://localhost:8083/api/config | python3 -m json.tool
```

**预期结果:**
- HTTP 200
- 返回更新后的配置
- `recording_enabled` 应该是 `false`

---

### 3. 验证更新持久化

```bash
curl -s http://localhost:8083/api/config | python3 -m json.tool
```

**预期结果:**
- `recording_enabled` 仍然是 `false`（验证之前的更新被保存了）

---

### 4. 更新多个字段

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"recording_enabled": true, "upload_enabled": false, "ai_processing_enabled": false}' \
  http://localhost:8083/api/config | python3 -m json.tool
```

**预期结果:**
- HTTP 200
- 三个字段都被更新

---

### 5. 测试错误处理 - 无效字段名

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"unknown_field": true}' \
  http://localhost:8083/api/config
```

**预期结果:**
- HTTP 400
- 错误消息: `"Unknown field: unknown_field"`

---

### 6. 测试错误处理 - 无效类型

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"recording_enabled": "not a boolean"}' \
  http://localhost:8083/api/config
```

**预期结果:**
- HTTP 400
- 错误消息: `"Field recording_enabled must be boolean"`

---

### 7. 注册心跳 (POST /api/heartbeat)

```bash
curl -X POST http://localhost:8083/api/heartbeat | python3 -m json.tool
```

**预期结果:**
- HTTP 200
- JSON格式:
  ```json
  {
    "status": "ok",
    "config": {
      "recording_enabled": ...,
      "upload_enabled": ...,
      "ai_processing_enabled": ...,
      "ui_show_ai": ...,
      "last_heartbeat": <更新后的时间戳>,
      "client_online": true
    }
  }
  ```

---

### 8. 验证 client_online 状态

```bash
# 立即发送心跳后查询
curl -X POST http://localhost:8083/api/heartbeat > /dev/null
curl -s http://localhost:8083/api/config | python3 -m json.tool
```

**预期结果:**
- `client_online` 应该是 `true`（因为刚刚发送了心跳）

---

### 9. 测试 client_online 超时

```bash
# 等待16秒后查询（心跳超时阈值是15秒）
sleep 16
curl -s http://localhost:8083/api/config | python3 -m json.tool
```

**预期结果:**
- `client_online` 应该变为 `false`（因为上次心跳已经超过15秒）

---

### 10. 重置为默认值

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"recording_enabled": true, "upload_enabled": true, "ai_processing_enabled": true, "ui_show_ai": true}' \
  http://localhost:8083/api/config | python3 -m json.tool
```

**预期结果:**
- HTTP 200
- 所有字段都被重置为 `true`

---

## 测试脚本（一次性运行所有测试）

如果你想一次性运行所有测试，可以使用以下脚本：

```bash
# 使用提供的Python测试脚本
python3 test_runtime_config_py.py
```

或者：

```bash
# 使用Bash脚本
./test_runtime_config.sh
```

---

## 验证清单

完成以上所有测试后，检查以下项目：

- [ ] ✅ 所有GET请求返回200
- [ ] ✅ 所有POST更新返回200
- [ ] ✅ 无效字段被正确拒绝（400错误）
- [ ] ✅ 无效类型被正确拒绝（400错误）
- [ ] ✅ 配置更新被正确保存
- [ ] ✅ 心跳功能正常工作
- [ ] ✅ `client_online` 在发送心跳后为true
- [ ] ✅ `client_online` 在15秒后超时变为false
- [ ] ✅ 线程安全（多个并发请求不会导致数据竞争）

---

## 常见问题

### Q: 什么是 `client_online`？
A: `client_online` 是一个计算字段，表示客户端是否在线。当上次心跳的时间距离现在不超过15秒时，它为 `true`。

### Q: 心跳的目的是什么？
A: 心跳用来告诉服务器客户端还活着。服务器会记录最后一次心跳的时间，以判断客户端是否在线。

### Q: 为什么某个字段总是返回我设置的值？
A: 因为设置是内存中的，会在服务器重启后重置为默认值。如果需要持久化，需要修改实现将设置保存到数据库。

### Q: 如何在并发请求中保证线程安全？
A: 使用了 `threading.RLock()`（可重入锁）来保护所有操作，确保同一时刻只有一个线程修改设置。

---

## 下一步

如果所有测试都通过了，就可以继续：

1. 将这些API集成到客户端代码中
2. 在客户端定期发送心跳（如每5秒一次）
3. 根据服务器返回的配置调整客户端行为
4. 添加数据库持久化来保存长期配置
