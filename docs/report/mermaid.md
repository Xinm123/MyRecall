```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': 'Inter, system-ui', 'fontSize': '14px' }}}%%
flowchart TB
    classDef input fill:#dbeafe,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a
    classDef process fill:#f0fdf4,stroke:#22c55e,stroke-width:1.5px,color:#14532d
    classDef decision fill:#fef9c3,stroke:#eab308,stroke-width:2px,color:#713f12
    classDef output fill:#faf5ff,stroke:#c084fc,stroke-width:1.5px,color:#701a75
    classDef terminal fill:#f1f5f9,stroke:#cbd5e1,stroke-width:1px,stroke-dasharray:4 4,color:#94a3b8

    subgraph TriggerLayer["触发源"]
        direction LR
        T1[/Idle定时器/]:::input
        T2[/App切换/]:::input
        T3[/点击事件/]:::input
        T4[/手动调用/]:::input
    end

    subgraph DebounceLayer["防抖"]
        direction LR
        D1[Click层]:::process
        D2[Trigger层]:::process
        D3{全局截流?}:::decision
    end

    P1[截图]:::process
    P2{去重?}:::decision
    P3[AX文本提取]:::process
    P4[元数据组装]:::process

    U1[/Spool磁盘队列/]:::output
    U2[/幂等上传/]:::output

    T1 & T2 & T4 --> D2
    T3 --> D1
    D1 & D2 --> D3
    D3 -->|通过| P1
    D3 -.->|拦截| X1([丢弃]):::terminal
    P1 --> P2
    P2 -->|通过| P3
    P2 -.->|重复| X2([丢弃]):::terminal
    P3 --> P4 --> U1 --> U2

    style TriggerLayer fill:#eff6ff,stroke:#3b82f6,stroke-width:2px,rx:12,ry:12
    style DebounceLayer fill:#fffbeb,stroke:#f59e0b,stroke-width:2px,rx:12,ry:12
```
**图2.1 事件驱动屏幕采集与防抖流程图**



```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': 'Inter, system-ui', 'fontSize': '14px' }}}%%
flowchart TB
    classDef process fill:#f0fdf4,stroke:#22c55e,stroke-width:1.5px,color:#14532d
    classDef decision fill:#fef9c3,stroke:#eab308,stroke-width:2px,color:#713f12
    classDef output fill:#faf5ff,stroke:#c084fc,stroke-width:1.5px,color:#701a75
    classDef fallback fill:#fff3e0,stroke:#f57c00,stroke-width:1.5px,color:#e65100

    Start([截图]) --> CheckAX{AX可用?}

    CheckAX -->|是| AX[无障碍树遍历]:::process
    CheckAX -.->|否| Fallback[OCR文本提取]:::fallback

    AX --> CheckEmpty{文本非空?}
    CheckEmpty -->|是| Source1[/accessibility/]:::output
    CheckEmpty -.->|否| Fallback

    Fallback --> Source2[/ocr/]:::output

    Source1 --> Merge[双源融合]:::process
    Source2 --> Merge

    Merge --> End([全文索引])
```
**图2.2 多源文本提取流程图**




```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': 'Inter, system-ui', 'fontSize': '14px' }}}%%
flowchart TB
    classDef input fill:#dbeafe,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a
    classDef store fill:#f0fdf4,stroke:#22c55e,stroke-width:1.5px,color:#14532d
    classDef process fill:#fff3e0,stroke:#f57c00,stroke-width:1.5px,color:#e65100
    classDef output fill:#faf5ff,stroke:#c084fc,stroke-width:1.5px,color:#701a75
    classDef decision fill:#fef9c3,stroke:#eab308,stroke-width:2px,color:#713f12
    classDef ready fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20

    In1[/截图/]:::input
    In2[/融合文本/]:::input
    In3[/元数据/]:::input

    Main[frames主表]:::store

    In1 & In2 & In3 --> Main

    Main --> Desc[描述生成]:::process
    Main --> Emb[嵌入生成]:::process
    Main --> FTS[/FTS5全文索引/]:::output

    Desc --> Sum[/语义摘要/]:::output
    Emb --> Vec[/向量语义索引/]:::output

    Main --> Check{处理完成?}:::decision
    Sum --> Check
    Vec --> Check
    FTS --> Check

    Check -->|是| Ready([可检索]):::ready
    Check -.->|否| Pending([待处理]):::input
```

**图2.3 记忆单元数据流图**



```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': 'Inter, system-ui', 'fontSize': '14px' }}}%%
flowchart TB
    classDef input fill:#dbeafe,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a
    classDef process fill:#f0fdf4,stroke:#22c55e,stroke-width:1.5px,color:#14532d
    classDef merge fill:#fef9c3,stroke:#eab308,stroke-width:2px,color:#713f12
    classDef output fill:#faf5ff,stroke:#c084fc,stroke-width:1.5px,color:#701a75

    Q[/自然语言查询/]:::input
    F[/过滤条件/]:::input

    Q --> FTS[全文检索]:::process
    Q --> Vec1[向量编码]:::process
    F --> FTS

    Vec1 --> Vec2[近似最近邻搜索]:::process

    FTS --> RRF[RRF结果融合]:::merge
    Vec2 --> RRF

    RRF --> E1[时间戳映射]:::process
    E1 --> E2[/结构化呈现/]:::output
```
**图2.4 混合语义检索与证据定位流程图**



