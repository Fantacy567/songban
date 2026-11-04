# H2 私人作品集前端交接

日期：2026-11-02。按 [platform 作品集规划](../../../docs/planning/learning-roadmap/platform/04-作品集与数据衔接.md)和 `app/platform_v1/schemas.py` 当前字段实现；业务鉴权、幂等回执和学习/比赛事实由后端负责。

本目录独立导出 `PortfolioPage` 和 `types.ts` 中的展示及请求类型，不改共享壳、路由或原学习页面。列表、详情、版本、外部工具作品、比赛来源提议与孩子确认均调用传入的同源 transport。没有自动公开、真实模型调用、外链抓取、远程 iframe 或浏览器持久化私人草稿。

## 中央接线

```tsx
import { PortfolioPage } from '../platform/portfolio';
import type { PortfolioTransport, WorkDetail } from '../platform/portfolio';

// platformApi 已负责 /api/platform/v1 前缀、当前会话、CSRF、超时和身份重核对。
const transport: PortfolioTransport = (path, method = 'GET', body) =>
  platformApi.request(path, method, body);

<PortfolioPage
  transport={transport}
  learnerId={explicitlySelectedAuthorizedLearner.id}
  mode={session.mode}
  identityKey={`${session.id}:${session.mode_epoch}:${boundary}`}
  onOpenLearning={(runId, artifactId) => openExistingLearningRoute({ runId, artifactId })}
  onOpenCompetition={projectId => openExistingCompetitionRoute(projectId)}
  onDirty={dirty => setGuard({ dirty })}
  onCurrentWork={(work: WorkDetail | null) => setCurrentPortfolioContext(work)}
  getAssetUrl={assetId => authorizedSameOriginAssetUrl(assetId)}
  renderImageTools={work => <CentralImageTools learnerId={work.learner_id} work={work} />}
/>
```

示例函数由中央实现，不是本模块新增的 API。`onOpenCompetition`、`onDirty`、`onCurrentWork`、`getAssetUrl`、`renderImageTools`、`refreshToken` 与 `beforeTransition` 均可选；`onOpenLearning` 必填。若未提供比赛路由回调，仅保留可读来源，不编造跳转地址。`refreshToken` 用于图片归档后的只读刷新，表单或待核对请求存在时延后读取；`beforeTransition` 保护切换详情或进入编辑前尚未保存的图片输入。

`learnerId` 必须来自明确选择且已授权的学习主体；不能从当前比赛账号、同一浏览器或只有一个孩子推断。当前 `WorkSummary` 只有原 artifact 引用，没有 run ID，因此学习详情使用 `onOpenLearning(undefined, work.source_ref.id)`；空态使用无参数 `onOpenLearning()`。中央仍须使用既有原作品/课次查找和离页保护，不把 artifact ID 当作 run ID。

`identityKey`、`learnerId`、`mode` 变化会重建组件私有子树并丢弃旧身份的迟到响应。中央在身份未确认期间应卸载本组件；本地 key 和角色显示不构成后端鉴权。`onDirty` 在表单改变、保存中和待核对时为 true，卸载时为 false，可直接接现有 guard。私人表单仅在当前挂载内保存；刷新或卸载前的保护由中央处理，不把它写入 localStorage。

`onCurrentWork` 在打开、重新读取、关闭、撤回已打开的比赛来源、身份子树卸载时传入当前详情或 null，供同一个松伴使用最小作品上下文；不能因此加载其他孩子或队友资料。`renderImageTools` 只在 `mode='learner'` 且已打开详情时渲染，管理者永不渲染此可写槽位。图片操作完成后的资产关联与授权由中央面板负责；作品详情再次读回时使用最新服务端投影。

`getAssetUrl` 只解析服务端投影给出的 `cover_asset_id`，不推断、不抓取外部作品链接。接受以 `/api/platform/v1/` 或 `/static/` 开头的同源绝对路径，以及同源 Blob URL。学习接入通过 `LearningApi.platformBinary('/assets/{id}/content')` 鉴权读取后建立 Blob URL，切换身份/孩子或卸载时撤销；不能直接用外链、供应商临时地址或跨源 Blob。失败使用文字预览或标记的松伴示意封面。封面不是作品运行截图或能力证明。

## 接口路径和字段

transport 接受相对 `/api/platform/v1` 的路径，默认 GET：

- `/learners/{learner_id}/works` → `WorkList`。
- `/learners/{learner_id}/works/{work_id}` → `WorkDetail`（包含 `versions`）。
- `/learners/{learner_id}/competition-source-links` → `CompetitionLinks`。
- `/learners/{learner_id}/competition-sources` → `CompetitionSources`；仅 manager 点击读取后调用。
- POST `/learners/{learner_id}/external-works` → `WorkDetail`。
- POST `/learners/{learner_id}/external-works/{work_id}/versions` → `WorkDetail`。
- POST `/learners/{learner_id}/competition-source-links` → `CompetitionLink`。
- POST `/learners/{learner_id}/competition-source-links/{link_id}/decision` → `CompetitionLink`。

外部作品字段为 `request_id,title,summary,url,tool_name,contribution,ai_assistance`；新版本再加 `expected_revision`。帮助情况直接使用 `none_reported|assisted|generated|unknown`，不把本人“未使用”声明写成独立核验。

