# MyRecall-v3 Audio 系统分析文档

**版本**: 1.0  
**最后更新**: 2026-02-09  
**状态**: Phase 2.0 工程完成（待24h稳定性验证）

---

## 📚 文档目录

本目录包含 MyRecall-v3 音频系统的完整技术文档，涵盖采集、传输、处理、存储、检索等全流程。

### 核心文档

| 文档 | 说明 | 状态 |
|------|------|------|
| **[01-audio-pipeline-overview.md](./01-audio-pipeline-overview.md)** | Audio Pipeline 完整架构详解 | ✅ 完成 |
| **[02-audio-api-reference.md](./02-audio-api-reference.md)** | Audio API 参考文档 | ✅ 完成 |
| **[03-audio-configuration.md](./03-audio-configuration.md)** | Audio 配置完全指南 | ✅ 完成 |
| **[04-audio-troubleshooting.md](./04-audio-troubleshooting.md)** | Audio 故障排查手册 | ✅ 完成 |
| **[05-audio-performance-tuning.md](./05-audio-performance-tuning.md)** | Audio 性能调优指南 | ✅ 完成 |

---

## 🎯 快速导航

### 按角色查找

#### 开发者
- **理解架构**：[01-audio-pipeline-overview.md](./01-audio-pipeline-overview.md)
  - 数据流图
  - 存储路径映射
  - 关键组件解析
- **API 集成**：[02-audio-api-reference.md](./02-audio-api-reference.md)
  - 上传 API
  - 查询 API
  - 检索 API
- **配置系统**：[03-audio-configuration.md](./03-audio-configuration.md)
  - 环境变量详解
  - 完整配置示例
  - 配置检查表

#### 运维人员
- **故障排查**：[04-audio-troubleshooting.md](./04-audio-troubleshooting.md)
  - 诊断流程
  - 常见问题解决
  - 诊断工具
- **性能调优**：[05-audio-performance-tuning.md](./05-audio-performance-tuning.md)
  - 优化策略
  - 硬件配置建议
  - 性能基准测试

#### 测试人员
- **验证报告**：[../results/phase-2-validation.md](../results/phase-2-validation.md)
  - 测试结果
  - Gate 状态
  - 已知问题

---

## 📊 Audio Pipeline 总览

```
┌─────────────────── CLIENT ───────────────────┐
│                                                │
│  🎤 AudioManager (sounddevice)                │
│       ↓                                        │
│  📦 AudioRecorder (WAV chunks)                │
│       ↓                                        │
│  💾 LocalBuffer (100GB FIFO)                  │
│       ↓                                        │
│  📤 UploaderConsumer (HTTP multipart)         │
│                                                │
└────────────────────┬───────────────────────────┘
                     │ POST /api/v1/upload
                     ↓
┌─────────────────── SERVER ───────────────────┐
│                                                │
│  📥 Upload API (save WAV)                     │
│       ↓                                        │
│  🗄️ SQLite audio_chunks (PENDING)            │
│       ↓                                        │
│  🔄 AudioProcessingWorker (daemon)            │
│       ↓                                        │
│  🔊 VAD (Silero ONNX + WebRTC fallback)      │
│       ↓                                        │
│  🗣️ Whisper (faster-whisper)                  │
│       ↓                                        │
│  📝 SQLite audio_transcriptions + FTS5        │
│       ↓                                        │
│  🔍 SearchEngine (全文检索)                   │
│                                                │
└────────────────────────────────────────────────┘
```

---

## 🗂️ 数据流速览

| 阶段 | Client | Server | 格式 |
|------|--------|--------|------|
| **1. 采集** | AudioManager | - | 16kHz mono WAV |
| **2. 缓冲** | LocalBuffer | - | 本地文件 |
| **3. 上传** | HTTPUploader | Upload API | HTTP multipart |
| **4. 存储** | - | audio_chunks | SQLite + 文件 |
| **5. VAD** | - | VoiceActivityDetector | 语音段 |
| **6. 转写** | - | WhisperTranscriber | 文本段 |
| **7. 索引** | - | audio_transcriptions_fts | FTS5 |
| **8. 检索** | - | SearchEngine | JSON API |

---

## 📁 存储路径