```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': 'Inter, system-ui', 'fontSize': '14px' }}}%%
flowchart TB
    classDef input fill:#dbeafe,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a
    classDef process fill:#f0fdf4,stroke:#22c55e,stroke-width:1.5px,color:#14532d
    classDef output fill:#faf5ff,stroke:#c084fc,stroke-width:2px,color:#701a75
    classDef skillsNode fill:#fff3e0,stroke:#f57c00,stroke-width:1.5px,color:#e65100

    U[/用户输入：自然语言查询/]:::input --> T1[时区感知解析]:::process
    T1 --> T2[渐进式检索调度]:::process

    subgraph Skills["Skills 记忆感知层"]
        direction LR
        M1[活动概览]:::skillsNode
        M2[混合检索结果]:::skillsNode
        M3[帧级上下文]:::skillsNode
        M4[原始截图]:::skillsNode
    end

    T2 --> M1
    T2 --> M2
    T2 --> M3
    T2 --> M4

    M1 --> T3[上下文窗口保护]:::process
    M2 --> T3
    M3 --> T3
    M4 --> T3

    T3 -.->|循环| T2
    T3 --> T4[语义输入组装]:::process
    T4 --> L([端侧大模型：推理生成]):::output

    style Skills fill:#fffbeb,stroke:#f59e0b,stroke-width:2px,rx:12,ry:12
```
**图2.5 回忆推理框架图**



```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': 'Inter, system-ui', 'fontSize': '14px' }}}%%
flowchart TB
    classDef input fill:#dbeafe,stroke:#3b82f6,stroke-width:2px,color:#1e3a8a
    classDef process fill:#f0fdf4,stroke:#22c55e,stroke-width:1.5px,color:#14532d
    classDef decision fill:#fef9c3,stroke:#eab308,stroke-width:2px,color:#713f12
    classDef output fill:#faf5ff,stroke:#c084fc,stroke-width:2px,color:#701a75

    Q[/用户查询/]:::input

    Q -->|概括性| S1[活动概览]:::process
    S1 --> D1{信息充足?}:::decision
    D1 -->|是| A1([回答]):::output
    D1 -->|否| S2[混合检索]:::process

    Q -->|具体性| S2
    S2 --> D2{命中结果?}:::decision
    D2 -->|否| A2([未找到]):::output
    D2 -->|是| S3[帧级上下文]:::process

    S3 --> D3{需要视觉?}:::decision
    D3 -->|否| A3([回答]):::output
    D3 -->|是| S4[截图描述]:::process
    S4 --> A4([回答]):::output
```
**图2.6 渐进式信息披露决策树**


---
config:
  theme: base
  themeVariables:
    fontFamily: ''
    fontSize: 14px
  layout: elk
---
flowchart LR
 subgraph Provider["模型推理层"]
    direction LR
        P1[/"云端模型"/]
        P2[/"本地模型"/]
  end
 subgraph Agent["智能体子进程"]
        A1["JSON-RPC通信<br>时区注入<br>Skills调用"]
  end
 subgraph Service["交互服务层"]
    direction LR
        S1["会话管理"]
        S2["并发控制"]
        S3["流式调度"]
  end
 subgraph UI["用户界面"]
    direction LR
        U1[/"消息输入"/]
        U2[/"会话列表"/]
  end
    U1 --> S2
    S2 --> S3
    S3 --> A1
    A1 --> P1 & P2
    S1 --> U2

     P1:::provider
     P2:::provider
     A1:::agent
     S1:::service
     S2:::service
     S3:::service
     U1:::ui
     U2:::ui
    classDef ui fill:#dbeafe,stroke:#3b82f6,stroke-width:1.5px,color:#1e3a8a
    classDef service fill:#f0fdf4,stroke:#22c55e,stroke-width:1.5px,color:#14532d
    classDef agent fill:#fff3e0,stroke:#f57c00,stroke-width:1.5px,color:#e65100
    classDef provider fill:#faf5ff,stroke:#c084fc,stroke-width:1.5px,color:#701a75
    style Provider fill:#faf5ff,stroke:#c084fc,stroke-width:2px,rx:12,ry:12
    style Agent fill:#fffbeb,stroke:#f59e0b,stroke-width:2px,rx:12,ry:12
    style Service fill:#f0fdf4,stroke:#22c55e,stroke-width:2px,rx:12,ry:12
    style UI fill:#eff6ff,stroke:#3b82f6,stroke-width:2px,rx:12,ry:12
```
**图2.7 自然语言交互框架图**
