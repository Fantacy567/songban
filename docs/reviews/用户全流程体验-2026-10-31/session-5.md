# 会话 5：经常被打断的普通用户，全流程独立体验

体验时间：2026-10-31 12:03—12:16（UTC+8）。报告整理于同日。
基线：委派给定提交 df463269b0cbb3d8851f8240a95b10e818eb0007。
环境：Windows、Edge（Playwright 驱动真实浏览器，headless）、1280×800 笔记本视口；截图采用整页截图，高度可超过 800。
体验者是 AI 代理模拟用户，并非真人用户研究。A 为“小林（合成体验）”，经常因家事离开页面；B 为“小周（合成同伴）”，使用独立浏览器上下文、独立账号完成 UI 注册和加入。

## 闭环结论

**在专属 8905 服务、短信和模型替身条件下，完整走完了站内闭环：游客活动 → 注册 → 保存资料 → 个人讨论与历史 → 建队与同伴加入 → 共同方向 → 显式共享 → 队长统筹确认 → 两名成员同步真实写出的体验文本成果 → 双向同伴检查 → 导出交接 → 复盘 → 退出、重登并续聊。**

后续找路全部依靠页面可见入口、DOM 和截图，没有阅读业务源码或旧 E2E，没有 API/数据库代写，没有隐藏路由辅助。该闭环应表述为“替身环境内 UI 独立走通”。正常 8893 的注册页及只读短信状态显示新用户注册暂不可用，因此不能表述为“生产新用户从头自然走通”。

没有制作或发布真实应用，没有实际录制或进行一分钟演示，没有向主办方报名或提交，没有实际短信送达，没有评估真实模型质量。T1 成果是页面内实际写出的项目说明文本；T2 是实际写出的演示讲稿与交接清单文本。两条成果与双方检查均明确写入这些边界。

对中断用户的整体判断：**已提交内容恢复可靠，讨论/进展草稿有恢复能力；资料输入的草稿保护不一致，个人/团队空间切换与重登落点使续做需要自己判断。**

## 环境、替身与辅助边界

- 所有业务写入仅在 http://127.0.0.1:8905 。该服务按 manifest 初始 0 用户、0 团队，两个账号均通过 UI 创建，号码为 18890000051、18890000052；队伍为“断点续学体验五队”。
- 正常 http://127.0.0.1:8893 仅访问游客页、打开注册 UI，并 GET 一次 /api/studio/sms-status。没有输入提交注册、发送短信、登录已有用户或修改正常数据。
- 8893 只读 API 返回 ready=false、configured=false、delivery_verified=false。这是事后/环境核对证据，不替代 UI 业务操作：[normal-sms-status.json](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/normal-sms-status.json)。
- 隔离服务沿用真实配置状态提示，但“获取验证码”使用独立进程测试替身，页面显示“本机开发测试码（未发送短信）”。按照委派与根会话明确告知继续。此条件是外部测试辅助；“底层未就绪却显示测试码”不作为生产 UI 矛盾。
- 模型回答明确为固定体验样例，mode=fixture，页面标注“协议测试替身，非真实模型/模拟测试”。固定样例讲校园失物招领，与断点续学主题不同，不计作真实模型缺陷。共享摘要由体验者手工改写，团队方向由 UI 手工保存。
- 个人工作台首次提问使用一次 [UX_TIMEOUT] 故障注入，返回 504、结果未知；刷新后核对，再勾选明确新尝试、去掉注入标记发送。未使用 [UX_SLOW]。
- 没有安装个人工具连接，没有改变配置、业务代码、提交或推送。探索脚本及证据只写本会话证据目录，唯一仓库报告为本文。
- 首次发布任务的原生确认框被 Playwright 默认取消，第二次点击后记录确认文案并接受；这是自动化操作处理，不归为产品失败。B 保存检查后立即点击进展入口曾遇到重绘导致输入框隐藏超时，重新点击可见入口后完成，亦不据此断言产品缺陷。
- 账号为合成数据，双方角色由同一 AI 代理操作。所谓“同伴检查”是独立登录身份的 UI 流程验证及实际文字内容核对，不是两个真人或独立专家的质量认证。

