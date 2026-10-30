# CORE-01 · 连接器持续同步到团队资料库（最小闭环）· 待 Codex 验收

日期：2026-10-29。执行：Cursor。范围只限 CORE-01；未实施 CORE-02，未加入 AI 规划或家长报告。

## 结论

后端闭环在真实 TCP 隔离服务上验证通过，共 26 项检查，全部通过。验证内容：本机网页登录用户选择一个 Codex 本机会话并勾选授权后，此后每个完成的回合会自动进入本队资料库，同队第二账号可读，另一团队不可读；停止、暂停、撤销、移出团队、服务重启后都不再上传，重新连接也不补传停用期间的内容。

浏览器界面没有实测：Chrome 在当前沙箱内被系统拒绝启动，在沙箱外运行的申请未获批准。浏览器验收脚本已写好，但没有运行过，不能把单元测试或 TCP 结果当作界面实测。

只承诺 Codex 本机会话（按本机安装的 codex-cli 0.145.0 日志格式），不代表 Cursor、WorkBuddy 等工具可用。

## 一、已有功能与本轮真正缺口

接手时，以下未提交代码已经存在（来自上一位执行者）并全部保留：`app/conversation_sync.py`（会话元数据列表、只读新增内容的 `Reader`、后台 `Manager`）、`app/team_core.py` 中的四个持续同步接口、`static/core.js` 中的持续连接卡片与资料库两行显示、`static/core.html` 缓存版本号，以及 5 项隔离单元测试。

本轮核对后确认的缺口，以及处理方式：

| 缺口 | 依据 | 处理 |
| --- | --- | --- |
| 真实 Codex 最终回复的阶段名是 `final_answer`，代码只认 `final` | 本机 codex 程序本体的字符串（未读会话文件） | 两者都接受；仍排除 `commentary` |
| Codex 会把 `<environment_context>`、AGENTS 指令、`<skill>` 等注入为“用户”消息，可能被当作用户原话上传 | 同上 | 优先使用 `event_msg/user_message`（用户实际输入）；兜底时排除注入前缀 |
| 会话首行（含内置说明）可能超过 64KB，导致会话不出现在列表 | 真实 `session_meta` 含 base_instructions | 首行读取上限提高到 2MB（仍只取 id/cwd/开始时间） |
| 在“我的连接”暂停或撤销时，后台任务要等下一次轮询才停 | 代码审查 | 暂停/撤销该连接时立即停止任务 |
| 临时数据库错误被当作权限变化而永久停止；其他 4xx 错误会无限重试 | 代码审查 | 只有 401/403 视为权限变化并停止；被拒收的内容（除 429 外的 4xx）可见地停止；其他错误继续重试，并显示“等待重试” |
| 服务关闭后，持续同步连接在“我的连接”里仍显示为有效 | 代码审查 | 关闭时撤销本进程的持续同步连接；写库失败也不阻断关闭 |
| 缺少真实 TCP 与浏览器验收 | 任务要求 | 新增两份验收脚本；TCP 已通过，浏览器未运行 |
| 测试里有像密钥的字面量 `sk-fake-...` | 任务要求清理 | 改为运行时拼接的合成值，源码中不再出现像密钥的字面量 |

没有新增产品需求。核心版没有“退出团队”入口，本轮也不新增，只在隔离库中删除成员关系来模拟。

## 二、修改文件与用途

- `app/conversation_sync.py`：改了四处，分别是接受 `final_answer`、以用户实际输入为准并排除注入消息、首行读取上限提高、错误分类（权限变化停止、拒收停止、临时错误重试）。另外 `close()` 现在返回被停止的连接编号。
- `app/team_core.py`：关闭时撤销持续同步连接（容错）；`PATCH connections/{cid}` 暂停或撤销时立即停止对应任务；新增 `import sqlite3`。
- `tests/test_continuous_sync.py`：从 5 项增加到 8 项。新增覆盖：当前 Codex 回合结构、拒收内容停止、在连接列表暂停/撤销后立即停止、关闭时撤销；同时把伪凭据改为运行时拼接，并区分临时错误与权限拒绝。
- `scripts/continuous_sync_acceptance.py`（新增）：真实 TCP 隔离验收。它会建立不含 `.env` 的代码镜像、临时数据库、临时 HOME 下的合成 Codex 日志，使用空闲回环端口，并写出证据 JSON。
- `scripts/continuous_sync_browser.cjs`（新增，未成功运行）：真实 Chrome 界面验收，覆盖选择会话、未勾选授权、连接、两行格式、自动刷新、队友可见、停止。
- `docs/reviews/core-01-connector.md`、`docs/reviews/core-01-evidence/tcp_acceptance.json`：本报告与 TCP 证据。
- `NEXT.md`：更新顶部交接条目。
- 未改：`static/core.js`、`static/core.html`（沿用已有卡片和 `20261029-6` 版本号）、模型或 provider、全局配置、8886 服务。

