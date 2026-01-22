# Qwen3‑VL Recall MVP 架构图（服务级）

> 面向 **Apple Recall / Windows Recall 同级能力** 的 **最小可落地架构（MVP）**，
> 覆盖截图采集 → 索引构建 → 多路召回 → Rerank → 解释的完整闭环。

---

## 一、总体架构总览（Service-Level）

```text
┌────────────────────────────────────────────┐
│              Client / OS Agent              │
│  Screenshot Capture · Foreground App · Time │
└───────────────┬────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────┐
│        Snapshot Ingestion Service           │
│  - Screenshot buffer                        │
│  - Time / App / Window metadata             │
└───────────────┬────────────────────────────┘
                │
        ┌───────┴─────────┐
        ▼                 ▼
┌──────────────┐   ┌────────────────────┐
│  OCR Service │   │  VLM Scene Analyzer │
│  (Text/Code) │   │  (Action / Scene)  │
└───────┬──────┘   └──────────┬─────────┘
        │                     │
        └──────────┬──────────┘
                   ▼
┌────────────────────────────────────────────┐
│   Semantic Snapshot Builder (Schema Layer) │
│  - OCR keywords                             │
│  - Activity label                           │
│  - Structured embedding input               │
└───────────────┬────────────────────────────┘
                │
        ┌───────┴───────────┐
        ▼                   ▼
┌───────────────────┐   ┌──────────────────┐
│ Qwen3‑VL‑Embedding│   │  Metadata Store  │
│  (Image/Text)     │   │  Time/App/Tags   │
└───────┬───────────┘   └─────────┬────────┘
        │                         │
        ▼                         ▼
┌────────────────────────────────────────────┐
│        Vector Index (FAISS / HNSW)          │
│        + OCR Inverted Index (BM25)          │
└────────────────────────────────────────────┘

─────────────────────  QUERY PATH  ─────────────────────

┌────────────────────────────────────────────┐
│            Query API / Recall API           │
│  Natural Language Memory Query              │
└───────────────┬────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────┐
│            Query Parsing Service            │
│  - Time parsing                             │
│  - Action / Object extraction               │
└───────────────┬────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────┐
│       Qwen3‑VL‑Embedding (Query)            │
└───────────────┬────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────┐
│        Multi‑Channel Recall Service         │
│  - Vector ANN Top‑K                         │
│  - Time / App filter                        │
│  - OCR keyword match                        │
└───────────────┬────────────────────────────┘
                │  (Top 500–1000)
                ▼
┌────────────────────────────────────────────┐
│       Qwen3‑VL‑Reranking Service            │
│  - Query + Image + OCR hints                │
└───────────────┬────────────────────────────┘
                │  (Top 20–50)
                ▼
┌────────────────────────────────────────────┐
│      Result API / Timeline UI Layer         │
│  Ranked Screenshots                         │
└───────────────┬────────────────────────────┘
                │ (on demand)
                ▼
┌────────────────────────────────────────────┐
│         Explanation VLM Service             │
│  "Why this matches your memory"            │
└────────────────────────────────────────────┘
```

---

## 二、核心服务拆解说明

### 1️⃣ Snapshot Ingestion Service
- 职责：
  - 接收 OS / Agent 截图
  - 记录 **时间、前台 App、窗口标题**
- 特点：
  - 纯 IO + metadata
  - 不做模型推理

---

### 2️⃣ OCR Service（强先验）
- 专注：
  - 屏幕文本、代码、日志
- 输出：
  - full_text（存档）
  - keywords（Recall 用）
- 备注：
  - 可替换为多模型 ensemble（中文 / code）

---

### 3️⃣ VLM Scene Analyzer（轻量）
- 功能：
  - 判断「在干什么」而不是「是什么」
- 输出示例：
  ```json
  {
    "activity": "debugging_code",
    "confidence": 0.91
  }
  ```

---

### 4️⃣ Semantic Snapshot Builder（关键中枢）
- 系统核心，而非模型
- 职责：
  - 组装 schema‑aware embedding 输入
  - 限制 OCR / Code token 占比
  - 写入统一 Snapshot 结构

> **Apple Recall 的本质不是模型，而是这一层。**

---

### 5️⃣ Vector Index + Metadata Store
- 向量库：FAISS / HNSW
- 元数据：
  - 时间轴
  - App / Activity
  - OCR 倒排索引

---

### 6️⃣ Multi‑Channel Recall Service
- 并行召回：
  - ANN（语义兜底）
  - 时间 / App 过滤（主路径）
  - OCR 精确匹配（高 precision）

---

### 7️⃣ Qwen3‑VL‑Reranking Service
- 真正做“判断”的地方
- 输入：Query × Image × Evidence
- 输出：相关性分数

---

### 8️⃣ Explanation VLM Service（可选）
- Explain‑on‑Demand
- 用户点击 / hover 才触发
- 输出：证据式自然语言解释

---

## 三、MVP 落地最小化建议

### MVP‑1（2 周）
- Screenshot → OCR → Embedding
- FAISS Top‑500
- 时间过滤

### MVP‑2（+1 周）
- Qwen3‑VL‑Reranking Top‑200
- 排序融合

### MVP‑3（可选）
- Explanation VLM
- Timeline UI

---

## 四、一句话总结

> **这是一个“模型被驯化在系统之中”的 Recall 架构，而不是一个模型驱动的 Demo。**

如果你愿意，下一步我可以：
- 把这张架构图压缩成 **单机 MVP**
- 或扩展成 **分布式 / 端侧 + 云协同版本**
- 或直接帮你写 **模块级接口定义（API / protobuf）**

