# OpenRecall 深度解析指南（架构视角）

> 适用对象：需要快速接手、重构、扩展 OpenRecall 的开发者/架构师。
>
> 目标：从“入口/模块职责/核心算法/数据契约/工作流”把项目讲透，帮助你在最短时间内做出正确改动。

---

## 1. 项目全景（关键文件与核心功能）

### 1.1 顶层工程文件

- `README.md`
  - 项目定位、安装与运行方式：`python3 -m openrecall.app`
  - CLI 参数：`--storage-path`、`--primary-monitor-only`
- `setup.py`
  - 依赖声明（Flask、mss、sentence-transformers、torch、Pillow 等）
  - OS-specific extras：Windows/macOS/Linux
  - OCR 依赖：`python-doctr` 以 Git 依赖形式安装（固定 commit）
- `docs/`
  - `encryption.md`：加密卷存储指引
  - `hardware.md`：硬件要求/兼容性
- `tests/`
  - `test_config.py`：验证跨平台 appdata 路径逻辑
  - `test_database.py`：验证 SQLite 建表、插入、去重与查询
  - `test_nlp.py`：验证 cosine 相似度（当前与实现存在预期不一致，见后文）

### 1.2 核心包目录：`openrecall/`

- `openrecall/app.py`：Web UI（Flask）+ 搜索/时间轴路由 + 启动后台录制线程
- `openrecall/config.py`：CLI 参数解析 + 数据目录/路径（db、截图、模型缓存）
- `openrecall/screenshot.py`：截图采集、相似度去重、保存图片、OCR、Embedding、写库
- `openrecall/ocr.py`：Doctr OCR predictor 初始化与文字抽取
- `openrecall/nlp.py`：SentenceTransformer embedding + 余弦相似度
- `openrecall/database.py`：SQLite schema、插入、查询；embedding blob 序列化/反序列化
- `openrecall/utils.py`：跨平台获取前台应用/窗口标题、用户活跃检测、时间格式化

---

## 2. 技术栈与方法论（库、算法、模式）

### 2.1 技术栈（按层拆解）

- 语言：Python
- Web：Flask（`openrecall/app.py`，使用 `render_template_string` + 内嵌模板）
- 截图：`mss`（`openrecall/screenshot.py`）
- 图像处理：Pillow（保存 WebP、缩放）
- OCR：`python-doctr`（`openrecall/ocr.py`，`ocr_predictor`）
- Embedding：`sentence-transformers`（`openrecall/nlp.py`，默认 `all-MiniLM-L6-v2`）
- 数值计算：NumPy（向量计算、序列化/反序列化）
- 存储：SQLite（`sqlite3` 标准库，`openrecall/database.py`）
- OS 集成：
  - macOS：pyobjc（AppKit/Quartz）+ `ioreg`
  - Windows：pywin32 + psutil
  - Linux：`xprop`、`xprintidle`（subprocess 调用）

### 2.2 方法论/结构模式

- **Pipeline（流水线）**：截图 → 去重 → OCR → Embedding → SQLite → Web 检索与展示
- **Producer/Consumer**：后台线程持续写入（Producer），Flask 路由查询展示（Consumer）
- **缓存/单例**：
  - `nlp.py` 模块级加载 SentenceTransformer 模型（避免每次调用重新加载）
  - `ocr.py` 模块级创建 Doctr predictor

### 2.3 核心算法

- **近似重复帧过滤**：MSSIM（Mean Structural Similarity Index）
  - 先缩放降低计算量，再做全局统计版 SSIM
- **语义检索相似度**：余弦相似度（cosine similarity）

---

## 3. 深度代码实现（逐模块讲透实现逻辑）

> 说明：此处描述以“当前仓库代码行为”为准；同时会标注关键的契约不一致/潜在缺陷，便于你后续修复。

### 3.1 配置与路径：`openrecall/config.py`

**职责**
- 使用 `argparse` 在模块导入时解析 CLI 参数：
  - `--storage-path`：自定义数据存储目录
  - `--primary-monitor-only`：仅录制主屏
- 计算/创建：
  - `appdata_folder`
  - `screenshots_path`
  - `db_path`（`recall.db`）
  - `model_cache_path`（`sentence_transformers/`）

**实现要点**
- `get_appdata_folder(app_name='openrecall')` 根据 `sys.platform` 返回默认数据目录并 `os.makedirs`。

**重要风险（数据目录契约）**
- 当传入 `--storage-path` 时，当前代码只设置 `appdata_folder = args.storage_path`，但 **没有设置 `screenshots_path`**。
- 随后代码会执行 `for d in [screenshots_path, model_cache_path]: ...`，这会导致 `screenshots_path` 未定义的运行时错误。

> 结论：如果你要让 `--storage-path` 正常工作，需要统一初始化 `screenshots_path` 与目录创建逻辑。

---

### 3.2 截图与入库主循环：`openrecall/screenshot.py`