## 每一步实际动作、指引与结果

### 1. 游客首页与活动：自然走通

先只读访问 8893 活动页，再在 8905 从游客 /#/events 开始。看到三场“虚构样例”活动和“看看这场活动”，选择“教育 Agent 创作周末”。活动详情直接展示个人材料输入区、样例规则入口和“创建或加入小队”。知道下一步可先放资料，也可以先组队。样例性质很明确。

证据：[01-normal-events.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/01-normal-events.png)、[02-guest-events.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/02-guest-events.png)、[03-event-detail.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/03-event-detail.png)。

### 2. 输入资料、注册：正常环境受阻；测试替身辅助后走通

游客先写合成资料，再点击“登录后保存材料”，弹窗没有丢掉原输入。切换“第一次来，注册账号”，填合成手机号、页面测试码、密码、姓名、优势和希望尝试的事，通过 UI 完成 A 注册。注册后原资料仍留在输入框，点击“保存并读取材料”才成为已保存材料。

正常 8893 注册 UI 明确“短信服务尚未配置，暂不能注册或使用验证码登录”，已有账号可用密码登录。未实际发短信，所以结论是公开状态与指引判定新注册当前不可用，不是一次真实短信投递测试。

证据：[04-login-from-material.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/04-login-from-material.png)、[06-test-sms.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/06-test-sms.png)、[07-registered-material-retained.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/07-registered-material-retained.png)、[57-normal-registration-unavailable.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/57-normal-registration-unavailable.png)。

### 3. 个人资料收集与刷新：保存走通，未保存补充丢失

把材料性质选为“虚构样例”，保存读取，页面显示 1 份“已读取”。随后输入“【未保存补充】希望回来时还能看到正在写的内容。”并刷新。已保存的 1 份仍在，未保存补充变为空。游客时有“刷新会丢失”提示，登录后这一明确警告消失；没有恢复提示。

再加入活动样例规则、点击“帮我整理”，成功显示两份材料与已保存整理结果。整理结果带来源、未核实和待确认，知道不能直接当赛规。这里的字段内容来自固定替身，不评价提取正确率。

证据：[08-material-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/08-material-saved.png)、[09-material-refresh.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/09-material-refresh.png)、[10-material-organized.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/10-material-organized.png)。

### 4. 个人工作台与生成中断：自然走通，故障恢复有效

点击左侧“实践”进入个人工作台，再“开始一段讨论”。页面明确“个人空间·本人可见”“共享前只有你可见”和材料须勾选。选两份个人材料、选“想方向”，输入合成问题与 [UX_TIMEOUT]。

结果未知时保留提问，提示先核对保存状态、不会自动重发。刷新后问题、材料选择与未知状态仍在。点击“核对保存状态”，再勾选“我已核对，明确发起一次新尝试”，移除注入标记后成功获得样例回复并显示“回答已保存到本人的会话”。每一步知道该怎么继续；核对按钮的可见反馈较弱，详见文案问题。

证据：[12-personal-workbench.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/12-personal-workbench.png)、[14-discussion-timeout.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/14-discussion-timeout.png)、[15-timeout-refresh.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/15-timeout-refresh.png)、[16-timeout-check.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/16-timeout-check.png)、[17-discussion-recovered.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/17-discussion-recovered.png)。

### 5. 创建小队与第二位同伴加入：自然走通

A 点击“创建或加入小队”，填队名并创建，页面直接进入共同方向。再点“小队”找到邀请码 7eee35948baf。B 在独立上下文从游客活动页打开注册，使用第二个合成手机号和页面测试码注册，点“直接开始实践”，填队伍码加入，成功进入该团队工作台。

A、B 分别在“成员”页补充本次意愿和 2 小时可用时间并保存。A 注册时填的能力已带入；本次团队意愿仍需另填。知道队长负责方向和发布任务，成员负责本人情况。

证据：[18-team-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/18-team-entry.png)、[19-team-created.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/19-team-created.png)、[20-team-code.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/20-team-code.png)、[21-companion-register.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/21-companion-register.png)、[23-companion-joined.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/23-companion-joined.png)、[24-profile.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/24-profile.png)。

