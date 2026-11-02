# P0 · UI 页面与状态规格

版本：`learning-ui-p0 1.1.1`；日期：2026-11-02；所有者：S02。同步 S03 契约0.2.1，保留0.2.0起点/检查语义，并补家庭授权恢复。

状态：本轮规格同步完成，供实现与归档消费。只读中央最新联合核对确认：S00已通过G0工程审阅并采用契约0.2.1启动隔离P1；本会话仅收尾P0规格。本文不表示页面、家庭权限、模型、付款或儿童可用性已经验收。本轮不启用新导航、不接主站、不改变运行环境；采用文字页面样板与行为契约，不提供HTML原型。视口与键盘条目是后续验收要求，不能写成实测通过。

## 1. 输入、范围与代码事实

已读本目录总入口、项目宪法 1.0.0、总体框架 1.0.0、UI 规划 learning-ui 1.0.0、工期 1.0.0、数据边界 contract-intent 1.0.0、验收与发布 1.0.0、决策记录、执行状态、P0、P1、S02 及会话协议。首轮补读 S01 `invitation-lesson 0.1.0`、`invitation-cards 0.1.0`。本次续办重读 S03 0.2.0 contracts全包与接口规格，验证期间收到文件更新后补读 `learning-v2-p0 0.2.1` 的家庭恢复、三个新增GET、样例/条件及冻结字段校验；最终以0.2.1快照核对。首课任务材料与判定以S01为准；HTTP路径、枚举、错误和身份以S03为准；不修改两者文件。

只读基线：工作根 `E:\松伴\songban-pr7-fix`，HEAD `0cf710280869bb920120675b727e543319ea0b88`，存在他人未提交业务修改。旧视觉以 `docs/planning/视觉宪法与 UI 契约.md` 的 design-v1 品牌和实际 CSS 为基础；学习/比赛分离按新宪法覆盖旧“活动/实践”在新学习范围的限制。

核对到的代码事实：

- `static/songban.js` 的 `routePages` 将 `work`/`tasks` 映射个人任务、`team-work` 映射团队任务、`workbench` 映射工作台、`collaboration` 映射分工。但 `routeFromHash()` 在非 `usesIdeaWorkflow()` 分支还会把 `work` 导向工作台或旧 overview、`tasks` 导向旧 overview、`ideas` 导向 direction。迁移必须保留这些历史分支，不能只测新流程的一张路由表。
- `shell()` 目前每次重建壳并卸载工作台；原团队定时刷新可触发 `render()`。学习入口接入时须由 S00 阻止旧轮询重绘学习根节点，不复制该重建方式处理孩子输入。
- `static/songban-onboarding.js` 已收兴趣、做过的事情、时间，城市和经历补充选填；成功后进入活动。它不含正式年龄、AI 起点、家庭关系；`skills` 不能直接当作 AI 熟练度。
- `frontend/workbench/types.ts` 现有职责为 `materials/direction/next_step`。学习四角色使用独立命名空间，旧消息仍按旧名称呈现。
- 旧工作台有本人会话、来源选择、请求状态、实际模型未知和身份失效保护。可借鉴反馈，不把其“unknown 后用户确认新尝试”的界面直接搬到新学习：新学习 unknown 在核对完成前不开放再次运行。
- `static/songban.html` 已有品牌资源、跳到正文、状态区；不改这些文件。既有字标与小松树继续使用，不新增另一套品牌，不伪造 `data-shell` 的实现完成标记。

## 2. 页面与导航契约

### 2.1 两个独立上下文

目标一级导航固定“AI 学习／黑客松”。AI 学习下有“当前学习／我的作品”，家长管理与获准后台是独立身份入口。黑客松保留原活动目录及选题、方向、分工、任务、提交、复盘；学习不创建虚构小队。个人资料不是第三个学习任务区。

开关关闭时保留原壳、原入口及当前书签行为。P4 新链路可用后由 S00 开启新导航：黑客松导航入口指向原活动目录 `#/events`，有进行中项目时另给“继续我的项目”指向经原流程判定的下一步；不能强行统一为 `#/work`。学习标签不能把原 `#/onboarding` 重定向成学习起点。

访问旧书签不询问学习年龄，也不创建课程记录。切换到黑客松前处理未保存输入；切换不会共享学习作品。P6 前无“加入比赛即同步全部资料”行为。

### 2.2 新页面地址与访问规则

以下为 P0 UI 路由建议，S00 冻结并串行注册；本轮未注册。`id` 仅为资源定位，不能作为授权；所有 query 值需校验类型及长度，不承载内容、身份 token 或任意返回网址。

- **L01 学习首页**：`#/learn`。先读当前受限身份、课程与可继续任务。未登录显示介绍与“请家长开启学习”；有效学习者没有记录才显示“开始第一次尝试”。不能在加载失败时显示“你还没开始”。
- **L02 年龄与起点**：`#/learn/start`。服务端当前学习者决定归属。仅补缺失信息；已完成时展示摘要与“调整我的起点”，不自动重做小尝试。`returnTo` 若使用只允许本模块预定义路由键。
- **L03 任务工作区**：`#/learn/run?id={run_id}`。当前关卡由服务端返回，不能以 query 值解锁。缺 id 回 L01 并提示选择任务；无权限/不存在统一说明“这个学习记录暂时不能打开”，不泄漏他人作品名。
- **L04 完成回顾**：沿用 S03 的 run 路由，以建议参数 `#/learn/run?id={run_id}&view=review` 表示回顾子视图，不增加另一个顶级路由，更不占用原比赛 `#/review`。允许查看进行中、补练和待复核的回顾，页标题随状态变化，不一律叫“完成了”。未知 view 回到该 run 当前任务；参数不能改变关卡或授权。
- **L05 作品列表与详情**：`#/learn/works`，建议详情为 `#/learn/works?id={artifact_id}&version={version_id}`。query 中 version 为不透明版本 ID，界面“第2版”来自版本数字；缺省由服务端返回最新可见版本。不可访问版本不回落到他人的公开作品。
- **F01 家长端**：`#/family`。授权核验、本人孩子学习、作品、已发布报告、课程权益。子视图使用受控 `view=learner|report|access`，资源仍由后端验权。不得根据 `role=parent` 获得权限。
- **A01 管理端**：`#/learning-admin`。按分配范围显示待办。建议案件定位 `?case={case_id}`；不存在/无权不给对象信息。管理入口不出现在孩子任务操作栏。

### 2.3 壳与生命周期

学习页面独立根节点建议 `[data-learning-root]`，所有新增样式限制在该根。宽屏沿用约 91px 品牌栏、108px 一级导航和最大 1060px 内容宽度；不能把工作区做成三列。手机一级导航可保留底部两项，正文预留底部安全区；表单输入时底栏不覆盖当前输入或主行动。

身份/路由切换时停当前读取、解绑事件、清除跨身份缓存并使请求代次失效；迟到响应不得写到另一孩子页面。只读状态刷新不替换正在编辑的 DOM、不抢焦点、不跳到页面顶部。状态 epoch 只是 UI 保护，服务端仍须撤销旧管理授权。

## 3. 三张页面样板

以下内容和示例姓名仅作虚构说明。实际活动材料、关卡名和字数限制从绑定的 S01 内容版本读取；本节示例不能作为孩子真实过程、学习评价或报告来源。

### 3.1 样板一：L01 学习首页

**目的**：孩子先知道今天继续做什么，再理解自己在哪里。默认当前任务在三关地图之上。该布局是工程建议；是否适合儿童仍需观察。

桌面从上至下：

1. 页标题“开始我的创作”或“接着上次做”，旁边只标本人学习称呼与“孩子学习模式”。不显示邮箱、手机号或班级排行。
2. 一张跨内容宽度的当前任务卡：作品“班级活动邀请卡”；动作“把邀请的对象和活动安排说清楚”；关卡文本“第 1 关 / 共 3 关”；保存状态；一个主按钮。首次为“开始第一次尝试”，回访为“继续做邀请卡”。副链接“调整帮助方式”进入 L02 摘要，不必重填。
3. 三关地图：每关是编号、短名称、文字状态和当前标记。第 1 关“说清要求”，第 2 关“操作与保存”，第 3 关“检查改进与解释”（冻结名称来自 S01）。`locked` 显示“完成前一步后再来”及实际前置项；`pending_review` 显示“等老师检查”；`needs_practice` 显示“再练一步”；`passed` 显示“这一步已有检查记录”。不以动画或累积对话数点亮。
4. “最近的作品”：至多三项、缩略预览、作品名、版本和状态；“查看全部作品”为普通链接到 L05。没有作品时仅说“保存第一版后，会出现在这里”，不再放第二个开始主按钮。

