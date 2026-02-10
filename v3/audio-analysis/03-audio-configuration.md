# MyRecall-v3 Audio 配置完全指南

**版本**: 1.0  
**最后更新**: 2026-02-09  
**适用范围**: Phase 2.0 音频系统

---

## 📋 目录

- [1. 配置概览](#1-配置概览)
- [2. 采集配置](#2-采集配置)
- [3. VAD 配置](#3-vad-配置)
- [4. Whisper 配置](#4-whisper-配置)
- [5. 存储与缓冲配置](#5-存储与缓冲配置)
- [6. 性能与调优配置](#6-性能与调优配置)
- [7. 完整配置示例](#7-完整配置示例)
- [8. 故障排查检查表](#8-故障排查检查表)

---

## 1. 配置概览

### 1.1 配置源优先级

MyRecall-v3 使用 pydantic-settings 管理配置，优先级（从高到低）：

```
1. 环境变量（OPENRECALL_* prefix）
2. .env 文件（myrecall_client.env / myrecall_server.env）
3. 代码默认值（openrecall/shared/config.py）
```

### 1.2 配置文件位置

**权威配置文件**：

| 角色 | 路径 | 说明 |
|------|------|------|
| **Client** | `/Users/pyw/new/MyRecall/myrecall_client.env` | 客户端采集配置 |
| **Server** | `/Users/pyw/new/MyRecall/myrecall_server.env` | 服务端处理配置 |

**加载方式**：

```bash
# 使用启动脚本（自动加载）
./run_client.sh --debug
./run_server.sh --debug

# 手动指定 env 文件
./run_client.sh --env=/path/to/custom_client.env
./run_server.sh --env=/path/to/custom_server.env
```

### 1.3 配置分类

| 类别 | 作用域 | 关键参数 |
|------|--------|----------|
| **采集** | Client | audio_enabled, audio_sample_rate, audio_device_* |
| **缓冲** | Client | buffer_max_size_bytes, buffer_ttl_hours |
| **上传** | Client | api_url, upload_timeout |
| **处理** | Server | audio_vad_backend, audio_whisper_model |
| **存储** | Server | server_data_dir, server_audio_path |

---

## 2. 采集配置

### 2.1 总开关

#### `OPENRECALL_AUDIO_ENABLED`

**说明**：启用/禁用音频采集  
**类型**：`bool`  
**默认值**：`true`  
**作用域**：Client

```bash
# 启用（默认）
export OPENRECALL_AUDIO_ENABLED=true

# 禁用（仅视频模式）
export OPENRECALL_AUDIO_ENABLED=false
```

**影响**：
- `true`：AudioManager 和 AudioRecorder 启动
- `false`：跳过音频采集，不消耗音频相关资源

---

### 2.2 音频格式参数

#### `OPENRECALL_AUDIO_SAMPLE_RATE`

**说明**：音频采样率（Hz）  
**类型**：`int`  
**默认值**：`16000`  
**作用域**：Client  
**约束**：**必须为 16000**（Whisper 要求）

```bash
# 默认值（推荐，不要修改）
export OPENRECALL_AUDIO_SAMPLE_RATE=16000
```

**警告**：
- ⚠️ 修改此值会导致 Whisper 转写失败或质量下降
- 如需其他采样率，必须在服务端重采样（当前不支持）

---

#### `OPENRECALL_AUDIO_CHANNELS`

**说明**：音频通道数  
**类型**：`int`  
**默认值**：`1`  
**作用域**：Client  
**约束**：**必须为 1**（Whisper 要求 mono）

```bash
# 默认值（推荐，不要修改）
export OPENRECALL_AUDIO_CHANNELS=1
```

**说明**：
- 即使输入设备是立体声，也会自动转换为单声道
- 转换方式：平均左右声道（`(L + R) / 2`）

---

#### `OPENRECALL_AUDIO_FORMAT`

**说明**：音频文件格式  
**类型**：`str`  
**默认值**：`"wav"`  
**作用域**：Client  
**约束**：**固定为 "wav"**

```bash
# 默认值（不可修改）
export OPENRECALL_AUDIO_FORMAT=wav
```

**说明**：
- WAV 格式保证无损录制
- 使用 PCM 编码（无压缩）
- 文件大小：~1.9MB/min（16kHz mono）

---

### 2.3 Chunk 时长

#### `OPENRECALL_AUDIO_CHUNK_DURATION`

**说明**：音频 chunk 时长（秒）  
**类型**：`int`  
**默认值**：`60`  
**作用域**：Client  
**范围**：`30-600` 秒

```bash
# 默认值（推荐）
export OPENRECALL_AUDIO_CHUNK_DURATION=60

# 更短 chunk（更频繁上传，更低延迟）
export OPENRECALL_AUDIO_CHUNK_DURATION=30

# 更长 chunk（减少上传频率，更大缓冲）
export OPENRECALL_AUDIO_CHUNK_DURATION=300
```

**权衡**：

| Chunk 时长 | 延迟 | 上传频率 | 内存占用 | 适用场景 |
|-----------|------|---------|---------|----------|
| **30s** | 低 | 高（120次/小时） | 低 | 实时性要求高 |
| **60s** | 中 | 中（60次/小时） | 中 | **默认推荐** |
| **300s** | 高 | 低（12次/小时） | 高 | 网络带宽受限 |

**影响**：
- 文件大小 = `sample_rate × channels × duration × 2 bytes`
- 60s chunk ≈ 1.9 MB

---

### 2.4 设备选择

#### `OPENRECALL_AUDIO_DEVICE_MIC`

**说明**：麦克风设备名称或索引  
**类型**：`str`  
**默认值**：`""` (默认输入设备)  
**作用域**：Client

```bash
# 使用默认麦克风（推荐）
export OPENRECALL_AUDIO_DEVICE_MIC=""

# 使用设备名称（支持部分匹配）
export OPENRECALL_AUDIO_DEVICE_MIC="MacBook Pro Microphone"

# 使用设备索引
export OPENRECALL_AUDIO_DEVICE_MIC="0"
```

**如何查找设备名称**：

```python
import sounddevice as sd
print(sd.query_devices())
```

输出示例：
```
  0 MacBook Pro Microphone, Core Audio (2 in, 0 out)
  1 MacBook Pro Speakers, Core Audio (0 in, 2 out)
  2 BlackHole 2ch, Core Audio (2 in, 2 out)
```

**常见设备名称**：
- macOS: `"MacBook Pro Microphone"`, `"External Microphone"`
- Windows: `"Microphone Array"`, `"Line In"`
- Linux: `"pulse"`, `"default"`

---

#### `OPENRECALL_AUDIO_DEVICE_SYSTEM`

**说明**：系统音频设备名称或索引  
**类型**：`str`  
**默认值**：`""` (禁用系统音频)  
**作用域**：Client  
**前置要求**：需要虚拟音频设备

```bash
# 禁用系统音频（默认）
export OPENRECALL_AUDIO_DEVICE_SYSTEM=""

# macOS（使用 BlackHole）
export OPENRECALL_AUDIO_DEVICE_SYSTEM="BlackHole 2ch"

# Windows（使用 VB-Audio Cable）
export OPENRECALL_AUDIO_DEVICE_SYSTEM="CABLE Output"

# Linux（使用 PulseAudio Monitor）
export OPENRECALL_AUDIO_DEVICE_SYSTEM="alsa_output.pci.monitor"
```

**虚拟设备安装指南**：

| 平台 | 推荐工具 | 下载地址 |
|------|---------|----------|
| **macOS** | BlackHole | https://existential.audio/blackhole/ |
| **Windows** | VB-Audio Virtual Cable | https://vb-audio.com/Cable/ |
| **Linux** | PulseAudio Monitor | 内置（`pavucontrol` 配置） |

**macOS BlackHole 安装步骤**：

```bash
# 1. 安装 BlackHole
brew install blackhole-2ch

# 2. 创建 Multi-Output Device
# 打开 Audio MIDI Setup.app → 点击 "+" → "Create Multi-Output Device"
# 勾选: BlackHole 2ch + 内置扬声器

# 3. 系统设置
# System Settings → Sound → Output → 选择 "Multi-Output Device"

# 4. 配置 MyRecall
export OPENRECALL_AUDIO_DEVICE_SYSTEM="BlackHole 2ch"
```

**注意事项**：
- ⚠️ 系统音频采集可能受 DRM 保护（Safari 视频等）
- ⚠️ 隐私风险：会记录系统所有声音（通知、音乐等）
- ⚠️ 需配置 Multi-Output Device 才能同时听到声音

---

## 3. VAD 配置

### 3.1 VAD 后端选择

#### `OPENRECALL_AUDIO_VAD_BACKEND`

**说明**：Voice Activity Detection 后端  
**类型**：`str`  
**默认值**：`"silero"`  
**作用域**：Server  
**可选值**：`"silero"`, `"webrtcvad"`

```bash
# Silero ONNX（推荐）
export OPENRECALL_AUDIO_VAD_BACKEND=silero

# WebRTC VAD（显式指定或自动 fallback）
export OPENRECALL_AUDIO_VAD_BACKEND=webrtcvad
```

**对比**：

| 后端 | 准确率 | 速度 | 依赖 | 适用场景 |
|------|-------|------|------|----------|
| **silero** | 高 (95%+) | 快 (~0.05s/30s) | ONNX Runtime | **默认推荐** |
| **webrtcvad** | 中 (85%) | 极快 (~0.01s/30s) | `webrtcvad-wheels` | fallback/低资源 |

**Silero 特点**：
- ONNX 推理路径（无需 torch.hub 作为主路径）
- 支持多语言（中文、英文等）
- 首次自动下载模型到 `OPENRECALL_SERVER_DATA_DIR/models/vad/silero_vad_v5.onnx`

**WebRTC 特点**：
- 轻量级二进制扩展（`webrtcvad` import，建议安装 `webrtcvad-wheels`）
- 无需模型下载
- 作为 Silero 初始化失败时的兜底路径

---

### 3.2 VAD 阈值

#### `OPENRECALL_AUDIO_VAD_THRESHOLD`

**说明**：语音概率阈值  
**类型**：`float`  
**默认值**：`0.5`  
**作用域**：Server  
**范围**：`0.0 - 1.0`

```bash
# 默认值（平衡灵敏度）
export OPENRECALL_AUDIO_VAD_THRESHOLD=0.5

# 更严格（减少误检，可能漏检轻声）
export OPENRECALL_AUDIO_VAD_THRESHOLD=0.7

# 更宽松（捕捉更多语音，可能包含噪音）
export OPENRECALL_AUDIO_VAD_THRESHOLD=0.3
```

**权衡**：

| 阈值 | 召回率 | 精确率 | 适用场景 |
|------|-------|--------|----------|
| **0.3** | 高 | 低 | 嘈杂环境（会议室） |
| **0.5** | 中 | 中 | **默认推荐** |
| **0.7** | 低 | 高 | 安静环境（单人录音） |

**实际效果**（以 60s chunk 为例）：

- 阈值 0.3: 转写率 ~60%（包含轻微噪音）
- 阈值 0.5: 转写率 ~40%（默认）
- 阈值 0.7: 转写率 ~20%（仅清晰语音）

### 3.3 Chunk 级门控与平滑滞回

#### `OPENRECALL_AUDIO_VAD_MIN_SPEECH_RATIO`

**说明**：chunk 内语音占比阈值，低于该值直接跳过 Whisper  
**类型**：`float`  
**默认值**：`0.05`

```bash
export OPENRECALL_AUDIO_VAD_MIN_SPEECH_RATIO=0.05
```

#### `OPENRECALL_AUDIO_VAD_SMOOTHING_WINDOW_FRAMES`

**说明**：帧级平滑窗口大小（对 Silero 概率 / WebRTC 0/1 统一平滑）  
**类型**：`int`  
**默认值**：`10`

```bash
export OPENRECALL_AUDIO_VAD_SMOOTHING_WINDOW_FRAMES=10
```

#### `OPENRECALL_AUDIO_VAD_HYSTERESIS_ON_FRAMES`

**说明**：进入语音状态所需连续语音帧  
**类型**：`int`  
**默认值**：`3`

```bash
export OPENRECALL_AUDIO_VAD_HYSTERESIS_ON_FRAMES=3
```

#### `OPENRECALL_AUDIO_VAD_HYSTERESIS_OFF_FRAMES`

**说明**：退出语音状态所需连续静音帧  
**类型**：`int`  
**默认值**：`5`

```bash
export OPENRECALL_AUDIO_VAD_HYSTERESIS_OFF_FRAMES=5
```

---

## 4. Whisper 配置

### 4.1 模型大小

#### `OPENRECALL_AUDIO_WHISPER_MODEL`

**说明**：Whisper 模型规模  
**类型**：`str`  
**默认值**：`"base"`  
**作用域**：Server  
**可选值**：`"tiny"`, `"base"`, `"small"`, `"medium"`, `"large-v3"`

```bash
# 默认值（推荐：速度与准确率平衡）
export OPENRECALL_AUDIO_WHISPER_MODEL=base

# 最快（适合实时场景）
export OPENRECALL_AUDIO_WHISPER_MODEL=tiny

# 最准确（需要 GPU）
export OPENRECALL_AUDIO_WHISPER_MODEL=large-v3
```

**模型对比**：

| 模型 | 参数量 | 模型大小 | VRAM | CPU速度（30s音频） | GPU速度（30s音频） | WER（英文） |
|------|--------|---------|------|------------------|------------------|-----------|
| **tiny** | 39M | ~75MB | ~1GB | ~5s | ~1s | ~10% |
| **base** | 74M | ~140MB | ~1GB | ~10s | ~2s | ~7% |
| **small** | 244M | ~460MB | ~2GB | ~30s | ~5s | ~5% |
| **medium** | 769M | ~1.5GB | ~5GB | ~100s | ~12s | ~4% |
| **large-v3** | 1550M | ~3GB | ~10GB | ~200s | ~20s | ~3% |

**推荐策略**：

```bash
# 开发/测试（快速迭代）
OPENRECALL_AUDIO_WHISPER_MODEL=tiny

# 生产（默认推荐）
OPENRECALL_AUDIO_WHISPER_MODEL=base

# 高质量场景（会议纪要、访谈）
OPENRECALL_AUDIO_WHISPER_MODEL=small

# GPU 环境（最佳质量）
OPENRECALL_AUDIO_WHISPER_MODEL=large-v3
```

---

### 4.2 计算类型

#### `OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE`

**说明**：Whisper 推理精度  
**类型**：`str`  
**默认值**：`"int8"`  
**作用域**：Server  
**可选值**：`"int8"`, `"float16"`, `"float32"`

```bash
# CPU 优化（推荐，默认）
export OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE=int8

# GPU 加速（需要 CUDA/ROCm）
export OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE=float16

# 最高精度（慢，仅调试用）
export OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE=float32
```

**对比**：

| 类型 | 速度 | 内存 | 精度损失 | 适用场景 |
|------|------|------|---------|----------|
| **int8** | 快 (1x) | 低 (1x) | ~1% WER 下降 | **CPU 生产环境** |
| **float16** | 最快 (2-3x) | 中 (2x) | 无 | **GPU 生产环境** |
| **float32** | 慢 (0.5x) | 高 (4x) | 无 | 仅用于验证基线 |

**平台支持**：

| 平台 | int8 | float16 | float32 |
|------|------|---------|---------|
| **CPU** | ✅ 推荐 | ✅ 可用 | ✅ 可用（慢） |
| **CUDA GPU** | ✅ | ✅ 推荐 | ✅ |
| **Apple MPS** | ❌ 不支持 | ❌ 不支持 | ✅ 回退 CPU |

**注意**：
- ⚠️ macOS M1/M2 无法使用 MPS 加速（CTranslate2 限制）
- ⚠️ float16 需要 GPU 支持 half-precision

---

### 4.3 语言设置

#### `OPENRECALL_AUDIO_WHISPER_LANGUAGE`

**说明**：转写语言代码  
**类型**：`str`  
**默认值**：`"en"`  
**作用域**：Server  
**格式**：ISO 639-1 语言代码

```bash
# 英文（默认）
export OPENRECALL_AUDIO_WHISPER_LANGUAGE=en

# 中文
export OPENRECALL_AUDIO_WHISPER_LANGUAGE=zh

# 日文
export OPENRECALL_AUDIO_WHISPER_LANGUAGE=ja

# 自动检测（不推荐）
export OPENRECALL_AUDIO_WHISPER_LANGUAGE=auto
```

**常用语言代码**：

| 语言 | 代码 | 注意事项 |
|------|------|----------|
| 英文 | `en` | 默认，准确率最高 |
| 中文 | `zh` | 支持普通话，粤语效果较差 |
| 日文 | `ja` | 需要 small 以上模型 |
| 韩文 | `ko` | 需要 small 以上模型 |
| 西班牙文 | `es` | 支持拉丁美洲和欧洲变体 |
| 法文 | `fr` | 需要 base 以上模型 |

**自动检测警告**：
- ⚠️ `auto` 会增加 ~20% 转写时间
- ⚠️ 多语言混杂场景可能识别错误
- ⚠️ 推荐显式指定主要语言

---

### 4.4 Beam Search 参数

#### `OPENRECALL_AUDIO_WHISPER_BEAM_SIZE`

**说明**：Beam search 宽度  
**类型**：`int`  
**默认值**：`5`  
**作用域**：Server  
**范围**：`1-10`

```bash
# 默认值（推荐）
export OPENRECALL_AUDIO_WHISPER_BEAM_SIZE=5

# 更快（准确率略降）
export OPENRECALL_AUDIO_WHISPER_BEAM_SIZE=1

# 更准确（速度降低）
export OPENRECALL_AUDIO_WHISPER_BEAM_SIZE=10
```

**权衡**：

| Beam Size | 速度 | 准确率 | 内存 | 适用场景 |
|-----------|------|--------|------|----------|
| **1** | 2x | -2% WER | 1x | 实时转写 |
| **5** | 1x | 基线 | 1x | **默认推荐** |
| **10** | 0.7x | +1% WER | 1.5x | 高质量场景 |

**实际效果**（base 模型，30s 音频）：

- Beam=1: ~8s（适合实时）
- Beam=5: ~10s（默认）
- Beam=10: ~15s（质量优先）

---

## 5. 存储与缓冲配置

### 5.1 存储路径

#### Client 端路径

##### `OPENRECALL_CLIENT_DATA_DIR`

**说明**：Client 数据根目录  
**类型**：`str`  
**默认值**：`"~/MRC"`  
**作用域**：Client

```bash
# 默认路径
export OPENRECALL_CLIENT_DATA_DIR=~/MRC

# 自定义路径
export OPENRECALL_CLIENT_DATA_DIR=/Volumes/External/MyRecall/client
```

**自动生成子目录**：
```
~/MRC/
├── audio_chunks/     # 音频 chunk 临时存储（上传后删除）
├── buffer/           # 待上传文件队列
├── video_chunks/     # 视频 chunk 临时存储
└── logs/             # 客户端日志
```

---

#### Server 端路径

##### `OPENRECALL_SERVER_DATA_DIR`

**说明**：Server 数据根目录  
**类型**：`str`  
**默认值**：`"~/MRS"`  
**作用域**：Server

```bash
# 默认路径
export OPENRECALL_SERVER_DATA_DIR=~/MRS

# 自定义路径（推荐：大容量磁盘）
export OPENRECALL_SERVER_DATA_DIR=/mnt/storage/MyRecall/server
```

**自动生成子目录**：
```
~/MRS/
├── audio/            # 音频文件永久存储
├── video/            # 视频文件永久存储
├── db/               # SQLite 数据库
│   └── recall.db
├── models/           # AI 模型缓存
│   ├── whisper/
│   └── vad/
│       └── silero_vad_v5.onnx
└── logs/             # 服务端日志
```

---

### 5.2 缓冲队列配置

#### `OPENRECALL_BUFFER_MAX_SIZE_BYTES`

**说明**：本地缓冲队列最大容量  
**类型**：`int`  
**默认值**：`107374182400` (100GB)  
**作用域**：Client

```bash
# 默认值（100GB）
export OPENRECALL_BUFFER_MAX_SIZE_BYTES=107374182400

# 50GB（低存储设备）
export OPENRECALL_BUFFER_MAX_SIZE_BYTES=53687091200

# 500GB（高可靠性需求）
export OPENRECALL_BUFFER_MAX_SIZE_BYTES=536870912000
```

**存储估算**：

| 场景 | 音频数据量 | 视频数据量 | 总计 | 推荐容量 |
|------|----------|----------|------|---------|
| **仅音频** | 2.7 GB/天 | 0 | 2.7 GB/天 | 50 GB (18天) |
| **音频+视频（1080p@2fps）** | 2.7 GB/天 | 20 GB/天 | 22.7 GB/天 | 100 GB (4天) |
| **音频+视频（4K@5fps）** | 2.7 GB/天 | 150 GB/天 | 152.7 GB/天 | 500 GB (3天) |

**FIFO 清理策略**：
- 容量超限时，删除最旧文件
- 确保新数据始终可入队
- 上传成功后立即删除

---

#### `OPENRECALL_BUFFER_TTL_HOURS`

**说明**：缓冲文件 TTL（Time To Live）  
**类型**：`int`  
**默认值**：`168` (7天)  
**作用域**：Client

```bash
# 默认值（7天）
export OPENRECALL_BUFFER_TTL_HOURS=168

# 3天（快速清理）
export OPENRECALL_BUFFER_TTL_HOURS=72

# 30天（长期保留）
export OPENRECALL_BUFFER_TTL_HOURS=720
```

**用途**：
- 防止长期未上传文件占用空间
- 网络中断恢复后的自动清理
- 与 `BUFFER_MAX_SIZE_BYTES` 共同作用

**清理时机**：
- 启动时扫描
- 每小时定期检查
- 入队新文件时触发

---

### 5.3 上传配置

#### `OPENRECALL_API_URL`

**说明**：Server API 地址  
**类型**：`str`  
**默认值**：`"http://localhost:18083"`  
**作用域**：Client

```bash
# 本地模式（默认）
export OPENRECALL_API_URL=http://localhost:18083

# 远程服务器
export OPENRECALL_API_URL=http://192.168.1.100:18083

# HTTPS（生产环境）
export OPENRECALL_API_URL=https://myrecall.example.com
```

**注意事项**：
- ⚠️ 确保 Server 端口与 `OPENRECALL_PORT` 一致
- ⚠️ 跨网络部署需配置防火墙规则
- ⚠️ HTTPS 需配置反向代理（Nginx/Caddy）

---

#### `OPENRECALL_UPLOAD_TIMEOUT`

**说明**：上传超时时间（秒）  
**类型**：`int`  
**默认值**：`300` (5分钟)  
**作用域**：Client

```bash
# 默认值（5分钟）
export OPENRECALL_UPLOAD_TIMEOUT=300

# 快速网络（1分钟）
export OPENRECALL_UPLOAD_TIMEOUT=60

# 慢速网络（30分钟）
export OPENRECALL_UPLOAD_TIMEOUT=1800
```

**推荐值**（基于网络带宽）：

| 网络类型 | 带宽 | 上传时间（1.9MB音频） | 推荐超时 |
|---------|------|---------------------|---------|
| **本地回环** | 无限 | ~0.1s | 60s |
| **千兆局域网** | 1 Gbps | ~0.02s | 60s |
| **百兆局域网** | 100 Mbps | ~0.15s | 120s |
| **4G/5G** | 10 Mbps | ~1.5s | 300s |
| **ADSL** | 1 Mbps | ~15s | 600s |

---

## 6. 性能与调优配置

### 6.1 Worker 线程数

#### `OPENRECALL_AUDIO_WORKER_THREADS`

**说明**：音频处理 worker 线程数  
**类型**：`int`  
**默认值**：`1`  
**作用域**：Server

```bash
# 默认值（单线程）
export OPENRECALL_AUDIO_WORKER_THREADS=1

# 多线程（4核 CPU）
export OPENRECALL_AUDIO_WORKER_THREADS=2

# 高并发（8核+ CPU）
export OPENRECALL_AUDIO_WORKER_THREADS=4
```

**注意**：
- ⚠️ Whisper 本身已多线程优化（`num_workers=4`）
- ⚠️ 增加 worker 会增加内存占用（每个 worker 独立加载模型）
- ⚠️ 推荐值：`min(CPU核心数 / 2, 4)`

---

### 6.2 模型预加载

#### `OPENRECALL_PRELOAD_MODELS`

**说明**：Server 启动时预加载模型  
**类型**：`bool`  
**默认值**：`true`  
**作用域**：Server

```bash
# 启用预加载（推荐，默认）
export OPENRECALL_PRELOAD_MODELS=true

# 禁用预加载（延迟加载，首次转写慢）
export OPENRECALL_PRELOAD_MODELS=false
```

**影响**：

| 预加载 | 启动时间 | 首次转写延迟 | 内存占用时机 |
|-------|---------|------------|-------------|
| **true** | +10s | 0s | 启动时 |
| **false** | 即时 | +10s | 首次请求时 |

**推荐场景**：
- ✅ 生产环境：启用（确保服务就绪）
- ✅ 开发环境：禁用（快速重启）

---

### 6.3 日志级别

#### `OPENRECALL_LOG_LEVEL`

**说明**：日志详细程度  
**类型**：`str`  
**默认值**：`"INFO"`  
**作用域**：Client + Server  
**可选值**：`"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`

```bash
# 默认值（生产推荐）
export OPENRECALL_LOG_LEVEL=INFO

# 调试模式（详细日志）
export OPENRECALL_LOG_LEVEL=DEBUG

# 仅错误（减少日志量）
export OPENRECALL_LOG_LEVEL=ERROR
```

**日志量对比**：

| 级别 | 日志量 | 包含内容 | 适用场景 |
|------|-------|---------|----------|
| **DEBUG** | 极多 | 函数调用、参数、中间结果 | 开发、排查 bug |
| **INFO** | 中等 | 启动、chunk 处理、关键状态 | **生产默认** |
| **WARNING** | 少 | 异常恢复、性能警告 | 稳定运行后 |
| **ERROR** | 极少 | 仅错误和崩溃 | 仅监控错误 |

---

## 7. 完整配置示例

### 7.1 本地开发环境

**myrecall_client.env**:
```bash
# ============ Audio 开发配置 ============

# 启用音频
OPENRECALL_AUDIO_ENABLED=true

# 音频格式（固定）
OPENRECALL_AUDIO_SAMPLE_RATE=16000
OPENRECALL_AUDIO_CHANNELS=1
OPENRECALL_AUDIO_FORMAT=wav
OPENRECALL_AUDIO_CHUNK_DURATION=60

# 设备（使用默认）
OPENRECALL_AUDIO_DEVICE_MIC=""
OPENRECALL_AUDIO_DEVICE_SYSTEM=""

# 存储（默认路径）
OPENRECALL_CLIENT_DATA_DIR=~/MRC

# 缓冲（50GB）
OPENRECALL_BUFFER_MAX_SIZE_BYTES=53687091200
OPENRECALL_BUFFER_TTL_HOURS=72

# 上传（本地）
OPENRECALL_API_URL=http://localhost:18083
OPENRECALL_UPLOAD_TIMEOUT=60

# 日志（调试）
OPENRECALL_LOG_LEVEL=DEBUG
```

**myrecall_server.env**:
```bash
# ============ Audio 开发配置 ============

# 存储（默认路径）
OPENRECALL_SERVER_DATA_DIR=~/MRS

# VAD（快速测试）
OPENRECALL_AUDIO_VAD_BACKEND=silero
OPENRECALL_AUDIO_VAD_THRESHOLD=0.5
OPENRECALL_AUDIO_VAD_MIN_SPEECH_RATIO=0.05
OPENRECALL_AUDIO_VAD_SMOOTHING_WINDOW_FRAMES=10
OPENRECALL_AUDIO_VAD_HYSTERESIS_ON_FRAMES=3
OPENRECALL_AUDIO_VAD_HYSTERESIS_OFF_FRAMES=5

# Whisper（快速模型）
OPENRECALL_AUDIO_WHISPER_MODEL=tiny
OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE=int8
OPENRECALL_AUDIO_WHISPER_LANGUAGE=en
OPENRECALL_AUDIO_WHISPER_BEAM_SIZE=1

# 性能（单线程）
OPENRECALL_AUDIO_WORKER_THREADS=1
OPENRECALL_PRELOAD_MODELS=false

# 日志（调试）
OPENRECALL_LOG_LEVEL=DEBUG
```

---

### 7.2 生产环境（CPU）

**myrecall_client.env**:
```bash
# ============ Audio 生产配置（CPU）============

# 启用音频
OPENRECALL_AUDIO_ENABLED=true

# 音频格式（固定）
OPENRECALL_AUDIO_SAMPLE_RATE=16000
OPENRECALL_AUDIO_CHANNELS=1
OPENRECALL_AUDIO_FORMAT=wav
OPENRECALL_AUDIO_CHUNK_DURATION=60

# 设备（配置实际设备）
OPENRECALL_AUDIO_DEVICE_MIC="MacBook Pro Microphone"
OPENRECALL_AUDIO_DEVICE_SYSTEM="BlackHole 2ch"

# 存储（大容量磁盘）
OPENRECALL_CLIENT_DATA_DIR=/mnt/storage/myrecall/client

# 缓冲（100GB）
OPENRECALL_BUFFER_MAX_SIZE_BYTES=107374182400
OPENRECALL_BUFFER_TTL_HOURS=168

# 上传（远程服务器）
OPENRECALL_API_URL=https://myrecall.internal.example.com
OPENRECALL_UPLOAD_TIMEOUT=300

# 日志（INFO）
OPENRECALL_LOG_LEVEL=INFO
```

**myrecall_server.env**:
```bash
# ============ Audio 生产配置（CPU）============

# 存储（大容量磁盘）
OPENRECALL_SERVER_DATA_DIR=/mnt/storage/myrecall/server

# VAD（Silero）
OPENRECALL_AUDIO_VAD_BACKEND=silero
OPENRECALL_AUDIO_VAD_THRESHOLD=0.5
OPENRECALL_AUDIO_VAD_MIN_SPEECH_RATIO=0.05
OPENRECALL_AUDIO_VAD_SMOOTHING_WINDOW_FRAMES=10
OPENRECALL_AUDIO_VAD_HYSTERESIS_ON_FRAMES=3
OPENRECALL_AUDIO_VAD_HYSTERESIS_OFF_FRAMES=5

# Whisper（base 模型，CPU 优化）
OPENRECALL_AUDIO_WHISPER_MODEL=base
OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE=int8
OPENRECALL_AUDIO_WHISPER_LANGUAGE=en
OPENRECALL_AUDIO_WHISPER_BEAM_SIZE=5

# 性能（2 workers，8核 CPU）
OPENRECALL_AUDIO_WORKER_THREADS=2
OPENRECALL_PRELOAD_MODELS=true

# 日志（INFO）
OPENRECALL_LOG_LEVEL=INFO
OPENRECALL_PORT=18083
```

---

### 7.3 生产环境（GPU）

**myrecall_server.env**:
```bash
# ============ Audio 生产配置（GPU）============

# 存储（大容量磁盘）
OPENRECALL_SERVER_DATA_DIR=/mnt/storage/myrecall/server

# VAD（Silero）
OPENRECALL_AUDIO_VAD_BACKEND=silero
OPENRECALL_AUDIO_VAD_THRESHOLD=0.5
OPENRECALL_AUDIO_VAD_MIN_SPEECH_RATIO=0.05
OPENRECALL_AUDIO_VAD_SMOOTHING_WINDOW_FRAMES=10
OPENRECALL_AUDIO_VAD_HYSTERESIS_ON_FRAMES=3
OPENRECALL_AUDIO_VAD_HYSTERESIS_OFF_FRAMES=5

# Whisper（small 模型，GPU 加速）
OPENRECALL_AUDIO_WHISPER_MODEL=small
OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE=float16
OPENRECALL_AUDIO_WHISPER_LANGUAGE=en
OPENRECALL_AUDIO_WHISPER_BEAM_SIZE=5

# 性能（4 workers，RTX 4090）
OPENRECALL_AUDIO_WORKER_THREADS=4
OPENRECALL_PRELOAD_MODELS=true

# CUDA 配置
CUDA_VISIBLE_DEVICES=0

# 日志（INFO）
OPENRECALL_LOG_LEVEL=INFO
OPENRECALL_PORT=18083
```

---

### 7.4 中文语音场景

**myrecall_server.env**:
```bash
# ============ Audio 中文配置 ============

# Whisper（中文优化）
OPENRECALL_AUDIO_WHISPER_MODEL=base
OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE=int8
OPENRECALL_AUDIO_WHISPER_LANGUAGE=zh
OPENRECALL_AUDIO_WHISPER_BEAM_SIZE=5

# VAD（Silero 支持中文）
OPENRECALL_AUDIO_VAD_BACKEND=silero
OPENRECALL_AUDIO_VAD_THRESHOLD=0.5
OPENRECALL_AUDIO_VAD_MIN_SPEECH_RATIO=0.05
OPENRECALL_AUDIO_VAD_SMOOTHING_WINDOW_FRAMES=10
OPENRECALL_AUDIO_VAD_HYSTERESIS_ON_FRAMES=3
OPENRECALL_AUDIO_VAD_HYSTERESIS_OFF_FRAMES=5

# 其他配置同生产环境
```

**注意事项**：
- ✅ base 模型对中文支持良好
- ✅ small/medium 模型可提升中英混杂识别
- ⚠️ 粤语、方言需 large 模型

---

## 8. 故障排查检查表

### 8.1 音频采集问题

**症状**：Client 日志无 `🎤 [AUDIO]` 输出

**检查清单**：
```bash
# 1. 确认音频已启用
echo $OPENRECALL_AUDIO_ENABLED  # 应为 true

# 2. 检查 sounddevice 安装
python3 -c "import sounddevice; print(sounddevice.query_devices())"

# 3. 查看可用设备
python3 -c "import sounddevice as sd; print(sd.query_devices())"

# 4. 检查设备名称
echo $OPENRECALL_AUDIO_DEVICE_MIC
echo $OPENRECALL_AUDIO_DEVICE_SYSTEM

# 5. 查看 client 日志
tail -f ~/MRC/logs/client.log | grep "AUDIO"
```

---

### 8.2 VAD 问题

**症状**：所有音频都被跳过（无转写）

**检查清单**：
```bash
# 1. 确认 VAD 阈值
echo $OPENRECALL_AUDIO_VAD_THRESHOLD  # 默认 0.5

# 2. 降低阈值测试
export OPENRECALL_AUDIO_VAD_THRESHOLD=0.3
./run_server.sh --debug

# 3. 切换 VAD 后端
export OPENRECALL_AUDIO_VAD_BACKEND=webrtcvad

# 4. 检查音频文件是否有效
ffprobe ~/MRS/audio/<checksum>.wav
```

---

### 8.3 Whisper 转写慢

**症状**：处理延迟 >60s/30s音频

**检查清单**：
```bash
# 1. 确认计算类型
echo $OPENRECALL_AUDIO_WHISPER_COMPUTE_TYPE  # CPU 用 int8

# 2. 检查模型大小
echo $OPENRECALL_AUDIO_WHISPER_MODEL  # 推荐 base

# 3. 降低 beam size
export OPENRECALL_AUDIO_WHISPER_BEAM_SIZE=1

# 4. 检查 CPU 占用
top -p $(pgrep -f "run_server")

# 5. 切换到更小模型
export OPENRECALL_AUDIO_WHISPER_MODEL=tiny
```

---

### 8.4 队列积压

**症状**：`GET /api/v1/queue/status` 显示大量 PENDING

**检查清单**：
```bash
# 1. 检查 worker 状态
curl http://localhost:18083/api/v1/queue/status | jq

# 2. 查看 server 日志
tail -f ~/MRS/logs/server.log | grep "AUDIO-SERVER"

# 3. 增加 worker 线程
export OPENRECALL_AUDIO_WORKER_THREADS=2

# 4. 检查磁盘空间
df -h ~/MRS

# 5. 检查数据库锁
sqlite3 ~/MRS/db/recall.db "PRAGMA busy_timeout;"
```

---

### 8.5 FTS 搜索无结果

**症状**：`GET /api/v1/search?q=...` 返回空

**检查清单**：
```bash
# 1. 确认转写已完成
curl "http://localhost:18083/api/v1/audio/transcriptions?limit=10"

# 2. 检查 FTS 表
sqlite3 ~/MRS/db/recall.db "SELECT COUNT(*) FROM audio_transcriptions_fts;"

# 3. 尝试简单查询
curl "http://localhost:18083/api/v1/search?q=the&content_type=audio"

# 4. 检查查询语法
curl "http://localhost:18083/api/v1/search?q=\"exact phrase\"&content_type=audio"

# 5. 查看 FTS5 tokenizer
sqlite3 ~/MRS/db/recall.db "PRAGMA table_info(audio_transcriptions_fts);"
```

---

## 📚 相关文档

- [Audio Pipeline 架构](./01-audio-pipeline-overview.md)
- [Audio API 文档](./02-audio-api-reference.md)
- [Audio 故障排查](./04-audio-troubleshooting.md)（待创建）
- [Audio 性能调优](./05-audio-performance-tuning.md)（待创建）

---

## 🔄 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-02-09 | 1.0 | 初始版本（完整配置指南） |
