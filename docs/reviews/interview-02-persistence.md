# INTERVIEW-02 · 个人访谈持久化与认证接口 · 待 Codex 验收

## 接口卡（先定后做）

所有端点都在 `/api/core/interview` 下，只接受网页登录的 `Authorization: Bearer <登录令牌>`。身份复用 `register_core` 里现有的 `person()`（查 `people.token_hash`）。插件凭证（`sbconn_` 开头）一律返回 403 `browser_required`；未登录或令牌失效返回 401 `unauthorized`。客户端不能指定 `user_id`、`asked_count`、问题编号或模型。错误格式沿用全站约定：`{"error":{"code":"…","message":"…","details":{…}}}`。

### 状态对象（所有成功响应都返回它）

```json
{"status":"asking","version":3,"asked_count":2,"max_questions":30,"age_band":"undisclosed","stage":"university",
 "messages":[{"id":"q1","role":"assistant","text":"你最近最想做点什么？","number":1},
             {"id":"u2","role":"user","text":"想做一个求职作品集里的小工具。"},
             {"id":"q3","role":"assistant","text":"你希望看这个作品的人最先注意到什么？","number":2}],
 "current_question":{"id":"q3","text":"你希望看这个作品的人最先注意到什么？","number":2},
 "profile":null,
 "source":{"kind":"model","model":"protocol-substitute"},
 "replayed":false,"created_at":"…","updated_at":"…"}
```

- `status` 只有四种：`not_started`（只有这一个字段）、`asking`、`pending_confirmation`、`confirmed`。
- `version` 是状态版本：开始后为 1，之后每次成功的回答、提前结束或确认各加 1。模型失败或请求被拒绝时不变。
- `asked_count` 由服务端从数据库里的助手提问条数算出，不接受客户端传入。最多 30 个。
- 消息 ID 由服务端生成：助手提问是 `q<序号>`，用户回答是 `u<序号>`，序号在本人访谈内递增。
- 内部追问目的 `purpose` 只存在数据库里，不在任何响应中返回。
- `source` 表示最近一次生成来自哪里：`{"kind":"model","model":"…"}` 表示模型生成；`{"kind":"no_answers","model":null}` 表示还没有任何回答就提前结束，引擎直接给出空草稿，没有调用模型。
- `replayed=true` 表示这是同一 `request_id` 的重复提交，服务端没有重新处理，返回的是当前状态。
- 待确认或已确认时，`profile` 为：

```json
{"status":"pending_confirmation","draft":{"interests":[{"text":"…","basis":"self_reported","evidence":["u2"]}],"goals":[],"experiences":[],
 "possible_strengths":[],"roles_to_try":[],"help_needed":[],"time_available":null,"next_practice":[],"conflicts":[],"unknowns":["…"]},
 "missing_fields":["goals","…"],"reason":"user_finished","model":"protocol-substitute","confirmed_at":null}
```

  确认后 `profile.status` 变为 `confirmed`，`confirmed_at` 为确认时间，草稿内容不变。

### 端点

| 端点 | 请求正文 | 作用 |
| --- | --- | --- |
| `GET /api/core/interview` | 无 | 读取本人当前状态；没开始过返回 `{"status":"not_started"}`，不调用模型 |
| `POST /api/core/interview/start` | `{"age_band":"可选","stage":"可选"}` | 开始访谈，由模型生成第一问 |
| `POST /api/core/interview/answer` | `{"version":3,"question_id":"q3","request_id":"客户端生成","text":"回答"}` | 回答当前问题，保存回答以及下一问或草稿 |
| `POST /api/core/interview/finish` | `{"version":3,"request_id":"客户端生成"}` | 提前结束，生成待确认草稿 |
| `POST /api/core/interview/confirm` | `{"version":4,"request_id":"客户端生成"}` | 确认当前版本的已有草稿，不调用模型 |

字段规则（多出字段、类型不对都返回 422 `invalid_input`）：

