# MyRecall-v3 Audio API 参考文档

**版本**: 1.0  
**最后更新**: 2026-02-09  
**Base URL**: `http://localhost:18083/api/v1`

---

## 📖 API 概览

MyRecall-v3 提供以下 Audio 相关 API：

| API | 方法 | 路径 | 说明 |
|-----|------|------|------|
| **上传** | POST | `/upload` | 上传音频 chunk（multipart） |
| **上传状态** | GET | `/upload/status?checksum=...` | 查询上传状态 |
| **Chunks 列表** | GET | `/audio/chunks` | 查询音频 chunks |
| **转写列表** | GET | `/audio/transcriptions` | 查询转写记录 |
| **统一检索** | GET | `/search?q=...` | 全文检索（含音频） |
| **Timeline** | GET | `/timeline` | 时间线（视频+音频） |
| **队列状态** | GET | `/queue/status` | 查看处理队列状态 |

---

## 🔼 音频上传 API

### POST `/api/v1/upload`

上传音频 chunk 文件（WAV 格式）。

#### Request

**Headers**:
```http
Content-Type: multipart/form-data
```

**Form Data**:
```json
{
  "file": <binary WAV data>,
  "metadata": {
    "type": "audio_chunk",
    "timestamp": 1707498600.123,
    "start_time": 1707498600.0,
    "end_time": 1707498660.0,
    "device_name": "microphone",
    "sample_rate": 16000,
    "channels": 1,
    "format": "wav",
    "file_size_bytes": 102400,
    "checksum": "sha256:abc123def456...",
    "chunk_filename": "microphone_2026-02-09_19-30-15_123456.wav"
  }
}
```

**元数据字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | 固定为 `"audio_chunk"` |
| `timestamp` | float | ✅ | Unix 时间戳（chunk 起始时间） |
| `start_time` | float | ✅ | Chunk 起始时间（Unix） |
| `end_time` | float | ✅ | Chunk 结束时间（Unix） |
| `device_name` | string | ✅ | 设备名称（`microphone` / `system_audio`） |
| `sample_rate` | int | ✅ | 采样率（16000 Hz） |
| `channels` | int | ✅ | 通道数（1=mono） |
| `format` | string | ✅ | 文件格式（`wav`） |
| `file_size_bytes` | int | ✅ | 文件大小（字节） |
| `checksum` | string | ✅ | SHA256 校验和（`sha256:...`） |
| `chunk_filename` | string | ❌ | 原始文件名 |

#### Response

**Success (202 Accepted)**:
```json
{
  "status": "accepted",
  "chunk_id": 123,
  "message": "Audio chunk queued for processing",
  "elapsed_ms": 45.2
}
```

**Error (400 Bad Request)**:
```json
{
  "status": "error",
  "message": "Invalid metadata or file format"
}
```

**Error (409 Conflict)**:
```json
{
  "status": "error",
  "message": "Duplicate checksum detected"
}
```

#### Example (curl)

```bash
curl -X POST http://localhost:18083/api/v1/upload \
  -F "file=@microphone_2026-02-09_19-30-15.wav" \
  -F 'metadata={
    "type": "audio_chunk",
    "timestamp": 1707498600.123,
    "device_name": "microphone",
    "sample_rate": 16000,
    "channels": 1,
    "format": "wav",
    "checksum": "sha256:abc123..."
  }'
```

---

## 📊 音频 Chunks 查询 API

### GET `/api/v1/audio/chunks`

查询音频 chunks 列表（支持分页、时间范围过滤）。

#### Query Parameters

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `limit` | int | ❌ | 20 | 返回数量 |
| `offset` | int | ❌ | 0 | 偏移量 |
| `page` | int | ❌ | 1 | 页码（与 offset 二选一） |
| `page_size` | int | ❌ | 20 | 每页数量 |
| `start_time` | float | ❌ | - | 起始时间（Unix timestamp） |
| `end_time` | float | ❌ | - | 结束时间（Unix timestamp） |
| `device_name` | string | ❌ | - | 设备名称过滤 |
| `status` | string | ❌ | - | 状态过滤（`PENDING`/`COMPLETED`/`FAILED`） |

#### Response

```json
{
  "data": [
    {
      "id": 123,
      "file_path": "/Users/pyw/MRS/audio/sha256_abc123.wav",
      "timestamp": 1707498600.123,
      "device_name": "microphone",
      "created_at": "2026-02-09T19:30:00.123456Z",
      "expires_at": "2026-03-11T19:30:00.123456Z",
      "encrypted": 0,
      "checksum": "sha256:abc123...",
      "status": "COMPLETED"
    }
  ],
  "meta": {
    "total": 150,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

#### Example (curl)

```bash
# 查询最近 20 个 chunks
curl "http://localhost:18083/api/v1/audio/chunks?limit=20&offset=0"

# 按时间范围过滤
curl "http://localhost:18083/api/v1/audio/chunks?start_time=1707498600&end_time=1707502200"

