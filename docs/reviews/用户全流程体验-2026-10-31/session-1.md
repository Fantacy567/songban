# 独立全流程体验报告 · 会话1

体验时间：2026-10-31 12:03—12:18（UTC+8，最后一次页面观察时间）。仓库提交：df463269b0cbb3d8851f8240a95b10e818eb0007。

**结论：正常服务的新用户注册受阻；在明确的短信、模型测试替身条件下，本会话独立完成了从游客浏览到双人协作、交接导出、复盘、退出重登并续做的界面闭环。** 所有功能阶段均实际操作，未按功能分工给其他会话。没有实现、上线校园失物招领助手，没有录制实际演示或向主办方提交作品。

## 用户与设备、方法

- 主角色：林小禾（合成体验），第一次参加黑客松的大学生，会整理资料和简单草图，不熟悉“智能体、统筹”等术语，希望做校园失物招领助手。
- 第二角色：陈一帆（合成体验），愿意核对流程和整理验证记录。用第二个独立浏览器 context，经UI自行注册、输入队伍码加入。
- 两个合成手机号：18890000011、18890000012。未发送真实短信。
- 设备：Windows、Edge、桌面 viewport 1440×1000，Playwright 驱动真实浏览器（headless），依靠页面可见文本、控件及DOM定位，检查关键截图。
- 正常服务 8893 仅浏览游客活动、打开注册弹窗、读取短信状态；所有业务写入均在独立的 8901。独立服务初始无账号、无团队。
- 不读业务源码或现有E2E学习隐藏路径，没有调用业务写API，没有直接数据库写入，没有安装个人工具连接，没有提交、推送或更改业务代码/配置。
- 本报告是AI代理模拟用户体验，并非真人用户研究。双人检查由同一个代理切换独立上下文完成，不构成两名真实人的独立评价。

证据根目录：`E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/`。步骤脚本：[steps.jsonl](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/steps.jsonl)；浏览器日志：[console.log](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/console.log)；测试边界：[manifest.json](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/manifest.json)。每张编号截图都有同名 .txt DOM 快照。完整页面截图可能高于1000像素；实际窗口仍为1440×1000。

## 逐阶段实际经历

这里的“自然走通”指在专属测试环境内，通过可见UI自行找路。注册与模型环节依赖预先明确的环境替身，不能据此判定正常服务端到端可用。无源码、隐藏路径或外部说明辅助找路。

1. **游客首页、活动选择｜自然走通。** 从 /#/events 开始，看到“给第一次出发的你”“先看看活动的方向”，三张活动卡均标“样例活动”；点击第二张“校园 AI 共创营”的“看看这场活动”。页面把材料输入放在活动详情里，说明当前是个人草稿。知道下一步可以放资料或登录。退出时也实际看到 /#/login 落地首页，“第一次参加黑客松，松伴陪你一步步来”与“找到适合我的黑客松”清晰。证据：[02-test-guest.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/02-test-guest.png)、[03-event-detail.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/03-event-detail.png)、[43-logged-out.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/43-logged-out.png)。

2. **登录注册｜正常服务受阻；测试环境辅助走通。** 在活动详情点击“登录后保存材料”，切到“第一次来，注册账号”，填写手机号、测试验证码、密码、姓名、能力和想尝试的事。测试码直接出现在页面，并注明“未发送短信”。注册后仍停在所选活动，材料入口可用。第二人也通过独立页面完成相同步骤。正常8893注册弹窗明确提示“短信服务尚未配置，暂不能注册或使用验证码登录”；只读 /api/studio/sms-status 返回 ready/configured/delivery_verified 均为 false；未点击正常服务的获取验证码或提交注册。证据：[04-login.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/04-login.png)、[06-register-code.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/06-register-code.png)、[07-after-register.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/07-after-register.png)、[15-second-register-code.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/15-second-register-code.png)、[47-normal-register-unavailable.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/47-normal-register-unavailable.png)、[normal-sms-status.json](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/normal-sms-status.json)。