## 三、真实接口与启动方式

以下接口都要求网页登录令牌，并且请求必须来自本机回环（检查 Host、客户端地址、转发头、Origin 和 Sec-Fetch-Site）。插件连接令牌不能代替网页登录。

- `GET /api/core/continuous-sessions`：本机最近 30 个 Codex 会话的编号、开始时间和工作目录，不含正文。
- `GET /api/core/teams/{sid}/continuous-sync`：本人在本队的状态，值为 `disconnected`、`running`、`retrying` 或 `stopped`，附带已上传轮数、最近记录号和错误说明。
- `POST /api/core/teams/{sid}/continuous-sync`，正文 `{"thread_id": "...", "consent": true}`：`consent` 必须恰好为 `true`；会话必须在本机列表中。
- `DELETE /api/core/teams/{sid}/continuous-sync`：停止并撤销该连接。
- `PATCH /api/core/teams/{sid}/connections/{cid}`，`pause` 或 `revoke`：若对应持续同步连接，立即停止。
- 入库沿用 `conversation-notes` 的保存逻辑（`capture_only`，不触发统筹）；读回用 `GET /api/core/teams/{sid}/library`，网页按“**注册姓名：用户原文** / 实际模型名：回复要点”两行显示，未知模型显示“模型名未获取”。
- 正式服务的启动命令不变：`.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8886`。本轮未重启 8886，正式服务尚未加载这些改动。

## 四、执行命令与结果

单元测试和隔离服务都在仓库镜像中运行，镜像排除了 `.env`、`data/`、`.songban/`、`.codex/` 等目录，因为导入 `app/main.py` 时会自动读取仓库根目录的 `.env`，且其中的 `DATABASE_PATH` 会覆盖外部设置。

1. 本次改动的单元测试：在镜像中运行 `python -m unittest tests.test_continuous_sync -v`，8 项全部通过。
2. 相关回归：在镜像中运行 `SONGBAN_CORE_ONLY=0 python -W ignore -m unittest tests.test_continuous_sync tests.test_team_core tests.test_core_workflow tests.test_team_connector tests.test_team_install`，共 65 项，62 项通过，3 项报错。3 项报错都在 `test_team_install`，原因是沙箱禁止在临时目录创建 `.cursor` 文件夹（`PermissionError`）。这是给 Cursor 写配置的安装器测试，与本次改动无关，但本轮没有在沙箱外复跑。未运行完整全量，也未运行需要 codex CLI 的 `test_connector_plugin`。
3. 语法与差异检查：`node --check static/core.js scripts/continuous_sync_browser.cjs`、`py_compile`（四个 Python 文件）、`git diff --check` 均通过；在改动文件中搜索 `sk-` 开头的像密钥字面量，没有结果。
4. TCP 验收：`.venv/bin/python scripts/continuous_sync_acceptance.py`，26 项全部通过（两个隔离进程分别使用临时端口 50837、51108，结束后已停止）。
5. 浏览器验收：`node scripts/continuous_sync_browser.cjs` 在沙箱内启动 Chrome 失败（`kill EPERM` / `SIGABRT`），沙箱外运行未获批准，所以没有运行。

## 五、TCP 验收证据，对照验收检查

证据文件：`docs/reviews/core-01-evidence/tcp_acceptance.json`，内含每项检查的名称、结果、状态码和合成资料库的两行内容。证据不含伪凭据，已检查。

- **验收检查 1（现状与缺口）**：见第一节。
- **验收检查 2（历史不入库、两回合自动入库、同队可见、另队不可见）**：在真实 TCP 上通过。连接前写入的历史回合和另一个未选择的会话都没有入库；连接后两回合分别入库；乙账号能读到；丙账号读本队资料库返回 403，丙自己的团队资料库为空。
- **验收检查 3（字段正确、两行显示、脱敏）**：
  - 姓名来自认证账号（甲、乙各自正确）。用户原文取自用户实际输入。回复要点按原文截取，不经模型总结。模型名取自日志 `turn_context`，没有时为空，显示“模型名未获取”。
  - 合成的 `API_KEY=…` 和 `Bearer …` 均显示为 `[已隐藏]`。思考摘要、过程说明、工具输出、环境注入、技能注入和旧历史都没有出现。服务日志也不含伪凭据。
  - 两行格式在 TCP 层核对了内容；“加粗”和“页面自动刷新”需要浏览器才能确认，未实测（见第六节）。
