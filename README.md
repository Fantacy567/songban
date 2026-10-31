# 松伴 · 当前仓库导航

核对日期：2026-10-31；代码基线：`b08c04e`。本节按当前路由和实现整理；下方旧版本记录只用于追溯。

当前项目是 FastAPI + SQLite 的团队协作应用。前台采用原生页面壳，个人讨论工作台使用 React + TypeScript 构建为同源静态资源。账户、团队权限、方向和正式任务沿用现有后端。

## 从哪里看代码

- 页面：`static/songban.html`、`songban.css`、`songban.js`、`songban-views.js`、`songban-library.js`，保持原生静态文件，无构建步骤。
- 真实协作：注册／登录 → 创建或加入小队 → 确认选题与方向 → 个性化分工问答 → 全员确认后内部AI发布任务 → 领取任务／同步成果 → 同伴检查 → 交付核对／复盘。团队数据沿用 `/api/core`。
- 登录：密码走 `POST /api/studio/login`；验证码走 `POST /api/studio/login-code`；验证码发送仍走 `/api/studio/codes`。短信服务未配置时明确返回错误，不模拟已发送。
- 活动目录仍是带明确标记的虚构样例；团队模型需要服务端配置。浏览器测试使用隔离的短信和模型替身，不证明真实供应商已经可用。
- 兼容：旧核心工作台保留 `/core`；`SONGBAN_CORE_ONLY=0` 继续启用旧 studio 默认入口。旧学习演示源码和会话 API 保留，统一前台不将演示会话当成团队授权。
- 启动：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8886`。
- [app/main.py](app/main.py)：应用工厂、数据库初始化、页面入口、模块注册、历史项目及学习体验 API。
- [app/onboarding.py](app/onboarding.py)：访客入口、兴趣选择校验与个人偏好保存；访客继续使用现有账号令牌与团队权限。
- [app/studio.py](app/studio.py) 与 [app/sms.py](app/sms.py)：现有账号、密码／验证码登录及短信适配；`studio.py` 同时保留历史业务。
- [app/team_core.py](app/team_core.py) 与 [app/core_workflow.py](app/core_workflow.py)：团队、共同方向、同步记录、统筹、队长确认、任务检查和下一步建议，接口前缀 `/api/core`。
- [app/materials.py](app/materials.py) 与 [app/materials_parse.py](app/materials_parse.py)：个人／团队资料空间、文档与图片解析、人工修订和交接草稿，接口前缀 `/api/materials`。
- [app/workbench.py](app/workbench.py) 与 [app/workbench_model.py](app/workbench_model.py)：私人讨论会话、模型请求、恢复及明确共享，接口前缀 `/api/workbench`。
- [static/songban.html](static/songban.html)、[static/songban.js](static/songban.js)、[static/songban-views.js](static/songban-views.js)：统一页面壳、路由、登录和团队页面；`songban-materials.*` 承载资料入口，`songban-landing.css` 与 `landing/` 承载首页样式和素材。
- [frontend/workbench/](frontend/workbench/)：React 工作台源码；构建输出为 `static/workbench/workbench.js` 和 `workbench.css`。修改这个模块需要重新构建。
- [plugins/](plugins/)：原生连接器及项目 MCP／命令行适配；安装与宿主核验在 `app/connector_plugin.py`、`app/team_install.py`、`app/plugin_host.py`。
- [tests/](tests/)、[scripts/](scripts/)、[docs/](docs/)：自动化测试、构建／验收／运维脚本、接口与规划及验收记录。

## QQ 邮箱登录配置

在仓库私密 `.env` 中配置 `QQ_SMTP_EMAIL`（QQ 或 Foxmail 发件地址）和 `QQ_SMTP_AUTH_CODE`（SMTP 授权码，不是 QQ 密码），然后重启服务。模板见 [.env.example](.env.example)。授权码获取方式见 [QQ 邮箱官方帮助](https://help.mail.qq.com/detail/106/985)。不要将真实配置提交到 Git。

发信使用 `smtp.qq.com:465`，开启 TLS 和证书验证。用户可用其他服务商的有效邮箱收取验证码。`GET /api/studio/email-status` 只说明配置是否齐全，不代表收件成功；真实收件需要用户在登录页点击「邮箱登录 → 获取验证码」并检查收件箱或垃圾邮件。

新邮箱先验证，再填写姓名、能力、目标和密码完成注册。访客注册会保留个人身份及已保存资料。已有手机号账号应先登录，在右上角「账号 → 绑定邮箱」完成验证，避免注册成另一个账号。邮箱绑定后，两种联系方式使用同一个账号和密码。

验证码 10 分钟有效、使用一次后作废，连续验证失败 5 次锁定；发送间隔 60 秒，每邮箱每小时最多 5 次、每来源地址每小时最多 20 次。发送失败不留下可登录的验证码，页面及接口不返回邮箱验证码或 SMTP 授权码。

实现：`app/email_delivery.py`（QQ SMTP），`app/email_login.py`（邮箱身份与验证码）。回归：`.venv\Scripts\python.exe -m unittest tests.test_email_login tests.test_dual_login tests.test_environment tests.test_sms`；测试均隔离真实发信。

## 当前页面与业务流程

默认 `SONGBAN_CORE_ONLY=1`，`/` 与 `/learning` 都返回 `static/songban.html`，提供「活动／实践」统一前台。

1. `#/login`：品牌首页与登录弹窗。支持手机号／邮箱加密码、短信验证码、邮箱验证码。已有手机号账号在右上角「账号」中绑定邮箱后，继续使用同一份团队和资料；未配置的验证码服务如实显示不可用。
2. `#/onboarding`：选择兴趣、做过的事情和可投入时间，选填城市与经历；无需登录。保存后进入 `#/events`、`#/event` 活动目录与详情，当前活动是明确标注的虚构样例。
3. `#/team`、`#/members`：创建／加入小队、成员资料与团队设置。
4. `#/materials`、`#/work`：导入资料，在个人或团队范围内进行本人的私有讨论。讨论须明确共享后才进入团队记录。
5. `#/direction`：队长核对并保存共同目标、规则、评分要求、不做事项和截止时间。
6. `#/tasks`：个人任务显示总体进度，团队任务显示成员名片、各自进度条和任务清单；进度按已验收任务数计算。真实小队保留同步进展、统筹、队长确认和同伴检查；模拟小队提供 4 位成员与可操作的示例任务。
7. `#/tools`、`#/library`：连接个人工具、查看明确共享的团队资料与对话记录。
8. `#/delivery`、`#/review`：交付核对、交接记录导出及团队复盘。