3. **选择活动、收集个人材料｜自然走通，整理使用fixture。** 粘贴带“合成场景，非真人访谈”标注的校园失物需求，填写来源作者，材料性质选“虚构样例”，点击“保存并读取材料”，再“加入本活动样例规则”“帮我整理”。看到2份材料“已读取”、条目来源、未独立核实、待确认截止时间；“不会自动发布方向或任务”明确了产出边界。知道整理只是资料，需要后续确认；实际未把条目通过“带入实践”批量共享，后续共同方向手工填写。证据：[08-materials-organized.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/08-materials-organized.png)。

4. **个人工作台讨论与历史｜自然走通，回答使用fixture。** 点击左侧“实践”，进入“个人空间·本人可见”；点击“开始一段讨论”，勾选1份个人材料，选择“想方向”，输入希望缩小校园助手范围、说明下一步产出的提问。回答明示固定体验样例并显示“回答已保存到本人的会话”。刷新页面后完整问答仍存在；最终退出重登后切回“我的个人空间”再次读到原历史。下一步共享或建队入口清楚。证据：[09-practice-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/09-practice-entry.png)、[11-personal-chat-result.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/11-personal-chat-result.png)、[12-personal-history-restored.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/12-personal-history-restored.png)、[48-personal-history-after-relogin.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/48-personal-history-after-relogin.png)。

5. **创建小队、第二位同伴加入｜自然走通，有一步绕路。** 点击工作台的“创建或加入小队”，输入“校园找找队（合成体验1）”，点创建。创建后自动进入共同方向页，没有在成功状态就展示邀请码；凭导航返回“小队”，看到“邀请同伴加入”和队伍码 ecf5c40f7741。第二人在独立context注册后，按“实践→创建或加入小队”进入组队页，填写队伍码并加入；其工作台显示该队名称，队长小队页随后出现两人。证据：[13-team-create-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/13-team-create-entry.png)、[14-team-created.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/14-team-created.png)、[16-team-code.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/16-team-code.png)、[17-second-join-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/17-second-join-entry.png)、[18-second-joined.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/18-second-joined.png)。

6. **个人工作情况与共同方向｜自然走通，下一步需要自行选导航。** “填写我的优势与时间”引导去成员页，注册时能力已带入；两人分别填写本次意愿和可用4/3小时并保存。队长进入“方向”，填写实际范围：仅完成最小流程说明与松伴体验记录，不声称实现助手；活动原文、评分均明确未知，截止留空。点击“保存共同方向”，收到成功提示。表单解释个人讨论不会自动改共同方向，但保存后没有明确“下一步去哪里”按钮，需凭工作台/任务导航继续。证据：[19-member-profile.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/19-member-profile.png)、[20-direction-empty.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/20-direction-empty.png)、[21-direction-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/21-direction-saved.png)、[22-team-workspace.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/22-team-workspace.png)。

7. **显式共享讨论｜自然走通。** 切回“我的个人空间”，在原回答下点击“选择内容共享”，选目标团队、重写本人摘要，点击“预览共享内容”。预览明确原提问也会共享，原助手回复不自动共享，其他回合仍私有，确认后不会自动统筹。点击“确认共享到团队”，显示记录编号；第二人去“资料库”实际看到原提问和编辑后的摘要。输出与范围在发送前清楚；但接收页把本人编辑摘要前缀显示为模型名，归属有歧义。证据：[23-share-personal-dialog.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/23-share-personal-dialog.png)、[24-share-preview.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/24-share-preview.png)、[25-shared-complete.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/25-shared-complete.png)、[26-second-sees-share.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/26-second-sees-share.png)。

8. **队长统筹与确认任务｜自然走通，任务建议使用fixture。** 队长切到团队“任务”，页面“我的下一步”提示综合当前信息；点击后生成“待确认建议”。展开“查看建议任务（2）”，读到T1“整理一页项目说明”、T2“准备一分钟演示与交付清单”以及各自负责人、检查方法和T2等待T1。点击“确认并发布这2项任务”，在浏览器原生确认框确认“新版本会替换当前正式任务，旧版本保留记录”。出现v1正式任务；第二人只显示由队长发起统筹和确认。证据：[27-tasks-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/27-tasks-entry.png)、[28-orchestration-draft.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/28-orchestration-draft.png)、[29-draft-expanded.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/29-draft-expanded.png)、[32-tasks-confirmed.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/32-tasks-confirmed.png)。

