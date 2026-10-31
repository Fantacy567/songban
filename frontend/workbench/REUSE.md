# 松伴工作台前端源码复用与交付记录

日期：2026-10-31。参考目录 `C:/Users/27736/Desktop/黑客松情报局` 只读。以下为实际提取和改写，SHA-256 已在本机复算，未将设计参考宣称为整文件逐行复制。

## 实际来源与目标

1. `src/components/ai-workbench.tsx`
   - SHA-256：`0e1b0a1e4310ed2884e4260d9134638293837a6656660954b9ff1705a14170a4`
   - 目标：`ProjectWorkbench.tsx`、`ConversationPanel.tsx`、`MessageCard.tsx`。
   - 提取目标卡 goal/nonGoals 展示、thread/welcome/examples、userRow/aiRow、bubble/cardHead/speaker 的 JSX 结构和职责选择组件组织，再按松伴字段改写。消息使用真实 message.id，不使用数组序号；旧空间/赛事/导航员分支改为统一本人 session。历史保留在服务端，不迁移清空／归档请求，也不删除旧会话。移除 Next Link、DSH、报名、主办方与固定全屏导航。统一通过封闭动作进入松伴原页面和方向表单。
2. `src/components/ai-workbench.module.css`
   - SHA-256：`71129c78d0c131254ecc9273a20a0c5c7f2487e6a9db2fe99d0a2e31a596f134`
   - 目标：`workbench.css`。
   - 直接提取 main 的 grid 行、thread 的滚动区域与 align-content、userRow/aiRow 的排列、bubble、cardHead、composer 和窄屏布局规则并改写。类名统一 sbw 前缀，替换为 design-v1 的 --sb-* tokens，去掉 DSH 字体、全页负边距和固定高度；不创建第二条站点导航。辅助材料区在窄屏变成可展开区域。
3. `src/components/specialist-avatar.tsx`
   - SHA-256：`a0a8549c99be11fed3048bee271ef6aa71d2971c70744d9f0c4fe1e5f064a50a`
   - 目标：`SpecialistAvatar.tsx`。
   - 实际复制 SVG 脸部、徽记 Mark、fallback 和 SpecialistAvatar 组件，保留原说明注释。去掉 use-client 指令，LOOKS 替换为 materials/direction/next_step 三职责及松伴紫绿配色。无外部图片／网络请求；原 Mark 中未映射的徽记仍为内部绘制分支，不显示额外职责。
4. `src/modules/team-assistant/TeamAssistantPanel.tsx`
   - SHA-256：`2759afd791f7733d119f388d625ad1e79e6fba9d9a1578be8efc7670b21fea3b`
   - 目标：`ConversationPanel.tsx`、`MessageCard.tsx`、`songban-adapter.ts`。
   - 提取错误对象解析、operation identifier 的 crypto 逻辑、Asia/Shanghai 日期格式、message metadata/source details 展示和 mounted/read/write guard 的状态模式。恢复逻辑改为松伴持久 requests/messages；正文使用 text，不保留 data envelope、projectId、DSH、Cookie 身份和 DELETE 清空逻辑。GET 可恢复，POST 不自动重试；未知请求须勾选新尝试，稳定编号在刷新前写入 sessionStorage。忙时输入仍可修改，成功只清除与本轮提交相同的草稿。
5. `src/modules/team-collaboration/ShareSuggestionPreview.tsx`
   - SHA-256：`e26cae708be1f6de8c43ae33da12c95aaa43fbb27505ae00cb3a72474970e96a`
   - 目标：`ShareTurnPreview.tsx`、`songban-adapter.ts`。
   - 提取 edit/preview/shared 步骤、heading focus、stable pending command、writeLock、mounted guard、确定回执后隔离外部刷新异常的控制流程与预览 JSX。原 project team-feed 调用改为 `/api/workbench/sessions/{id}/share`；正文上限 3500，个人会话从 `/api/core/me` 明确选择已加入团队。预览直接展示原提问、本人编辑摘要、团队、实际模型与 fixture 说明；原助手回复仅供本人展开核对，不自动共享。未知共享结果锁定原正文和 request_id，只有用户点击核对才重发同一操作。没有自动采纳／统筹逻辑。

没有直接复制 `client-api.ts`，其固定前缀、服务端 envelope 和 Cookie 约定均不适用；适配层的实际来源为上列两个组件。没有复制参考项目 .env、密钥、数据库、DSH 配置、node_modules、Next 配置或服务端实现。

这些源文件未包含独立许可证头；未推断或捏造源项目授权条款。保留头像源注释与此来源记录。打包器保留 React/依赖的合法注释；原 Montserrat 字体及字体许可证未迁移，因为未使用该字体资源。