### Client 端
- **音频 chunks**：`~/MRC/audio_chunks/` (临时)
- **缓冲队列**：`~/MRC/buffer/` (100GB FIFO)

### Server 端
- **音频文件**：`~/MRS/audio/` (永久)
- **数据库**：`~/MRS/db/recall.db` (SQLite)

---

## 🔧 关键配置

```bash
# 启用音频
export OPENRECALL_AUDIO_ENABLED=true

# 采样率（Whisper 要求 16kHz）
export OPENRECALL_AUDIO_SAMPLE_RATE=16000

# Chunk 时长（秒）
export OPENRECALL_AUDIO_CHUNK_DURATION=60

# 麦克风设备（空=默认）
export OPENRECALL_AUDIO_DEVICE_MIC=""

# 系统音频设备（需虚拟设备，如 BlackHole）
export OPENRECALL_AUDIO_DEVICE_SYSTEM=""

# Whisper 模型（tiny/base/small/medium/large-v3）
export OPENRECALL_AUDIO_WHISPER_MODEL=base

# VAD 后端（silero/webrtcvad）
export OPENRECALL_AUDIO_VAD_BACKEND=silero
export OPENRECALL_AUDIO_VAD_THRESHOLD=0.5
export OPENRECALL_AUDIO_VAD_MIN_SPEECH_RATIO=0.05
export OPENRECALL_AUDIO_VAD_SMOOTHING_WINDOW_FRAMES=10
export OPENRECALL_AUDIO_VAD_HYSTERESIS_ON_FRAMES=3
export OPENRECALL_AUDIO_VAD_HYSTERESIS_OFF_FRAMES=5
```

---

## 🚀 快速开始

### 1. 启动 Server

```bash
conda activate v3
cd /Users/pyw/new/MyRecall
./run_server.sh --debug
```

### 2. 启动 Client

```bash
conda activate v3
cd /Users/pyw/new/MyRecall
./run_client.sh --debug
```

### 3. 验证音频采集

```bash
# 检查日志
tail -f ~/MRS/logs/server.log | grep "🎧 \[AUDIO-SERVER\]"
tail -f ~/MRC/logs/client.log | grep "🎤 \[AUDIO\]"

# 查看队列状态
curl http://localhost:18083/api/v1/queue/status

# 查询转写记录
curl "http://localhost:18083/api/v1/audio/transcriptions?limit=10"
```

---

## 📈 当前状态（Phase 2.0）

| 指标 | 状态 |
|------|------|
| **采集** | ✅ 双设备（mic + system）支持 |
| **VAD** | ✅ Silero ONNX 主路径 + WebRTC fallback |
| **转写** | ✅ faster-whisper (CPU/GPU) |
| **FTS 索引** | ✅ FTS5 全文检索 |
| **Timeline** | ✅ 视频+音频统一 |
| **API** | ✅ 完整 REST API |
| **24h 稳定性** | ⏳ 待验证（2-S-01 gate） |

---

## 📚 相关文档

### v3/ 目录
- [Phase 2.0 详细计划](../plan/04-phase-2-detailed-plan.md)
- [Phase 2.0 验证报告](../results/phase-2-validation.md)
- [Phase Gates 定义](../metrics/phase-gates.md)
- [A/B Benchmark 输入样例](../../tests/fixtures/audio_ab/manifest.example.json)

### 代码目录
- Client: `openrecall/client/audio_*.py`
- Server: `openrecall/server/audio/*.py`
- Config: `openrecall/shared/config.py`
- Database: `openrecall/server/database/migrations/v3_001_*.sql`

---

## 🔄 更新日志

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-02-09 | 1.1 | 新增配置指南、故障排查手册、性能调优指南 |
| 2026-02-09 | 1.0 | 创建初始文档（Pipeline Overview + API Reference） |

---

## ✅ 待办事项

- [x] 创建 `03-audio-configuration.md`（详细配置指南）
- [x] 创建 `04-audio-troubleshooting.md`（故障排查手册）
- [x] 创建 `05-audio-performance-tuning.md`（性能调优指南）
- [ ] 补充 24h 稳定性测试结果（2-S-01 gate）
- [ ] 添加 Mermaid 交互式流程图
- [ ] 添加实际运行截图与日志示例
