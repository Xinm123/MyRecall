# 设计：清除 openrecall 元素，统一改名为 myrecall

- **日期**：2026-05-05
- **状态**：待实施
- **范围**：将项目内所有活动代码、配置、脚本、服务文件、顶层文档中的 `openrecall` / `OpenRecall` / `OPENRECALL_*` 一次性改为 `myrecall` / `MyRecall` / `MYRECALL_*`。
- **不在范围**：历史归档目录（`openspec/changes/archive/`、`docs/superpowers/specs/`、`docs/superpowers/plans/`）与第三方参考代码（`_ref/screenpipe/`）。

---

## 1. 背景

项目当前处于 OpenRecall → MyRecall 的半迁移状态：

- 数据目录已迁移至 `~/.myrecall/{client,server}`
- 部分配置示例已新增 `myrecall_*.toml.example`（与旧的 `*.toml.example` 并存且 diff 不一致）
- Python 包仍叫 `openrecall/`，`setup.py` `name="OpenRecall"`
- 约 30 个 `OPENRECALL_*` 环境变量散落在 `shared/config.py`、TOML、shell、systemd、文档中
- 顶层文档（README/CLAUDE/AGENTS/GEMINI）混用品牌名

目标是完成迁移、清除残留、回到一致的命名空间。

## 2. 决策（用户已确认）

| 议题 | 选择 |
|---|---|
| 改名目标 | 完整改名 `openrecall` → `myrecall`（包名、env、setup 名、入口、systemd、脚本、配置、文档） |
| 旧 env 兼容 | **硬切**，不保留 `OPENRECALL_*` 双读 |
| 历史档案 | **冻结**，不动 `openspec/changes/archive/` 与 `docs/superpowers/{specs,plans}/` |
| 提交粒度 | **4 阶段**，每阶段一个 commit，且每阶段验证门（测试/冒烟）必须为绿才进入下一阶段 |

## 3. 命名映射

| 维度 | 源 | 目标 |
|---|---|---|
| Python 包目录 | `openrecall/` | `myrecall/` |
| Python 包名（setup.py `name=`） | `OpenRecall` | `MyRecall` |
| 模块路径 | `openrecall.{client,server,shared}` | `myrecall.{client,server,shared}` |
| 入口命令 | `python -m openrecall.{client,server}` | `python -m myrecall.{client,server}` |
| 环境变量前缀 | `OPENRECALL_*`（约 30 个） | `MYRECALL_*` |
| systemd unit 文件 | `openrecall-server.service` | `myrecall-server.service` |
| systemd 内部署路径 | `/data/apps/MyRecall/openrecall`、`/data/venvs/openrecall`、`UV_CACHE_DIR=/data/.cache/uv/openrecall` | 同形改为 `myrecall` |
| Egg-info 目录 | `OpenRecall.egg-info/` | 删除→`pip install -e .` 重新生成 `MyRecall.egg-info/` |
| 配置示例（双套去重） | `client.toml.example` 与 `myrecall_client.toml.example` 并存且 diff 不同；server 同 | 仅保留 `myrecall_{client,server}.toml.example`；先把旧文件独有的字段并入新文件再删除 |
| 顶层文档字样 | README/CLAUDE/AGENTS/GEMINI.md 内 `OpenRecall`、`openrecall`、`OPENRECALL_*` | 全部 → `MyRecall` / `myrecall` / `MYRECALL_*` |
| 数据目录 | 已是 `~/.myrecall/{client,server}` | 不变 |
| 覆盖率配置 | `.coveragerc` / `.coveragerc.critical` 内 `source = openrecall` / `omit` 路径 | `source = myrecall` / 路径改为 `myrecall/...` |
| 日志组件名 | `logging_config.py` 默认 `component="openrecall"` | `component="myrecall"` |
| CLI `prog` 名 | `__main__.py` 内 `prog="openrecall-client"`、`prog="openrecall-server"` | `prog="myrecall-client"`、`prog="myrecall-server"` |
| JS 自定义事件 | `openrecall-config-changed`（5 个 HTML 模板） | `myrecall-config-changed` |

