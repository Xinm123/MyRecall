## 总体原则（满足你的要求）
- 运行任何程序前都先 `conda activate MyRecall`（跑测试/启动 server/client）。
- 测试分层：Unit / Module(Integration) / System(E2E) / Perf / Security。
- 覆盖率门禁：整体 80%+；关键路径 100%（服务端 API/DB/配置/搜索过滤等）。
- 默认回归要快：默认只跑 unit+integration（不跑模型/端到端/基准/安全），并行执行。

## 现有 tests 盘点与“规整化”策略（你要求的重点）
- 当前 tests/ 已大量使用 pytest，但混入 unittest、手工脚本型测试、依赖 localhost/固定端口、以及模型下载/大资源测试。
- 规整化要做的事：
  1) 统一 pytest 风格（把 unittest.TestCase 迁为 pytest）。
  2) 把“手工脚本型/依赖已启动服务/固定端口”的文件移出默认 pytest 发现路径，或加 marker 并默认跳过。
  3) 把 AI/模型/网络依赖测试标记为 `model`/`gpu`/`slow`，默认不跑，显式开启才跑。
  4) 用统一 fixtures 管理测试数据目录（OPENRECALL_DATA_DIR）、DB、截图文件，保证隔离与可重复。
  5) 尽量消除 `time.sleep` 的不稳定：改为“等待条件满足 + 超时”的轮询，或可注入更小间隔。
  6) 移除 tests/__pycache__ 等产物并加入忽略规则。

## 单元测试（Unit）
- 新建 `tests/unit/`，补齐细粒度测试：
  - openrecall/shared/config.py（环境变量覆盖/默认值/类型转换）
  - openrecall/shared/utils.py（时间格式化等）
  - openrecall/server/config_runtime.py（锁/更新/校验）
  - openrecall/server/nlp.py（cosine_similarity 等纯函数；模型部分用 mock）
  - openrecall/server/database.py（迁移/row_to_entry/查询边界）
- 每个用例都有明确断言，覆盖正常与异常路径。

## 模块测试（Integration/Module）
- 新建 `tests/integration/`：
  - Flask test_client 测 /api：/health、/config GET/POST、/upload 输入校验与返回码、/queue/status
  - 测 /search：仅时间、仅 q、q+时间、start>end 自动交换、空 q 不触发 embedding
  - mock 外部依赖：不下载模型、不进行真实 OCR/VL 推理、不依赖系统截图
  - fixtures：准备临时数据目录、临时 sqlite、生成小 png，跑完自动清理

## 系统测试（E2E / 用户场景）
- 新建 `tests/e2e/`（pytest + Playwright）：
  - 端到端用户旅程：
    - Grid：打开弹窗、左右切换、计数/app/时间更新、Esc/遮罩关闭
    - Search：时间区间筛选生效（无 q/有 q），弹窗左右切换
    - Timeline：滑块切换图片
    - Control Center：开关操作→请求发送→页面状态变化（hide-ai/class）
  - E2E server 启动方式：测试中启动临时 server（临时端口+临时数据目录），避免污染你本机 18083 数据；你手工验证仍可继续用 18083。

## 性能基准（Perf）
- 新建 `tests/perf/`（pytest-benchmark）：
  - /api/config、/api/health、/api/upload（小 payload）响应时间基线
  - 默认回归不跑 perf；CI 可设置为可选 job 或 nightly。

## 安全测试（Security）
- 新建 `tests/security/` + 静态工具：
  - bandit：代码弱点扫描
  - pip-audit：依赖漏洞扫描
  - 动态用例：路径穿越（/screenshots）、/api/upload 输入异常不写盘等

## 测试基础设施（CI/报告/覆盖率/通知/数据方案）
- 新增配置文件：
  - pytest.ini：定义 markers（unit/integration/e2e/perf/security/model/slow）与默认选择
  - .coveragerc：整体 80%+，关键路径 100%（对关键模块设置更严格阈值/单独报告）
  - tests/conftest.py：统一 OPENRECALL_DATA_DIR、flask_client、screenshot_factory、临时 DB
- 报告：pytest 输出 junit.xml + coverage.xml + htmlcov（可选）
- CI：新增 GitHub Actions（.github/workflows/tests.yml）
  - job: unit+integration + coverage 门禁（主分支/PR 默认跑）
  - job: e2e（可选，或 nightly 跑 chromium；可扩展 webkit/firefox）
  - job: security（bandit + pip-audit）
  - 失败通知：GitHub Checks；可选 Slack webhook（仅用 secret，不写死）

## 执行时间与快速回归策略
- 默认 `pytest -m "not e2e and not perf and not security and not model"`（或在 pytest.ini 里设默认）
- 并行：pytest-xdist
- 慢测试（模型/真实服务/端到端）分组，只在需要时运行。

## 交付时我会给出的“规整化映射表”
- 给出每个现有 tests 文件应归类到 unit/integration/e2e/model/legacy 的映射，并完成迁移/标记/重写，保证默认回归集稳定可跑。

确认后我将开始：先做“规整化现有 tests + 新增 pytest.ini/.coveragerc/conftest + 覆盖率门禁”，再补齐缺口的 unit/integration，再落地 Playwright E2E、perf、安全与 CI。