- `age_band`：`undisclosed`、`under_13`、`13_18`、`19_25`、`26_plus`，或省略，表示不透露。
- `stage`：`undisclosed`、`primary_school`、`secondary_school`、`university`、`job_seeking`（就业探索）、`working`、`other`，或省略。
- `version`：正整数，不接受布尔值。
- `question_id`：必须等于当前问题的 ID。
- `request_id`：8–64 位 `[A-Za-z0-9_-]`，由客户端为每一次操作生成；重发同一次操作时必须沿用。
- `text`：文字，去掉首尾空白后为 1–1000 字，不能含控制字符。

### 一次回答怎样保存

1. 读取当前状态（只读事务，读完即关闭）。
2. 如果这个 `request_id` 已经处理过：内容相同就直接返回当前状态（`replayed:true`），不再调用模型；内容不同返回 409 `request_id_reused`。
3. 依次检查：访谈必须处于提问中，否则 409 `interview_closed`；`version` 必须是当前版本，否则 409 `version_conflict`，`details.current_version` 给出当前版本；`question_id` 必须是当前问题，否则 409 `stale_question`。
4. 同一进程里，同一个人同一时间只允许一个模型调用，否则 409 `interview_busy`，可以稍后重试。
5. 按数据库里的历史加上这次回答，调用 `next_turn`。**模型调用期间不持有任何数据库事务或锁**。
6. 写入事务（`BEGIN IMMEDIATE`）里再次核对 `request_id` 和版本：版本已经变了，返回 409；没变，就把本次回答、下一问或草稿、请求记录和新版本一起写入，一次提交。

提前结束与此相同（没有 `question_id`）。确认不调用模型，只检查状态是待确认、版本一致，然后标记为已确认。

### 示例

开始：

```text
POST /api/core/interview/start   {"stage":"university"}
200  {"status":"asking","version":1,"asked_count":1,"current_question":{"id":"q1","text":"…","number":1},…}
```

回答成功，以及同一次请求重发：

```text
POST /api/core/interview/answer  {"version":1,"question_id":"q1","request_id":"req-0001-abcd","text":"想做求职作品"}
200  {"status":"asking","version":2,"asked_count":2,"current_question":{"id":"q3",…},"replayed":false,…}
同一正文再发一次 → 200 {…,"version":2,"replayed":true}
```

失败：

```text
409 {"error":{"code":"version_conflict","message":"访谈已经更新，请刷新后再回答。","details":{"current_version":2}}}
409 {"error":{"code":"stale_question","message":"这个问题已经回答过或不是当前问题，请刷新。","details":{"current_version":2}}}
503 {"error":{"code":"model_not_configured","message":"访谈模型尚未配置……","details":{"retryable":true,"current_version":1}}}
502 {"error":{"code":"model_invalid_json","message":"模型返回的不是合法JSON。……","details":{"retryable":true,"current_version":1}}}
409 {"error":{"code":"interview_exists","message":"访谈已经开始，不能重新开始……","details":{"status":"asking","current_version":2}}}
409 {"error":{"code":"no_draft","message":"还没有待确认的画像草稿。","details":{"status":"asking","current_version":2}}}
```

模型失败（超时、未配置、格式不合格等）沿用 INTERVIEW-01 的错误码和状态码，`details.retryable` 为 true，并带上 `current_version`。原有记录、版本和问题数都不变，客户端可以用同一个 `request_id` 原样重发。

其他受控错误：`interview_not_started`（409，还没开始就回答或提前结束）、`interview_busy`（409，同一个人有一次模型调用正在进行，`retryable:true`）、`already_confirmed`（409）、`request_id_reused`（409）、`empty_answer` 和 `text_too_long`（422）。

## 实际改动

- 新增 `app/interview_store.py`：三张新表，以及 `register_interview(api, db, problem, now, person, runner, scrub)` 和上述五个端点。
  - `core_interviews`：每人一行，主键是 `user_id`，因此每人只有一份访谈，不能重置或删除。
  - `core_interview_messages`：存回答和提问。`purpose` 和 `dimension` 只存不返回；用户回答写入前，用 `team_core.scrub` 把疑似凭据替换掉。
  - `core_interview_requests`：保存 `request_id`、本次正文指纹和处理后的版本，用于识别重复提交。
