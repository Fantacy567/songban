> 最新学习产品规划：[文档目录](docs/planning/README.md)。已拆分整体规划、产品流程、前端、后端、美术与接口规范；交付规则不限定 UI 风格或布局。内容为待实施草案。

> [Spec Kit 项目宪法](.specify/memory/constitution.md) 已直接写入强制接口规范；[详细接口附件](docs/planning/前后端接口规范.md)给出字段、状态、权限和联调样例。现行代码入口与新产品规划分别说明。

# 松伴 · 统一黑客松前台（2026-10-30）

默认 `/` 和 `/learning` 现在提供同一套「活动／实践」前台，参考所给预览站重写品牌首页、登录弹窗、活动与团队页面。保留手机号＋密码登录，新增短信验证码登录；两种方式使用同一账号和团队。实现与验收边界见 [统一前台接入说明](docs/core-collaboration/统一前台接入说明.md)。

- 页面：`static/songban.html`、`songban.css`、`songban.js`、`songban-views.js`、`songban-library.js`，保持原生静态文件，无构建步骤。
- 真实协作：注册／登录 → 创建或加入小队 → 保存方向 → 统筹／队长确认 → 同步成果 → 同伴检查 → 交付核对／复盘。团队数据沿用 `/api/core`。
- 登录：密码走 `POST /api/studio/login`；验证码走 `POST /api/studio/login-code`；验证码发送仍走 `/api/studio/codes`。短信服务未配置时明确返回错误，不模拟已发送。
- 活动目录仍是带明确标记的虚构样例；团队模型需要服务端配置。浏览器测试使用隔离的短信和模型替身，不证明真实供应商已经可用。
- 兼容：旧核心工作台保留 `/core`；`SONGBAN_CORE_ONLY=0` 继续启用旧 studio 默认入口。旧学习演示源码和会话 API 保留，统一前台不将演示会话当成团队授权。
- 启动：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8886`。

以下是此前代码入口说明；与上述入口冲突时以上述说明为准。

# 松伴 · 此前代码入口

当前默认入口为核心协作工作台：连接个人工具 → 获准对话进入团队资料库 → 按需统筹 → 队长确认任务 → 成员执行与交叉验收。找比赛、社区和长期成长入口保留为后续方向；旧功能与历史说明在下方。

本机网页「连接个人工具」可注册原生「松伴连接器」插件。资料库按「注册姓名：用户原话 / 模型名：回复要点」显示；当前对话上传只记录，不自动触发分析。没有宿主事件钩子，不承诺后台捕获所有聊天；客户端需要实际调用同步工具并收到记录号。

- 原生插件源码：`plugins/songban-native/`；安装器：`app/connector_plugin.py`。
- 安装/资料库说明：`docs/core-collaboration/原生松伴连接器.md`。
- 启动：`.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8886`。
- 默认核心工作台接口：`/api/core`；历史工作台与接口保留，但默认封锁。
- 学习体验前台：`/learning`（独立于团队工作台的本地体验流程；前端位于 `static/learning.html`、`static/learning.css`、`static/learning.js`）。
- 统一前台视觉契约：以参考 `#/event` 页面为 design-v1 基准，约束活动／实践页面壳、tokens、状态和验收；见 [`docs/planning/视觉宪法与 UI 契约.md`](docs/planning/视觉宪法与%20UI%20契约.md)。
- 完整兼容回归：`SONGBAN_CORE_ONLY=0 .venv/bin/python -m unittest discover -s tests -q`。原生插件安装测试需要本机有 `codex` CLI；不会调用付费模型。

## 连接器与赛后成长记录

现有网页「实践 → 个人工具」保留 Codex 原生插件及 Codex/Cursor/WorkBuddy 项目 MCP 接入。选题讨论与任务页已接入共享入口；获准的用户原话及可见模型回复以两段显示，按成员配色，支持关键词/成员/环节/任务筛选、历史分页和MCP检索原文。旧摘要与全文分别标注，不保证所有对话自动采集。详见[本轮资料库接入](docs/core-collaboration/对话资料库与连接器接入.md)。团队速读、家长成长报告及下一场记忆的新增意图见[专项宪法](docs/planning/松伴连接器与赛后成长报告宪法.md)，多 Agent 分工仍是讨论方案。

## 本轮流程验收与短信配置

- [修复计划与复验（2026-10-31）](docs/reviews/修复计划与复验-2026-10-31.md)：全量审计问题的修复、验证命令和仍需补齐的产品能力。
- [完整流程验收报告（2026-10-31）](docs/reviews/完整流程验收报告-2026-10-31.md)：明确已跑通的协作子流程及完整比赛仍缺少的环节。
- [短信服务配置与实际验收](docs/core-collaboration/短信服务配置.md)：仓库 Secrets、配置检查、真实发送验证与部署边界。