手机维持相同顺序。地图竖排三节点，不能横向滑动才能找到下一关；近期作品单列。主按钮全宽或足够宽，短状态在按钮上方；欢迎语不占满首屏。768px 采用单列任务卡与地图；1440px 可横排三节点但不改变 DOM 阅读顺序。

初次开始先执行 UIA-02：缺授权去 F01 的进入说明；有授权时可先到 L02 了解起点，也可按服务端 current_action 用保守起点进入首课，missing_fields 不构成强制入门门槛。跳过/未答不伪装成选过帮助方式。已有活动 run 按服务端返回恢复，不为补问档案而重建。回访必须读服务端 resume 目标，不从 localStorage 猜最近任务。待人工复核时主按钮变为“查看检查进展”到 L04，已有草稿保留但不冒充已通过。课程未开通时显示实际报名/授权状态，主按钮为“查看开启方式”，孩子端不出现“立即付款”。

焦点：路由进入后定位 h1（可程序聚焦，不进入常规 Tab 队列）；Tab 顺序为当前主行动、调整帮助、可访问的关卡、作品链接。地图当前节点用 `aria-current="step"`，锁定项是可读说明而非无反应链接；加载期间只给 skeleton 与“正在读取学习记录”，不出现虚假 0% 进度。

### 3.2 样板二：L03 任务工作区

**目的**：孩子能完成当前操作、看懂保存与检查，并在需要时求助。页内只有一个当前主行动；帮助不是默认全屏对话。

桌面布局：标题行“班级活动邀请卡”、第几关、返回学习；下方两列，主区约 2/3、辅助区约 1/3，间距 24px。主区从上至下为一句目标、当前任务卡、材料与输入、结果或作品预览、检查反馈、主行动区；三关位置条放在当前任务内容下方并可折叠。辅助区为当前角色、三个帮助入口、当前工具卡、“找老师帮忙”。完整历史对话折叠且不抢主区高度。

手机和 768px：标题 → 当前目标与任务 → 材料/输入/结果 → 当前行动 → 相邻帮助展开区 → 位置条/历史。辅助列移到主行动后，保留邻近输入的“需要提示”文本触发点。展开帮助不会遮住输入，关闭后焦点回触发点；不使用悬浮聊天气泡。系统键盘打开时当前输入可滚到可视区，行动区在文档流中，不做覆盖输入的固定悬浮条。

任务切片与主行动切换：

- **T1 说清要求**：先展示受控活动资料，再让孩子填写活动名、对象、日期、开始/结束时间、地点、准备物品、邀请目的、表达偏好。字段有可见 label、简短例子入口和材料定位；示例不预填成本人答案。主行动“确认我的要求”：先 PUT requirements 的 confirmed=true（UIA-04），成功后 POST checks 的 stage=clarify、purpose=advance（UIA-08）；保存失败不检查，检查失败保留要求。只有 outcome=advanced、progress_effect=passed_and_unlocked 的回执及最新 run 允许后才显示“进入下一步”（UIA-10）。半成品用次级“保存草稿”、confirmed=false；次级“先看看还缺什么”可发 preflight，但不解锁。不在此偷偷生成成品。
- **T2 操作与保存 · 未运行**：预填孩子自己已保存要求，允许编辑；当前工具卡说明会得到一段可编辑文字。主行动“试着生成”（UIA-05）。先持久化本次输入及 revision，再发受控文本运行；保存失败即停止。不能点击一次触发多个请求。
- **T2 · 运行中**：保留输入快照与请求状态，行动区“正在生成，稍后可以核对”。不启动第二次运行；允许阅读材料、返回 L01 后再恢复。模型输出只显示纯文本/受控结构，不执行 HTML、JS 或模型建议的网址。
- **T2 · 生成成功**：标题“这是一份候选文案，先看看”，标“AI 帮助生成”。主行动“保存这张作品”（UIA-07）。原样采用用 authorship=ai_candidate_unedited，实际编辑后按真实来源标记，不能默认 child_edit。点保存成功才产生不可变作品版本。随后“打开已保存的作品”（UIA-15）：GET 同一版本成功并显示后，孩子明确“我已打开这张作品”提交 readback；取得回读回执后主行动“检查并进入下一步”，发 stage=create、purpose=advance。仅 advanced/passed_and_unlocked 的回执和最新 run 才进入下一关；反馈不满足时留当前步骤。生成、保存、预取或打开按钮点击都不能代替回读回执；是否理解生成/保存区别仍需 M2。
- **T3 · 检查**：上方最新作品和材料并排/手机上下显示，检查时间、地点、邀请对象等绑定 S01 规则；孩子先作判断并解释。主行动“检查我的结果”（UIA-08）：先 POST self-checks 独立保存自查，成功再 POST checks(stage=review,purpose=preflight)。此时可缺反思/迁移，反馈指明尚缺项，不派单、不解锁、不改通过。规则检查、AI 建议、人工结论各自带标签；规则 pass 只显示“这次预检没有发现规则问题”，不显示“已过关”。只有勾选“我检查过了”不等于合格证据。
- **T3 · 改进**：反馈指向具体字段/句子，例如“请对照资料，再看活动地点”。主行动“保存我的修改”（UIA-07），成功产生 v2，旧检查注明“针对 v1”；随后主行动“检查修改后的作品”。若原事实已正确，孩子改进邀请语；不篡改本人作品制造错误。预设错题 `EX_A_WRONG_TIME` 只能单独标“练习样例”。仅换空格、颜色或照抄教练整句不满足 S01 的实质独立修改。不可把 v1 的通过徽章贴到 v2。
- **T3 · 解释与小迁移**：解释“我改了哪里，为什么”；用材料 B 的空白练习区重新填写事实、目的/偏好、本人邀请语和至少两处与 A 不同的说明。不调用模型填写迁移、不预填 A 或 reviewer_only 答案；主作品仍绑定 A，迁移单独存 attempt revision。主行动“保存我的解释”或“提交这次小尝试”（UIA-09）。有具体答案帮助时如实标记并安排新的本人尝试，不隐藏帮助或假称重做同题就是独立迁移。
- **T3 · 提交老师**：依 S01 S3.4，用当前作品、自查、解释、迁移与帮助组成证据集。主行动“保存修改并重新检查”逐项等保存回执，最后只发 stage=review、purpose=preflight。孩子随后明确点“交给老师看看”，才发 stage=review、purpose=submit_review，带完整精确证据引用；服务端重新校验，不能凭旧预检通过派单。HTTP 201 仅表示反馈记录成立；只有 outcome=awaiting_review、progress_effect=pending_review、非空 case_id 才显示“已交给老师”及真实负责人/期限。blocked_support/blocked_evidence/blocked_unknown 均留在可恢复状态，不显示送审成功。M1–M4 由获准人员核对，第三关不以规则全绿自动通过；通过后“看看这次的作品”到 L04。

工具卡先露出“这一步能用它做什么”和三步操作；展开后再见可编辑提示词、检查方法、注意事项、不会时怎么办。没有自由 URL/文件上传/终端按钮。仅接受本课授权的材料与模板；模型候选、手动编辑、示例、成人代录分别标记。

首课内容投影使用材料 A“松果班故事交换会”和材料 B“星叶班纸桥挑战”，页面常驻“这是练习用的虚构活动，不是真实通知”。预览字段严格为 `title/audience/date/start_time/end_time/place/preparation/invitation_line`，按此顺序展示，未知字段不渲染。S01 建议上限为标题40字、邀请语160字、解释300字、目的/偏好120字，最终从版本化内容读取，超限不静默截断。`reviewer_only` 内容不下发孩子端或帮助模型，不能先发到客户端再用 CSS 隐藏。

内容包的 `fixture` 是测试材料性质，API mode `mock/live/replay` 是运行模式：UI 统一显示“模拟练习／真实工具生成／历史回放”，但不将 fixture 原值混传到 API。真实生成使用虚构活动材料不等于 mock；样例练习也不等于真实模型操作达成。R04 的正式操作目标未满足时不能用 mock 通过宣传真实学习效果。

