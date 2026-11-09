# 平台松伴组件接线

`index.tsx`导出`mountCompanion(host, props)`，浏览器IIFE入口为`window.SongbanCompanion.mount`；独立bundle由中央构建脚本登记。本模块不自带账号、token、fetch地址、路由或供应商。`Companion`可作为React组件使用；原生双壳建议保留同一个host并调用handle.update，卸载前handle.unmount。

props为`identityKey`、`context`、`transport`、`onAction`、可选`presentation`、`disabled`及`onLearningAdapter`。身份key必须包含经服务器核对的主体、模式和epoch；身份变化会卸载旧组件，清除未发送文字及旧私有记录。context允许hall、learning、portfolio、competition，resource_id及learner_id只是引用，后台重新校验。

transport提供open、read、send、readMessage四个Promise方法，字段定义见types.ts。它由中央封装同源请求、cookie／Bearer优先级、CSRF及响应后身份栅栏；不能自动重发写入。组件不使用localStorage保存私聊。请求超时会保留原request_id和输入，按钮只读原会话核对；未找到结果不视为未派发。收到明确4xx拒绝后保留输入，先重新读取。

在learning上下文组件不渲染第二个聊天窗口；读取并核验后通过onLearningAdapter传回learning_run引用。实际课程页继续只渲染原frontend/learning/CompanionPanel及其helps/model接口，不复制课程对话至平台表。大厅和作品集可浮层，另需主区展示时使用embedded。

onAction只接收四个已登记导航动作：打开AI教学大厅、黑客松教学大厅、作品集、已授权比赛队伍。中央映射到实际路由，不能将任意字符串当URL或业务写入。课程通关、投票、报告发布及出图不由聊天触发。

后台默认static，明确显示本地指引；mock仅本地隔离fixture，不代表真实模型。平台live工程已有显式适配，但默认未配置，不自动使用本机模型凭据；课程既有live仍遵循原有授权、预算和unknown。组件实现并不表示已经完成双壳接线和真实浏览器验收，最终证据由中央集成测试记录。

## 显式实时文字配置

后台`CompanionSettings`包含enabled、config_version、model_id、server runner、max_calls、max_output_tokens（默认800）、max_input_chars、timeout_seconds及lease_seconds。中央由`PlatformSettings.companion_settings`传入，构造`CompanionService(...,settings=...)`后调用migrate，后台周期运行worker_once。不会发现.env、复用旧DeepSeek key或从客户端接受预算。`text_runner`工厂仅接受显式受支持HTTPS地址、key及model_id，使用单次兼容chat请求，关闭代理环境与重定向，不重试未知请求。

P02B-companion-live为增量迁移，保留P02和学习迁移校验和。max_calls是整库累计上限：queued/pending已预占，已派发、失败回执及unknown均保守占用；未派发即因身份或来源变化取消才释放。重启和配置版本变化不把已用次数归零。费用估值未知，额度是次数，不是货币。显式增加程序配置上限属于新的服务端授权，界面不能自行扩大。

消息新增pending/running/succeeded/failed/unknown；GET只读原记录，派发只在worker_once。worker先持久化running，离开事务才调用runner，再检查原cookie session或participant账号/浏览器epoch、授权与来源快照；撤权、切身份或来源变化会抑制返回正文。running租约过期后unknown且不再派发。实际模型按响应记录，供应商未返回保持null。学习孩子还需有效live_model用途授权；撤去该用途后历史实时回复隐藏正文及动作，自己的问题仍可见。

前端只有capabilities.live_available才显示live选项；发送后对已知message做有界GET轮询，不重新POST；unknown停止轮询并保留输入和原请求号。轮询停止后可点击“核对原回应”。所有模型建议动作仍由服务器固定白名单给出，不接受模型输出直接写业务。

2026-11-02独立验证：24项临时SQLite域测试、10组组件fixture浏览器案例、严格TypeScript检查通过。兼容供应商测试全部使用httpx.MockTransport和虚构凭据，没有真实供应商请求。实际部署配置、真实供应商及真实儿童效果仍未验收。