- `app/team_core.py` 改了三行：
  - `ensure_core_schema` 追加建这三张表（`CREATE TABLE IF NOT EXISTS`，不改动旧表、不迁移旧数据）；
  - `register_core` 新增可选参数 `interview_runner=None`；
  - 在 `person()` 定义之后调用 `register_interview`，所以身份校验就是网页登录用的那一个，没有另建一条认证路径。
- `app/main.py`：`create_app` 新增可选参数 `interview_runner=None` 并传给 `register_core`。不传时，引擎在每次调用时用 `model_runner()` 读取现有服务端模型配置；没有配置就返回 503 `model_not_configured`，不会退回到本地固定问题。
- `app/interview.py`：`STAGES` 增加 `job_seeking`（就业探索）。其他引擎逻辑未改。年龄段和阶段只传给模型，用于调整措辞，不参与任何判断。
- 新增 `tests/test_interview_api.py`，共 20 项测试。
- 没有改动：前端、注册流程、`people.profile` 和 `skills`、团队快照、插件上下文、模型和 provider 配置。

## 测试（真实结果）

所有测试都在不含 `.env` 的临时代码镜像里运行（镜像中没有 `.env`，也没有 `data/`），只使用临时 SQLite 文件和合成账号甲、乙、丙。模型由协议替身 `Script` 代替（一个记录调用并按模式返回的函数），**不代表真实模型的效果**。没有发出任何真实或付费的模型请求。

- `tests.test_interview_api`：**20 项全部通过**。
  - 归属与登录：
    - 开始前读取返回 `not_started`，没有调用模型；
    - 五个端点在不带令牌、令牌错误、Basic 认证三种情况下都返回 401；
    - 甲开始并回答后读取到版本 2、问题数 2、消息 `q1/u2/q3`，响应里没有 `purpose`；
    - 乙读取得到 `not_started`，乙回答、提前结束、确认都被拒绝；
    - 甲的插件令牌访问五个端点都返回 403；
    - 请求里夹带 `user_id` 或 `asked_count` 返回 422。
  - 重启：同一个临时 SQLite 文件三次关闭并重新 `create_app`。提问中、待确认、已确认三种状态都完整保留，重启后还能继续回答，阶段 `job_seeking` 也保留了下来。
  - 重复提交与输入：
    - 同一 `request_id` 重发返回 `replayed:true`，不再调用模型，只有 1 条回答；
    - 同一编号换了正文返回 409；
    - 旧版本返回 `version_conflict`，旧问题返回 `stale_question`；
    - 空回答、超过 1000 字、数字、控制字符、`version` 为 True、`"1"` 或 0、`request_id` 过短或含中文、`question_id` 为列表、缺字段、正文是数组，全部返回 422；
    - 访谈结束后再回答或再提前结束返回 409；
    - 重复开始一律返回 409 `interview_exists`；
    - 以上被拒绝后，再读取的状态完全不变。
  - 并发：
    - 模型调用期间，另开一个连接执行 `BEGIN IMMEDIATE` 能在 0.3 秒内成功，说明没有持有写锁；同时读取到的仍是原状态。
    - 同一个进程内的第二份回答返回 `interview_busy`，最终只保存了第一份回答。
    - 用两个 `create_app` 实例模拟两个进程：快的一份先保存（版本 2），慢的一份返回 409 `version_conflict`，数据库里只有一条回答。
  - 模型失败：
    - 替身模拟不可用（503）和返回非 JSON（502）时，`details={"retryable":true,"current_version":1}`，再读取的状态不变；
    - 用同一 `request_id` 重试后成功，版本变为 2、问题数为 2，只多计一次；
    - 开始阶段失败后仍是 `not_started`，可以重新开始；
    - 不注入模型且没有配置密钥时返回 503 `model_not_configured`，表里没有任何记录。
  - 上限与确认：
    - 问到 30 个问题后，替身仍然提问，被引擎拒绝（502 `question_limit_reached`），状态不变；改为正常替身后，用同一编号重试，得到草稿，`reason=limit_reached`，数据库里恰好 30 个提问，没有第 31 个。
    - 提前结束得到待确认草稿，证据指向 `u2`；确认后模型调用次数不变，草稿内容不变；同一编号重发返回 `replayed`；再次确认返回 `already_confirmed`。
    - 不回答就提前结束：得到空草稿，`source.kind=no_answers`，没有额外调用模型。
    - 没有草稿时确认返回 `no_draft`，用旧版本确认返回 `version_conflict`。
  - 不外泄：甲的回答里放了标记词，并完成确认。以下响应中都找不到这个标记词、内部 `purpose` 或草稿内容：
    - 甲和乙读取团队快照；
    - 甲和乙读取 `/api/core/me`；
    - 插件读取 `context` 和 `my-tasks`；
    - 乙读取 `library`、`history`、`handoff.md`。
    `people.profile` 和 `skills` 仍是原来的值。