焦点与更新：点保存后用 `role=status` 读出“第 2 版已保存”，焦点不离开保存按钮；显式进入下一步后聚焦新任务标题；提交校验失败聚焦首个错误字段并关联错误说明。生成结束只播报“候选文案已到，可以查看”，出现“查看候选文案”锚点，不强制滚动或抢走输入。检查回执若为用户主动提交可聚焦反馈标题；后台更新只提示有新结果。

### 3.3 样板三：L04 作品与完成回顾

**目的**：让孩子看见真实作品、具体修改和下一步。不能把长报告放在作品前面。

桌面与手机阅读顺序一致：

1. 标题按当前事实为“看看这次的作品”“再改好一个地方”或“作品已收到，等老师检查”。作品预览置顶，标作品版本与保存时间；草稿缺省不画虚假完成卡。内容由固定模板呈现，长中文自动换行。
2. 检查摘要：哪个版本、哪些规则、谁检查、何时检查；“AI 建议”与“已获人工复核”分开。没有记录写“还没有检查结果”，不能写“全部通过”。
3. 一次具体变化：有 v1/v2 字段差异和来源才显示“你补上了活动时间”；否则只列“第 2 版已保存”。可展开前后文字和证据，缺失解释写“还没留下为什么这样改”。
4. “这次我做了什么”：孩子本人操作、本人解释、AI 提示、成人代录/同伴帮助分别标记；无帮助记录仅说“没有记录到线上提示”，不能推断完全独立。
5. 当前主行动及出口：`needs_practice` 为“去改这个地方”回 L03 并定位问题；`pending_review` 为“查看检查进展”展开案件；`passed` 且存在已发布、有权益的下一课才为“继续下一课”。MVP 只有一课时主行动“看看我的作品”到 L05，说明“这次练习先到这里”，不放空的下一课按钮。

手机单列，过程明细默认折叠；桌面允许作品与检查摘要两列，但 DOM 仍先作品后检查，具体修改在其下整行。地图只作页尾回看，不覆盖成果内容。

待人工复核必须显示真实负责岗位/已分配人员、预计反馈时间和联系出口。0.2.0 的检查送审在无值班时可返回201与 outcome=blocked_support、progress_effect=none、case_id=null，表示已存反馈但未派单；单独求助 NewCase 无配置仍为503 support_unavailable。两者均显示“人工支持尚未开放，你可以先保存并返回作品”，不得混称“已交老师”。历史案件有队列负责人但尚未认领时写“等待老师接手”；异常缺负责人/时限写“反馈安排尚未确认”并转真实支持出口，不能假填“24小时”。正式试点前缺负责人或时限是阻塞项。到期未处理写“还没收到检查结果，我们保留了这次作品”，提供案件联系入口，不生成催促次数游戏。

本人报告事实核对是 L04 的可选子区，不等于家长报告已发布：只展示 S03 允许的本人有限事实与来源。孩子可“这些记录需要改一处”提交 dispute，不能编辑观察结论或发布报告；未解决异议时不提示“已经发给家长”。此动作归 UIA-17。

焦点：进入页聚焦与状态匹配的 h1；展开版本差异保持 summary 焦点；“去改这个地方”带受控字段键，目标字段不存在就定位任务标题；不使用任意 selector。返回 L04 保留上次展开位置，但重新核验检查与版本。

## 4. L02 年龄、经历与起点

### 4.1 一次只问一个主题

称呼沿用已授权学习档案；没有称呼时单独走 profile，不混入起点 answers。起点六主题依次为年龄段、AI经历、兴趣、帮助偏好、静态小尝试、起点选择；每页只问一个主题，标题显示真实剩余步骤，不固定声称“一分钟”。每页主按钮“保存并继续”，次按钮“返回／暂时跳过”；另可“先开始练习”，在有效授权下按服务端保守起点开始，不把未答主题改成跳过或已答。保存回执后才前进，失败保留当前选择。

读 GET start 获得完整 answers；新记录六主题均为 unanswered/null。写 `PATCH /learners/{learner_id}/start` 只带 request_id、当前 expected_revision 和本次编辑的 answers 子集，至少一主题；不提交其余旧字段。一个主题的 state/value 整体替换。字段状态与界面对应如下：

- unanswered/null：“还没回答”；未触碰/离页不发写入，不自动套默认选项。“清除这题答案”需本人明确操作才发 unanswered/null，历史修订保留。
- skipped/null：“这题暂时跳过”；仅点“暂时跳过”发送，刷新后不再强迫补问。超时、没输入或按返回不算跳过。
- answered/value：“已保存你的回答”；必须来自实际选择/输入。小尝试非空且非纯空白；没试过是实际经历选项，不等于未答。兴趣 answered/[] 只代表本人明确选择“暂无兴趣选项”。
- chosen_start 的 accepted_default/value/recommendation_revision：“已采用这次建议”；仅点“采用当前建议”产生，单独一次 PATCH，不与其他主题编辑合并。recommendation_revision 与 expected_revision 均使用当前服务端版本，value 与该版推荐一致；过期409先读新建议，再由孩子确认，不能自动接受新值。自行选择用 answered/value。

PATCH 返回完整快照，更新 revision/saved_at、missing_fields、skipped_fields 和各状态。completion_status 的 not_started/draft/completed/completed_with_skips 只说明问卷主题是否处理；mini_attempt_status 的 not_attempted/skipped/answered 独立展示，不能把“资料已处理”写成“已完成小尝试/能力评估”。只在实际 answered 时展示小尝试答案。

年龄段由 S01 教研候选经 S03 `config.age_band_options` 供应；UI 不自行冻结具体区间。当前 S01 候选“6–8岁／9–12岁／13–17岁／暂不填写”仅供表达试验，按中央 Q01 在 P4 真实试用前收口，不额外阻塞可配置的 P1 工程。用途说明“帮助松伴把话说得更适合你”，不收精确生日、学校和家庭地址。年龄未提供时使用中性短句表达，不推断能力；是否影响课程资格由独立服务端规则解释，不能由前端年龄判断。称呼避免鼓励填写实名。

AI 经历使用行为选择，例如“没试过／用过别人给的提示／自己改过提示和结果”；不是“你是新手还是高手”。如含“没试过”，与已做过项互斥。小尝试只读静态材料并保存本人回答，不调用模型、不称考试，没有年龄排行榜；模型服务故障不会把已作答的小尝试改为未完成。

### 4.2 低龄与初学分开

表达偏好与帮助力度是两个维度：短句/逐步呈现用于阅读需要；“带着我做／让我先试试／我想挑战一下”决定默认提示展开程度。低龄但有经验者可先独立操作；年龄较大但初学者可逐步练习。孩子随时调整，不覆盖历史帮助和已有尝试，不跳过同一学习目标的检查。

有经验者可先做同目标的小尝试，由服务端版本化规则给可调整的帮助建议，不能“我用过 AI”即直接第三关。仅 experience 与 mini_attempt_text 都实际已答且规则有结论时，recommendation_basis=rules；页面用 recommendation_source_fields 说明“根据你保存的经历和这次小尝试”。缺证据时 basis=insufficient_evidence、recommendation=guided、sources=[]，显示“先带着你做，你还可以换一种方式”，不捏造能力观察。

推荐不等于本人选择：chosen_start 未答/跳过时 effective_start=guided、effective_start_source=conservative_fallback，仅决定当前保守教学方式，不写回 chosen_start/help_preference。点“采用当前建议”才记录 accepted_default，自选则记录 learner_choice；后来推荐更新不覆盖已选路线。默认辅助区可以展示逐步提示，但要写“松伴先提供逐步提示”，不能写“你选择了带着我做”。

### 4.3 不重复问答

进入前读服务端 answers、missing_fields、skipped_fields、mini_attempt_status、saved_at 与学习者归属。missing_fields 只列 unanswered；已跳过主题不列入必补。旧兴趣可在确认确属本人学习者并获准映射后展示“沿用上次选择”，本人确认后再存 answered；家长账号自己的参赛兴趣不能自动变成孩子兴趣。未知归属先不导入。

旧 `skills` 是创作经历，只显示其原意思；不当 AI 熟练度。不重新询问原赛事时间/城市，不把原参赛访谈变成首课必答题。更新任一偏好只保存该修改，不清空另外已填字段，也不抹掉旧证据。多标签冲突进入 §7 的比对流程，不能照旧页面直接“读取最新选择”并删除未保存选择。

主行动 UIA-03；小尝试 UIA-09。辅助资料不持久化在跨身份共享 localStorage；本地恢复须按受限会话及学习者隔离，身份撤销时清空。读不到起点时提示“暂时没读到上次的选择”，禁止当空档案反复提问。

