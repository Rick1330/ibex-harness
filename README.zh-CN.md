<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.pt-BR.md">Português (Brasil)</a> ·
  <a href="README.zh-CN.md">中文</a> ·
  <a href="README.ar.md">العربية</a>
</p>

# IBEX Harness

**面向多租户 AI 智能体的自托管记忆与上下文层。**

IBEX 是运行在自有基础设施上的记忆与上下文层。将智能体指向兼容 OpenAI 的端点，或接入 MCP 服务器：IBEX 会解析租户
与智能体身份、注入有界上下文、存储受治理的记忆，并为每次请求附加证据。

## 为什么选择 IBEX

- **每次调用都有身份。** `org_id` 绝不从 URL 或浏览器接收。AuthService 是唯一权威，所有数据路径都显式过滤租户。
- **有界上下文，而不是提示词堆砌。** 上下文组装在令牌预算和截止时间内检索、排序并打包记忆与指令；失败时降级为
  仅指令上下文，而不是阻塞代理。
- **请求附带证据。** 追踪、脱敏状态、捕获模式和发布状态随运行一起记录。

## 快速开始

前置条件：Docker Compose v2 或 Podman Compose、GNU Make，以及
[`infra/tool-versions.conf`](infra/tool-versions.conf) 中的版本。

```bash
git clone https://github.com/Rick1330/ibex-harness.git
cd ibex-harness
make setup
make check-tools
make compose-dev-up
make db-migrate
make db-seed
```

按照 [`DEVELOPMENT_GUIDE.md` §4.4](engineering/DEVELOPMENT_GUIDE.md#44-run-services) 中的命令在两个终端启动
AuthService 和代理，然后运行：

```bash
make dev-smoke
```

控制台：

```bash
pnpm install --frozen-lockfile --ignore-scripts
pnpm --filter @ibex/console dev
```

打开 `http://127.0.0.1:3000`。控制台为只读；缺少操作员会话和 `IBEX_OPERATOR_API_ORIGIN` 时会安全失败。

## 服务

| 服务 | 运行时 | 状态 |
| --- | --- | --- |
| 代理 | Go | 本地已实现；托管 SLO 证据待补 |
| AuthService | Go | 本地已实现；生产密钥管理待补 |
| 记忆 | Python / FastAPI | 本地已实现 |
| 上下文组装 | Python / gRPC | 暂定 |
| Embedder | Python | 按配置为已实现或实验性 |
| 管理 API | Python / FastAPI | 已挂载并测试；操作员界面暂定 |
| Workers | Python / Celery | 混合 |
| 控制台 | Nuxt 4 + Nitro | 暂定；10 个核心界面中有 3 个具备实时读取路径 |

完整清单见 [`services/README.md`](services/README.md)。

## 文档

- [架构](engineering/ARCHITECTURE.md)
- [开发指南](engineering/DEVELOPMENT_GUIDE.md)
- [环境变量](engineering/ENVIRONMENT_VARIABLES.md)
- [安全](engineering/SECURITY.md)
- [状态与证据](https://ibexharness.com/docs/architecture/status-and-evidence)
- [贡献](CONTRIBUTING.md)

IBEX 区分 **已实现**、**已挂载但暂定**、**已设计未实现** 和 **已推迟**。本地路由、模式、测试数据和设计文档都不是
部署证据。

## 安全与多租户

- 纵深防御：PostgreSQL RLS 加显式 `org_id` 过滤。
- 跨租户读取返回 `404`，而不是 `403`。
- 密钥绝不进入日志、追踪、浏览器配置或测试数据。
- 记忆内容是不可信输入：会被隔离，且绝不当作指令执行。
- 请通过 [`engineering/SECURITY.md`](engineering/SECURITY.md) 的私密流程报告漏洞。

## 许可证

[MIT](LICENSE)

---

[英文权威 README](README.md)