**冻结清单（不替换）：**
- `openspec/changes/archive/`
- `docs/superpowers/specs/`
- `docs/superpowers/plans/`
- `_ref/screenpipe/`
- 任何 `*.egg-info/` 中的旧元数据文件（Stage 3 整体重建）
- `*.sql` 迁移文件（注释内容不影响执行，白名单 grep 排除）

## 4. 4 阶段提交计划

每阶段一个 commit。每阶段进入下一阶段前必须满足"验证门"。

### Stage 1 — 包重命名 + import 重写

**改动**
- `git mv openrecall/ myrecall/`
- 全仓静态替换：
  - `import openrecall` → `import myrecall`
  - `from openrecall` → `from myrecall`
  - 字符串字面量里的 `"openrecall.xxx"`、`"openrecall/"` 路径（动态 `importlib`、Flask 模板/静态资源路径、`logger.getLogger("openrecall...")` 等）
  - HTML 模板中 JS 事件名：`openrecall-config-changed` → `myrecall-config-changed`（`client/web/templates/settings.html`、`client/web/templates/layout.html`、`client/web/templates/index.html`、`server/templates/layout.html`、`server/templates/index.html`，共 5 处）
- `myrecall/main.py` / `myrecall/client/__main__.py` / `myrecall/server/__main__.py` 中 banner 日志：
  - `"OpenRecall Starting"` → `"MyRecall Starting"`
  - `"OpenRecall Client Starting"` → `"MyRecall Client Starting"`
  - `"OpenRecall Server Starting"` → `"MyRecall Server Starting"`
- `myrecall/shared/logging_config.py`：`def configure_logging(component: str = "openrecall")` → `component="myrecall"`
- `myrecall/client/__main__.py`、`myrecall/server/__main__.py`：`prog="openrecall-client"` → `prog="myrecall-client"`，`prog="openrecall-server"` → `prog="myrecall-server"`

**验证门**
1. `python -c "import myrecall.client; import myrecall.server; import myrecall.shared"` 不报错
2. `pytest -m unit` 全绿
3. `grep -RIn '\bopenrecall\b' myrecall/ tests/ scripts/` 命中 0 行（品牌名"OpenRecall"和 `OPENRECALL_*` 前缀 env 名不在 Stage 1 清除范围，由 Stage 2/4 处理）

### Stage 2 — env 名 + 配置 / 脚本 / 服务文件

