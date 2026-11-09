# 七门试学课程：来源与内容边界

U期增量核对日期：2026-11-04（Asia/Shanghai）；原目录与封面证据日期为 2026-11-03。这是技术资料核对记录，不是教师签名或儿童学习效果报告。课程状态均为 `trial`，`education`、`pilot` 均为 `pending`；`technical: draft` 保持冻结契约，自动检查结果另存于 evidence。

AI 工作台署名：2292576833。原创课程内容及 SVG 沿用 [COPYRIGHT.md](../../COPYRIGHT.md) 中 2292576833、Fantacy567、andorwu5-dev 的三方共同所有权。外部技术资料仅做参考链接和简短转述，未复制其插画、品牌界面或大段文本。

## 已阅读的一手资料与支持范围

2026-11-04 通过官方页面正文与定位搜索复读了下列第 2–11 项；实际阅读章节、短转述、精确 URL 与日期存于 [source-checks.json](source-checks.json)，对应 [teachers.json](teachers.json) 的来源字段。第 1 项仅保留 2026-11-03 的历史术语参考，不标成今日复核。教师脚本、首课顺序和预计用时是本项目设计，资料本身不验证这些设计的教育效果。没有调用模型、发送邮件/短信或执行外部插件。

1. [GitHub Blog：Spec-driven development with AI](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)，开头及实施检查部分：描述目标、AI 返回代码的工作方式，以及结果可能不符合意图。用于 ai-tools 的术语背景。五步练习是本课设计，不宣称是术语唯一标准。
2. [GitHub Docs：Responsible use of Copilot inline suggestions](https://docs.github.com/en/copilot/responsible-use/inline-suggestions)，Limitations 与 Best practices：生成代码可能有误，应审查与测试。用于 ai-tools 与 models 的核查边界，不外推为任意模型的具体错误率。
3. [MDN：What will your website look like?](https://developer.mozilla.org/en-US/docs/Learn_web_development/Getting_started/Your_first_website/What_will_your_website_look_like)，First things first / Sketching：先规划内容用途，从简单网页与草图开始。用于 imagination；四格目标卡和预计用时是课程设计，未经过本平台儿童试点。
4. [MDN：JavaScript — Adding interactivity](https://developer.mozilla.org/en-US/docs/Learn_web_development/Getting_started/Your_first_website/Adding_interactivity)，事件与更新页面的说明：点击可触发处理代码。用于 ai-tools 与 first-project。最小按钮 HTML 为本项目原创，已在 Edge 中执行原文及修改变体。
5. [MDN：What are extensions?](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/What_are_WebExtensions)，正文定义：扩展为浏览器增加功能。用于 plugins 的真实宿主扩展示例；本课只有重点高亮这一课程内开关，没有安装原生插件。
6. [MDN：permissions](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/permissions)，权限声明与请求范围：外部浏览器扩展可以申请特定能力。用于 plugins；不将浏览器权限机制等同于所有插件机制。
7. [Google：Introduction to Large Language Models](https://developers.google.com/machine-learning/crash-course/llm)，What is a language model / Context：语言模型根据上下文估计 token 序列的概率。用于 models 的儿童化简述，不把软件描述为有意识的人。
8. [MDN：Overview of HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Overview)，HTTP flow / HTTP Messages：请求、响应和状态码。用于 api。本项目的 `greet`、1–40 字符及 422 行为来自冻结契约，不能归因于 MDN。
9. [MDN：Introduction to web APIs](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Client-side_APIs/Introduction)，APIs in client-side JavaScript / APIs that fetch data：浏览器能力接口与向服务器取数据的接口。用于 api，避免把 API 全部解释为模型服务。
10. [Anthropic：Building effective agents](https://www.anthropic.com/research/building-effective-agents)，简单方案、任务路由与评估：不同任务可分配给不同能力，应考虑质量、延迟和成本。用于 model-powered-app 的职责拆分。文章含较早工具背景；课程未依赖其具体产品版本、型号或价格。
11. [Google Cloud：API key best practices](https://docs.cloud.google.com/docs/authentication/api-keys-best-practices)，Don't include API keys in client code：密钥不嵌入客户端，服务端持有凭据。用于 model-powered-app 的接入边界，不表示本项目已接入 Google 服务。

## U期每课独立产出

- ai-tools：角色介绍卡；先示范，再让孩子提出要求、查看、追问修改、检查并保存。原五项代码流程排序保留为可选参考。
- imagination：兴趣火花、组合后的文字画面或自选的作品方向；愿意制作小工具时才选用四格目标卡，不强迫每个幻想都有实用用途。
- first-project：按钮网页、一次亲自修改、修改前后观察；课程记录不冒充作品创建。
- plugins：重点高亮开关前后的观察。封面中的格线和装饰模块是附加能力的比喻，不表示当前开放了这些扩展。
- models：共同提醒任务的固定样例 A/B 对照、具体错误和选择依据；不作真实供应商排名。
- api：一次有效请求、一次空白错误与修正后的观察；问候由本站固定规则产生。
- model-powered-app：输入、职责、输出、失败回退四格方案；用本课给出的故事正常输出与空输出固定样例检查。UI 按钮只查字段是否齐全并串起路径，语义是否合理由学习者自己判断。

旧目录三步结构与 activity.kind 保留兼容历史记录，展示为可选“动手试/参考材料”；主入口是老师对话。每课可直接开始，既有作品与前课成果只作为可选延续。工具入门和想象都用纯文本成果，但教学方法与产出不同；其余五课分别关联现有受控工具，不新增路由或任意执行入口。

七位老师的具体开场、帮助方式、知识点、误区和成果要求见 [teachers.json](teachers.json)。真人试用时可使用 [TRIAL.md](TRIAL.md) 的场景与空白观察记录；目前尚未招募或记录真实参与者。

## 工程证据和待验收项

U期离线命令：`node scripts/validate_ai_teachers.cjs`；`node --test tests/test_ai_teachers.cjs tests/test_ai_course_catalog.cjs`。2026-11-04 已通过 16 项内容测试（新增老师测试 7 项、原目录测试 9 项）。验证覆盖冻结 ID、来源记录对应、角色差异、已知强制作答回归、工具范围和未伪造审阅状态。自然语言检查只能发现已编码的回归模式，不能证明老师实际表现或孩子理解。

旧 `evidence/evidence.json` 与封面截图仍是 2026-11-03 版本，未冒充当前工作台 UI 证据；七个 SVG 文件保持不变。目录文案改动后旧 catalogSha256 不匹配属预期，旧首个项目起步代码未改。

运行 `node --test tests/test_ai_course_catalog.cjs` 可检查有效目录和八种契约错误。运行 `node scripts/validate_ai_course_catalog.cjs --render` 可重建 `evidence/`，检查 SVG XML、尺寸、元信息、无执行元素/外部资源、浏览器可解码、七份文件/去色构图/渲染哈希互异，并执行目录中的按钮代码。

封面 `evidence/all-covers.png` 与七张逐图 PNG 均来自本地 Edge 渲染。自动哈希不同只证明不是同一数据，不能替代视觉审阅；本次已实际查看总览中的全部七图。构图分别为桌面电脑、立体画册、积木桥、可拆模块机器、双装置比较台、双向通信桥、能力连接与回退应用。

这些检查不验证平台身份隔离、课程保存 API、整页导航或部署状态；由 C02/C03 与主会话整合验收。教师审阅、儿童独立操作与理解观察、阅读难度和用时估计仍待真实试点。真实模型质量、速度、费用与配置连通性本轮未验证，也未发起付费调用。