## 5. 家长与管理关键页面

### 5.1 F01 家长端

页面顺序：家庭管理身份与授权状态 → 活动/课程权益 → 当前孩子学习摘要 → 作品版本 → 可观察过程 → 已发布报告 → 下一步。首轮一位家长管理一位学习者；数据仍带归属，不以省略选择器代替校验。手机依此单列，桌面也不把订单付款作为孩子成绩卡。

关系未建立：说明“先建立孩子档案并确认学习授权”，主行动“填写孩子资料”；自称家长只显示“关系已声明，待按试点流程确认”。待授权列具体同意版本、用途、范围与撤回入口；未经同意不预勾选。核验进行中、被退回、授权到期各有真实原因和下一步；不声称已做法定身份验证。

0.2.1恢复链：新鲜认证后GET families取得本人家庭，再读取family/learner及consents，不依赖localStorage记住family_id。只有成功items=[]才显示未建家庭；401/403/服务故障走身份/错误恢复。新request_id重复建家庭的family_exists返回读取本人家庭，不无限新建。孩子和staff不能调用家庭发现入口。

授权页使用服务端effective_scopes，不把历史active记录或勾选scope当当前有效权限。pending关系只显示本人已提交的最小历史记录、无有效scope，不因此开放新的同意提交。按返回consent_id/revision撤回；历史记录用其consent_version读取原文，新确认用Config指向版本。GET consent-texts只显示服务端原文及scope_purposes，不自行编写或让模型补授权文本；核对text_sha256对应版本。草案/撤下、正文缺失或acceptance_enabled=false时显示“授权内容待确认”，不开放正式授权按钮。只有approved_for_pilot、acceptance_enabled=true且关系verified等后端条件满足才可确认；研发fixture不能签发真实权限。

进入孩子模式（UIA-12）前显示“进入后，这个浏览器的家长管理会退出；回来管理需要重新登录”。按 S03 账号级旧 Bearer 轮换提案，另明确“这个账号在其他设备上的旧版登录也可能需要重新登录”，不虚假承诺只影响当前标签；该兼容成本由 S00 冻结。请求期间禁用重复切换；只有服务端确认撤销旧管理会话并签发受限会话后进入 L01。失败/结果未知时遮蔽管理内容并核对当前会话，不能回到原高权限界面继续操作。其他标签收到失效事件时收起私有内容；事件只传会话变更信号，不传孩子资料。返回家长端（UIA-13）重新认证，浏览器后退、bfcache、标签重新可见均先核验 session，不得恢复管理权。

报告状态：`draft` 不对家长展示正文，只说“报告尚未发布”；`pending_review` 显示“老师正在核对”，有真实时间/出口；`failed` 显示“报告暂未整理好，作品仍可查看”；`published` 才提供已发布快照与来源；`revoked` 收起正文和下载，说明“这份报告已撤回，等待重新核对”。旧下载副本无法保证被删除。新作品不静默改旧报告，页面标明报告截止版本与日期。

报告只摘要本人过程，不展示全队聊天；参赛报告和学习报告显式标来源类型。观察缺证据用“目前还不了解”，不显示天赋分、人格诊断或同龄排行。家长提供的协助自述按自述标注，不改成系统观察。

订单与权益：`pending`“等待核验”，`verified`“款项已核验”；课程是否可用另读 entitlement，不能到款即在前端自动开通。`closed` 显示原因，`refunded` 显示已确认退款事实和相应权益规则。P0/P1 不出现真实收款入口；P5 报价、期限、退款和历史只读规则未冻结前，不写金额、到账时间或永久保留承诺。孩子端预算不足只引导找家长/支持，不展示核款按钮。

### 5.2 A01 获准后台

目标待办顺序为关系与授权、求助、作品复核、报告审核、订单核验；内容配置随后，统计最后。P1–P4 隐藏尚无契约的核款/退款与内容发布操作，P5 才按授权启用，不做无效按钮。顶部显示当前获准职责和处理范围。教师只看分配案件，核款人员不因此获得孩子私聊，内容编辑者不因此能发布报告。隐藏导航之外，直接请求仍须后端拒绝。

每个案件卡显示案件类别、获准目标称呼、课程/作品/报告版本、必要证据、当前状态、负责人和截止时间。选择案件进入详情，默认主行动“开始核对”；有证据且服务端允许才显示“保存复核结论”。退回必须给孩子能执行的一条改进说明，缺证据可请求补充，不强制二选一“通过/失败”。

作品复核显示同版本规则检查与孩子解释，不能检查 v1 却通过 v2。证据不清楚时“保存补问”使用 decision=needs_information，保存 M1–M4 已填/unclear 项，案件保持 claimed 且不改过关；不强迫老师结案。passed 必须 M1–M4 恰好各一条 supported 与有效来源，缺项、重复项、unclear 不可通过。报告审核显示引用对应作品与帮助来源；发布、撤销各是独立动作（UIA-17），需要明确目标与版本确认，不能点击“生成报告”即通知家长已发布。生成失败只重整已有事实，不重跑孩子实验。

认领/转交/延期（UIA-16）必须显示新负责人、期限和原因并等待回执。并发处理返回冲突时停止操作，比较当前状态后重新决定，不能覆盖另一老师结论。逾期按截止时间排序，转交没有回执不显示成功。服务端缺允许动作则只读；前端不能靠角色字符串拼出运营权限。

无待办明确“当前分配范围内没有待办”，读取失败不能称“全部处理完”。后台手机先案件标题、状态、对象、证据、操作，复杂明细可展开；不压缩成不可读多列表格。

## 6. 四角色、帮助与组件

### 6.1 角色与帮助等级

学习角色建议固定 `guide` 主向导、`tool_guide` 工具向导、`creation_coach` 创作教练、`review_coach` 检查复盘教练。共用品牌形象，用角色名和少量配饰区分；每轮只显示一个当前角色及用途。不声称四个独立专家互相验证；实际模型未知时详情写“模型信息暂未取得”。

“我不知道怎么开始／给我一点提示／帮我检查”是求助意图，不是能力等级。帮助强度单独记：H0 未提供本次线上提示；H1 一句定位问题；H2 分步操作；H3 明确标记的局部示例。可逐级展开，也可直接请求更多帮助；不给孩子扣分或贴“依赖 AI”标签。阅读示例不自动写入作品，采用后需保留帮助来源。

主向导负责当前任务/恢复，不自动改学习进度；工具向导解释输入/运行/保存；创作教练帮助孩子作表达选择；检查复盘教练先引导自查再解释反馈。只有规则与获准人工结论可支持过关。求助按钮、打开提示、模型真正返回、采用示例分别记录，不把“展示了按钮”记成“孩子用了帮助”。

UIA-06 读取当前必要资料与帮助上下文，不能把全历史、家长资料和队友对话一起送出。Attempt/Reflection/作品统一用 HelpDisclosure，保留 unknown、成人内容帮助、同伴内容帮助、AI帮助与 example_reference；引用示例须有可访问的 example_source_ids，不再使用窄枚举 declared_help。未报告额外帮助不改变 AI 原样候选的作者来源。UIA-11 人工求助先让孩子选“看不懂任务／不会操作／服务没连上”，可填一句说明；默认附本课当前步骤和必要版本，提交前明确可见材料，不自动发出完整私聊。

### 6.2 组件清单与行为约定

- **当前任务卡**：标题、动作、保存/检查两个事实、一项主行动。缺数据时 skeleton；空态来自成功空响应；不可用说明具体门槛。
- **关卡节点**：编号、名称、文字状态、前置条件；支持 locked/available/in_progress/pending_review/needs_practice/passed，不能把运行状态当关卡状态。
- **材料与输入**：可见 label、描述、错误关联、长度提示；中文输入法 composing 时不提交；Enter 在文本框换行，提交靠明确按钮。
- **作品预览/版本选择**：模板化文本、版本与保存时间、作者/帮助来源；草稿与不可变版本明显区分；旧检查贴对应版本。
- **运行状态卡**：pending/running/succeeded/failed/unknown，模式 `mock/live/replay` 与结果状态分离显示。状态新鲜度/最后核对时间不得冒充供应商处理进度；无依据不显示百分比。
- **检查反馈卡**：规则检查、AI 建议、人工复核三个来源标签，问题定位与恢复动作；等待或缺证据不能使用绿色通过图标。
- **帮助展开区**：`button` 配 `aria-expanded` 和 `aria-controls`，展开不替换任务；长回复先给当前行动，其余“展开完整建议与来源”。收起后不删除原文。
- **对话框**：适用于离开未保存、身份切换、复核/发布确认；标题、说明、取消、明确动作。开启后焦点进入，Tab 不逃逸，Escape 等同取消，关闭后恢复触发点；不得因点遮罩而丢稿。
- **状态/错误/空态**：状态常驻相关操作附近，toast 只作补充。正常结果 `aria-live=polite`，需立即处理的错误可用 alert；不要每轮查询重复播报相同文本。
- **工具/来源卡**：有版本、来源性质和只读全文；不把任意模型 URL 变成默认外链，首课不开放外部执行。