# 按设备名称过滤
curl "http://localhost:18083/api/v1/audio/chunks?device_name=microphone"
```

---

## 📝 转写记录查询 API

### GET `/api/v1/audio/transcriptions`

查询音频转写记录（支持分页、时间范围过滤）。

#### Query Parameters

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `limit` | int | ❌ | 20 | 返回数量 |
| `offset` | int | ❌ | 0 | 偏移量 |
| `start_time` | float | ❌ | - | 起始时间（Unix timestamp） |
| `end_time` | float | ❌ | - | 结束时间（Unix timestamp） |
| `device` | string | ❌ | - | 设备名称过滤 |
| `speaker_id` | int | ❌ | - | 说话人 ID 过滤（Phase 2.1） |

#### Response

```json
{
  "data": [
    {
      "id": 456,
      "audio_chunk_id": 123,
      "offset_index": 0,
      "timestamp": 1707498610.5,
      "transcription": "Hello, this is a test recording.",
      "transcription_engine": "faster-whisper:base",
      "speaker_id": null,
      "start_time": 1707498610.0,
      "end_time": 1707498612.5,
      "text_length": 33,
      "device": "microphone",
      "created_at": "2026-02-09T19:30:15.123456Z"
    }
  ],
  "meta": {
    "total": 500,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

#### Example (curl)

```bash
# 查询最近转写记录
curl "http://localhost:18083/api/v1/audio/transcriptions?limit=20"

# 按时间范围查询
curl "http://localhost:18083/api/v1/audio/transcriptions?start_time=1707498600&end_time=1707502200"
```

---

## 🔍 全文检索 API

### GET `/api/v1/search`

全文检索（支持视频 OCR + 音频转写）。

#### Query Parameters

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `q` | string | ✅ | - | 搜索关键词 |
| `limit` | int | ❌ | 20 | 返回数量 |
| `offset` | int | ❌ | 0 | 偏移量 |
| `content_type` | string | ❌ | `all` | 内容类型（`vision`/`audio`/`all`） |
| `start_time` | float | ❌ | - | 起始时间过滤 |
| `end_time` | float | ❌ | - | 结束时间过滤 |

#### Response

```json
{
  "data": [
    {
      "type": "audio_transcription",
      "id": 456,
      "timestamp": 1707498610.5,
      "transcription": "Hello, this is a test recording.",
      "text_snippet": "...this is a test recording...",
      "device": "microphone",
      "speaker_id": null,
      "rank": -0.234
    },
    {
      "type": "video_frame",
      "id": 789,
      "timestamp": 1707498620.0,
      "ocr_text": "Test document with important notes",
      "text_snippet": "...important notes...",
      "app_name": "Notes.app",
      "window_name": "Untitled",
      "rank": -0.567
    }
  ],
  "meta": {
    "total": 50,
    "limit": 20,
    "offset": 0
  }
}
```

#### Example (curl)

```bash
# 全文检索
curl "http://localhost:18083/api/v1/search?q=test&limit=20"

# 仅检索音频
curl "http://localhost:18083/api/v1/search?q=meeting&content_type=audio"

# 时间范围 + 关键词
curl "http://localhost:18083/api/v1/search?q=project&start_time=1707498600&end_time=1707502200"
```

---

## ⏱️ Timeline API

### GET `/api/v1/timeline`

获取时间线数据（视频帧 + 音频转写，按时间排序）。

#### Query Parameters

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `start_time` | float | ✅ | - | 起始时间（Unix timestamp） |
| `end_time` | float | ✅ | - | 结束时间（Unix timestamp） |
| `limit` | int | ❌ | 100 | 返回数量 |
| `offset` | int | ❌ | 0 | 偏移量 |

#### Response

```json
{
  "data": [
    {
      "type": "video_frame",
      "timestamp": 1707498605.0,
      "frame_id": 789,
      "frame_url": "/api/v1/frames/789",
      "app_name": "Chrome",
      "window_name": "Google Search",
      "ocr_text": "search results..."
    },
    {
      "type": "audio_transcription",
      "timestamp": 1707498610.5,
      "transcription_id": 456,
      "transcription": "Let me search for that",
      "device": "microphone",
      "start_time": 1707498610.0,
      "end_time": 1707498612.5
    }
  ],
  "meta": {
    "start_time": 1707498600.0,
    "end_time": 1707502200.0,
    "total": 250,
    "limit": 100
  }
}
```

#### Example (curl)

```bash
# 获取 1 小时时间线
curl "http://localhost:18083/api/v1/timeline?start_time=1707498600&end_time=1707502200&limit=100"
```

---

## 📈 队列状态 API

### GET `/api/v1/queue/status`

查看音频/视频处理队列状态。

#### Response

```json
{
  "video_queue": {
    "pending": 5,
    "processing": 2,
    "completed": 123,
    "failed": 1
  },
  "audio_queue": {
    "pending": 8,
    "processing": 1,
    "completed": 250,
    "failed": 0
  },
  "timestamp": "2026-02-09T19:45:30.123456Z"
}
```

#### Example (curl)

```bash
curl "http://localhost:18083/api/v1/queue/status"
```

---

## 🔐 认证（Phase 5+）

**当前状态（Phase 2.0）**：认证占位符，所有请求无需 token。

**未来实现（Phase 5）**：
```http
Authorization: Bearer {api_key}
```

---

## ⚠️ 错误代码

| 状态码 | 说明 | 示例 |
|--------|------|------|
| 200 | 成功 | 查询成功 |
| 202 | 已接受（异步处理） | 上传成功，排队处理中 |
| 400 | 请求错误 | 缺少必填字段、格式错误 |
| 404 | 未找到 | Chunk ID 不存在 |
| 409 | 冲突 | 重复上传（checksum 已存在） |
| 500 | 服务器错误 | 内部错误 |

---

## 📚 相关文档

- [Audio Pipeline 概览](./01-audio-pipeline-overview.md)
- [Audio 配置说明](./03-audio-configuration.md)（待创建）
- [Phase 2.0 验证报告](../results/phase-2-validation.md)