**改动**
- `myrecall/shared/config.py`：所有 pydantic `Field(alias="OPENRECALL_*")` → `"MYRECALL_*"`，对应 docstring 同步
- env 文件：`myrecall_client.env`、`myrecall_server.env` 内 `OPENRECALL_*` → `MYRECALL_*`
- 实际配置：`server-local.toml`、`client-local.toml`、`server-remote.toml`、`client-remote.toml` 中的注释与可能存在的 env 名引用
- 配置示例去重：`diff client.toml.example myrecall_client.toml.example` 合并独有字段到 `myrecall_client.toml.example`，删除 `client.toml.example`；server 同
- shell：`run_client.sh`、`run_server.sh` 内 `OPENRECALL_DEBUG` → `MYRECALL_DEBUG`、`-m openrecall.x` → `-m myrecall.x`、注释中的部署路径
- systemd：`openrecall-server.service` 重命名为 `myrecall-server.service`，内部 `WorkingDirectory`、`EnvironmentFile`、`UV_CACHE_DIR`、`ExecStart` 路径同形替换
- 测试 fixture：`tests/conftest.py` 中 `tempfile.mkdtemp(prefix="openrecall_test_data_")` → `myrecall_test_data_`；`Path("openrecall/server/database/migrations")` → `"myrecall/server/database/migrations"`；`os.environ.setdefault("OPENRECALL_DATA_DIR", ...)` → `"MYRECALL_DATA_DIR"`
- `.coveragerc` 与 `.coveragerc.critical`：`source = openrecall` → `myrecall`；所有 `omit` 路径前缀 `openrecall/` → `myrecall/`
- 硬编码 `os.environ.get("OPENRECALL_*")`（非 pydantic alias，Stage 1 全仓 sed 不会触及）：
  | 文件 | 内容 |
  |------|------|
  | `myrecall/client/__main__.py` | `os.environ["OPENRECALL_CLIENT_WEB_ENABLED"]` |
  | `myrecall/client/accessibility/debug.py` | `os.environ.get("OPENRECALL_ACCESSIBILITY_DEBUG")` |
  | `myrecall/client/recorder.py` | `os.environ.get("OPENRECALL_ACCESSIBILITY_DEBUG")` |
  | `myrecall/client/events/permissions.py` | `os.environ.get("OPENRECALL_SKIP_PERMISSION_CHECK")` |
  | `myrecall/shared/config_base.py` | `os.environ.get("OPENRECALL_CONFIG_PATH")` |
  | `myrecall/shared/config.py` | legacy fallback：`"OPENRECALL_IDLE_CAPTURE_INTERVAL_MS"`、`"OPENRECALL_CAPTURE_INTERVAL"` |
  | `myrecall/client/chat/conversation.py` | `os.environ.get("OPENRECALL_CLIENT_DATA_DIR")` |
  | `myrecall/client/chat/config_manager.py` | `os.environ.get("OPENRECALL_CHAT_API_BASE")` |
  | `myrecall/server/ocr/rapid_backend.py` | docstring `OPENRECALL_OCR_*` → `MYRECALL_OCR_*` |

**验证门**
1. `pytest -m "unit or integration"` 全绿
2. `./run_server.sh --mode local --debug` 起得来；`curl -fsS http://localhost:8083/v1/health` 通
3. `./run_client.sh --mode local --debug` 起得来；浏览器打开 `http://localhost:8889/` 加载 Grid 成功
4. 触发一次 manual capture，验证 ingest → 处理 → 可搜（端到端冒烟）

### Stage 3 — 打包元数据

**改动**
- `setup.py`：`name="OpenRecall"` → `"MyRecall"`
- 删除 `OpenRecall.egg-info/`
- 重新 `pip install -e .` 生成 `MyRecall.egg-info/`
- `requirements.txt` 内若有 OpenRecall 注释清理

**验证门**
1. `pip install -e .` 无报错且产出 `MyRecall.egg-info/`
2. `pip show MyRecall` 显示新元数据；`pip show OpenRecall` 应失败
3. `python -m myrecall.client --help` 与 `python -m myrecall.server --help` 正常输出

### Stage 4 — 顶层文档清扫 + 终检

**改动**
- `README.md`、`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`：`OpenRecall` → `MyRecall`、`openrecall` → `myrecall`、`OPENRECALL_` → `MYRECALL_`
- `myrecall_{client,server}.toml.example` 头部注释里的 `OpenRecall` → `MyRecall`
- `AGENTS.md` 中的 `--cov=openrecall` → `--cov=myrecall`
- `tests/conftest.py`：`openrecall_test_data_` → `myrecall_test_data_`；`import openrecall` → `import myrecall`（全仓替换 Stage 1 已覆盖但需确认）
- `README.md` 中的 GitHub URL `github.com/openrecall/openrecall.git`：若 GitHub repo 同步改名为 `myrecall` 则替换；若未改名则保留旧名并在注释中说明（非本仓库代码层面的变更）

**最终验证门（白名单 grep）**
```bash
grep -RIn -E 'openrecall|OpenRecall|OPENRECALL_' . \
  --exclude-dir=openspec/changes/archive \
  --exclude-dir=docs/superpowers/specs \
  --exclude-dir=docs/superpowers/plans \
  --exclude-dir=_ref \
  --exclude-dir=.git \
  --exclude='*.egg-info/*' \
  --exclude='*.sql'
```
**期望命中 0 行。** 命中即视为漏网，提交前必须补回或加入白名单（带说明）。

