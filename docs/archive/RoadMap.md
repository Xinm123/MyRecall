# MyRecall 开发路线图 (Development Roadmap)

> **项目目标**: 将 OpenRecall 重构为 **MyRecall** —— 一个隐私优先、端边云分离 (Client-Edge-Cloud)、具备多模态 AI 理解能力的个人数字记忆系统。
> **开发策略**: 原地重构，逐步异构 (In-Place Refactoring -> Gradual Heterogeneity)。先在单机完成架构拆分，最后迁移至物理硬件。

---

## 🧭 v3 治理补充：Phase 2.6（音频硬冻结治理）

> 本节是对 v3 现行里程碑治理的补充说明。它不改变本归档文档的历史演进叙事，只解释为何在 Phase 2.5 与 Phase 2.7 之间新增独立治理阶段。

### 为什么 Phase 2.6 必须独立存在

* **职责解耦**：将“冻结治理动作”与“标签对齐实现动作”分离，避免 Phase 2.7 失败时无法归因（治理失败 vs 实现失败）。
* **审计闭环**：冻结状态必须具备证据包（稳定性、性能预算、回滚演练、配置漂移审计），不能只停留在文字声明。
* **例外可控**：给 P0/P1 修复提供明确审批通道，防止“为了修 bug 破坏冻结边界”。
* **与 screenpipe 原则对齐**：对齐其质量门禁、回滚与 soak 验证哲学，但保留 MyRecall 的 phase-gate 管理结构，不强行同构。

### v3 执行顺序图（治理后）

```mermaid
flowchart LR
    P25["Phase 2.5: WebUI Dashboards"] --> P26["Phase 2.6: Audio Freeze Governance"]
    P26 -->|"all 2.6-G-* PASS"| P27["Phase 2.7: Frame Label Alignment Gate"]
    P27 -->|"GO"| P3["Phase 3: Vision Search Parity"]
    P3 --> P4["Phase 4: Vision Chat MVP"]
    P4 --> P5["Phase 5: Deployment Migration"]
```

## 🟢 第一部分：基础夯实与架构解耦 (Foundation & Decoupling)
**目标**：修复原版工程缺陷，建立强类型契约，并将单体架构拆分为可通过 HTTP 通信的 CS 架构。

### Phase 1: 基础设施重构 (Infrastructure Hardening)
* **核心目标**: 引入工程化配置管理，修复“路径未自动创建”的严重 Bug，确立独立的数据存储空间。
* **预期变动**:
    * 引入 `pydantic-settings` 替换 `argparse`。
    * 重写 `openrecall/config.py`。
    * 将默认存储路径迁移至 `~/.myrecall_data` 以实现数据隔离。
* **验证方案**: 单元测试验证 `Settings` 初始化时，磁盘上是否自动生成了 `screenshots/`, `db/`, `buffer/` 等目录。

### Phase 2: 数据库强类型化 (Strict Database Layer)
* **核心目标**: 消除 SQLite 查询返回类型不一致（Blob vs Array）的混乱，为 API 传输打好数据基础。
* **预期变动**:
    * 修改 `openrecall/database.py`。
    * 定义 `RecallEntry` Pydantic 模型。
    * 强制所有查询接口在返回前将 Embedding 反序列化为 `List[float]` 或 `np.ndarray`。
* **验证方案**: 编写测试用例，写入随机向量，读取后断言其类型不再是 `bytes`。

### Phase 3: 逻辑物理分离 (Physical Separation)
* **核心目标**: 在文件系统层面分离“采集”与“计算”代码，消除循环引用。
* **预期变动**:
    * 重组目录结构，创建 `openrecall/client/` (采集), `openrecall/server/` (计算), `openrecall/shared/` (公共)。
    * 移动 `screenshot.py` 到 `client/`，移动 `nlp.py`, `ocr.py` 到 `server/`。
    * 修复所有的 Import 路径。