## 构建与挂载

- 根 `package.json` 与 `package-lock.json` 锁定依赖；`tsconfig.workbench.json` 只检查当前前端目录。
- `npm ci --ignore-scripts --no-audit --no-fund`
- `npm run typecheck:workbench`
- `npm run build:workbench`
- 实际产物：`static/workbench/workbench.js`、`static/workbench/workbench.css`。IIFE 只暴露 `window.SongbanWorkbench.mount(host, options)`，返回 `{unmount()}`。CSS 以 `.sbw` 作用域融入原壳。
- 已实际运行 `npm ci --ignore-scripts --no-audit --no-fund` 后重新类型检查／构建，前后哈希一致。最终改动后再构建一次，哈希仍一致。最终 JS SHA-256：`fd2f472ec674ab3354de390970b78aed209a625fa24e4abdbbc28fcf779c1fd9`；CSS：`17d4e7efc7cb71afc90be98a3d019bc4a6c2a0445ced05c1a14aba6aaf2af7b9`。
- 无 iframe，无第二个 Next／Web 服务，无运行时 CDN。FastAPI 原站同源提供静态资源和接口。
- 本机 Node：`C:/Users/27736/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe`。本机没有 npm 可执行文件时，使用已有 runtime 的 `pnpm/bin/pnpm.cjs dlx npm@11.6.2` 执行上述 npm 命令；没有改系统配置。

## 身份、恢复与集成约定

- mount 的 identityKey 使用稳定用户 ID；token 只在适配器内存中传递，不写缓存／日志。壳在换身份／团队时先 unmount，再挂载新实例；dispose 中止等待，所有异步结果先检查实例生命周期。
- 草稿、选材、已选会话、未知生成编号和共享预览按用户＋团队＋会话分开存 sessionStorage；服务端才是历史与请求状态的事实来源。浏览器禁用 storage 时仍可使用，但无法保证未发送草稿刷新恢复。退出时壳清除 `songban:workbench:` 前缀缓存。
- 请求超时或未知结果只 GET 核对，不重放原 POST；新尝试需显式勾选。服务端 pending/running 阻止新一轮。同会话内单写锁防双击。
- 401 交给 onUnauthorized；403 实际权限丢失清空私人 UI。source_unavailable/share_scope/captain_required 仅作为可恢复操作错误；来源失效触发重读目录，并允许移除旧选择。
- 接受来源可选 status/warnings/truncated 并以纯文本展示，部分解析、截断、样例不包装为完整事实。coverage.history_limited 为真时显示「本轮只采用部分历史」。实际模型 null 显示未知，fixture 单独标明。
- onPrepareDirection 只在当前队长上下文触发，不保存方向；onShared 只刷新原壳核心状态。任务、方向、材料和记录跳转均来自白名单。

## 验证与范围

组件级浏览器测试：`tests/browser.cjs` 使用隔离内存 HTTP fixture，运行真正的构建产物，不发短信，不调用真实模型，不读取手工数据库。

运行 `npm run test:workbench`。本机通过环境变量 `SONGBAN_CHROMIUM_EXECUTABLE=C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe` 使用已安装 Edge；也可安装 Playwright Chromium。若使用桌面 runtime 的 Playwright，可设置 `SONGBAN_PLAYWRIGHT_MODULE` 为其模块绝对路径。

实际已通过 17 项行为检查：职责与材料字段、纯文本、生成中编辑输入保留、安全动作、显式共享与原提问明示、共享同编号恢复、历史和草稿刷新恢复、未知请求不自动重发、明确新尝试、运行中刷新、身份切换迟到响应、个人团队选择、来源撤回可恢复、撤权后清空私人展示，以及响应式折叠／中文性质、OCR／部分解析／截断说明。390／768／1440 无横向溢出，截图已人工检查。901px 以下默认折叠材料与任务，视口跨断点变化会重置默认展开状态，用户仍可自行展开。

输出写到被忽略的 `tests/artifacts/`：`result.json`、`share-preview.png` 与三档 `workbench-*.png`。最终测试使用 package-lock 锁定的 Playwright 1.62.1 和现有 Edge。首次系统未安装 Playwright bundled headless shell，改用现有 Edge 后运行通过；未将启动失败当成测试通过。

主站壳的 5 秒刷新、真实 SQLite/API、跨用户权限和原统筹链路由集成／验收会话负责联合验证；这里的内存 fixture 不能证明真实模型效果或短信送达。未编辑主站壳／Python，未提交、推送或发布。