### 6.3 视觉与可访问性约束

沿用 `--sb-bg` 米白、`--sb-surface` 白卡片、`--sb-ink` 正文、purple/lavender 的语义。卡片约 17px、控件约 13px；间距沿用 8/12/16/24/32/44。不更改全局 tokens；若现有颜色达不到文字对比度，使用现有更深语义 token 的学习作用域组合并交 S00 确认，不能因为“沿用紫色”忽略可读性。

正文建议 16–18px、行高约 1.7；内页桌面标题 28–32px、手机 24–28px；辅助文字仍需可放大阅读。按钮/选择控件至少 44×44px 可触区，焦点有连续可见轮廓且不只靠颜色。文字目标对比至少 4.5:1，大字与控件边界至少 3:1；这些是实现验收目标，本轮未测产品。

单个任务区仅一个主色按钮；返回、保存辅助草稿、看例子用次级样式。运行中若原按钮禁用，旁边说明原因，并保留可用恢复/返回入口。原生控件优先，radio/checkbox 分组用 fieldset/legend；状态变化不改变 Tab 顺序。长链接/请求号用 `overflow-wrap:anywhere`，不截断恢复信息。

所有非必要动画可在 `prefers-reduced-motion: reduce` 下停止，不用动画表达唯一的过关状态；首课不依赖声音、读秒、拖拽或鼠标悬停。页面必须能在 390/768/1440px 和 200% 缩放使用，键盘路线见 §9。

## 7. 全状态与恢复规则

### 7.1 状态互相独立及显示优先级

至少分别保存页面读取状态、编辑保存状态、关卡状态、模型运行状态、作品版本/检查适用性、人工案件、报告和权益状态。不设计一个包办一切的 `completed`。

同屏冲突时优先顺序：身份失效/授权撤销 → 不可访问内容 → 版本冲突 → 结果未知 → 已知运行/保存错误 → 运行中/等待人工 → 正常编辑/只读。高优先级只遮蔽必要数据或操作；不能把低优先级仍存在的 unknown 账目抹去。身份失效优先清私有内容，“保留输入”承诺以服务端已保存事实为准。

每个回执至少能让 UI 回答：保存了什么、绑定哪个版本、现在可做什么、若等待由谁何时处理。页面先展示这些，再在成人支持详情显示错误 code/request_id；孩子不需要看堆栈、供应商密钥或精确成本。

### 7.2 通用状态 S01–S15

- **S01 默认/可用**：身份与资源读取成功后显示实际内容和 allowed actions。按钮是否可用取决于服务端能力，缺字段视为不可写，不根据缓存猜权限。
- **S02 加载**：“正在读取上次的学习”，保留壳与版式占位；首屏不显示零作品、未报名或通过。若有缓存明确“上次看到的内容，正在核对”，未核对前不提交。
- **S03 空态**：仅成功响应确认为空时出现。L01 开始首课；L05 无作品回 L01；F01 未建立档案进入建档；A01 无待办说明当前分配范围。没有统一“去购买”空态。
- **S04 编辑未保存**：“这些修改还没保存”。默认只在当前页面保留输入，若本地缓存成功另说“仅保留在这个浏览器”；绝不写“已同步”。站内离开对话框提供“留在这里／保存后离开／放弃本次修改”；保存失败不离开，浏览器关闭依浏览器标准提示，不承诺必能拦截。
- **S05 保存中/已保存**：重复按钮禁用，显示“正在保存”；只有匹配当前学习者、run、revision 的回执才能显示“第 n 版已保存 · 时间”。服务端保存的是旧输入快照而用户已继续编辑时，仍显示“上一版已保存，这些新修改还没保存”。
- **S06 读取网络失败**：“暂时没读到最新记录，可以重新读取”。保持现有已验证内容并标过期；空白时不当空态。主行动“重新读取”，只发 GET，不自动发模型或检查副作用。
- **S07 保存失败/保存结果未确认**：明确 4xx 未写入时可修正后再存；连接中断/5xx 无法判定是否持久化时说“还没确认这次是否保存，请先核对”。按原 request_id 查询/相同正文核对，不生成新 id 盲目重放。界面留当前输入，不播放成功动画。
- **S08 模型已知失败**：“这次没有拿到可用文案，你保存的要求还在”。只有后端给已知终态及允许新尝试才出现“修改后再试一次”，用户明确触发新 request_id；错误不归因于孩子。未确认保存则不能说已保存。
- **S09 结果未知**：“这次有没有完成还没确认，你的要求已经保存。先看看有没有新结果。”仅在输入确已存储时使用后半句。主行动“核对这次结果”，次动作“查看处理进展”；保留运行 id、预占预算与案件，不自动重发、不提供“确认重复生成”勾选框。unknown 核对后若 succeeded 展示原结果，若 failed 且允许新运行再开放重试。若无法查到请求则说明尚未确认，不能当失败退款。
- **S10 预算不足/用量待核对**：“暂时不能再请 AI 帮忙，已保存的内容还在”。分别解释“本次可用次数不足”与“上次使用还在核对”；保留手动编辑、已授权保存、查看作品与静态提示。主行动按情境为“继续修改作品”或“找学习支持”，孩子不付款。unknown 预占不计零，不自动返还并重跑。
- **S11 版本冲突**：“另一处保存了新内容，先看看两份有什么不同”。并列或手机上下展示“我还没保存的修改／最新已保存内容”，主行动“核对最新内容”，允许复制本人修改再手动合并；确认后带最新 revision 保存。禁止自动覆盖、自动扔掉本地草稿、替用户自动合并证据结论。
- **S12 身份失效/撤销**：“学习身份需要重新确认，请家长帮忙”。停止请求、隐藏私有内容、清该身份缓存、丢弃迟到响应；主行动进入安全重新认证/家长帮助，不能跨身份回填。可恢复的只有同一重新授权学习者的服务端草稿。本地尚未保存内容可能丢失，不能承诺全已留存。
- **S13 恢复中/恢复完成**：先核对身份、content version、run、draft revision、未结运行与检查。0.2.0 读取 Run 的 current_attempt_ref/current_requirements_ref/current_self_check_ref/current_reflection_ref/current_transfer_attempt_ref/current_artifact_id/active_model_run_id 后，按精确引用 GET 资源，不依赖本地最后一张POST回执。起点 GET 返回完整 answers 与推荐版本；不重发 PATCH 来“读取”。无未保存冲突时回服务端指定步骤并提示“接着上次继续”；本地同身份草稿更新则先进入 S11。旧课版本保留；只有显式确认迁移才换规则，普通刷新不新建课次或重新生成。
- **S14 内容复核中/不可用**：“这段内容还在核对，先看看活动资料”。隔离待复核候选，不自动存为孩子作品、不假称过关；说明可做的手动任务及人工出口。已保存历史内容的可见性由后端判定，拒绝访问时不从缓存恢复。
- **S15 等待老师/超期**：显示案件、负责岗位/人员和期限；缺一项如实说明待安排。主行动查看进展，辅助联系支持；重复求助复用同案件，不刷多单。超期不自动通过，不用无限转圈遮住返回学习。

### 7.3 页面状态覆盖与不适用项