## 5. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| Stage 1 漏改字面量字符串（`importlib`、Flask 模板路径、SQL 文本、logger 名） | 启动期 `ImportError` 或运行期 `KeyError` | Stage 1 验证门含 `grep '\bopenrecall\b'` 应为 0；跑 `pytest -m unit` |
| pydantic alias 改名后旧 env 设置失效 | 进程读不到配置回退默认 | Stage 2 同步改所有 env / TOML / shell / service；硬切无双读兜底（用户决策） |
| 重复 toml 示例合并丢字段 | 配置示例缺项 | `diff` 取并集后再删旧文件；删除前先 `git add` 暂存 |
| `pip install -e .` 卡在旧 egg-info | Stage 3 失败 | Stage 3 第一步 `rm -rf OpenRecall.egg-info` |
| systemd 部署机 unit 名变了 | 远端需手工 `daemon-reload` | Stage 4 commit message 写明 `systemctl disable openrecall-server && systemctl enable myrecall-server && systemctl daemon-reload` |
| 终检 grep 漏过冻结目录里的合法引用 | 终检误报 | `--exclude-dir` 已显式列出；冻结目录全程不动 |
| LanceDB / SQLite 数据目录 | 不受影响 | `~/.myrecall/` 已是目标命名 |
| 硬编码 `os.environ.get("OPENRECALL_*")` 字符串漏改 | 部分配置读不到值，回退默认 | Stage 2 改动清单显式列出 7 文件 9 处；Stage 2 验证门跑端到端冒烟捕捉 |

## 6. 测试策略

**最小集合（每 commit 之前必跑）：**
```bash
pytest -m unit -x
```

**完整门（每 stage 完成时必跑）：**
```bash
pytest -m "unit or integration" -x
```

**Stage 2 / Stage 4 加跑端到端冒烟：**
```bash
./run_server.sh --mode local --debug    # 后台
./run_client.sh --mode local --debug    # 后台
curl -fsS http://localhost:8083/v1/health
curl -fsS http://localhost:8889/         # Grid 页面 200
# 触发一次 manual capture，验证 ingest → 处理 → 可搜
```

**Stage 4 最终白名单 grep 命中 0 即整体通过。**

## 7. 不做的事（YAGNI）

- 不实现 OPENRECALL→MYRECALL 双读兼容层
- 不重写 `openspec/changes/archive/`
- 不重写 `docs/superpowers/{specs,plans}/`
- 不动 `_ref/screenpipe/`
- 不引入"产品名常量"或"重命名抽象层"——一次硬替换最干净
- 不动 `~/.myrecall/` 数据迁移逻辑（数据目录已是 myrecall）

## 8. 部署侧切换说明（commit message 内写明）

部署机收到 Stage 4 之后的代码，需按顺序执行一次：

```bash
# 旧 unit 停用
sudo systemctl disable --now openrecall-server || true
sudo rm -f /etc/systemd/system/openrecall-server.service

# 安装新 unit（路径以仓库内 myrecall-server.service 为准）
sudo cp myrecall-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now myrecall-server

# 重装 venv 内的包元数据
/data/venvs/myrecall/bin/pip install -e .
```

迁移期间数据目录无需变动（已经是 `~/.myrecall/`）。

> 部署机若已有 `OPENRECALL_*=...` 形式的 env 文件（如 `/data/apps/MyRecall/openrecall/openrecall.env`），需要：
> 1. 路径目录跟随仓库新结构（`openrecall` → `myrecall`）
> 2. 文件内的 `OPENRECALL_*` 变量名全部改为 `MYRECALL_*`
> 3. systemd unit 中 `EnvironmentFile=` 指向新路径
