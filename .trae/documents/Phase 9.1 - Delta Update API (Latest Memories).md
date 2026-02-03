## 前置要求（你强调的运行方式）
- 任何测试/启动 server 或 client 之前都先执行：`conda activate MyRecall`。<mccoremem id="03ffxerbflqposr29lgv5cxd5" />
- 你当前 server 运行在 `OPENRECALL_PORT=18083`，API 基址为 `http://localhost:18083/api`。<mccoremem id="03ffxerbflqposr29lgv5cxd5" />

## 现状对齐（和当前代码库一致）
- 数据表叫 `entries`（不是 `memories`），字段包含：`id, app, title, text, description, timestamp, status, embedding`。
- 数据库访问是模块函数（[database.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py) 没有 `Database` 类）。
- 前端模板当前依赖字段：`entry.app`, `entry.timestamp`, `entry.status`, `entry.description`，并约定截图文件名 `{timestamp}.png`（见 [index.html](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/templates/index.html#L344-L387)）。

## Task 1：补齐 DB 增量查询（server/database.py）
- 新增函数：`get_memories_since(timestamp: float)`（按现有风格做成模块函数）。
- SQL（按需求，但适配本库 schema）：
  - `SELECT id, app, title, text, description, timestamp, status FROM entries WHERE timestamp ` 
  - 实现时使用：`timestamp > ? ORDER BY timestamp DESC`
  - 不加 `status='COMPLETED'` 过滤，让新入库的 `PENDING/PROCESSING` 也能被 UI 拉到。
- 返回：`List[dict]`（JSON-safe，不返回 `embedding`）：
  - 必含：`id, timestamp, app, title, text, description, status`
  - 派生：`filename: f"{timestamp}.png"`
  - 可选别名：`app_name=app`、`window_title=title`（给未来前端 JS 用，不影响现有字段）。

## Task 2：新增 API（server/api.py）
- 新增路由：`GET /api/memories/latest`（挂在现有 `api_bp` 下）。
- 参数：`since`（query，float）
  - 缺省：默认 `0`
  - 非法：返回 `400`（说明 since 必须是 float）
- 逻辑：调用 `get_memories_since(float(since))` 并返回 JSON 数组。

## Verification（按你现在的启动方式）
- 先 `conda activate MyRecall`，保证用同一环境启动 server/client。<mccoremem id="03ffxerbflqposr29lgv5cxd5" />
- 用浏览器或 curl：
  - `http://localhost:18083/api/memories/latest?since=0`：应返回所有 entries。
  - 选一个中间的 `timestamp` 再请求：`...since=<that_ts>`：应只返回 timestamp 更大的 entries。

## 备注
- 需求里写的 `db.get_memories_since(...)`：在本库里我会实现为 `database.py` 里的函数并在 `api.py` 里 import 使用（等价且符合现有架构）。