## 克隆后不要复制私人配置

`.env`、数据库、`.songban/`、`.codex/` 及本机走查证据不入库。请复制 `.env.example` 并自行配置需要的服务；在自己的松伴账号中创建团队并连接自己的工具。GitHub有代码不等于已部署公网服务。

以下是分阶段历史说明；与当前行为冲突时，以以上入口及最新交接为准。

---

# 当前开发方向：松伴 · 团队同频

默认只开放：个人工具同步重要进展 → 团队总智能体比较观点并提出安排 → 队长确认 → 个人工具取回任务 → 再次同步进度。其他入口锁定，旧资料保留。

启动 `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8886`，打开 http://127.0.0.1:8886/ 。

- 开发范围：`docs/core-collaboration/需求与开发范围.md`
- 前端/插件交接：`docs/core-collaboration/接口与插件交接.md`
- 通用插件：`plugins/songban-team/README.md`（MCP＋命令行＋共享文件监听，不读取其他私人会话）
- 本轮测试：`.venv/bin/python -m unittest discover -s tests -p 'test_team*.py' -v`

以下保留历史说明，涉及旧入口时以本轮交接为准。

---

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

**同一 Wi-Fi 下队友一起用：**用 `--host 0.0.0.0` 启动，在 `.env` 设置 `PUBLIC_BASE_URL=http://<本机局域网IP>:8886`（`ipconfig getifaddr en0` 可查 IP），重启后“成员入口”复制出的链接队友就能打开。只在可信网络里这样做，入口链接等同成员钥匙。

端口占用时换一个空闲端口，不要停止别的服务。服务终端按 Ctrl+C 结束。`requirements.txt` 是直接依赖；`requirements.lock.txt` 是本次实际安装的完整版本清单。

手机号注册默认要求验证码实际发送成功。仅在隔离的本机开发环境，才可设置 `SONGBAI_ALLOW_TEST_CODES=1`，让未发送的测试验证码显示在页面；公网或共享网络严禁开启。密码登录连续失败会按账号和来源暂停五分钟。

## 第一次使用

1. 创建项目，首位成员是队长。保存队长入口，分别发送其他成员入口。
2. 保存规则与讨论各一份；可以点击“添加两份演练原文”，它们会明确标注为示例。
3. 在“分工确认”选择规则演练或真实模型。核对原文引用，修改目标、负责人、工时、依赖和验收标准。
4. 队长点击“保存并确认分工”。确认后首版冻结原文与分工。
5. 各成员通过自己的入口开始任务，提交成果；另一位成员通过或退回。
6. 必须任务全部验收通过后，查看交付清单和基于实际记录的复盘，导出 Markdown。

跨窗口协作用不同浏览器配置文件/无痕窗口，避免同一个 localStorage 会话被另一个入口替换。刷新同步，首版没有实时推送。localhost 邀请链接只在这台电脑有效；跨设备需换成队友能访问的后端地址。访问口令等同成员钥匙，不公开发布。

## 真实模型配置

内置预设为 **DeepSeek-V4.1-Flash / `deepseek-flash`**，使用官方 `https://api.deepseek.com`。复制 `.env.example` 为 `.env`，在本地填写 `DEEPSEEK_API_KEY`，重启服务。没有有效密钥时会显示“等待配置”，不会附送或虚构模型额度。

也可由队长进入“模型接入”，填自己的 API 根地址和 key，点击读取模型列表，再选择完整名称与 ID。密钥仅暂存本次服务进程内存，服务重启后需重新连接；切回内置会清除自带配置。模型列表来自服务提供者，读取成功不代表实际生成质量已经通过验证。只接受 `MODEL_ALLOWED_HOSTS` 中的 HTTPS 服务；用户配置不能指向 localhost、回环或内网地址。

兼容旧配置：服务端可填写 `MODEL_API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME` 作为自定义默认模型；`DEEPSEEK_API_KEY` 非空时官方预设优先。根地址由程序追加 `/chat/completions`，不能填完整请求路径。

该适配器要求服务支持 Chat Completions 的 `messages`、`response_format: {type: json_object}`、`max_tokens` 和非流式 `choices` 返回。请求上限 5000 输出 token；DeepSeek 官方调用关闭额外思考，以控制本任务的延迟和费用。密钥只留服务端；用户选择模型模式后，本项目的原文、成员信息和截止时间会发送给所选服务。每份草案分别记录请求模型和上游响应模型标识，页面显示完整 ID。