- L01/L05：覆盖 S01–S03、S06、S12、S13；任务摘要反映 S08–S10、S14、S15。只读列表没有自身编辑未保存/保存冲突，返回前仍须由原编辑页处理 S04/S11；不能在卡片直接触发模型。
- L02：覆盖 S01–S07/S11–S13；0.2.0 起点和小尝试完全静态，不显示模型运行、预算或模型重试状态 S08–S10。待关系授权使用 S12/授权说明，不重复问答；completion 与 mini_attempt_status 独立显示。
- L03：覆盖 S01–S15；S04/S05/S07 是草稿/作品保存，S08/S09 是模型运行，必须分区；新版本、错误、检查和预算可同时存在，按 §7.1 选择主行动。
- L04：覆盖 S01–S03、S06、S12–S15及“新版本需重查”；若允许编辑反思，编辑区覆盖 S04–S07/S11。没有可生成操作时不显示无关预算/模型重试按钮。
- F01：覆盖 S01–S07/S11–S13；报告 draft/pending_review/published/failed/revoked，关系/同意/权益各自展示。报告整理的模型问题由支持处理，不提供“重跑孩子实验”。
- A01：覆盖 S01–S07/S11–S15；案件处理与发布分别等待回执。列表与只读证据没有编辑未保存，结论表单有；unknown 用于管理写入结果核对时不得据此再次核款/发权益。

### 7.4 特有状态的动作与结果

关卡 `locked` 只读且说明缺哪个前置；`available` 可开始；`in_progress` 可继续；`pending_review` 查询等待；`needs_practice` 定位具体补练；`passed` 查看结果/合法下一步。内容关卡 `G1_requirements/G2_create_save/G3_check_transfer` 对应 S03 建议 API 阶段键 `clarify/create/review`，孩子看到中文短名，前端不再建另一组权威枚举。前端无“设为 passed”按钮。

保存 v2 后 v1 检查留历史，当前投影 `recheck_required`，关卡可返回 `needs_practice`，显示“作品已更新，需要重新检查”。已打开下游草稿仍可编辑，依赖旧检查的新过关/发布暂停；由服务端返回范围与原因并向孩子解释，不能无提示撤销所有成果。若查看的是 v1，仍准确说“v1 当时有检查记录”，不说它支持 v2。反思、迁移或帮助披露改版同样重新核对证据集，不只监听作品版本。

权益未激活、到期、撤销与课程停用分开显示；允许的历史只读、编辑和报告访问按报价/授权版本返回，不由前端随意永久锁定或承诺永久保留。支付、授权、模型余额、课程通过互不替代。

### 7.5 检查回执如何决定文案和去向（0.2.0）

同一 POST checks 的 HTTP 201 只表示反馈资源已保存。UI 同时消费 purpose、rule_result、progress_effect、outcome、case_id、parent_revision，并重新读取最新 Run；不可只看 pass、201 或按钮点击。

- preflight + feedback_only + none：显示“预检结果已保存”，列问题/缺项；规则 pass 时只显示“这次预检没有发现规则问题”。不显示人工等待，不改变地图节点或历史通过。即使无值班、证据完整，也不主动查询或创建审核案件。
- advance + advanced + passed_and_unlocked：仅 clarify/create 合法，显示“这一步检查通过，可以继续”，读取最新 run 后进入允许的下一步。预检结果不能直接作为推进回执，必须重新发明确 advance 并校验当前 revision。
- submit_review + awaiting_review + pending_review + 非空 case_id：仅 review 合法，显示“已交给老师”，读取真实案件负责人、due_at 与支持出口。不能显示第三关已经通过。
- blocked_evidence：显示“还需要补上这些记录”，按 missing_evidence 提供相应操作；没有精确定位则回当前任务标题。无案件，不写“老师正在看”。结构缺引用422、证据过期409另走字段/版本反馈，不硬凑空ID。
- blocked_support：即使201也显示“反馈已保存，老师暂时还不能接单”；case_id=null、progress_effect=none，不进等待审核页。可保存返回作品或联系已配置支持；恢复值班后由孩子明确重新送审，不能自动派单。
- model_state 为 pending/running/unknown 时：rule_result=unknown、progress_effect=none、case_id=null；预检仍为 feedback_only，正式动作为 blocked_unknown。显示“先等这次生成/核对有结果”，只查询原运行/用量核对，不新生成、不退预算，不记录“学习失败”。
- needs_practice：依据具体反馈给补练操作，区分规则反馈与正式关卡状态。预检不能把已通过历史改为失败；第三关正式通过须另看 human_result 与最新 Run，不改写原 Check.progress_effect 的历史含义。

回执自相矛盾或存在未知枚举时，保留已保存输入并提示“还需核对最新进展”，禁用推进/送审成功展示，重新 GET 原资源。不能以未知值默认 passed。

## 8. 行动与接口消费者登记

UIA 是本规格的稳定行动编号，不是已上线 API。已按 S03 文本与机器提案核对 §8.1 HTTP 对接，待 S00 冻结；下列每项列明所需入参/回执与成功去向。任何未映射项不得开始对应依赖实现，P5 等后期项不阻塞独立 P1 工程。所有副作用使用 request_id；更新使用 expected_revision；前端不提交 passed、verified 或任意角色授权字段。

- **UIA-01 读取学习入口**：读受限身份、profile 缺项、enrollment/entitlement、resume 目标、课程版本、任务与近期作品。成功留 L01；入口失败用 S06，不做空记录推断。
- **UIA-02 开始/继续**：创建或恢复绑定课程版本的 learning_run；入参为已授权 enrollment，起点使用服务端真实选择或显式保守兜底。响应含 run_id、当前关卡、allowed_actions。已有 run 不重复创建；成功 L03，起点未答可选 L02，缺授权去家长说明。
- **UIA-03 保存/调整起点**：PATCH answers 的本次主题与 expected_revision，不提交派生结果；profile 称呼修改单独处理。服务端回完整答案状态、推荐依据/版本和处理程度。成功下一主题或 L01/L03，不重置其他主题和历史学习事实，不造默认本人选择。
- **UIA-04 保存任务草稿/要求**：绑定 run/task/content version、草稿正文与 revision。回执含持久化 revision/time；可继续编辑。保存失败不能进入模型调用或假称已保存。
- **UIA-05 试着生成**：以已保存 draft revision、当前 lesson/role、受控工具与必要来源建立 model_run；返回 id/status/预算状态。查询运行为只读子动作；仅 succeeded 且结果可见才展示候选。失败/unknown 按 S08/S09。
- **UIA-06 按需帮助**：以角色、求助意图、帮助等级、当前任务/版本和必要来源建立教学帮助；回 help/model run 与实际角色/提示词版本。静态卡仅记录可观察展开事件，不伪造模型运行。
- **UIA-07 保存作品新版本**：以候选或手动内容、模板版本、来源与 expected_revision 保存；返回 artifact_id/version、来源归属与检查适用性。成功仍在 L03，主行动转检查；刷新后同一 request_id 不重复产生版本。
- **UIA-08 发起/读取检查**：自查先独立保存；checks 必须给 stage 和 purpose=preflight/advance/submit_review，再携带对应精确证据。preflight仅反馈；clarify/create的advance才可正式推进；review的submit_review才可建立人工案。回执依 §7.5 决定显示；没有必须作品版本时传null，不伪造作品id。
- **UIA-09 保存反思/小迁移**：保存任务版本对应的本人解释、答案、是否有代录及帮助来源；反思与小迁移是独立记录。回证据 id、待检查项与下一步，不能只用对话条数完成迁移。
- **UIA-10 进入下一步/看回顾**：纯路由只读导航，正式推进由 UIA-08 的 checks(purpose=advance) 承担；只有最新 Run 允许时导航，不能客户端 `step++` 解锁。完成后 L04；无下一课不创建空任务。
- **UIA-11 请求人工帮助**：原因类别、当前版本、孩子确认可见的必要材料；回 case_id、负责人、due_at、状态与可用联系出口。提交超时先查原请求；已有未结案件可继续补充，不重复开单。
- **UIA-12 进入孩子模式**：家庭管理有效身份与明确目标 learner；返回服务端撤销确认和新受限会话。成功清管理缓存进入 L01；unknown 先锁定管理内容并查身份，不盲目再次签发。
- **UIA-13 返回管理/读取家长**：独立重新认证，再读取家庭关系、孩子摘要、权益和已发布报告；scope 必须后端确认。安全返回目标只限 F01，不能开放任意 URL 跳转。
- **UIA-14 家长关系与同意**：建档、声明、核验进度、同意版本确认/撤回为不同操作；回各自状态与生效范围。点击“我是家长”不能签发学习/后台权限。
- **UIA-15 读取作品/报告**：本人作品及指定版本、有效发布快照、来源、撤销状态；只读，不重建报告、不触发模型。无权限统一拒绝；版本缺失不得自动加载别的学习者记录。
- **UIA-16 管理案件**：获准读取/认领/转交/延期/结论保存，带案件 revision、依据、目标版本、负责人/期限；回审计与最新状态。成功留案件详情；冲突 S11，不覆盖他人结论。
- **UIA-17 报告事实核对/异议、生成、审核、发布、撤销**：独立操作；孩子只核对有限事实并提交异议。内容生成读已存学习事实，发布绑定已审核快照、无未决异议与最新 revision，撤销含原因。UI 只有获准角色显示动作，回执后状态更新；不将生成结果直接给家长。
- **UIA-18 核款与权益查看**：P5 方启用核款/退款写入；待核验订单和已开通权益分开读取。操作版本、款项依据、审计与权益由后端事务处理。P0 不显示真实支付，不填假价格或供应商。