**职责**
- 多显示器截图（可选只录主屏）
- 用户活跃检测：空闲时跳过
- 相似度去重：过滤“变化很小”的帧
- 保存 WebP 截图到 `screenshots_path`
- OCR 抽取文本，生成 embedding，写入 SQLite

#### 3.2.1 `take_screenshots()`
- 使用 `mss.mss()` 获取 `sct.monitors`
- 约定：
  - `sct.monitors[0]` 是“所有屏幕拼接视图”
  - `sct.monitors[1]` 是主屏
- `--primary-monitor-only` 为真时只抓取 index=1
- `sct.grab(monitor_info)` 输出 BGRA，转换为 RGB：`np.array(sct_img)[:, :, [2, 1, 0]]`

#### 3.2.2 `mean_structured_similarity_index(img1, img2)`
- 将 RGB 转灰度（线性加权）
- 计算均值、方差、协方差
- 代入全局统计版本 SSIM：返回 [-1, 1] 的相似度

#### 3.2.3 `is_similar(img1, img2, similarity_threshold=0.9)`
- 先 `resize_image()`（Pillow `thumbnail`）压缩图像
- 再计算 MSSIM，阈值默认 0.9

#### 3.2.4 `record_screenshots_thread()`（后台线程）
- 循环：
  1) `is_user_active()` 判断活跃；不活跃 sleep
  2) `take_screenshots()`
  3) 与 `last_screenshots` 做相似度比较
  4) 变化明显则保存图片、OCR、embedding、写库

**重要风险（函数重复定义导致行为混乱）**
- 文件中出现 **两次同名 `record_screenshots_thread` 定义**，后者覆盖前者（Python 以最后定义为准）。
- 前一个版本会保存为 `{timestamp}_{monitorIndex}.webp`，后一个版本保存为 `{timestamp}.webp`。
- 前一个版本末尾出现 `return screenshots`，但该函数按设计是无限循环线程函数，该 `return` 语义不合理且变量来源不清晰。

> 结论：目前实际运行行为由“第二个定义”决定。建议删除重复定义并固化截图命名契约。

---

### 3.3 OCR：`openrecall/ocr.py`

**职责**
- 初始化 Doctr OCR predictor：`ocr_predictor(pretrained=True, det_arch=..., reco_arch=...)`
- 对输入图像进行 OCR，并把 `words` 拼接为文本

**实现逻辑**
- `extract_text_from_image(image)`：
  - 调用 `result = ocr([image])`
  - 遍历 `pages → blocks → lines → words`，把 `word.value` 拼接
  - 以空格与换行分隔

**工程化注意点**
- predictor 在模块导入时初始化：冷启动慢、依赖问题会影响整个应用导入。
- 输入 `image` 目前直接传入 `np.ndarray`，实际可用性依赖 doctr 对 numpy 输入的支持。

---

### 3.4 Embedding 与相似度：`openrecall/nlp.py`

**职责**
- 加载/缓存 SentenceTransformer（默认 `all-MiniLM-L6-v2`）
- 提供 `get_embedding(text)` 与 `cosine_similarity(a, b)`

**实现逻辑**
- `get_model(model_name)`：
  - `cache_path = os.path.join(model_cache_path, model_name)`
  - 若目录存在：从本地目录加载
  - 否则：下载模型并 `model.save(cache_path)`
- 模块级 `model = get_model(...)`：避免重复加载
- `get_embedding(text)`：
  - 若 model 加载失败或输入为空：返回 384 维 float32 零向量
  - 按行 split 并过滤空行后编码：`model.encode(sentences)`
  - 对行向量做均值聚合：`np.mean(..., axis=0)`
- `cosine_similarity(a, b)`：
  - 若任一向量范数为 0：返回 `0.0`
  - 否则返回点积/范数积并 clip 到 [-1, 1]

**测试契约不一致**
- `tests/test_nlp.py` 期望当任一向量为零向量时结果为 NaN；但当前实现返回 `0.0`。

> 结论：需要你明确“零向量”的产品语义：0（不相似）、NaN（无效）、或跳过该条。

---

### 3.5 数据库：`openrecall/database.py`

**职责**
- SQLite 表结构初始化与索引
- 插入条目（timestamp 唯一去重）
- 查询条目、时间戳
- embedding 以 BLOB 方式存储

**表结构**
- `entries(id, app, title, text, timestamp UNIQUE, embedding BLOB)`
- `idx_timestamp` 索引

**写入：`insert_entry(text, timestamp, embedding, app, title)`**
- `embedding.astype(np.float32).tobytes()` 序列化
- `ON CONFLICT(timestamp) DO NOTHING` 去重

**读取：`get_all_entries()`**
- 使用 `sqlite3.Row` row_factory
- embedding 用 `np.frombuffer(..., dtype=np.float32)` 反序列化
- 返回 `Entry(namedtuple)`，其中 `embedding` 为 `np.ndarray`

