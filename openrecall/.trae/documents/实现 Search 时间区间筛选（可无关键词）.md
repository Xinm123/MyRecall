## 前置（运行任何程序）
- 运行任何程序前都先执行：`conda activate MyRecall`（包括启动 server 或 client）。

## 目标与当前问题
- 目标：让 search 页的“Start Time / End Time”真正起作用，并支持不输入关键词也能按时间筛选。
- 当前实现的问题点：
  - 后端仅在 start_time 和 end_time 同时存在时才走时间筛选；只填一个会被忽略。
  - 后端无论是否输入 q 都会做向量检索：`get_embedding(q)`；当 q 为空/未填时要么报错、要么逻辑上不符合“仅按时间过滤”的预期。
  - 前端模板固定渲染 similarity_score（`entry.similarity_score * 100`），当不做向量检索时会缺字段。

## 改动 1：后端 /search 逻辑支持时间区间筛选
修改 [app.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/app.py)：
- 将 `q` 视为可选：`q = (request.args.get("q") or "").strip()`。
- 解析 `start_time`/`end_time`：支持
  - 两者都填：如 start > end 自动交换；按区间查询。
  - 只填 start：查询 >= start。
  - 只填 end：查询 <= end。
  - 都不填：保持原行为（取全部完成的 entries）。
- 仅当 `q` 非空时才做 embedding + cosine 排序；否则按时间倒序直接返回（不设置 similarity_score）。

## 改动 2：补充数据库按单边时间过滤的查询
修改 [database.py](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/database.py)：
- 新增两个函数（保持只返回 `status='COMPLETED'` 与现有 search 一致）：
  - `get_entries_since(start_time: int)`
  - `get_entries_until(end_time: int)`
- 继续复用 `_row_to_entry`，并按 `timestamp DESC` 排序。

## 改动 3：前端 search 模板兼容“无关键词仅筛时间”
修改 [search.html](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/server/templates/search.html)：
- 结果卡片底部的“Match: xx%”改为条件渲染：
  - 如果 `entry.similarity_score` 存在则显示百分比。
  - 否则显示 `Match: —`（或隐藏该块；我会选 `—` 更直观）。
- 可选：把 Search Query 文案标注为“可选”，避免误解。

## 验证（使用你现有的 18083）
- 修改完成后重启 server（仍然使用 18083 端口即可）：
  - `conda activate MyRecall`
  - 然后启动 server（用你当前的启动方式/命令即可，不需要新开端口）
- 直接在 `http://127.0.0.1:18083/search` 测试。
- 测试用例：
  1) 只填 Start Time，q 留空：结果应只包含该时间之后的记录。
  2) 只填 End Time，q 留空：结果应只包含该时间之前的记录。
  3) Start + End 都填，q 留空：结果应只包含区间内记录。
  4) Start > End（反着选）：仍然能正常筛选（自动交换）。
  5) q 非空 + 时间区间：先按时间筛，再按相似度排序。

## 影响范围
- 仅影响 search 页筛选与渲染逻辑，不改变数据库结构与现有录制/上传流程。