* **验证方案**: 系统在新的目录结构下，依然可以通过 `python -m openrecall.app` 正常启动并录制。

### Phase 4: API 接口化 (API Implementation)
* **核心目标**: **关键里程碑**。切断 Client 对 Server 的直接函数调用，转为 HTTP 通信。
* **预期变动**:
    * **Server**: 引入 FastAPI (或扩展 Flask)，新增 `/api/upload` 和 `/api/health` 接口。
    * **Client**: 编写 `HTTPUploader` 类，替代原有的 `database.insert_entry()` 调用。
* **验证方案**: 启动 Server，运行独立的 Client 脚本发送模拟数据，检查 Server 数据库是否成功入库。

---

## 🔵 第二部分：智能升级与传输优化 (Intelligence & Link)
**目标**：增强系统的“智商”，并确保数据传输的鲁棒性。

### Phase 5: 采集端缓冲机制 (Client Buffering)
* **核心目标**: 赋予 Client “断网生存能力”。当 API 不可达时，数据不丢失。
* **预期变动**:
    * 在 Client 端实现 `LocalBuffer` 队列系统。
    * 逻辑：截图 -> 存本地 -> 后台线程尝试上传 -> 成功则删 / 失败则保留重试。
* **验证方案**: 关闭 Server，运行 Client 录制 1 分钟（数据积压）；启动 Server，观察 Client 是否自动上传并清空积压数据。

### Phase 6: 多模态大脑植入 (MLLM Integration)
* **核心目标**: 集成轻量级多模态大模型（如 Moondream2），实现对画面的语义理解。
* **预期变动**:
    * Server 端新增 `ai_engine.py`。
    * 修改数据库 Schema，增加 `description` (TEXT) 字段。
    * 重构处理流水线：并行执行 OCR + MLLM 推理 -> 融合生成 Embedding。
* **验证方案**: 传入一张无文字的图片（如“猫”），验证数据库中是否生成了包含 "A cat is..." 的文本描述。

---


### Phase 5: 采集端缓冲机制 (Client Buffering)

#### 1. 核心目标 (Core Objectives)
* **解耦采集与上传**：确保采集线程（Capture Thread）不会因为网络波动或服务器响应慢而被阻塞，保证录制的流畅性。
* **断网生存 (Offline Survival)**：在客户端网络断开或 Server 不可达的情况下，数据暂时留存在本地，确保数据零丢失 (Zero Data Loss)。
* **自动恢复**：一旦网络恢复，后台能够自动将积压的数据上传，无需用户人工干预。

#### 2. 预期变动 (Expected Changes)

* **架构调整**：引入 `LocalBuffer` 模块，构建**生产者-消费者 (Producer-Consumer)** 模型。
* *生产者 (采集线程)*：负责截图/采集数据。只负责将数据写入 LocalBuffer，不负责网络传输。此过程必须极快且非阻塞。
* *缓冲区 (LocalBuffer Queue)*：一个持久化的队列（不仅仅是内存队列），用于存储待上传的数据包。
* *消费者 (上传线程)*：独立的后台线程，负责从 LocalBuffer 读取数据，调用 API 上传，并处理回执。

* **数据流转逻辑**：
* **入队**：截图 -> 存入本地磁盘队列。
* **出队与确认**：读取数据 -> 上传 Server -> **仅当收到 Server `200 OK` 确认后**，才物理删除本地文件。
* **重试机制**：若上传失败（网络错或 5xx），**保留本地文件**，休眠片刻后（退避策略）自动重试。


## 3. 关键技术点 (Key Engineering Points)
* **线程安全 (Thread Safety)**：确保采集线程的“写”和上传线程的“读/删”操作是互斥的，避免数据竞争。
* **应用退出保护**：如果在上传过程中 App 被关闭，下次启动 App 时，`Uploader Thread` 必须先扫描本地持久化队列，优先上传上次未完成的数据（这也是为什么必须用持久化存储的原因）。
* **批量上传 (Batching - 可选优化)**：如果单张截图上传效率低，消费者可以一次从队列取出 N 张（如 5 张）打包上传，减少 HTTP 请求开销。