### 6. 共同方向与刷新：自然走通

A 手工填入“断点续学清单的页面流程体验”、资料与检查记录产出、没有正式赛事要求与评分信息、不制作应用/不提交主办方等边界，截止时间留空。保存后刷新，再到工作台能看到已保存共同方向；个人讨论不会自动覆盖方向的说明清楚。

证据：[25-direction-fields.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/25-direction-fields.png)、[26-direction-restored.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/26-direction-restored.png)、[27-return-discussion.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/27-return-discussion.png)。

### 7. 个人历史与显式共享：自然走通，有空间切换绕路

建队后的工作台显示“还没有会话”。使用可见团队下拉切回“我的个人空间”，原讨论历史出现；不是历史丢失。

在原回复点“选择内容共享”，选择团队、人工编辑摘要并预览。页面明确共享的是本轮原提问、编辑摘要和模型来源，其他回合不共享。预览阶段刷新后，编辑区收起；重新点“选择内容共享”，摘要和目标团队均自动恢复。再次预览并确认共享。

B 的“资料库”能看到共享原提问和编辑摘要。A 从个人空间点“查看已共享记录”却得到创建/加入小队内容，需要自己用团队选择器切回团队。未借助代码或隐藏路由。

证据：[28-personal-history-found.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/28-personal-history-found.png)、[29-share-dialog.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/29-share-dialog.png)、[30-share-preview.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/30-share-preview.png)、[31-share-refresh.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/31-share-refresh.png)、[32-shared-refreshed.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/32-shared-refreshed.png)、[33-shared-record.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/33-shared-record.png)、[34-companion-material-library.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/34-companion-material-library.png)。

### 8. 队长统筹与确认任务：自然走通（固定样例）

A 切回团队、点“任务”，页内“我的下一步”提示将当前资料交给团队智能体统筹。点击“综合当前信息”，得到“待确认建议”，展开两项建议任务，看到了 T1 负责人小林、T2 负责人小周及 T2 等待 T1、检查方法。点击“确认并发布这 2 项任务”，接受原生确认后得到已确认安排 v1；正式任务才出现。

任务内容来自替身：T1 整理一页项目说明；T2 准备一分钟演示与交付清单。本次以真实写出的文字说明和讲稿满足“准备”的有限范围，没有伪造实际制作成果。

证据：[35-tasks-before-coordination.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/35-tasks-before-coordination.png)、[36-coordination-draft.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/36-coordination-draft.png)、[37-draft-details.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/37-draft-details.png)、[39-tasks-confirmed.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/39-tasks-confirmed.png)、[dialogs.log](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/dialogs.log)。

### 9. A 同步成果，离开再返回：自然走通，草稿恢复明确

点击 T1 的“同步这项任务的进展”，填入实际写出的项目说明文本、选择“本人报告完成”、填写可逐项阅读的成果依据。未保存先导航到工作台，再回任务页展开补充。输入、任务、完成状态、依据保留，并有“已保留你未保存的输入，请核对最新团队资料后再保存”。

点击“同步本人进展”后刷新，仍显示 T1 本人报告完成、等待同伴检查。未把自己报告等同已验收，知道应等另一成员。

证据：[40-progress-form.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/40-progress-form.png)、[41-progress-navigation-return.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/41-progress-navigation-return.png)、[42-a-progress-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/42-a-progress-saved.png)。

### 10. B 检查 T1 并同步 T2：自然走通，需手动刷新

B 从资料库进入任务页，初始仍显示 T1 尚无进展。按页面可见“立即刷新”，获得新报告，“我的下一步”变为“先检查队友交来的 T1”。展开当前成果依据，实际逐项阅读目标用户、问题、最小范围、三步流程，点“检查 T1 的成果”，选通过，写明只核对文字完整性、并非真人或产品验收，保存检查。

B 再同步自己的 T2：真实写出一分钟讲稿（开场、三步演示安排、已知限制、分工）及交接清单，明确没有录制或正式演示；填写对应依据，提交本人完成。页面提示等待另一成员检查。