响应不得把任意字符串按钮作为 UI 指令直接执行；导航/action 必须白名单映射到本节编号，未知 action 显示为普通建议。错误至少区分：认证失效、范围拒绝、授权未满足、内容不可用、字段校验、revision 冲突、request_id 冲突、预算不足、进行中、结果未知、服务故障。具体 code 以 S03 为准，不在 UI 将所有 409 当覆盖确认。

### 8.1 与 S03 机器提案的 HTTP 映射

已只读核对 S03 `contracts/openapi.proposed.json` 0.2.1（保留0.2.0起点/检查协议）。**完整 API 地址 = OpenAPI servers 的 `/api/learning/v2` + 下列相对 paths**；例如 GET `/session` 实际为 GET `/api/learning/v2/session`，PATCH `/learners/{learner_id}/start` 实际为 PATCH `/api/learning/v2/learners/{learner_id}/start`，不得当根API，也不得再重复添加两次前缀。验证同时对照operations.json完整路径和ui-actions.json的operation_id；附加读取/同流程复用显式列出。未请求任何业务接口；本次关闭项见§8.2。

- UIA-01：`GET /session`、`GET /config`、`GET /learners/{learner_id}/profile`、`GET /learners/{learner_id}/home`、`GET /courses`、`GET /courses/{course_version_id}`、`GET /learners/{learner_id}/artifacts`；home 的 current_action 决定下一步。
- UIA-02：`GET /learners/{learner_id}/home` → `POST /learners/{learner_id}/runs` 或恢复 `GET /runs/{run_id}`。入学先由获准管理身份调用 `POST /learners/{learner_id}/enrollments`，不能由孩子自行发grant。
- UIA-03：`GET/PATCH /learners/{learner_id}/start`，operation_id=getStart/saveStart；0.2.0 不保留旧PUT别名。PATCH只发送本次 answers 子集；明确采纳推荐单独提交。基本档案 `GET/PATCH /learners/{learner_id}/profile` 按角色权限使用。兴趣导入只作为用户可确认的已授权来源，不直接读家长个人偏好。
- UIA-04：第一关用 `GET/PUT /runs/{run_id}/requirements`，`confirmed` 只表达孩子确认，不是 passed；工具/迁移输入用 `POST /runs/{run_id}/attempts`、`GET/PATCH /attempts/{attempt_id}`。更新带各自聚合根的 revision，不能混用 run/requirements/attempt revision；回执返回 parent_revision 后更新父版本。
- UIA-05：`POST /attempts/{attempt_id}/model-runs` → `GET /model-runs/{model_run_id}`；未知核对案件 `GET /reconciliation-cases/{case_id}`。202 只表示受理，不清空未保存编辑。
- UIA-06：`POST/GET /runs/{run_id}/help`，当前工具卡 `GET /courses/{course_version_id}`、获准材料 `GET /courses/{course_version_id}/materials/{material_id}`。帮助绑定 task_id/task_card_version，静态帮助与 AI 帮助均记录实际内容等级，只有 AI 分支使用模型额度。
- UIA-07：首次 `POST /runs/{run_id}/artifacts`，以后 `POST /artifacts/{artifact_id}/versions`，绑定 attempt_revision/template_version_id/HelpDisclosure；保存后 `GET /artifacts/{artifact_id}/versions/{version_id}` 与 `POST /artifacts/{artifact_id}/readbacks` 复用 UIA-15 的显式回读行为。回 parent_revision 后同步 run/作品revision，避免随后检查用旧值。
- UIA-08：`POST /runs/{run_id}/self-checks` 存孩子判断，恢复 `GET /self-checks/{self_check_id}`；`POST /runs/{run_id}/checks`、`GET /checks/{check_id}`、`GET /runs/{run_id}`。NewCheck.stage 配合 purpose，具体按钮及回执见 §3.2/§7.5；clarify/advance 无作品也可检查，create/advance 要同版readback，review/submit_review 要全组证据。获准人工结论复用 UIA-16 的 resolveCase。
- UIA-09：起点静态小尝试复用 UIA-03 的 `PATCH /learners/{learner_id}/start`，提交 answers.mini_attempt_text 的 state/value，不提前创建假run；课内迁移 `POST /runs/{run_id}/attempts` + `PATCH /attempts/{attempt_id}`，kind=transfer，task_id=S3.3、材料B、transfer_response。解释 `POST /runs/{run_id}/reflections`、恢复 `GET /reflections/{reflection_id}`，引用确切迁移revision、自查及HelpDisclosure；修改时 NewArtifactVersion 已保存解释，未做迁移前不假造 transfer_attempt_id 调reflect。
- UIA-10：`GET /runs/{run_id}`、`GET /artifacts/{artifact_id}`、`GET /checks/{check_id}` 读取后导航。advance是 checks 的purpose，不是另一个路由；保存、回读或预检本身均不解锁。
- UIA-11：`POST /runs/{run_id}/cases`，`GET /cases`、`GET /cases/{case_id}`，补充说明 `POST /cases/{case_id}/messages`；队列缺配置按 support_unavailable 留作品返回。相同 learner/run/reason_category 的未结求助复用原案；消息按案件范围展示，不能转为公开聊天。
- UIA-12：`POST /sessions/enter-learner`，恢复 `GET /session`；身份 cookie 不在 JS 内保存或由旧 Bearer 换取。响应丢失且仍未获得有效新 cookie 时走重新认证，不重放旧凭证取新权限。
- UIA-13：`GET /session-bootstrap` → `POST /sessions/authenticate` → `GET /session`、`GET /families` → `GET /families/{family_id}`、`GET /learners/{learner_id}/consents`、`GET /learners/{learner_id}/home`、`GET /learners/{learner_id}/reports`；退出 `POST /sessions/logout`。普通读取不刷新认证cookie，不依赖旧缓存猜family_id。
- UIA-14：`GET /config`、`GET/POST /families`、`GET /families/{family_id}`、`POST /families/{family_id}/learners`、`GET/POST /learners/{learner_id}/consents`、`GET /consent-texts/{consent_version}`、`POST /consents/{consent_id}/revoke`。按版本原文/批准状态和真实关系决定能否确认，不新增“我是家长即确认”接口；draft/withdrawn文本不开放正式授权。
- UIA-15：`GET /learners/{learner_id}/artifacts`、`GET /artifacts/{artifact_id}`、`GET /artifacts/{artifact_id}/versions/{version_id}`；明确打开已保存版本后，用响应 read_receipt_id 发 `POST /artifacts/{artifact_id}/readbacks` 并等回执，不能预取即记孩子已看。报告用 `GET /learners/{learner_id}/reports`、`GET /reports/{report_id}`。回读只证明作品取回，不证明理解；普通 GET 不替代有副作用的回读提交。
- UIA-16：`GET /cases`、`GET /cases/{case_id}`、`GET /cases/{case_id}/evidence`、`POST /cases/{case_id}/claim|transfer|resolve`；延期 `POST /cases/{case_id}/extensions` 带 new_due_at 与 reason。unknown 用量核对仅获准 staff 调用 `POST /reconciliation-cases/{case_id}/resolve`。
- UIA-17：`POST /runs/{run_id}/reports`，本人事实核对 `GET /reports/{report_id}` 与 `POST /reports/{report_id}/disputes`；获准人员 `POST /reports/{report_id}/submit-review|reviews|publications|revocations`。生成另有 generation_status，unknown 不写成 failed；无正文权限只展示状态。
- UIA-18：P0–P4 **无核款/退款写入端点**，S03 明确延后P5。本期 `GET /learners/{learner_id}/home` 读权益，获准管理者 `POST /learners/{learner_id}/enrollments` 仅使用既有grant/entitlement；`GET /learners/{learner_id}/usage` 只表示用量，不能当付款或自行发放权益。