9. **第一位成员同步真实标注成果｜自然走通。** 在T1下点“同步这项任务的进展”，表单自动选中T1。直接在页面写成一页文字说明：目标用户、核心问题、最小范围、三步流程、真实UI观察、未实现限制；选择“本人报告完成”，另填实际依据和核对方法，保存。页面明确显示“本人报告完成”“等待同伴检查”，并提示完成与检查是两件事。产物即报告正文，不是假链接或声称存在的外部程序。证据：[33-task-progress-selected.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/33-task-progress-selected.png)、[34-first-reported.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/34-first-reported.png)。

10. **第二位成员检查、再同步自己的成果｜自然走通。** 第二人在“任务”刷新，下一步提示“先检查队友交来的T1”。展开“查看当前成果依据”，实际读完一页说明，再点“检查T1的成果”，填写逐项检查结论；认可范围限定文字说明，未认定助手可运行。随后点击本人T2的同步入口，把开场、三步口述流程、限制、分工、交接清单写成一分钟文字脚本，明确没有录制视频、实现助手或实际演示，并保存为本人完成报告。证据：[35-second-check-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/35-second-check-entry.png)、[36-peer-check-form.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/36-peer-check-form.png)、[37-second-reported.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/37-second-reported.png)。

11. **队长检查第二人成果｜自然走通。** 队长刷新，展开T2当前成果依据，实际逐段读过脚本；点击“检查T2的成果”，记录开场、三步说明、限制、分工和清单均存在，认可范围仅为文字脚本及体验记录。保存后两项任务显示同伴检查通过，统计2/2；“我的下一步”转为交接核对。证据：[38-captain-reads-second.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/38-captain-reads-second.png)、[39-two-peer-checks.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/39-two-peer-checks.png)。

12. **交付/交接｜平台内自然走通；外部正式提交未发生。** 点击“交付”，看到当前2/2检查记录、无可核对截止时间、演示与文件“需实测”、主办方收件“未知”。页面反复说明记录不是完成率或收件证明。点击“导出当前交接清单”，成功下载Markdown；检查文件含共同目标、两份完整报告、成员依据、检查人和检查说明、对应报告与检查记录ID、提交前仍需核对项。没有主办方入口或真实回执可供本场景提交；不把该阶段写成真实作品交付完成。证据：[40-delivery-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/40-delivery-entry.png)、[handoff-export.md](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/handoff-export.md)。

13. **复盘｜自然走通。** 点击“复盘”，看到2项任务、2项当前成果检查、3条进展和共同目标。填写本次实际学到的共享与检查区别、创建队伍与方向衔接问题、未实现作品的边界；“保存到团队记录”后出现“网页复盘”条目，计数增至4。知道这段文字会对团队可见。证据：[41-review-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/41-review-entry.png)、[42-review-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/42-review-saved.png)。

14. **退出、重登、续做｜自然走通。** 点击退出回到落地首页，经“登录↗”用密码重登。自动进入原团队工作台，团队信息恢复；去复盘读取此前记录和2项检查，再补存“重登续做验证”，计数增至5；切到个人空间确认原讨论历史仍在。团队工作台没有个人空间的旧会话，需要自己理解右上角空间切换。证据：[43-logged-out.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/43-logged-out.png)、[44-relogin.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/44-relogin.png)、[45-review-restored.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/45-review-restored.png)、[46-resume-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/46-resume-saved.png)、[48-personal-history-after-relogin.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/48-personal-history-after-relogin.png)。

旅程结束后补查右上角“?”使用帮助。它用四段短文覆盖建队、方向、任务统筹、同伴检查、未连工具可直接网页补进展，以及正式提交边界，说明帮助内容是有用的。第一次经过方向保存页时没有主动弹出这些指引。证据：[49-help.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/49-help.png)。