证据：[43-b-task-check-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/43-b-task-check-entry.png)、[44-b-after-manual-refresh.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/44-b-after-manual-refresh.png)、[45-b-check-t1.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/45-b-check-t1.png)、[47-b-result-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/47-b-result-saved.png)。

### 11. A 检查 T2：自然走通

A 点击“立即刷新”，看到 T2 新成果；展开并实际阅读文字，按开场、三步、限制、分工、清单逐项核对。保存通过检查，注明只证明讲稿文本准备完成，未验收应用或真实演示。两任务当前成果均有另一账号的检查记录。

证据：[48-a-check-t2.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/48-a-check-t2.png)、[49-delivery-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/49-delivery-entry.png)。

### 12. 交付与交接：站内自然走通；正式外部提交未发生

点击“交付”，页面显示 2/2 当前成果有同伴检查，并提示截止时间未知、演示文件需实测、主办方收件未知。点“导出当前交接清单”成功下载 Markdown，文件包含目标、v1、两项成果与依据、检查人及检查记录。只导出了交接清单，没有外部交接确认或正式提交回执。

证据：[49-delivery-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/49-delivery-entry.png)、[handoff-export.md](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/handoff-export.md)。

### 13. 复盘：自然走通

点“复盘”，看到 2 项任务、2 项有同伴检查、3 条进展。填入实际体验收获与卡点，点“保存到团队记录”，新增“网页复盘”记录、计数变 4。B 刷新复盘页也能看到。页面明确复盘会被团队看到。

证据：[50-retrospective.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/50-retrospective.png)、[51-reflection-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/51-reflection-saved.png)、[59-companion-review-visible.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/59-companion-review-visible.png)。

### 14. 退出、重登、续做：自然走通，但缺少上次阶段提示

A 点击退出回游客首页，打开登录，以同账号密码登录。默认到团队工作台：共同方向保留，但“还没有会话/开始一段讨论”占据主要位置，没有直接指出已完成任务互查与复盘。

点击可见“任务与统筹”能找回 v1、2/2 检查和四条记录；复盘页也保留内容。再回工作台、切“我的个人空间”，找回原会话。重新发一轮明确标为“重登后续做”的提问，成功保存新回复。退出重登后材料勾选变为 0，材料本体仍在，未把这点记为数据丢失。

证据：[52-logout.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/52-logout.png)、[53-relogin-landing.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/53-relogin-landing.png)、[54-relogin-task-state.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/54-relogin-task-state.png)、[55-relogin-review.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/55-relogin-review.png)、[56-relogin-personal-history.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/56-relogin-personal-history.png)、[58-relogin-continued.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/58-relogin-continued.png)。

## 问题按严重性排序

### 阻断：正常服务新用户注册未就绪

复现：正常 8893 游客活动 → 登录 → 第一次来注册。实际 UI 显示短信服务未配置、不能注册；只读状态亦未就绪。预期新用户能在合法可用的身份验证途径下进入项目。影响为无已有账号的新用户无法按产品指引进入后续团队闭环。

建议：先恢复并验证正常注册链路；在恢复前于游客关键 CTA 清楚说明当前只能浏览/已有账号登录，避免用户先长篇录入材料后才发现无法保存。此次没有请求发送真实短信，不能报告实际投递失败。

证据：[57-normal-registration-unavailable.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/57-normal-registration-unavailable.png)、[normal-sms-status.json](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/normal-sms-status.json)。

### 明显绕路 1：登录后的资料草稿刷新直接丢失

复现：活动详情已登录 → 保存一份资料 → 输入另一段未保存补充 → 刷新。预期恢复草稿，或至少明确预警未保存。实际补充为空，已保存资料仍在；登录后不再显示游客时的“刷新会丢失”，只留“当前输入先留在本页；登录后保存至个人空间”。

建议：与进展表单使用一致的草稿恢复体验；同时按已登录状态调整说明，明确“尚未保存/已保存”以及离开风险。对经常被打断者，这会造成实质性重写。

证据：[08-material-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/08-material-saved.png)、[09-material-refresh.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/09-material-refresh.png)；正面参照 [41-progress-navigation-return.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/41-progress-navigation-return.png)。