**容易混淆的入口：** `#/work` 是讨论工作台，正式任务在 `#/tasks`；`#/onboarding` 是已接入的兴趣选择页，成员设置仍在 `#/members`；`#/ideas` 映射到方向页，`#/collaboration` 映射到工作台。旧 `static/learning.*` 和 `/api/learning/v1/sessions` 仍保留，不能把体验会话当成真实团队授权。

兼容页面 `/core`、`/classic` 仍在；设置 `SONGBAN_CORE_ONLY=0` 会将根入口切回旧 studio，并开放兼容接口。日常开发以统一前台和对应模块为准，勿因文件同名相似而改到旧页面。

## 本机网址清单

以下端口状态于 2026-10-31 在当前电脑核对。`127.0.0.1` 仅指打开链接的这台电脑；这些地址不代表公网部署。

### 当前项目：8893

当前服务运行正常。无需手机号登录：首次保存兴趣或进入工作台、活动详情等页面时会建立独立访客身份，沿用现有权限保存自己的数据。团队页面仍需创建或加入小队；已有账号可选择登录。访客凭证保存在当前浏览器，退出或清除网站数据后不能靠手机号找回该访客空间。

- [http://127.0.0.1:8893/](http://127.0.0.1:8893/)：主站入口。
- [http://127.0.0.1:8893/#/login](http://127.0.0.1:8893/#/login)：品牌首页，点击登录打开账号弹窗。
- [http://127.0.0.1:8893/#/onboarding](http://127.0.0.1:8893/#/onboarding)：兴趣、城市、经历和时间选择，保存后继续浏览活动。
- [http://127.0.0.1:8893/#/events](http://127.0.0.1:8893/#/events)：样例活动列表。
- [http://127.0.0.1:8893/#/event?id=education-agent-weekend](http://127.0.0.1:8893/#/event?id=education-agent-weekend)：教育 Agent 创作周末样例详情和比赛资料入口。资料整理结果集中显示比赛时间、地点、赛道、提交截止、组队要求、展示安排、提交内容和评分标准；缺失信息标为待补充，活动日期不会作为提交截止时间。
- [http://127.0.0.1:8893/#/team](http://127.0.0.1:8893/#/team)：创建、加入或查看小队。
- [http://127.0.0.1:8893/#/direction](http://127.0.0.1:8893/#/direction)：共同方向、比赛规则与截止时间；队长保存。
- [http://127.0.0.1:8893/#/work](http://127.0.0.1:8893/#/work)：本人讨论工作台，支持个人空间及团队范围内的私有讨论。
- [http://127.0.0.1:8893/#/tasks](http://127.0.0.1:8893/#/tasks)：个人／团队进度、成员名片、正式任务与统筹；可切换 4 人模拟小队。
- [http://127.0.0.1:8893/#/tools](http://127.0.0.1:8893/#/tools)：个人工具连接与插件安装入口。
- [http://127.0.0.1:8893/#/library](http://127.0.0.1:8893/#/library)：团队已共享的对话和资料记录。
- [http://127.0.0.1:8893/#/materials](http://127.0.0.1:8893/#/materials)：个人／团队资料导入、解析、整理与交接。
- [http://127.0.0.1:8893/#/members](http://127.0.0.1:8893/#/members)：成员资料和团队设置。
- [http://127.0.0.1:8893/#/delivery](http://127.0.0.1:8893/#/delivery)：交付要求核对和交接记录导出。
- [http://127.0.0.1:8893/#/review](http://127.0.0.1:8893/#/review)：团队复盘。

兼容路由 `#/ideas` → `#/direction`、`#/collaboration` → `#/work`；`/learning` 是同一主站的另一个入口。它们不是独立的网站。

### 仓库保留的旧页面

- [http://127.0.0.1:8893/core](http://127.0.0.1:8893/core)：旧「团队同频」界面，当前可访问，沿用真实账号和团队接口。
- [http://127.0.0.1:8893/static/learning.html#/onboarding](http://127.0.0.1:8893/static/learning.html#/onboarding)：仓库原有的学习体验／兴趣选择页，使用样例流程，与真实团队授权隔离。该源码仍在仓库，和已删除的 8906 临时演示不同。
- [http://127.0.0.1:8893/classic](http://127.0.0.1:8893/classic)：更早的项目协作界面；当前核心模式锁定，实测 HTTP 423。
- [http://127.0.0.1:8893/workflow](http://127.0.0.1:8893/workflow)：历史图形流程页；当前核心模式锁定，实测 HTTP 423。

### 开发与测试

- [新版家长报告演示：8900](http://127.0.0.1:8900/#/review)：在复盘底部点击「生成家长报告」。服务端只读取当前孩子的兴趣、经历、本人分工与任务成果、同伴反馈和复盘草稿，实际调用已配置的模型生成过程概述、成长观察和家庭陪伴建议；页面支持复制文字、下载独立 HTML 和浏览器打印为 PDF。顶部可切换孩子；选择「已有成果与验收进度」可演示更完整的报告。任务状态和事实直接来自记录，模型观察附依据，缺少资料如实显示。生成失败或额度不足会显示错误，不用固定报告冒充模型输出。其他演示流程仍使用预设回复。
- [全流程预填演示：8899](http://127.0.0.1:8899/#/onboarding)：无需输入账号，兴趣、城市、经历及各步文字输入（含选填材料、链接和作者）已预填为教育类黑客松的完整虚构案例。提供 5 位模拟成员、5 个选题对话，以及“从选题到领取任务”和“已有成果与验收进度”两个场景。顶部可切换成员、流程步骤，或点击“补入示例”填回空白输入。方向页先点击“开启选题讨论”，再点“填入 5 人讨论”“下一位队友确认”，可依次展示 3/5、4/5；本人确认、投票和队长确认仍点击页面原有按钮，其他人的投票、任务领取可用顶部模拟按钮完成。赛规、五人群聊、成果报告、检查说明、AI 提问及复盘均有具体案例文字；材料保存和 AI 发送后的空白会自动补回，手动修改或主动清空会保留，点击“补入示例”只补空白。案例集中维护在 `static/songban-demo-content.json`。该旧演示服务的模型回复、网页链接内容和工具连接均为模拟；真实模型家长报告使用上面的 8900 入口。
- 重开这份演示：`.\.venv\Scripts\python.exe scripts/run_demo.py --port 8899`。每次启动使用 `.browser-cache/demo/` 下新建的独立数据库，不读取主站数据；演示改动只保存在本次演示数据库。主站 `8893` 的代码和账号入口不自动启用演示脚本。新版启动脚本仅为家长报告读取服务端模型配置，其余演示调用保持隔离；使用 `--resume 私密恢复清单.json` 可保留演示数据库与身份。

- [http://127.0.0.1:8893/health](http://127.0.0.1:8893/health)：服务和数据库健康状态，当前返回正常；不证明真实模型调用或短信发送已验收。
- [http://127.0.0.1:8893/api/docs](http://127.0.0.1:8893/api/docs)：Swagger API 调试入口。HTML 返回正常；界面依赖外部资源，展示仍受网络与页面安全策略影响。
- [http://127.0.0.1:8893/api/openapi.json](http://127.0.0.1:8893/api/openapi.json)：机器可读的接口说明。包含兼容接口，不代表核心模式下全部开放。
- [http://127.0.0.1:8896/](http://127.0.0.1:8896/)：当前运行的隔离工作台 QA 服务，由 `scripts/qa_workbench_server.py` 启动；使用合成账号、独立数据库和模拟模型回复。
- `8886`：历史文档的启动示例端口，当前未监听。`8890`、`8892`、`8905` 当前也未监听。
- `8906`：本次临时免登录演示已按要求关闭，相关目录已移入回收站，不能再用作入口。

### GitHub 与外部参考站

- [GitHub 仓库](https://github.com/Fantacy567/songban)：项目源码；当前开发分支为 [feat/material-intake](https://github.com/Fantacy567/songban/tree/feat/material-intake)。GitHub 仓库地址不是运行网站。
- [线上参考演示首页](https://songban-hackathon-preview-20261030.social-cat-4573.chatgpt.site/#/login)：此前用户指定的独立演示站。
- [线上参考演示兴趣选择](https://songban-hackathon-preview-20261030.social-cat-4573.chatgpt.site/#/onboarding)、[线上参考演示工作流程](https://songban-hackathon-preview-20261030.social-cat-4573.chatgpt.site/#/work)：同一参考站的页面，可能受其浏览器体验状态影响；与本机 8893 的真实团队数据独立。本次只核对仓库中的引用，没有修改或重新部署该站点。

## 启动与构建

Windows PowerShell，首次安装：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8893
```

打开 `http://127.0.0.1:8893/`；健康检查为 `/health`，接口定义为 `/api/openapi.json`。端口已运行时直接访问，不重复启动。macOS／Linux 将 Python 路径换为 `.venv/bin/python`，端口也可按需调整。

仓库已包含工作台构建产物。修改 `frontend/workbench/` 后运行：

```sh
npm ci
npm run typecheck:workbench
npm run build:workbench
```

SQLite 默认位于 `data/collab.sqlite3`，可通过 `DATABASE_PATH` 调整。`.env`、数据库、私人连接配置和 `.browser-cache/` 均不入库。模型及短信配置见 `.env.example` 和[短信配置说明](docs/core-collaboration/短信服务配置.md)；健康检查或配置存在不代表外部服务已经实际验收。

## 验证与后续整理

在独立测试环境安装 `requirements-test.txt` 后运行兼容回归；CI 使用相同的模式，测试模型和短信均为替身：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
$env:SONGBAN_CORE_ONLY = '0'
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
npm run typecheck:workbench
npm run test:workbench
```

原生插件测试需要 Codex CLI；工作台浏览器测试需要 Playwright 浏览器，可用 `SONGBAN_CHROMIUM_EXECUTABLE` 指定已有 Chromium／Edge。测试应使用隔离数据库和配置，不在真实团队中写入验收数据。当前 GitHub Python 工作流覆盖 Windows／Linux 的 Python 回归，尚未包含工作台 TypeScript 与浏览器检查。

兴趣引导和免登录访客入口已接入；私人兴趣通过 `/api/core/me/preferences` 保存到 SQLite，其他账号和团队连接器不能代为读写。当前仍需收口：参考演示的逐步执行体验尚未完整接入真实协作；活动数据仍为样例；真实报名、正式提交回执及家庭成长功能不能按规划文档宣称已实现。后续应先统一入口和真实业务状态，再逐项迁移体验，避免增加另一套账号、任务或团队事实。

现行开发边界见[项目工作台宪法](docs/planning/项目工作台宪法.md)、[接口契约](docs/planning/项目工作台接口契约.md)及[统一前台接入说明](docs/core-collaboration/统一前台接入说明.md)。家庭学习与成长功能的[规划目录](docs/planning/README.md)、[Spec Kit 宪法](.specify/memory/constitution.md)包含草案内容，功能状态须对照所在分支的实现和测试。

以下保留此前代码入口与阶段记录；其中旧入口、启动命令和能力描述若与本节冲突，以本节及实际代码为准。

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

### 选题公示与团队适配排名

`#/ideas` 公示队员idea与可行性对话，全员确认后由队长发起AI适配排名，依据成员能力、可投入时间和公开评分维度，不自动选题。`#/idea-library` 为选题库，`#/library` 为开发/复盘库；原记录保留。详见[选题公示与团队适配决策](docs/core-collaboration/选题公示与团队适配决策.md)。

新队伍必须先在选题公示中明确确认最终选题，才开放方向与任务；赛事评分资料在选题页先填写。首次选题共享可自动建立本人idea并直接呈现对话。原生连接器1.2.1改用桌面实际Codex宿主安装检查，旧会话需重新选择插件刷新工具。


### 分工问答与内部AI发布（2026-10-31）

保存共同方向后进入`#/division`，逐位确认职责、能力边界、可用时间和交付要求；最后一位确认后由内部AI生成并发布任务。成员进入`#/work`领取任务，`#/team-work`看全队进度。主导航仅保留选题、方向、分工、任务、提交、复盘；连接器和资料库折叠为辅助入口。模型失败保留回答，明确重试，不生成假任务。新团队不再使用队长手动发布，历史计划及其原确认人保留。详见[分工接入与验证](docs/core-collaboration/分工问答与内部AI任务发布.md)。

## 两个分支合并后的流程兼容

新建团队保留访谈、赛事资料、公示选题、分工问答、任务检查及家长报告分享流程。已有选题投票轮次继续全员确认、排名、一人一票、平票重投和队长确认，不能通过另一套选题接口绕过投票。连接器 1.3.0 同时提供两类共享工具及资料检索。

`python -m uvicorn app.preview_server:app --host 127.0.0.1 --port 9017` 提供正常入口和 `/demo/` 隔离引导演示（模型为明确标记的测试替身）。`scripts/run_demo.py` 的五人演示保持独立入口，其复盘家长报告仍使用服务端真实模型配置；新增入口不会把这项调用改成静态报告。邮箱登录及 QQ SMTP 配置继续保留。

## 版权与项目归属

松伴由 **2292576833、Fantacy567、andorwu5-dev 共同拥有**。AI 工作台由 2292576833 负责，前端与后端由 Fantacy567 负责，美术设计由 andorwu5-dev 负责。完整声明见 [COPYRIGHT.md](COPYRIGHT.md)。