预设与协议依据：[DeepSeek 首次调用](https://api-docs.deepseek.com/quick_start/agent_integrations/)、[模型列表](https://api-docs.deepseek.com/api/list-models/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)（2026-10-26 核对）。

**当前实测状态（2026-10-26，0.2 时记录；0.3 未再调用付费接口）：** 运行环境已有 DeepSeek 凭据；官方 `/models` 读取成功，返回 DeepSeek-V4-Pro / `deepseek-v4-pro`。生成请求被服务商以 HTTP 402“余额不足”拒绝，真实生成尚未通过。已补充明确的余额错误，不自动重复重试。需要可用余额或其他有效密钥才能继续真实生成验收。

**没有模型额度也能用（0.3）：**“离线规则生成”会读取讨论里的任务行，例如：

```text
任务：搭建 FastAPI 接口和数据库 3h
任务：@胡方耀 做任务看板页面 2.5小时
- [ ] 设计 logo 和海报
待办：前后端联调 1h
TODO: 加分项：暗黑模式
```

`@成员` 或“某某负责”指定负责人，否则按角色和技能匹配；`2h`、`3小时` 是估时（默认 1.5 小时）；“可选/加分项”标为可选；联调任务自动依赖前面的前后端任务；讨论里没有提交相关任务时，会引用赛规中的提交条款，补一项“对照赛规核对提交清单”。以问号结尾的句子会列为待确认问题。没有任务行时使用原来的角色模板。

“模型优先生成”（接口 `mode: "auto"`）先调用模型；未配置、余额不足、超时、限流或输出不合格时，自动改用离线规则，并在草案和过程记录里写明原因。页面始终标注“离线规则引擎 · 非大模型”，不冒充 AI。接口 `mode: "model"` 仍然只用模型，失败就报错。接口模拟测试能验证请求与校验逻辑，不能证明真实模型的建议质量、延迟或成本。

**自动同步：**页面每 8 秒检查一次 `GET /api/projects/{id}/pulse`，队友有新操作时自动刷新；正在输入时不打断，只提示有新进度。任务页顶部的“我的下一步”列出等你验收、进行中、被阻塞和可以开始的任务。

**交卷前与时间不够（0.4，仍不调用大模型）：**“交付与复盘”会把赛规里含评分、提交、演示、文档、接口、页面等字样的句子，和任务标题、验收标准、成果说明做名称对照。例如赛规写了“演示视频”和“项目说明”，两项都出现在已验收任务里才算覆盖；只写“评分关注创新”这类句子会标成请人工核对。任务页在分工确认后显示剩余时间和未完成必须任务的估时；时间不够时列出建议先不做的可选项，以及建议收窄的必须任务。建议不会改已确认的任务。确认后仍不能直接加任务或改负责人。

## 给胡的前端接入

松伴（首页 `/`，`static/studio.html`）的分工和约束见 `docs/前后端宪法.md`。`docs/接口交接.md` 只描述上一版 `/api/projects`（`/classic`）。不要把模型密钥、短信密钥或微信密钥写进前端配置。

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
- 比赛网页抓取会逐跳校验公网地址、固定实际连接 IP，并在解压后内容超过上限时中止；不要通过代理绕开这些限制。
- 用 `.venv/bin/python scripts/backup_database.py` 创建一致性快照；不要在运行中仅复制主数据库文件而忽略 WAL。
- 部署命令：`.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`。需配置 HTTPS 入口、持久磁盘、模型环境变量、`PUBLIC_BASE_URL` 和明确 CORS；本轮只本地运行。
- 容器：`docker build -t hackathon-collab .`，`docker run -p 8000:8000 -v hc-data:/data --env-file .env hackathon-collab`。数据库在 `/data`，必须挂持久卷；只能单进程（`--workers 1`），因为模型设置和自带密钥保存在进程内存。Dockerfile 尚未在本机构建验证（本机没有 Docker）。
- 健康检查：`GET /health`，预期 200 且 `status=ok`。健康正常不代表真实模型质量已测。
- 更新前备份数据库与当前代码版本。在新目录验证后切换服务；失败时停止本项目服务，恢复旧代码并使用备份数据库，再以相同命令启动。首版没有破坏性自动迁移，不自动覆盖数据库。
- 这是本地协作原型，未实现公开注册、完整账号恢复、组织管理或公网滥用防护；对外正式服务需单独完成这些工作。

### 赛后复盘与家长报告

`#/review` 支持本人感悟、想法和比赛结果保存，明确调用模型结合本人工作记录生成报告，预览确认后生成家长二维码。家长只看整理后的只读报告，不开放原始聊天；持码可读、30天有效、可撤销。局域网二维码要求手机同Wi-Fi，跨网络仍需正式公网部署。详见[复盘与家长报告](docs/core-collaboration/赛后复盘与家长报告.md)。