### 明显绕路 2：个人空间的“查看已共享记录”展示组队表单

复现：已有团队，把个人会话某轮明确共享给该团队 → 保持“我的个人空间” → 点击“查看已共享记录”。预期看到目标团队共享记录，或让用户选择已加入的团队。实际资料库导航被选中，主体却是“这次，和谁一起做？”及创建/加入表单；已有队伍只能从右上选择器自行发现。

建议：该入口携带最近共享目标或显示“选择团队查看记录”；已有团队时不把新建/加入作为主要动作。共享确认成功后提供直接进入目标记录的链接。

证据：[30-share-preview.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/30-share-preview.png)、[33-shared-record.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/33-shared-record.png)、[34-companion-material-library.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/34-companion-material-library.png)。

### 明显绕路 3：重登落到空团队会话，当前项目阶段不突出

复现：个人空间先讨论，再建队完成任务、交接和复盘 → 退出 → 密码登录。预期显示最近访问位置或“上次完成两项互查，继续交付核对”。实际落团队工作台，主要 CTA 是“开始一段讨论”，会话为空；任务与历史仍在其他入口，容易误以为要重来。

建议：默认返回上次页面；或在工作台空会话时也显示现有任务、最近同步、当前下一步，并明确“本团队暂无会话，个人空间有历史”。这是找路问题，不是记录丢失。

证据：[53-relogin-landing.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/53-relogin-landing.png)、[54-relogin-task-state.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/54-relogin-task-state.png)、[56-relogin-personal-history.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/56-relogin-personal-history.png)。

### 明显绕路 4：切回任务页时仍需手动刷新才能看到队友新成果

复现：B 保持登录于资料库；A 保存 T1 成果；B 从导航进入任务。实际初始仍显示 T1 尚无进展、本人应等待前置成果；点击“立即刷新”后才显示可检查的 T1 和正确下一步。预期进入任务页即拉取当前资料，或明确提示页面是缓存状态。

建议：导航进入任务或页面重新获得焦点时更新一次，保留用户草稿；用同步时间/有新进展标识减轻等待误判。这里只证实此时手动刷新前后差异，没有测定后台轮询周期或断言永不更新。

证据：[43-b-task-check-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/43-b-task-check-entry.png)、[44-b-after-manual-refresh.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/44-b-after-manual-refresh.png)。

### 文案可改 1：没有前置任务时仍说“前置成果已有检查记录”

T1 是首个任务、没有前置，刚发布时交接数为 0/2。“我的下一步”却解释“它的前置成果已有检查记录”。行动“可以先做 T1”合理，依据表述不精确。

建议：无依赖时写“这项任务没有前置依赖，可以开始”；有依赖且检查通过时才使用当前说法。

证据：[39-tasks-confirmed.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/39-tasks-confirmed.png)。

### 文案可改 2：编辑摘要在资料库仍以模型名作发言前缀

复现：把固定回答摘要手工改成体验事实再共享，B 在资料库看到“ux-review-sample：【人工整理…】”。预期保留“本人编辑摘要”身份，并另列模型来源。实际通用说明为“模型名称：回复关键信息”，容易把人工改写归给模型。

建议：内容署名“由小林编辑的共享摘要”，下方单列原回答模型、测试模式及本轮原提问。本次通过主动在正文标“人工整理”才避免误解，不能要求普通用户自己补标签。

证据：[30-share-preview.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/30-share-preview.png)、[34-companion-material-library.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/34-companion-material-library.png)。

### 文案可改 3：结果未知时“核对保存状态”缺少显著核对结果

故障注入后刷新，点击“核对保存状态”，页面仍为未知状态，未看到明确“刚刚核对：提问已保存、回答尚未找到”的结果。用户可以依靠提示勾选并重试，流程没有阻断，但难以确认按钮是否已做事。

建议：显示核对时间、已保存/未发现的对象和后续动作，不只保留静态未知提示。这是模拟故障下的界面反馈建议，不证明真实超时后的后台行为。

证据：[15-timeout-refresh.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/15-timeout-refresh.png)、[16-timeout-check.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/16-timeout-check.png)。

## 三个最有效的优点

