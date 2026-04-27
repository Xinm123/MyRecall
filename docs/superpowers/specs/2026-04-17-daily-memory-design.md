# Daily Memory 设计文档

> **Date:** 2026-04-17  
> **Status:** Draft  
> **Owner:** MyRecall Team

---

## 1. 目标

为每一天自动生成一个 Markdown 日记文件，按固定 1 小时整点对齐组织。基于 frame 的 AI description（含完整 narrative）进行 LLM 聚合润色，输出连贯的中文日记段落。

---

## 2. 核心设计原则

- **整点对齐**：所有 segment 固定为 1 小时，对齐到本地时间的整点（如 `09:00 - 10:00`）。
- **流式追加**：随着 frame 不断进入 Edge，定时任务逐步闭合 segment 并追加到 Markdown。
- **无状态恢复**：仅依赖 `checkpoints.yaml` 中的 `last_processed_end_time`，Server/Client 重启后可无缝续写。
- **本地时区为准**：Markdown 的日期、小时块均按用户本地时区显示；底层 checkpoint 仍存储 UTC。

---

## 3. 存储位置

```
~/.myrecall/server/daily_memories/YYYY-MM-DD.md
```

其中 `YYYY-MM-DD` 为**本地日期**。

---

## 4. Checkpoint 持久化

### 4.1 文件方案

采用独立的 YAML 文件存储所有日期的 checkpoint，避免为单行状态引入 SQLite migration 和锁竞争。

```
~/.myrecall/server/daily_memories/checkpoints.yaml
```

格式示例：

```yaml
2026-04-16: "2026-04-16T23:00:00Z"
2026-04-17: "2026-04-17T10:00:00Z"
```

- 键：本地日期（`YYYY-MM-DD`）。
- 值：该日 Markdown 文件最后追加到的时间块结束点，以 **UTC ISO8601** 存储。
- 写入策略：**原子写**（先写 `.tmp` 再 `replace`），防止进程崩溃导致文件损坏。
- 读取策略：启动时一次性加载到内存 dict；每次 segment 处理完成后原子重写 YAML。

---

## 5. Segment 切分算法

### 5.1 规则

1. **固定 1 小时，整点对齐**：segment 边界为本地时间的整点（`09:00 - 10:00`、`10:00 - 11:00`）。
2. **顺序推进**：从 `last_processed_end_time` 开始，每小时每小时地向前推进。
3. **触发条件**：只有当前时间 ≥ 该 segment 的结束时间（`segment_end`）时，才允许处理该 segment。
4. **重启恢复**：Server 重启后读取 checkpoint，依次补写尚未处理的 segment。Worker 每轮处理昨日和今日，支持隔夜恢复；停机超过 48 小时的历史日期不再自动补写。

### 5.2 算法流程

```python
def process_daily_memory(local_date: date):
    now_utc = datetime.now(timezone.utc)

    checkpoint = get_checkpoint(local_date)
    if checkpoint is None:
        start_time = local_date_start_utc(local_date)  # 00:00 local -> UTC
    else:
        start_time = parse_utc(checkpoint)

    # 必须等下一个完整小时结束才能开始处理
    if now_utc < start_time + timedelta(hours=1):
        return

    # 只处理属于 local_date 的 segment，不超过 local_date 的次日 00:00
    day_end_local = datetime.combine(local_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=local_tz())
    day_end_utc = local_to_utc(day_end_local)

    current_start = start_time
    while current_start + timedelta(hours=1) <= now_utc and current_start + timedelta(hours=1) <= day_end_utc:
        segment_end = current_start + timedelta(hours=1)

        frames = query_frames_with_description(
            start=current_start,
            end=segment_end,
            description_status='completed',
        )

        summary = generate_segment_summary(frames)
        append_to_md(local_date, current_start, segment_end, summary)
        update_checkpoint(local_date, segment_end)

        current_start = segment_end
```

### 5.3 重启场景示例

> 以下示例假设本地时区为 UTC，以便 checkpoint（UTC）与显示时间（本地）数值一致。实际运行时会按用户本地时区计算。

| 场景 | checkpoint | 当前时间 | 行为 |
|------|------------|----------|------|
| 正常隔夜 | `2026-04-17T18:00:00Z` | 次日 09:00 | 依次补写 `18:00-19:00` 到 `08:00-09:00` |
| 宕机 3 小时 | `2026-04-17T10:00:00Z` | 13:00 | 补写 `10:00-11:00`、`11:00-12:00`、`12:00-13:00` |
| 距离 1.5h | `2026-04-17T09:00:00Z` | 10:30 | 先写 `09:00-10:00`，`10:00-11:00` 未满，等待 |

---

## 6. 空 Segment / 无 Description Segment

| 情况 | 处理方式 | checkpoint |
|------|----------|------------|
| 空 segment（无 frame） | 写入占位块 `## HH:00 - HH+1:00\n\n无活动记录。` | **推进** |
| 有 frame 但全帧无 description | 不写内容，仅推进 checkpoint | **推进** |

---

## 7. LLM 聚合

### 7.1 Provider 设计

Daily Memory 使用**独立的 LLM 配置**，通过轻量级的 `DailyMemoryProvider` 直接调用 OpenAI-compatible Chat Completion API。

**配置项（TOML）：**

