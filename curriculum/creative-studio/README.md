# 首个网页作品教学草稿

本目录是课程内容与可复现实验，不是已发布课程。知识目标和来源在 `first-web-v1.json`，三个 `examples/` 子目录分别提供事件、状态和条件的最小示例。示例代码属于平台提供的支持，不计作孩子独立完成。

运行 `node scripts/validate_creative_curriculum.cjs` 会启动仅提供这些示例的临时本机服务，并在浏览器中验证：点击与清空、按钮文字与行为的区别、计数与显示、修改初值与增量、刷新重置，以及阈值以下／等于／以上。脚本另外生成明确的表达式变体，检验 `>`、`>=` 和 `===` 的不同结果。运行不会调用模型、读取真实孩子资料或修改课程状态。结果写入仓库外 `outputs/curriculum-technical-*/results.json`，包括浏览器版本、课程版本和示例文件 SHA-256。

技术自动检查只能支持对应代码行为。`technical_review` 和 `education_review` 留给实际复核者填写，试点记录必须来自真实、获准的观察，不能由自动脚本补造。

技术复核应逐项确认事实与所引文档一致、示例能够运行、误解提示准确、迁移题没有暗中增加前置知识。教研复核应检查说明的可读性、帮助如何逐步减少、观察记录能否区分独立完成与提示后完成；发现不适合孩子的内容时修改版本后重新核验。试点中记录孩子做了什么、得到何种帮助和稍后能否再次尝试，不仅记录“点击通关”。

技术来源（2026-11-03 再核对）：[MDN 事件](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Scripting/Events)、[MDN 变量](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Scripting/Variables)、[MDN 条件语句](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Scripting/Conditionals)。这些来源支持程序语义，不证明松伴教学有效。