- 反向改坏验证：每次只改坏 `interview_store.py` 的一处，测试都会失败，共 10 处，全部被抓到：
  - 保存前不再核对版本；
  - 不识别重复的 `request_id`；
  - 模型调用期间持有写锁；
  - 去掉进程内的忙碌保护；
  - 确认时不核对版本；
  - 放行插件令牌；
  - 允许多余字段；
  - 在响应里返回 `purpose`；
  - 重复开始不拦截；
  - 不核对 `question_id`。
  改完后镜像里的文件已逐字节恢复。
- 相关回归：`tests.test_interview`、`tests.test_team_core`、`tests.test_interview_api` 共 73 项全部通过。
- 全量 `unittest discover`：208 项中 202 项通过。另外 6 项是已知的沙箱限制，与本次改动无关：3 项 `test_team_install` 因为沙箱禁止创建 `.cursor` 目录，3 项 `test_studio.ExtractTests` 因为没有公网 DNS。

## 限制

- 只交付了后端，**页面和注册流程都还没有接入**。
- 真实模型的效果只有监理做过的烟雾测试，本次的协议替身不代表模型质量。
- 跨进程的保证只有数据库层面的“版本比较 + 原子写入”：同一时刻只有一份结果能保存，不会重复写入，也不会互相覆盖。但多个进程可能同时为同一个人调用模型，并且都付费，只有一份结果被采用。进程内的忙碌保护挡不住其他进程。
- 一次模型调用进行中时，同一个人的其他提交会得到 `interview_busy`。如果进程在模型调用期间崩溃，忙碌标记随进程一起消失，数据库状态不变，可以重试，不会永久锁死。
- 每人只有一份访谈，不提供重置、删除或多份访谈。确认只是把草稿标为已确认，不发布到团队，也不写入 `people.profile` 和 `skills`。
- `request_id` 记录会一直保留，没有清理策略。数据量是每次操作一行，规模很小。
- 回答中疑似凭据的内容，写入前会用 `scrub` 替换，但这是启发式规则，不能保证拦住所有敏感内容。

## 回退

1. 删除 `app/interview_store.py` 和 `tests/test_interview_api.py`。
2. 在 `app/team_core.py` 里，去掉对 `interview_store` 的导入、`ensure_core_schema` 里追加的 `+ INTERVIEW_SCHEMA`、`register_core` 的 `interview_runner` 参数，以及 `register_interview(...)` 那一行。
3. 在 `app/main.py` 里，去掉 `create_app` 的 `interview_runner` 参数和传参。
4. 从 `app/interview.py` 的 `STAGES` 中去掉 `job_seeking`。

三张新表不被其他代码读取，留在库里没有影响；如需清理，可以执行 `DROP TABLE core_interview_requests, core_interview_messages, core_interviews`（SQLite 需要分三条语句执行）。