```toml
[daily_memory]
provider = "dashscope"   # 可选，缺失时 fallback 到 [description].provider，再缺失时 fallback 到 [ai].provider
model = "qwen-turbo"     # 可选，缺失时 fallback 到 [description].model，再缺失时 fallback 到 [ai].model_name
api_key = ""             # 可选，缺失时 fallback 到 [description].api_key，再缺失时 fallback 到 [ai].api_key
api_base = ""            # 可选，缺失时 fallback 到 [description].api_base，再缺失时 fallback 到 [ai].api_base
```

**实现：**
- 新建 `openrecall/server/daily_memory/provider.py`
- `get_daily_memory_provider()` 先读取 `daily_memory.*`，缺失字段依次 fallback 到 `description.*`，再缺失时 fallback 到 `ai.*` 的对应字段
- 由于现有的 `DescriptionProvider` 接口强制要求传入 `image_path`（用于截图分析），无法直接复用于纯文本聚合场景，因此 Daily Memory 使用独立的轻量级 `DailyMemoryProvider`，直接通过 HTTP 调用 OpenAI-compatible Chat Completion API

### 7.2 Prompt 输入

每个 segment 的 prompt 包含该时段内所有 `description_status='completed'` 的 frame，每帧格式：

```
[timestamp] app_name | summary | narrative | tags
```

**完整 Prompt 示例：**

```markdown
你是一位擅长整理用户数字生活日记的助手。请根据以下时间段内的屏幕截图描述，写一段简洁、连贯的日记总结。

日期：2026-04-17
时间段：10:00 - 11:00
总帧数：42

帧记录：
[10:02] Claude Code | 编辑 API 参考文档 | 正在调整 activity-summary 的 API 字段顺序，移除了 recent_texts 并将 summary 提到前面。 | tags: API, documentation, Claude Code
[10:05] Safari | 阅读 LanceDB 文档 | 正在查看 LanceDB 的 BM25 与向量搜索混合检索实现，重点关注与 FTS5 的对比。 | tags: LanceDB, vector search
...

要求：
- 用一段连贯的中文自然语言描述，150-300 字
- 突出主要活动（使用时间最长的应用）
- 提到应用切换和主题变化
- 按时间顺序叙述
- 不要列出每个帧的细节，进行适当的合并与概括
```

### 7.3 LLM 失败处理

- **不做 fallback**。
- LLM 调用失败时：**不写 Markdown、不推进 checkpoint**。
- 5 分钟后下次 Worker 运行时会**重试同一 segment**。

---

## 8. Worker 设计

- **新增模块**：`openrecall/server/daily_memory/worker.py`
- **类名**：`DailyMemoryWorker`
- **运行周期**：每 5 分钟执行一次 `process_daily_memory()`
- **启动方式**：Server 启动时自动初始化并作为后台线程运行
- **异常处理**：单次运行异常不中断线程，记录日志后等待下次周期

---

## 9. 时区处理

- **显示层**：Markdown 文件中的日期、segment 标题均使用**用户本地时区**。
- **存储层**：`checkpoints.yaml` 中的 `last_processed_end_time` 以 **UTC ISO8601** 存储。
- **查询转换**：Worker 先将本地时间块转换为 UTC 范围，再查询数据库中的 `frames.timestamp`。
- **时区获取**：MVP 阶段使用 Python `datetime.now().astimezone().tzinfo` 自动检测系统时区，不支持手动配置。

---

## 10. Markdown 文件格式

```markdown
# 2026-04-17

## 09:00 - 10:00

无活动记录。

## 10:00 - 11:00

上午 10 点到 11 点，你主要在 Claude Code 中推进 API 文档和模型设计。先是整理了 activity-summary 的字段结构，随后调整了 description provider 的接口。中途切换到 Safari 查阅了 LanceDB 的 BM25 与向量搜索资料。结束前在微信上简短讨论了字段命名。

## 11:00 - 12:00

...
```

---

## 11. 相关文件变更

### 11.1 新增文件

| 文件 | 说明 |
|------|------|
| `openrecall/server/daily_memory/__init__.py` | 包入口 |
| `openrecall/server/daily_memory/worker.py` | `DailyMemoryWorker` 实现 |
| `openrecall/server/daily_memory/provider.py` | `get_daily_memory_provider()` 及 fallback 逻辑 |
| `openrecall/server/daily_memory/service.py` | `DailyMemoryService`，负责切分、prompt 构建、文件追加、YAML checkpoint 管理 |
| `openrecall/server/daily_memory/prompts.py` | 中文 prompt 模板 |

### 11.2 修改文件

| 文件 | 说明 |
|------|------|
| `openrecall/server/app.py` | 启动 `DailyMemoryWorker` |
| `openrecall/server/config_server.py` | 新增 `[daily_memory]` 配置项解析、新增 `daily_memories_path` |

---

## 12. 边界情况清单

| 边界 | 预期行为 |
|------|----------|
| Server 重启 | 读取 checkpoint，补写昨日和今日未处理 segment（停机超过 48 小时的历史日期不自动补写） |
| 连续多天空 segment | 每个空小时均写"无活动记录。" |
| 全帧无 description | 不写 LLM 内容，仅推进 checkpoint |
| LLM 调用超时/失败 | 不写、不推进，5 分钟后重试 |
| 用户变更系统时区 | 新产生的 segment 按新时区显示，历史 md 不变 |
| 本地模型未加载 | `provider='local'` 在启动时直接报错，需切换为 API 模式（openai/dashscope） |
