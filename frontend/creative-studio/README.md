# 儿童编程创作工作台

本模块负责真实网页项目的界面，不自行创建身份、保存密钥或启动模型。统一入口与学习身份由宿主页面提供。AI 工作台贡献版权为 2292576833；项目共同所有权见仓库 COPYRIGHT.md。

## 接线

从 `index.tsx` 导入 `CreativeStudio`。传入已有 `LearningApi` 的 `api`、当前 `identityKey`，孩子模式传 `learnerId`。`initialProjectId` 用于首次深链恢复；后续作品选择通过 `onProjectChange` 告知宿主。身份变化会卸载整个私密工作区。

`onDirty` 供宿主未保存内容提醒使用；`beforeTransition` 处理有草稿时的作品切换。宿主可提供 `onOpenPortfolio`。宿主在检查身份或退出期间必须收起组件；不要把未验证的账号字段当作学习身份。组件全部业务请求使用 `api.platform`，保留现有 cookie、CSRF、前后身份检查和取消机制。

模型按钮仅在服务端返回 `runtime.available=true` 时启用。没有 Harness 运行环境时，手工编辑、保存、运行浏览器代码和版本恢复仍可使用。进入页面、刷新和读取状态不会发起模型调用。未知结果只读取原记录，不自动重发；轮询达到上限后显示人工核对入口。

## 预览边界

预览使用服务端受鉴权的专用 HTML 文档：`/api/platform/v1/studio/projects/{id}/preview/{version}/document`。URL 只含作品与版本 ID，不携带 token。文档返回单独的严格 CSP、`sandbox allow-scripts` 和禁止缓存头；iframe 同样仅声明 `sandbox="allow-scripts"`，没有 `allow-same-origin`。

不能改回 `srcdoc`：它会继承主页面的 `script-src 'self'` 并阻止作品脚本。也不能为运行作品而放宽整个平台的 `script-src`。主页面只允许本地 iframe 文档；版本绑定、私密文档访问与身份恢复由后端负责。

## 教学表达

孩子先提出想法，再预测、操作、观察、解释和修改。界面分别显示固定教学提示、AI 协助内容、孩子保存的代码版本和自述观察；生成或运行成功不会自动认定掌握、通过或发布。观察内容随孩子明确点击归档保存到本人作品集。此组件不宣称教研认证或已证实教育效果。

## 验证

运行 `node scripts/build_creative_studio.mjs` 生成独立资源；宿主也可直接通过 TSX 导入参与原学习页面构建。

运行 `node frontend/creative-studio/tests/browser.cjs` 做隔离浏览器组件验证：共 15 项，包含在严格主页面 CSP 下运行预览、阻止读取父文档和外部请求、手写修改、AI 作业只读轮询、真实观察归档、冲突保留输入、身份切换、未知模型结果仍能手工编辑归档与移动端布局。测试没有真实模型、邮件或数据库调用，不能替代真实 HTTP 接线与部署环境验收。

`tests/entry.cjs` 另验证 8 项新旧入口与访谈确认衔接，包括保存确认完成后才离开、恢复已有邀请卡课次、旧课程目录故障不影响独立创作入口。

`tests/http.cjs` 在明确授权的隔离虚构家庭实例验证真实 HTTP 与数据库流程，拒绝使用保留的 8894 / 8895 服务。设置 `SONGBAN_CREATIVE_SYNTHETIC=1` 和该隔离实例的 `SONGBAN_CREATIVE_HTTP_ORIGIN` 后运行。当前 12 项通过，含主页面真实 CSP、作品集往返、家长只读归档、退出撤权、1440×900 首屏对话输入可见及手机布局；不调用模型。后台、课程内容复核和真实 Harness 容器仍须独立验收。
