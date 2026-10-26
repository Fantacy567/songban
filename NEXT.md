# 开发交接 · 2026-10-26 · v0.2

## 目标与完成状态
- 赛内协作首版：需求、流程、FastAPI/SQLite、可操作页面、接口交接、部署准备与验收报告已完成。
- 主流程：规则/讨论→草案编辑→队长确认→依赖任务→提交→跨成员退回/通过→交付复盘导出。双自动化浏览器会话走通；刷新共享，无实时推送。
- 本地项目 work/hackathon-collab；此前2292576833/-为空仓库。本次未向远端写入。源码交接包在上层hackathon-collab-v0.2-source.zip，不含密钥、数据库或虚拟环境。

## 模型事实与下一步
- 默认DeepSeek-V4-Pro / deepseek-v4-pro。自带key由队长在页面输入，从可信服务/models选完整名称与ID，不能从key字符串猜模型名。
- 自带key仅本次服务内存，不回显/落盘；重启清除。请求与响应模型ID分别记录。
- 当前环境DEEPSEEK_API_KEY存在。官方列表200，真实生成失败。一次公开的32-token诊断确认上游402 insufficient_balance_error。不要重复重试；不使用历史聊天密钥。
- 已补明确503 model_insufficient_balance、权限错误、限流提示。真实生成及建议质量未验收；需要有可用额度的key后再做一次有上限的生成和人工评估。

## 实际验证
- 26项unittest通过（0.787秒）；真实TCP与进程重启保留原文/任务/审计；一致性数据库备份通过。
- 最新浏览器完整流程通过，390px隐藏模型入口可点击且保持可见、主体无横向溢出、无未处理JS异常。录像21.16秒；不是教学视频，角色不是实际队友。
- 模型UI与协议模拟通过，不等于真实DeepSeek生成。
- 独立证据审查通过；需求与模型实测边界已同步，详情docs/验收报告.md。

## 运行与交接
- 主服务http://127.0.0.1:8886，exec session79556、PID13941。只操作此本项目服务，不影响8871—8873等其他服务。
- .venv依赖已安装，启动/回退详见README.md。健康GET /health；流程/workflow；接口/api/openapi.json。
- Node=/Users/ben/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node；NODE_PATH=/Users/ben/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules；PLAYWRIGHT_BROWSERS_PATH=.browser-cache；系统Chrome。
- 首版正式方案仅确认一次，未实现公网账号、录音、代码托管、GitHub自动验收或科学最优分工保证。
- 下一步：可用模型额度后完成真实生成验收；用户与胡进行真人接口联调，按需求选择下一版范围。