错误映射：401 `session_expired/session_revoked` → S12；403 `consent_required/entitlement_required/child_mode_restricted` → 对应身份/授权解释；404 `resource_not_found` → 不泄漏对象名；409 `revision_conflict` → S11，`idempotency_conflict` → 保留输入并核对操作号（不得诱导覆盖），`active_run_unknown` → S09，`budget_exhausted` → S10，`evidence_stale` → 当前证据重查，`invalid_transition` → 重新读取允许动作；410 `report_revoked` → 收起报告；422 `invalid_input/invalid_sources` → 字段或来源反馈；423 `learning_paused` → 已认证历史读取/退出/获准核对仍可达；429 `rate_limited` → 服务端有等待时间才显示，不循环自动再发；503 `model_unavailable/support_unavailable` → 保存已有内容与相应服务出口。

### 8.2 UI-Q1–Q4 关闭记录（对照 0.2.0）

**UI-Q1：已关闭规格缺口。** GET/PATCH start、StartAnswerPatch、六主题state/value及明确采纳版本约束已完整对应 §4。只保存当前主题、缺失保持原值、清空/跳过不同、保守兜底不冒充选择；UI 已删除旧PUT及扁平SaveStart映射。START-first-topic/restored-draft/default-explicit/default-stale/patch-preserves-omitted等离线条件提供支持。G1真实存储、并发/刷新和身份恢复仍未验收。

**UI-Q2：已关闭规格缺口。** NewCheck强制purpose；§3.2逐按钮指定preflight/advance/submit_review，§7.5逐回执控制成功文案。预检不派单不解锁，clarify/create明确推进，review明确送审；201不当送审成功，blocked_support与单独求助503分开。CHECK-review-preflight-no-dispatch/preflight-illegal-pass/review-no-staff-blocked/unknown-waits等离线条件支持；G2实际事务、唯一派单、版本竞争及人工处理仍未验收。

**UI-Q3：已关闭规格缺口。** requirements首次GET 404表示本run尚无草稿，PUT expected_revision=0创建；FactSelection允许空白，confirmed=false可存半成品。confirmed=true才强制完整，但不自动推进；另发 clarify/advance 通过R01/R02。不能把跨范围404当本人空草稿，归属先由已授权run确定；P2持久化仍待验证。

**UI-Q4：按可实施降级方案关闭。** allowed_actions采用operation_id白名单，Action.type另有资源动作白名单；Run提供当前证据引用，Case提供support_contact_label。精确字段不存在时回任务标题，不能解析label猜DOM/URL。无需新增不确定定位字段才允许P1；以后扩展由S00批准，不保留为当前阻塞。

附带对齐：authorship=ai_candidate_unedited、统一HelpDisclosure（含unknown与示例来源）、人工needs_information保持claimed、M1–M4各一条supported才通过；无作品clarify、同版回读和精确自查/反思/迁移revision继续保留。关闭均指文档及离线条件对齐，不代表G0由本会话通过或G1/G2/儿童试用已完成。

## 9. 验证故事与实际验证边界

### 9.1 可开发验收故事（后续实现执行）

UI-V01 首次且无团队：从 L01 → 授权已满足的 L02 → 首课 T1/T2/T3 → L04 → F01 已发布报告；每个主操作有 UIA 映射，不需要团队、比赛、连接器或真实付款。核对“AI 候选/作品已保存/关卡通过”是不同回执。

UI-V02 回访且旧参赛用户：原 `#/work`、`#/tasks`、`#/team-work`、`#/workbench`、`#/collaboration`、`#/onboarding` 在对应旧工作流语义下仍可达；不触发学习起点。显式进入学习后，合法本人已有兴趣只确认/补缺，不复制家长个人经历。

UI-V03 不同年龄与经历/逐题恢复：低龄有经验、较大年龄初学、未提供年龄都可调整提示；一题PATCH后刷新其余仍unanswered，显式skipped不再必问；accepted_default单独绑定当前推荐revision，过期409不自动采纳；保守effective_start不伪造本人选择，问卷completed不代表小尝试answered或能力通过。对应S03 START-01–04，G1运行待验收。

UI-V04 刷新/断网：编辑未保存→离开提示；保存回执丢失→核对原请求；已运行→刷新只读恢复；unknown→不能再次生成或自动退预算；known failed→用户明确新尝试；预算不足→仍可看已存作品和合法手动修改。

UI-V05 检查与版本：预检规则pass且无值班也不派单/解锁；clarify/create仅advance成功才推进；review只在明确submit_review与awaiting_review/pending_review/非空case_id回执后显示已送审。201 blocked_support/blocked_evidence不显示等待老师，unknown不假失败/重跑。v1检查不支持v2，版本竞争保留修改；needs_information保存unclear但不通过，M1–M4缺项/重复不可通过；真实等待有负责人/期限。对应S03 CHECK-01–04、HELP-01、REVIEW-01，G2/G3运行待验收。

UI-V06 身份切换与家庭恢复：家长进入孩子模式后其他标签旧管理请求失效；迟到响应不回填，返回管理须重新认证。清缓存后经families→consents→同版本文本恢复；列表读取失败不当空家庭，pending无有效scope，草案/撤下文本无授权按钮。猜别的run/artifact/report/case ID不泄漏对象名，后退不恢复敏感缓存。对应RECOVERY-01及AUTH场景，运行未验收。

UI-V07 报告与运营：draft/pending_review 家长看不到正文；published 只读快照；revoked 后续访问失效；新作品不更改旧快照；订单 verified 但权益尚未生效时如实显示；不同后台职责不能互相越权。

UI-V08 键盘：跳过导航→L01 主行动→L03 材料/输入→生成→查看候选→保存→检查→帮助展开/关闭→人工求助；所有操作有可见焦点，不要求拖拽/悬停。检查对话框 Tab 循环、Escape 取消、返回触发点、校验错误焦点及中文输入法不误提交。

UI-V09 视口：390/768/1440px 下逐页查看标题、长中文、长链接、三关地图、状态错误、身份对话框，主体无横向溢出；768 使用单列而非拥挤双栏；200% 缩放仍可操作；手机键盘不遮当前输入与主按钮，底部安全区足够；减少动效无功能损失。

UI-V10 儿童观察：请符合授权流程的真实试用者说出“现在要做什么／怎样保存／卡住找谁／是否已通过”。分别记录看不懂任务、不会操作和服务问题，不以成人主观满意替代；不将研发 fixture 写成儿童教学有效性。

### 9.2 本轮证据

本轮仅执行文档一致性、路由/代码基线只读核对、行动与状态覆盖及文件范围检查。没有运行新学习页面、390/768/1440 浏览器、真实键盘、模型、支付、数据库迁移或儿童试用。外部证据根为 `E:\松伴\outputs\learning-p0-20261102\S02`，结果及输入指纹见 [S02 交接](../handoffs/S02.md)。

## 10. 待决、冻结与交接边界

1. **S00，G0冻结评审**：§8.2 UI-Q1–Q4已对照0.2.0关闭规格缺口；S00确认回顾子视图、版本参数、开关及三份交付的最终快照。UIA-01–17已映射，UIA-18核款写入属于P5。不能将离线条件通过替代G1/G2运行或真实儿童验收，不再把旧PUT/检查意图缺失列为当前阻塞。
2. **S01/教研，首课内容冻结与真实试点门槛**：具体材料、三关证据与小迁移、提示等级含义由 S01 收口；年龄范围/时长按中央 Q01 在 P4 试用前定，不额外阻塞可配置 P1。无儿童试用保留待验证状态。
3. **S00/S04，阻塞 G1**：管理授权撤销、新受限会话、跨标签失效与身份恢复方案；没有后端保证不启用“孩子模式”。
4. **产品/实际运营负责人，阻塞真实试点/G3–G4**：人工案件负责人、处理期限、联系渠道、关系确认和授权文案；开发可用显式虚构值，正式服务不得缺责任主体。
5. **S00/美术/S05/S07，阻塞 UI 实现验收**：学习作用域对比度与组件样式、三个视口、200% 缩放、键盘/屏幕阅读器及减少动效实测。保留品牌不代表自动满足可访问性。
6. **产品/S11，阻塞 G5**：报价、权益到期/退款后的历史访问、报告保留与核款流程；P0 不决策金额和生产政策。

S02 只写本文件与自己的 handoff；不修改中央规划、S01/S03 输出、主站/工作台源码、构建或配置。完成规格与验证后停止，G0 是否通过由 S00 决定。回退可撤下本文件与本会话交接；外部证据单独保留或由负责人处理，不删除其他会话文件。
