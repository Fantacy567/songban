# Learning v2 P0 提案包

此目录只描述拟议契约，不注册API，不创建数据库或调用服务。业务语义见[接口与迁移规格](../接口与迁移规格.md)。版本为0.2.1，日期2026-11-02，等待S00冻结。

- `openapi.proposed.json`：OpenAPI 3.1提案，66个HTTP操作、100个schema，cookie/CSRF、操作权限与业务条件。
- `operations.json`：紧凑索引，可按 operation_id 对照请求/响应 schema。
- `ui-actions.json`：S02 的 UIA-01–18 映射；付款核验/退款写入留 P5。
- `examples.json`：16个虚构协议样例，包含首主题PATCH、review预检，以及清缓存后家庭/授权发现和未获批准的版本化授权草案；不是业务数据库记录。
- `contract-cases.json`：48个离线契约条件正反例，验证起点/检查既有约束及最小家庭列表、授权摘要、草案禁用等，不能当业务通过证据。
- `acceptance.json`：37条待实现验收场景，全部 `not_run`，含RECOVERY-01清缓存重新登录后恢复本人家庭/授权与越权拒绝。
- `frozen-0.2.0.json`：0.2.0起点/检查及引用共13个schema的SHA-256；生成器不重写此基线，验证器检查0.2.1未改变它们。
- `validation-result.json`：本次离线检查结果与上述 JSON 的 SHA-256。
- `build-contracts.cjs`：可重复生成契约、索引、映射、样例、离线条件与后续验收JSON，只写本目录。
- `validate-contracts.cjs`：检查JSON、引用、端点/参数、schema组合/条件、样例、正反例及派生字段不变量，读取S01作品字段对齐，输出validation-result。结构断言数与离线条件逐项结果分别记录，后端业务场景执行数仍为0。

在 `E:\松伴\songban-pr7-fix` 执行：

```powershell
node docs/planning/learning-roadmap/p0/contracts/build-contracts.cjs
node docs/planning/learning-roadmap/p0/contracts/validate-contracts.cjs
```

0.2.1仅新增GET families、GET learner consents、GET consent-texts/{consent_version}，更新UIA-13/14。家庭限当前manager本人且MVP最多1；pending只读本人既有授权；孩子不能读成人管理记录。文本版本/hash、用途、批准状态和可确认状态由服务端提供，当前样例为研发草案，未获真实试点批准。UI不得自行补授权条款。

0.2.0语义保持：起点PATCH逐主题合并、检查preflight/advance/submit_review、HelpDisclosure与人工unclear规则不变。仅S03文件变动，无业务API在本次被注册或修改。

验证器是本契约所用schema子集的校验工具，不替代完整OpenAPI规范验证器或服务器集成测试。allOf/if/then/oneOf/contains约束在本包内有正反例；跨字段草稿投影/补丁保留不变量另行离线检查。`x-business-rules`中的来源权限、数据库当前性、事务/幂等、实际派单和值班、推荐规则输出等仍须acceptance场景验证。不要把结构匹配理解为审核、授权、预算或内容正确。

修改字段时改生成器后重生成并验证；避免只手改生成 JSON 导致下次覆盖。只在 S00 完成 G0 合并审阅后发布冻结版。服务端实现、旧 Bearer 并发撤销、真实模型与人工复核仍未验收。
