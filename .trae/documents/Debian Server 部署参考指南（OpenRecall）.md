## 输出目标
- 在仓库新增一份仅面向 Debian 的部署/运维指南，覆盖安装、目录权限、systemd、Nginx+HTTPS、防火墙、验证、备份与安全加固。

## 需要写入的新文档
- 新增 `docs/DEPLOYMENT_DEBIAN_SERVER_GUIDE.md`
- 内容结构：
  - 背景与适用范围（Server only，SQLite+PNG 持久化）
  - 目录与权限（/opt 代码 + /var/lib 数据）
  - 运行环境方案（conda MyRecall / venv 二选一）
  - 环境变量文件 `/etc/openrecall/openrecall.env`
  - systemd unit（openrecall-server.service）
  - Nginx 反代与 Let’s Encrypt HTTPS 模板
  - 防火墙端口策略（只放行 80/443；8083 不外露）
  - 联调验证清单（/api/health、/api/queue/status、UI 与落盘检查）
  - 备份与监控（db+screenshots、磁盘空间、日志、队列）
  - 安全加固（API 默认无鉴权：VPN/allowlist/BasicAuth 方案）
  - 常见问题排查（依赖/权限/超时/模型缓存）

## 文档联动
- 在 `docs/DEPLOYMENT_CLIENT_SERVER.md` 顶部补一行链接指向 Debian 指南，避免重复内容。

## 验证
- 通过本地 Markdown 预览检查：标题层级、代码块、变量名与路径一致性
- 与代码实现核对入口与端口默认值：`python -m openrecall.server`、默认 8083、API 路径 `/api/*`。
