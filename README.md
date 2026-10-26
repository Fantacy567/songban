# 赛内协作助手 · 可运行首版

为 2—8 人小队整理原文依据、确认分工、推进共享任务并交叉验收。实现范围见 `docs/需求文档.md`，流程见 `docs/业务流程.md`。

## 启动

在本目录运行，Python 3.11 或以上（本轮使用 3.14.7）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8886
```

- 工作台：http://127.0.0.1:8886/
- 图形流程：http://127.0.0.1:8886/workflow
- 接口定义：http://127.0.0.1:8886/api/openapi.json
- Swagger 调试页：http://127.0.0.1:8886/api/docs（其页面资源需能访问 jsDelivr）
- 健康检查：http://127.0.0.1:8886/health

端口占用时换一个空闲端口，不要停止别的服务。服务终端按 Ctrl+C 结束。`requirements.txt` 是直接依赖；`requirements.lock.txt` 是本次实际安装的完整版本清单。

## 第一次使用

1. 创建项目，首位成员是队长。保存队长入口，分别发送其他成员入口。
2. 保存规则与讨论各一份；可以点击“添加两份演练原文”，它们会明确标注为示例。
3. 在“分工确认”选择规则演练或真实模型。核对原文引用，修改目标、负责人、工时、依赖和验收标准。
4. 队长点击“保存并确认分工”。确认后首版冻结原文与分工。
5. 各成员通过自己的入口开始任务，提交成果；另一位成员通过或退回。
6. 必须任务全部验收通过后，查看交付清单和基于实际记录的复盘，导出 Markdown。

跨窗口协作用不同浏览器配置文件/无痕窗口，避免同一个 localStorage 会话被另一个入口替换。刷新同步，首版没有实时推送。localhost 邀请链接只在这台电脑有效；跨设备需换成队友能访问的后端地址。访问口令等同成员钥匙，不公开发布。

## 真实模型配置

内置预设为 **DeepSeek-V4-Pro / `deepseek-v4-pro`**，使用官方 `https://api.deepseek.com`。复制 `.env.example` 为 `.env`，在本地填写 `DEEPSEEK_API_KEY`，重启服务。没有有效密钥时会显示“等待配置”，不会附送或虚构模型额度。

也可由队长进入“模型接入”，填自己的 API 根地址和 key，点击读取模型列表，再选择完整名称与 ID。密钥仅暂存本次服务进程内存，服务重启后需重新连接；切回内置会清除自带配置。模型列表来自服务提供者，读取成功不代表实际生成质量已经通过验证。只接受 `MODEL_ALLOWED_HOSTS` 中的 HTTPS 服务，不向任意内网地址或重定向目标转发凭据。

兼容旧配置：服务端可填写 `MODEL_API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME` 作为自定义默认模型；`DEEPSEEK_API_KEY` 非空时官方预设优先。根地址由程序追加 `/chat/completions`，不能填完整请求路径。

该适配器要求服务支持 Chat Completions 的 `messages`、`response_format: {type: json_object}`、`max_tokens` 和非流式 `choices` 返回。请求上限 5000 输出 token；DeepSeek 官方调用关闭额外思考，以控制本任务的延迟和费用。密钥只留服务端；用户选择模型模式后，本项目的原文、成员信息和截止时间会发送给所选服务。每份草案分别记录请求模型和上游响应模型标识，页面显示完整 ID。

预设与协议依据：[DeepSeek 首次调用](https://api-docs.deepseek.com/quick_start/agent_integrations/)、[模型列表](https://api-docs.deepseek.com/api/list-models/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)（2026-10-26 核对）。

**当前实测状态（2026-10-26）：** 运行环境已有 DeepSeek 凭据；官方 `/models` 读取成功，返回 DeepSeek-V4-Pro / `deepseek-v4-pro`。生成请求被服务商以 HTTP 402“余额不足”拒绝，真实生成尚未通过。已补充明确的余额错误，不自动重复重试。需要可用余额或其他有效密钥才能继续真实生成验收。

本地规则演练是显式标签提取和角色模板，页面不会把它标成 AI 理解。接口模拟测试能验证请求与校验逻辑，不能证明真实模型的建议质量、延迟或成本。真实模型失败时不会静默切换成规则结果。

## 给胡的前端接入

详见 `docs/接口交接.md`。前端用接口返回的成员 `access_token` 设置 `Authorization: Bearer <token>`；不能自己提交职位来取得队长权限。另起本地前端时在 `ALLOWED_ORIGINS` 填明确 Origin，例如 `http://localhost:5173`，重启后端。不要把模型密钥写进前端配置。

## 测试

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/http_restart_check.py
```

浏览器完整验收需要 Node、Playwright、Chrome 和 Playwright 的 FFmpeg 组件：

```sh
node scripts/e2e.cjs
```

如果 Playwright 不在本项目 Node 搜索路径，可通过 `NODE_PATH` 指定现有安装。视频组件可用 Playwright CLI 安装；可设置 `PLAYWRIGHT_BROWSERS_PATH` 放在本项目 `.browser-cache`。本轮环境的具体运行命令与结果记在验收报告。E2E 会在测试服务创建明确标注的开发验收项目；不会声称由真实队友操作。

## 数据、部署准备与回退

- 数据默认在 `data/collab.sqlite3`；可用 `DATABASE_PATH` 指向持久磁盘。SQLite、WAL、`.env`、虚拟环境和测试截图均被 `.gitignore` 忽略。
- 用 `.venv/bin/python scripts/backup_database.py` 创建一致性快照；不要在运行中仅复制主数据库文件而忽略 WAL。
- 部署命令：`.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`。需配置 HTTPS 入口、持久磁盘、模型环境变量和明确 CORS；本轮只本地运行。
- 健康检查：`GET /health`，预期 200 且 `status=ok`。健康正常不代表真实模型质量已测。
- 更新前备份数据库与当前代码版本。在新目录验证后切换服务；失败时停止本项目服务，恢复旧代码并使用备份数据库，再以相同命令启动。首版没有破坏性自动迁移，不自动覆盖数据库。
- 这是本地协作原型，未实现公开注册、完整账号恢复、组织管理或公网滥用防护；对外正式服务需单独完成这些工作。
