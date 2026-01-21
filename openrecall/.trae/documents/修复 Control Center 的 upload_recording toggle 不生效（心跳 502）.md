## 必要前置（每次都要做）
- 运行任何 OpenRecall 的 server/client/脚本前：先执行 `conda activate MyRecall`。<mccoremem id="03ffsg4dhicq0dfp7l12jurqr" />

## 现象与根因定位
- Control Center 的 toggle（upload_enabled / recording_enabled）已成功 `POST /api/config` 写入服务端（浏览器 console 有 “Config updated on server”）。
- 但客户端是否“执行”这些开关，依赖客户端心跳同步：客户端在 [recorder.py::_send_heartbeat](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/client/recorder.py#L166-L188) 调用 `POST /api/heartbeat` 拉取 config，再决定是否暂停录制/是否入队上传。
- 你这里客户端心跳一直 `HTTP Error 502: Bad Gateway`，导致客户端一直保持默认 `recording_enabled=True / upload_enabled=True`，所以 upload/recording toggle 看起来“能切但没效果”。
- 代码层面的不一致：心跳 URL 目前硬编码 `http://localhost:{settings.port}/api/heartbeat`（不走 `settings.api_url`）且使用 `urllib`，更容易在代理/反代环境里触发 502。

## 临时绕过（不改代码也可先验证）
- 启动 client 前确保本机 loopback 不走代理：设置 `NO_PROXY=localhost,127.0.0.1` 或临时取消 `HTTP_PROXY/HTTPS_PROXY`（502 很可能就是代理回的）。

## 代码修复方案（包含 Consumer 尊重开关）
1) 统一心跳地址与网络栈
- 修改 [recorder.py::_send_heartbeat](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/client/recorder.py#L166-L188)：
  - 心跳 URL 改为 `{settings.api_url.rstrip('/')}/heartbeat`（不再硬编码 localhost/port）。
  - 改用 `requests.post(..., timeout=2)`，并在 host 为 `localhost/127.0.0.1/::1` 时显式禁用环境代理，避免 502。

2) 让 Consumer 也尊重 upload_enabled（立即停止上传积压项）
- 改造 [consumer.py:UploaderConsumer](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/client/consumer.py)：
  - 新增一个可选的回调/状态提供者（例如 `should_upload: Callable[[], bool]`），默认恒为 True。
  - 在每次准备上传前先判断 `should_upload()`：
    - 若为 False：不上传、不 commit buffer；进入可中断等待（例如 1s）后继续循环。
    - 若为 True：按现有逻辑正常上传。
- 在 [recorder.py:ScreenRecorder.__init__](file:///Users/tiiny/Test2/MyRecall/openrecall/openrecall/client/recorder.py#L141-L159) 创建 consumer 时注入 `should_upload=lambda: self.upload_enabled`，这样 upload toggle 一旦通过心跳同步到 `self.upload_enabled`，consumer 会立刻停/继续。

3) 验证 toggle 生效（本地全流程）
- 在 `conda activate MyRecall` 后启动 server + client：
  - server 端应出现 `POST /api/heartbeat` 200；UI 的 `client_online` 变为 true。
  - 切 `recording_enabled=false`：client 日志出现 `Recording paused`，并停止产生新截图/入队。
  - 切 `upload_enabled=false`：
    - Producer：不再 enqueue 新任务；
    - Consumer：即使 buffer 里有积压，也应停止上传（仅等待，不删除）。
  - 再切回 `upload_enabled=true`：Consumer 继续把积压上传完。

## 兼容性说明
- 该方案不改变服务端 API，仅调整 client 内部一致性与线程协作方式；未来你把 server 部署到 Debian 计算端时，只需把 `OPENRECALL_API_URL` 指向那台机器即可，心跳/上传会一致走同一个地址。