比赛提议字段为 `request_id,project_id,expected_source_revision,selected_refs,contribution,title,summary`；只可勾选服务端当前账号返回的本人 report/task 引用。决定字段为 `request_id,expected_revision,decision`，决定仅 `accept|decline|revoke`。manager 不出现孩子确认按钮，learner 不出现管理者来源提议入口。

前端不发送 owner、公开状态、封面 ID、AI 完成度或额外认证字段。`visibility` 按 schema 只呈现 private，没有假公开按钮。学习检查和报告回到原学习模块查看；任务安排不显示成已完成成果。历史选择展示对应 `WorkVersion.actual_outputs`，不会把当前标题/贡献说明宣称为历史快照。

## 失败与冲突

transport 拒绝对象约定可包含 `status` 和 `code`，兼容当前 LearningApi 风格；0、无 HTTP status 或 5xx 均保守视为结果待核对。每次显式保存生成一个 `request_id`，保存中锁定按钮并防同步重复点击。

网络未知时保留原 body 和编号、冻结表单，不自动再次 POST。用户点击“核对刚才的保存”才用完全相同的路径/body/request_id 请求现有幂等回执；不会生成新编号或修改原内容。当前契约没有单独 GET 操作回执端点，所以此操作是原请求的显式幂等核对，不承诺上游尚未执行。

409 时保留输入、读取当前详情或来源，停止旧请求。外部版本必须由用户点击“使用当前版本号，保留我的输入”后再提交新编号；比赛来源须显式使用最新来源并重新勾选。读取当前版本失败有重读出口。授权失败清除可见作品；身份切换后的旧响应不会填回新页面。

本地“放弃未保存内容并返回”只在无保存中/待核对操作时可用。外链在详情中仅以 `http/https`、无凭据的安全链接新页打开，明确说明将离开平台且未独立核验，不读取其缩略图或运行代码。

## 视觉与验证

作品画廊用大幅 3:2 预览、图下文字和留白，不加外层卡片边框/重阴影；键盘焦点保留清晰轮廓。文字产物使用真实保存文字的排版预览，外部作品使用原创松树代码图形且标示“示意封面”；打开详情才能看到实际链接。所有样式限定在 `[data-platform-portfolio]`，手机表单字体不小于16px，窄容器与200%放大可切单列。

```text
node node_modules/typescript/bin/tsc --project frontend/platform/portfolio/tests/tsconfig.json
node frontend/platform/portfolio/tests/portfolio.cjs
```

16 项 Edge 组件场景全部使用明确虚构的账号、作品、日期与内存 transport，覆盖默认私有/无边框、真实文本详情、原 artifact 返回、新增、历史版本、危险外链拒绝、响应丢失同请求手动核对、409版本采用、管理者提议、孩子接受/拒绝/撤回、图片回退、跨学习者投影抑制、身份迟到响应、防重复、dirty/context/image槽回调、390/768/1440、键盘和200%放大。证据默认 `E:/松伴/outputs/platform-portfolio-h2/`，可用 `SONGBAN_PORTFOLIO_EVIDENCE` 改目录。

以上16项是组件隔离测试，不代表学校试用或供应商验收。

## 统一学习壳接入与 HTTP 验证

后续接入由 [PlatformPortfolioPage](../../learning/PlatformPortfolioPage.tsx)、[PlatformImagePanel](../../learning/PlatformImagePanel.tsx)、[PlatformCompanion](../../learning/PlatformCompanion.tsx) 与学习 `index.tsx` 完成。manager 先读取本人家庭关系并明确选择孩子，再核对有效学习及家长摘要授权；learner 只用自身 ID。所有平台调用复用 `LearningApi.platform` 的身份、CSRF 与迟到响应栅栏。

大厅和作品集共用一个松伴；课程首作与 run 页面继续原主对话，不叠加平台聊天。图片生成只在用户明确点击后 POST，排队后只 GET 原任务；刷新从作品的 `/image-jobs` 恢复最近20项任务。样例标明本地固定素材，真实图片模型仍须实际配置与授权。归档回执后重新读取图片绑定和作品详情，不重新生成。旧作品版本配图与当前配图区分。

实际 HTTP 集成命令只允许固定 QA `http://127.0.0.1:8901`，执行前验证 `demo_mode=true`、sample可用且live关闭；使用代码仓库已有的明确虚构账号，不使用真实用户或供应商配置：

```text
node frontend/platform/portfolio/tests/platform-http.cjs
```

最后一轮12步通过，证据在 `E:/松伴/outputs/platform-http-h5/results.json`：家长登录/显式选孩子、进入孩子模式、三导航/单页标题/黑客松认识、私人外部作品、当前作品本地松伴、样例图自动保存与鉴权Blob、390px与刷新回读、课程无双聊天、退出清理、同家长重入和另一虚构账号隔离。API错误、页面异常与外部请求均为0；只发起1次sample图片任务，刷新没有再次生成；供应商调用0。

验证发现并修复两项前端问题：归档后面板图片绑定未刷新，以及身份切换结束前快速导航被原目标覆盖。松伴首次只读加载误触未保存保护由H03同步修正。当前结果不代表真实图片供应商、真实模型、学校或儿童教学质量验收；唯一演示站的切换与最终服务整合由中央负责。