1. **“我的下一步”跟随阶段变化。** 待统筹、核对草案、检查队友、等待检查、交付核对都有具体指引，任务卡能直接打开进展或检查操作；手动刷新得到最新状态后很容易继续。
2. **讨论与进展的中断恢复设计有效。** 结果未知不自动重发，刷新仍保留问题与状态；共享摘要可恢复；未保存进展跨导航保留且显式提示，已保存方向、任务、检查、复盘重登均在。
3. **共享、检查和正式提交的边界清晰。** 私人讨论默认本人可见，共享有预览和确认；本人报告与同伴检查分离；交付显示未知/需实测，导出含报告及检查对应信息，不把内部完成冒充主办方收件。

## 证据与运行记录

完整证据目录：E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/

- [manifest.json](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/manifest.json)：服务隔离与初始账号/队伍数量。
- [browser.cjs](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/browser.cjs)：本会话新写探索工具，仅控制浏览器和采集证据。
- [steps.jsonl](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/steps.jsonl)：按时间记录 UI 操作和可访问 DOM 读取（含自动化超时）。
- [console.log](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/console.log)：2 条资源 404 与 1 条注入 504；未记录 pageerror。404 日志没有 URL，不能归因具体资源或业务失败；504 是本次主动注入，不作生产故障。
- [dialogs.log](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/dialogs.log)：发布任务确认框原文。
- [handoff-export.md](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/handoff-export.md)：由交付 UI 实际下载的清单，已读取核对。
- 01—59 系列 PNG（另有 46-b-current），33 起多数关键页面同时保存同名 TXT；截图、DOM 与逐步操作交叉支撑上述结论。
- 已目视检查游客活动、未知结果恢复、资料刷新、共享记录误入口、进展恢复、交付、重登落点等关键整页截图。未将 DOM 中隐藏折叠项算作用户已看到，实际需要时均通过可见展开入口操作。

完整站内闭环已达到；生产注册可用性、真实短信、真实模型建议、真实作品质量与主办方提交仍不在本次完成范围。

## 补充验证：资料草稿刷新前后直接对照

2026-10-31 12:22:19—12:22:20（UTC+8），应汇总会话要求，仅补一次未保存资料输入的刷新验证。上次浏览器已关闭，本次通过 UI 重新登录原有“小林（合成体验）”账号，没有新建账号或业务资料。仍为 8905、1280×800，通过活动列表进入第一场活动的个人资料输入页。

- 刷新前时间：2026-10-31T04:22:19.622Z；URL 为 http://127.0.0.1:8905/#/event；inputValue 为“【合成草稿｜仅补验，不保存】我临时离开资料填写页，希望刷新后还能继续这段尚未保存的文字。”；已保存材料数量为 2，保持已登录。
- 刷新后时间：2026-10-31T04:22:20.153Z；URL 不变；inputValue 为空字符串；已保存材料数量仍为 2，保持已登录。
- 实际动作仅为在“文字或聊天记录”输入框填写上述合成草稿、读取 inputValue 并截图、刷新一次、再次读取并截图。未点击保存或整理。输入至刷新完成期间观察到的非 GET/HEAD/OPTIONS 请求为零。
- 初次补验脚本因通用 textarea 定位匹配多个元素，在填写及刷新前即停止；随后改为可见标签“文字或聊天记录”定位，完成上述唯一一次输入与刷新对照。没有修改业务代码或服务。

结论得到直接值对照支持：**未保存资料草稿刷新后丢失，而已有材料保持 2 份。** 这次未保存文字与首次体验不同，避免把旧日志中的返回值当成本次实测值。

独立 JSON（不含密码、令牌、cookie 或请求正文）：[draft-refresh-comparison.json](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/draft-refresh-comparison.json)。

截图：[60-draft-refresh-before.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/60-draft-refresh-before.png)、[61-draft-refresh-after.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/61-draft-refresh-after.png)。两张已目视检查，补验后共 61 张截图。

补验探索脚本：[draft-refresh-check.cjs](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-5/draft-refresh-check.cjs)。脚本凭据从运行环境读取，未写入脚本或 JSON。只关闭本次浏览器，测试服务保持运行。
