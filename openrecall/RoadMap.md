# MyRecall 开发路线图 (Development Roadmap)

> **项目目标**: 将 OpenRecall 重构为 **MyRecall** —— 一个隐私优先、端边云分离 (Client-Edge-Cloud)、具备多模态 AI 理解能力的个人数字记忆系统。
> **开发策略**: 原地重构，逐步异构 (In-Place Refactoring -> Gradual Heterogeneity)。先在单机完成架构拆分，最后迁移至物理硬件。

---

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