## 问题，按严重性排序

**S1｜阻断：正常8893尚不具备本次新用户注册条件。**

复现：正常服务 /#/events → 登录 → 第一次来，注册账号。实际：注册弹窗直接告知短信未配置，只给已有账号密码登录的出路；只读状态API也为未就绪。预期：首次参赛者能够注册，或在开始填写前获得清楚的暂不可用解释和可继续体验的正式路径。影响：真实新用户无法从游客独立闭环。本次没有发短信验证，因此结论是“UI和配置状态表明注册不可用”，不是一次真实短信发送失败。建议：正式开放前完成服务端短信配置与送达验证；未开放时把新用户入口明确标成暂不可注册并给可理解的后续选择。证据：[47-normal-register-unavailable.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/47-normal-register-unavailable.png)、[normal-sms-status.json](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/normal-sms-status.json)。

**S2｜明显绕路：建队完成后，邀请队友和继续执行的下一步没有就地承接。**

复现：工作台→创建或加入小队→输入名称→创建。实际直接跳共同方向，邀请码不在当前页；返回“小队”才看到码。再保存方向后只有“共同方向已更新。已有草案需要根据新资料重新统筹”，当时实际还没有草案，也没有去任务页的按钮。预期：创建成功即可复制邀请码；方向保存后看到一条明确行动，例如“继续讨论”或“去任务生成分工”。建议：在建队成功页同时提供“邀请同伴”和“确认方向”；保存方向后按真实状态显示下一步，尚无草案时避免使用“已有草案”。严重程度为多一步探索、非阻断，实际通过可见导航走通。证据：[14-team-created.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/14-team-created.png)、[16-team-code.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/16-team-code.png)、[21-direction-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/21-direction-saved.png)。

**S2｜明显理解绕路：加入团队/重登落入团队工作台后，原个人讨论的去处不明显。**

复现：在个人空间讨论→创建团队→工作台，或退出后重登。实际团队工作台显示“给想法一个开始”和空会话状态，原讨论要在右上角切回“我的个人空间”才出现。预期：让新手明确这是另一个会话空间，并给“查看个人讨论”入口，避免误以为历史消失。建议：空状态补一句“你的个人讨论仍在个人空间”，附直达按钮；空间名称用“当前团队中的本人讨论”解释，而非仅“本人可见”。数据实际未丢失。证据：[22-team-workspace.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/22-team-workspace.png)、[44-relogin.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/44-relogin.png)、[48-personal-history-after-relogin.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/48-personal-history-after-relogin.png)。

**S2｜信息归属风险：团队资料库把用户重写的摘要列在模型名称后。**

复现：个人回答→选择内容共享→完全重写“本人编辑摘要”→预览并共享；第二人打开资料库。实际接收页显示“ux-review-sample：”后接我自己重写的摘要，页头写“模型名称：回复关键信息”，没有就地标明这是用户编辑版。预期：队友能区分模型原文与队友整理出的摘要。建议：用“林小禾编辑的摘要（基于…模型回答）”，保留测试来源，避免让模型名承担本人改写内容的作者身份。此问题是UI归属文案，与fixture回答质量无关。证据：[24-share-preview.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/24-share-preview.png)、[26-second-sees-share.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/26-second-sees-share.png)。

**S3｜文案可改：没有前置任务时仍称“前置成果已有检查记录”。**

复现：发布首版任务，T1无前置、T2等待T1，尚未同步任何成果。实际“我的下一步”对T1说“它的前置成果已有检查记录”，同时统计0/2检查。预期：说明“这项任务没有前置依赖，可以先开始”。建议按“无依赖”和“依赖已核对”分别用语。此为界面操作指引（页面标“不调用模型”），不能归咎于模型回答内容。证据：[32-tasks-confirmed.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/32-tasks-confirmed.png)。

**S3｜文案可改：赛事要求、评分填“未知”后仍说已保存原文和评分依据。**

