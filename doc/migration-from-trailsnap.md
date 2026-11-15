# 从 TrailSnap 同仓部署迁移

新仓库为 `LC044/TrailSnap-Feedback`。源码目录从 `package/requirement-platform/{server,web}` 变成根目录的 `{server,web}`。MCP、HTTP、域名、数据库表和历史迁移编号保持兼容。

1. 在原部署目录保存当前镜像 digest、Compose 项目名、`.env`、反向代理配置和实际数据库卷名称。不要将这些备份提交到公共仓库。
2. 暂停原 API、worker、MCP 的写入，通过 SQLite 在线备份或停止后的完整复制备份数据库和 uploads，验证备份可读。不要运行 `docker compose down -v`。
3. 克隆新仓库，将原 `.env` 私下复制到新部署目录。保留原 `RP_JWT_SECRET`，否则登录、邮件签名和已加密模型密钥会失效。
4. 找到原卷名：`docker volume ls` / `docker volume inspect <原卷名>`。新 `.env` 设置 `RP_DATA_VOLUME=<原卷名>`。生产 Compose 显式复用 external 卷；不会悄悄新建空卷。新安装需先 `docker volume create <名称>`。
5. `RP_IMAGE_TAG` 固定 CI 生成的 `sha-...` 或发布标签，执行 `docker compose -f docker-compose.prod.yml pull`，再 `docker compose -f docker-compose.prod.yml up -d`。API 首先执行 Alembic 迁移；worker 和 MCP 等待健康检查通过。
6. 核验 `/api/health`、旧需求编号、附件、匿名编辑回执、MCP、GitHub 同步和反向代理路径。主应用继续使用 `VITE_REQUIREMENT_PLATFORM_URL=https://feedback.trailsnap.cn`，无需链接本仓源码。
7. 配置 SMTP 后在提交页自愿订阅，收件人确认邮箱。查看“邮件通知”的投递状态；通过管理员咨询验证邮件到对话闭环。
8. 原 AI 连接保留。执行器改为官方 DSH SDK，需 DeepSeek Messages 协议端点，不能把仅支持 `/chat/completions` 的旧端点当作兼容连接。通过 AI 设置的“测试连接”验证，再启用任务路由。

## 回滚

出现异常先停新 API、worker、MCP。保留新数据库与附件副本，恢复原镜像和一致性备份后再启动。不要在已有新会话/通知的生产库上直接降级，以免丢失记录。此迁移仅新增表；历史需求和用量记录保留。

## 通知语义

业务事件和邮件 outbox 在同一数据库事务提交。原子领取、租约、指数退避、稳定 Message-ID、失败列表和人工重试提供至少一次投递。SMTP 已接收但确认丢失时仍可能重复，不能声称恰好一次送达；`sent` 表示 SMTP 接收，不代表用户收件箱已收到。未验证、退订和已删除需求不会继续发送事件邮件。旧有联系方式不会被擅自当作订阅。

匿名用户的验证邮箱会收到仅限本需求私有讨论的链接（30 天有效），不授予编辑正文、审核或执行权限。退订立即撤销此类邮箱讨论链接。原匿名编辑回执仍可独立使用。
