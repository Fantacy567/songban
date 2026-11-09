# 七位课程老师的内容包

Copyright © 2026 2292576833、Fantacy567、andorwu5-dev。保留 [项目版权](../../COPYRIGHT.md) 与外部来源各自权利。

这是 U03 内容范围，配合 U期冻结契约供统一工作台使用。课程内容是试学版本；知识资料阅读、工程检查、教师审阅、儿童试用四者分别记录。

## 内容与接口

- `teachers.json`：版本为字符串 `1`；固定七个 course_id。公开 Teacher 为 course_id、name、opening、suggestions、goal、sources、tools。后台专用 system_prompt、help_strategy、artifact_instruction 为字符串，knowledge_points、misconceptions 为字符串数组，review 为对象。
- sources 项含 title、url、supports、checked_at。review 保留 technical=draft、education=pending、pilot=pending，sources_checked_at 是实际资料核查日。来源阅读不能改写成人类审阅通过。
- `catalog.json`：保留原课程 id、version、chapter、order、activity.kind、三步键和七个 SVG 路径，兼容旧进度记录。老师对话是主入口，旧练习是可选参考。
- `source-checks.json` 和 `SOURCES.md`：2026-11-04 复读的官方页面与边界说明；记录具体章节，避免仅有域名就称已核查。
- `TRIAL.md`：首课操作脚本、七课探索场景与空白观察模板。它是可用材料，不是试点完成报告。

## 教学用法

先调用既有平台能力读取老师材料。模型上下文应包含全部后台教学字段与来源范围；公开接口不得包含 system_prompt。开场是静态示范，只有实际模型请求结果才有模型来源。提示建议供选择，孩子可用自己的文字或直接要求草稿。

小芽陪伴第一次输入、查看、修改、检查、保存角色卡；云朵先发散想象；阿桥依据真实现象协作做项目；齿轮比较课程扩展开关；星镜检查输出依据；小邮区分请求、响应与模型；织光分配作品能力与失败回退。相同服务端模型可以扮演不同教学角色，七位老师不等于七个供应商模型。

text-artifact 只产生纯文本候选。creative-studio 复用现有受限代码工作台。plugin-lab 仅为课程高亮扩展；model-compare 为固定样例对照；api-lab 向本站教学接口发真实 HTTP 请求但没有模型生成；model-app 用固定示例推演。老师不能从这些语义动作扩展出外部安装、任意 URL 或自动执行代码。

## 检查

在仓库根目录执行：

```text
node scripts/validate_ai_teachers.cjs
node scripts/validate_ai_course_catalog.cjs
node --test tests/test_ai_teachers.cjs tests/test_ai_course_catalog.cjs
```

检查离线运行，不请求模型。验证器是内容与范围检查，不是自然语言正确性证明。后台投影、权限、实际模型行为、UI 保存恢复由各工程会话和主会话整体验收；本包不宣称已验收部署。