复现：方向页赛事要求填“正式主办方要求未知，待核实”，评分填“未知，尚未获得主办方评分依据”，保存后打开交付。实际状态为“有记录”，说明“已保存原文和评分依据”，导出也沿用该说明。预期：至少不要把任意已填写文字称作已保存原文；建议改“已填写相关信息，待核实”，或提供用户可选的“尚未获得/已有原文”状态。页面已注明“有记录不是完成率”“仍需核实”，因此此项不判为提交状态造假或阻断。证据：[21-direction-saved.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/21-direction-saved.png)、[40-delivery-entry.png](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/40-delivery-entry.png)、[handoff-export.md](E:/松伴/songban-materials/.browser-cache/ux-review/20261031/session-1/handoff-export.md)。

其他小观察：同步成果和检查的示例以“请求返回200、空输入错误”为主，对不会编程的新手不够亲切；可以加“逐项核对文案、同伴按三步流程试用”示例。共同方向页标题“让每个智能体知道，我们要去哪”比“全队共同目标”更依赖术语。未把这些偏好建议夸大成失败。

## 最有效的三个优点

1. **允许先个人探索，再显式共享。** 不用先组队就能留资料、讨论；共享前预览目标团队、原提问、本人摘要和模型来源，能建立边界感。实际第二人看到了被共享内容，个人历史也保留。
2. **“我的下一步”会随状态变化。** 统筹前、草案待确认、本人完成等待检查、队友先检查、两项检查后交接等都有实际观察；它比顶栏十个功能入口更能引导第一次参赛者。
3. **完成、检查、交付边界清楚且可导出。** 自报完成不会直接成为同伴检查通过；不同账号需写检查依据。交付明确区分2/2任务记录、文件实测、主办方收件，导出保留报告与检查ID，重登后记录仍在。

## 完整闭环及边界

- 平台内实际完成：游客活动→两人注册→个人材料→个人讨论及历史→创建/加入小队→共同方向→显式共享→队长统筹/确认→两人同步真实文字产物及依据→互相检查→交接清单导出→复盘→退出/密码重登→继续保存。
- 完成的是“松伴界面中的协作记录与文字交接”闭环。校园助手的编码、部署、真实用户验证、真实演示、比赛报名和主办方提交均未发生，不能写成全流程真实参赛已经完成。
- 正常服务在注册处受阻。完整后续依赖专属测试环境，不能用本结果代替生产可用性验收。
- 短信：隔离进程显示本机测试码；其底层 /sms-status 仍报告真实配置未就绪。该并存是测试安排，不能写成生产矛盾，也不证明短信送达。
- 模型：整理、个人讨论、团队统筹均用固定fixture，页面有“协议测试替身/固定体验样例”标识。只评估入口、保存、共享、确认、状态衔接；不评价真实AI理解能力或建议质量。
- 产品路径没有靠业务源码、旧E2E、隐藏URL、业务API写入或数据库补全；测试环境本身是明确辅助，其余路径均依页面独立找到。正常服务短信状态读取是唯一业务只读API辅助核对，已单独标注。
- 自动化定位曾把链接当按钮、把“?”作为无障碍名称，修正到真实DOM角色/“使用帮助”即可；一次原生发布确认框被Playwright默认取消，随后明确接受UI确认再发布。这些属于浏览器脚本适配，不作为产品缺陷。
- DOM文本含select中未选中的“还没有会话”，截图证明实际选中的是已有会话；曾在进度更新误读，随后已纠正，本报告不列为缺陷。
- 控制台保存了2条404资源错误，没有捕获到pageerror。日志未记录404资源URL，无法准确归因，不宣称对业务有影响；没有把它们扩展成确定缺陷。
- 只新增本会话证据和本报告，没有修改业务代码、其他会话文件或正常服务数据。

**对新手视角的总体判断：入口温和、个人探索和任务检查衔接较顺；建队邀请、方向保存后的下一步、个人/团队会话切换还需要用户自己理解。修复真实注册条件后，优先补齐这三个衔接点，比继续增加功能更能改善“我现在该做什么、做完会得到什么”的清晰度。**