- **验收检查 4（去重、临时失败）**：重复写入同一回合后，资料库对应记录仍只有 1 条。把隔离数据库设为只读后追加回合，状态显示“等待重试”，已上传计数不变；恢复写权限后只补传 1 次，没有重复。
- **验收检查 5（停止与重连）**：
  - 停止后，追加的回合不入库，连接被撤销。
  - 在连接列表中暂停后，任务立即停止；随后恢复该连接也不会继续上传。撤销同样立即停止。
  - 在隔离库中移出成员后不再上传，该成员读状态返回 403。
  - 重新连接不补传停用期间的回合。
- **验收检查 6（拒绝与重启）**：
  - 以下请求都被拒绝：缺少授权、授权值不是 `true`（422）；未登录（401）；Host 不是本机、带转发头、跨站 Origin（403）；用插件连接令牌冒充网页登录（401/403）；另一团队账号开启、读取或停止本队同步（403）；指定任意路径的会话（404）。
  - 正常关闭服务时撤销了持续同步连接。启动新的隔离进程后状态为“未连接”，重启期间和重启后追加的回合都不入库。
  - 整个过程中没有生成草案，也没有调用模型（测试替身一旦被调用就会留下标记，验收时未发现）。
- **验收检查 7（浏览器）**：未验证，见第六节。
- **验收检查 8**：见第四节。

## 六、未验证项与已知限制

- **浏览器界面没有实测**：选择会话、授权勾选、成功提示、停止，以及资料库第一行加粗、第二行普通字和停留页面自动刷新，都没有在真实浏览器中看过。脚本 `scripts/continuous_sync_browser.cjs` 已写好，需要在允许启动 Chrome 的环境中运行，它会在 `docs/reviews/core-01-evidence/` 下写出 `ui_*.png` 和 `ui_acceptance.json`。
- **没有用真实 Codex 会话验证**：日志格式依据本机 codex-cli 0.145.0 程序本体的字符串（`final_answer`、`commentary`、`TurnCompleteEvent.last_agent_message`、`UserMessageEvent` 以及注入标记），再用合成日志验证；按要求没有读取或选择任何私人会话。Codex 升级后格式可能变化。
- **非回环客户端地址没有在真实 TCP 上测**：那需要把隔离服务绑定到局域网地址。真实 TCP 上测的是 Host、转发头和跨站来源；客户端地址为 203.0.113.3 的情况由单元测试覆盖。
- **核心版没有“退出团队”入口**：本轮用直接删除隔离库成员关系来模拟。
- **进程被强杀（SIGKILL）时，持续同步连接在库里不会被标记撤销**：这条连接仍算在每人最多 10 条的有效连接里，直到用户撤销或 30 天后过期；但明文令牌只在内存里，重启后无法再使用，新进程也不会恢复采集。
- 同步依赖松伴本机服务保持运行，每 2 秒检查一次。
- 回复要点只是截取前 800 字的原文，不是摘要。
- 8886 没有更新，真实环境里还没有开启任何对话同步，不能宣称用户已经在自动同步。

## 七、回退方式

- 不涉及数据库结构变化。持续同步产生的连接名为“Codex持续同步 · 会话前8位”，可以在网页“我的连接”中撤销。资料库里已入库的记录与手动同步的记录格式相同。
- 只回退本轮改动：删除 `scripts/continuous_sync_acceptance.py`、`scripts/continuous_sync_browser.cjs` 和 `docs/reviews/`，再撤销 `app/conversation_sync.py`、`app/team_core.py`、`tests/test_continuous_sync.py` 中第二节列出的改动。上一位执行者的未提交代码仍保留，不要用 `git checkout` 整体还原这些文件。
- 整体停用持续同步：在 `app/team_core.py` 中去掉 `conversation_sync` 的导入与 `/continuous-*` 路由，并去掉 `static/core.js` 中的持续连接卡片。原生插件的手动同步不受影响。
- 本轮没有提交、推送或部署，也没有重启或停止其他服务。自己启动的隔离进程和临时目录都已清理。