#### 4. 验证方案 (Verification Plan)

* **Case 1: 弱网/抖动 (Weak Network)**
* **操作**：在上传过程中，使用工具（如 Clumsy 或 Charles）模拟 50% 丢包或高延迟。
* **预期**：采集画面不卡顿；数据最终能全部上传成功；Client 日志中出现“Retry”记录。


* **Case 2: 断网积压 (Offline Accumulation)**
* **操作**：1. 关闭 Server 或断开 Client 网络；2. Client 继续运行录制 1 分钟。
* **预期**：1. Client 不应报错崩溃；2. 本地存储（文件夹或DB）大小增加；3. LocalBuffer 队列计数增加。


* **Case 3: 断点续传 (Recovery)**
* **操作**：接上 Case 2，恢复 Server 或网络；观察 Client 行为。
* **预期**：1. Client 自动检测到网络恢复；2. 本地积压文件开始快速减少（被消费）；3. Server 端收到积压的旧数据（时间戳为 1 分钟前的）。


* **Case 4: 进程重启 (Process Restart)**
* **操作**：1. 断网录制，积压 100 条数据；2. **强杀 Client 进程**；3. 恢复网络，重启 Client。
* **预期**：1. Client 启动后自动扫描到 100 条遗留数据；2. 自动开始上传，直到队列清空。


* **Case 5: 磁盘满载 (Disk Full)**
* **操作**：模拟本地磁盘满或达到 Buffer 设定上限。
* **预期**：Client 触发保护机制（如停止录制或覆盖旧数据），且不会导致 App 崩溃。


---

## 🟠 第三部分：体验优化与部署 (UI & Deployment)
**目标**：提升用户交互体验，并完成最终的硬件部署。

### Phase 7: UI 现代化与适配 (UI Revamp)
* **核心目标**: 适配新的数据模型，展示 AI 生成的描述，修复原版内嵌模板的代码异味。
* **预期变动**:
    * 将 HTML 从 Python 代码中剥离，存为独立的 `.html` 模板文件。
    * 前端增加“AI 洞察”展示区域。
* **验证方案**: 浏览器访问 Web 界面，检查时间轴和详情页是否美观且包含 AI 描述。

### Phase 8: 混合搜索实现 (Hybrid Search)
* **核心目标**: 结合 OCR（精确匹配）和 MLLM（语义匹配）提升搜索召回率。
* **预期变动**:
    * 重写 Server 端的 `/search` 逻辑。
    * 实现 Rerank 策略：综合关键词匹配分和向量相似度分。
* **验证方案**: 搜索屏幕上不存在的抽象概念（如“代码报错”、“很多窗口”），验证系统能否召回相关截图。

### Phase 9: 硬件部署 (Physical Deployment)
* **核心目标**: **最终形态**。将 Server 部署至 Debian 计算盒子，Client 保留于 PC。
* **预期变动**:
    * 在 Debian 盒子上配置运行环境 (Python, PyTorch ARM版)。
    * 修改 PC 端 Config，将 `API_URL` 指向 Debian 盒子的局域网 IP。
* **验证方案**: PC 进行日常操作，Debian 盒子 CPU 负载上升（正在计算），通过浏览器访问 Debian IP 查看完整的记忆时间轴。

---

## 📊 开发原则 (Guidelines)

1.  **测试优先 (TDD)**: 每个阶段开始前，必须先编写或明确测试用例。
2.  **微步提交**: 每个 Phase 完成后，代码必须是可运行的（Green Build）。
3.  **开闭原则**: 尽量不修改已测试通过的复杂逻辑（如 SSIM 算法），而是通过封装来调用它。