**重要风险（查询返回类型不一致）**
- `get_entries_by_time_range(start_time, end_time)` 直接 `SELECT *` 并 `Entry(*result)`，**没有**反序列化 embedding。
- 这导致：
  - `get_all_entries()` 返回 `Entry.embedding: np.ndarray`
  - `get_entries_by_time_range()` 返回 `Entry.embedding: bytes/blob`

> 结论：数据库查询层应统一输出契约（推荐：永远返回 `np.ndarray`），避免上层重复 `frombuffer` 或类型错配。

---

### 3.6 Web UI 与搜索：`openrecall/app.py`

**职责**
- 路由：
  - `/`：时间轴 slider 浏览历史
  - `/search`：按 query 语义相似度排序展示
  - `/static/<filename>`：从 `screenshots_path` 提供截图文件
- 启动后台线程 `record_screenshots_thread()` 持续写库

#### 3.6.1 模板组织
- `base_template` 以字符串内嵌
- 自定义 `StringLoader(BaseLoader)` 给 Jinja 提供 `base_template`

#### 3.6.2 时间轴 `/`
- `timestamps = get_timestamps()`（按 timestamp DESC）
- 前端 slider 使用 `reversedIndex = timestamps.length - 1 - slider.value` 把 slider 值映射到倒序数组
- 通过 `/static/${timestamp}.webp` 加载截图

#### 3.6.3 搜索 `/search`
- 若提供 `start_time`/`end_time`：调用 `get_entries_by_time_range`
- 否则调用 `get_all_entries`
- 计算：
  - `query_embedding = get_embedding(q)`
  - 对每条 entry 的 embedding 与 query embedding 做 `cosine_similarity`
  - `np.argsort(similarities)[::-1]` 排序

**重要风险（多处契约不一致会导致运行时错误）**
1) embedding 二次反序列化风险
- `search()` 中固定做：`np.frombuffer(entry.embedding, dtype=np.float32)`
- 但 `get_all_entries()` 已经返回 `np.ndarray`，再 `frombuffer` 会产生类型/语义问题。

2) 模板中对 `Entry` 的访问方式可能错误
- 模板中使用 `entry['timestamp']`（字典式访问）
- 但数据库返回的是 `Entry(namedtuple)`，更可靠的方式应是 `entry.timestamp`。

3) 截图文件命名契约
- UI 默认请求 `/static/<timestamp>.webp`
- 若截图保存逻辑采用 `{timestamp}_{i}.webp`，则 UI 将无法找到图片。

---

## 4. 工作流与数据流（模块交互）

### 4.1 端到端工作流（从屏幕到检索）

1) **启动**
- `python -m openrecall.app`
- `create_db()` 初始化 SQLite
- 创建后台线程运行 `record_screenshots_thread()`
- 启动 Flask Web 服务（默认端口 8082）

2) **后台采集（Producer）**
- 每 3 秒循环：
  - `is_user_active()` 为 False：跳过
  - `take_screenshots()` 抓取屏幕图像
  - 与上次截图比较 `is_similar()`：相似则跳过
  - 保存截图到 `screenshots_path`
  - OCR：`extract_text_from_image()`
  - embedding：`get_embedding()`
  - 写库：`insert_entry(text, timestamp, embedding, app, title)`

3) **Web 查询（Consumer）**
- 时间轴 `/`：读取 `timestamps` 并按时间浏览图片
- 搜索 `/search`：读取 entries → 向量化 query → 余弦相似度排序 → 渲染结果

### 4.2 数据契约（建议你显式固化）

- **截图命名契约**：UI 以 `{timestamp}.webp` 作为静态资源键
- **Entry.embedding 类型契约**：建议查询层统一输出 `np.ndarray(float32, dim=384)`
- **零向量相似度契约**：0/NaN/过滤（需要和测试/产品期望一致）

---

## 5. 架构债与优先级建议（可选）

如果你准备进入“稳定可用 + 可维护”的状态，建议优先处理：

1) `config.py`：修复 `--storage-path` 分支未初始化 `screenshots_path` 的问题（否则自定义目录直接崩）
2) `screenshot.py`：去掉重复的 `record_screenshots_thread` 定义，并统一截图命名策略与 UI 契约
3) `database.py`：统一 `get_all_entries` 与 `get_entries_by_time_range` 的 embedding 返回类型
4) `app.py`：模板改为 `entry.timestamp` 访问；并避免对已经是 `np.ndarray` 的 embedding 再 `frombuffer`
5) `nlp.py` vs `tests/test_nlp.py`：统一零向量相似度行为（返回 NaN / 0 / 跳过）

---

## 6. 快速定位（按你要改什么）

- 想改“录制策略/去重阈值/频率”：`openrecall/screenshot.py`
- 想改“存储结构/索引/查询性能”：`openrecall/database.py`
- 想改“检索排序/embedding 策略”：`openrecall/nlp.py` + `openrecall/app.py`
- 想改“OCR 模型/抽取效果”：`openrecall/ocr.py`
- 想改“UI/交互”：`openrecall/app.py`（模板内嵌）
- 想改“跨平台活动窗口/空闲检测”：`openrecall/utils.py`
