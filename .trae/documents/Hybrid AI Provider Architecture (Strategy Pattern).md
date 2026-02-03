## 你补充的运行/测试约束（会纳入验证步骤）
- 任何测试/启动前都先 `conda activate MyRecall`。<mccoremem id="03ffxerbflqposr29lgv5cxd5" />
- Server 启动（你当前习惯）：
  - `OPENRECALL_PORT=18083 OPENRECALL_API_URL=http://localhost:18083/api OPENRECALL_DATA_DIR=/tmp/openrecall_status_server ... -m openrecall.server`<mccoremem id="03ffxerbflqposr29lgv5cxd5" />
- Client 启动：`conda activate MyRecall && OPENRECALL_API_URL=http://localhost:18083/api OPENRECALL_DATA_DIR=/tmp/openrecall_status_client ...`<mccoremem id="03ffxerbflqposr29lgv5cxd5" />

## 现状梳理（避免误拆）
- Worker 目前并没有硬编码 Moondream；本仓库的本地图像描述逻辑在 [ai_engine.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai_engine.py)，Worker 通过 [worker.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/worker.py#L53-L56) 拉起引擎并在任务处理中调用。

## 总体目标（Strategy + 插件式）
- 新增 `openrecall/server/ai/` 包，定义统一接口 + 多 Provider 实现 + 工厂选择。
- 现在先把“截图→描述（Vision）”做成可切换 Provider；同时在配置/工厂层预留“每个模型单独选 local 或 API、以及一键全走 API”的布局，后续扩展 Embedding/OCR 不需要推翻结构。

## Task 1：配置更新（支持全局默认 + 单模型覆盖）
在 [shared/config.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/shared/config.py) 里新增字段（保持现有 `Settings` 风格：snake_case + `Field(..., alias=...)`）：
- 全局默认（对应你原始需求）：
  - `ai_provider: str = "local"`（env: `OPENRECALL_AI_PROVIDER`，值：`local|dashscope|openai`）
  - `ai_model_name: str = ""`（env: `OPENRECALL_AI_MODEL_NAME`）
  - `ai_api_key: str = ""`（env: `OPENRECALL_AI_API_KEY`）
  - `ai_api_base: str = ""`（env: `OPENRECALL_AI_API_BASE`）
- 为“每个模型可单独选 local/API”提前留位（本期只会用到 vision，但结构先铺好）：
  - `vision_provider: str = ""`（env: `OPENRECALL_VISION_PROVIDER`；为空则回退到 `ai_provider`）
  - `vision_model_name: str = ""`（env: `OPENRECALL_VISION_MODEL_NAME`；为空则回退到 `ai_model_name`）
  - `vision_api_key: str = ""`（env: `OPENRECALL_VISION_API_KEY`；为空则回退到 `ai_api_key`）
  - `vision_api_base: str = ""`（env: `OPENRECALL_VISION_API_BASE`；为空则回退到 `ai_api_base`）
- “全部使用 API”的选项：
  - 约定 `ai_provider=openai|dashscope` 即为全局走 API；未来如果加 embedding_provider/ocr_provider，也可遵循“若具体 provider 为空则跟随 ai_provider”。

## Task 2：抽象接口（base.py）
新增 `openrecall/server/ai/base.py`：
- `AIProvider(ABC)`：`analyze_image(self, image_path: str) -> str`
- 定义可被 Worker 精准捕获的异常层次：
  - `AIProviderError`（基类）
  - `AIProviderConfigError`（缺 key/base/model 等）
  - `AIProviderUnavailableError`（依赖未安装）
  - `AIProviderRequestError`（网络/超时/响应结构不对）

## Task 3：Provider 实现（providers.py）
新增 `openrecall/server/ai/providers.py`：
- `LocalProvider`：
  - 将现有 Qwen3-VL 推理逻辑从 [ai_engine.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai_engine.py) 迁入/复用，确保模型只在 `__init__` 加载一次。
  - `analyze_image(image_path)` 内部打开图片、按 CPU 情况 resize、生成描述。
  - `vision_model_name` 或 `ai_model_name` 支持覆盖模型路径；为空则保持当前默认模型。
- `DashScopeProvider`：
  - 依赖 `dashscope`：用延迟 import，缺失则抛 `AIProviderUnavailableError`（提示如何安装）。
  - 设置 `dashscope.api_key`。
  - 通过 `dashscope.MultiModalConversation.call` + `file://{abs_path}` 调用并稳健提取文本。
- `OpenAIProvider`（兼容 OpenAI/DeepSeek/vLLM/Moonshot 等 OpenAI-compatible）：
  - 使用 `requests`（仓库已依赖）。
  - 读取 `api_base`，POST 到 `{api_base}/chat/completions`。
  - Base64 图片，按 GPT-4o Vision 消息格式发请求。
  - 处理 timeout、非 2xx、返回结构异常，统一抛 `AIProviderRequestError`。

## Task 4：工厂（factory.py）
新增 `openrecall/server/ai/factory.py`：
- `get_ai_provider(capability: str = "vision") -> AIProvider`
- 选择逻辑（为未来扩展做布局）：
  - `capability=="vision"` 时优先读 `settings.vision_*`，否则回退到 `settings.ai_*`。
  - 通过 `settings.(vision_provider or ai_provider)` 实例化对应 Provider。
  - 工厂做单例缓存，避免 Worker/预加载重复构造。

## Task 5：Worker 重构（worker.py）
修改 [worker.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/worker.py)：
- 用 `get_ai_provider()` 替换 `get_ai_engine()`。
- 初始化时记录日志（保持现有 logging 风格）：`logger.info(f"🤖 AI Engine initialized: {settings.vision_provider or settings.ai_provider}")`。
- 运行时调用改为：`description = ai_provider.analyze_image(str(image_path))`。
- Provider 调用周围增加窄捕获：
  - 捕获 `AIProviderError`（或兜底 `Exception`）时不让线程崩溃；建议降级 `description=""` 继续 OCR+Embedding，让条目仍可搜索。

## 启动预加载适配（让 local 依旧可预热）
- 修改 [openrecall/main.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/main.py#L28-L50) 与 [server/__main__.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/__main__.py#L27-L50)：
  - 不再固定预加载 `get_ai_engine()`。
  - 当选择的 vision provider 是 `local` 时，调用 `get_ai_provider("vision")` 完成预加载；云端 provider 跳过。

## 测试与验证（会跟随改动一起做）
- 修复/更新现有依赖 `get_ai_engine` 的测试：
  - [test_async_worker.py](file:///Users/tiiny/Test2/MyRecall/openrecall/tests/test_async_worker.py) 改为 patch `get_ai_provider`，并断言 `analyze_image` 收到的是路径字符串。
- 新增一个不触网的单测：mock `requests.post`，验证 `OpenAIProvider` payload 和 header 组装正确。
- 手动验证（按你的启动方式）：
  - `conda activate MyRecall` 后按你提供的 server 命令启动，并设置：
    - 例如 DashScope：`OPENRECALL_VISION_PROVIDER=dashscope OPENRECALL_VISION_API_KEY=...`
    - 或全局：`OPENRECALL_AI_PROVIDER=openai OPENRECALL_AI_API_BASE=... OPENRECALL_AI_API_KEY=... OPENRECALL_AI_MODEL_NAME=...`
  - 观察日志出现 `🤖 AI Engine initialized: dashscope/openai/local`。
  - 上传图片后确认 DB 中 `description` 更长更细（云端通常更详细），且 worker 不因超时/网络问题退出。

## 兼容性策略
- 保留 [ai_engine.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/ai_engine.py) 不删不破坏，让现有模型测试和旧入口仍可用；LocalProvider 会复用其逻辑/配置。
