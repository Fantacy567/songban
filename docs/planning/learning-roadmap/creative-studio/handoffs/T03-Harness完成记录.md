# T03 Harness 完成记录

日期：2026-11-03（Asia/Shanghai）。独立侧栏会话执行；未启动子代理或另建会话。

已完成本机可安全限定的固定源码 SDK 构建、协议验证、所用字段类型检查、worker 边界修复与部署准备。**缺少 Docker/Podman，不能认定真实 Harness 容器或真实模型已验收。** 没有新增付费调用、真实邮件、系统组件安装或主机 Harness agent 执行。

## 接续与修改

阅读了 `docs/planning/learning-roadmap/creative-studio/` 的现有规划与负责代码。源码为 `E:/松伴/outputs/harness-source-20261102`，HEAD 确认为 `ce7073d51254c26cd63b22a60835b8f948deb447`；执行后 `git status --porcelain` 仍为空，未改上游 checkout。

1. `deploy/harness/file-guard.mjs`（新增）：源码明确 `fs-local.cwd` 只是解析默认值，原 `tool-fs` 可访问容器其他路径。现用固定源码 `ToolsService.guard()` 对 `read/write/edit` 做三个文件的严格白名单；拒绝路径穿越、其他路径／目录、符号链接、其他工具、权限升级与过大输入。守卫先注册，再发布 `songbanFileGuard` 就绪标记。
2. `deploy/harness/profile.mjs`（新增）：拆出纯 profile 与 SDK options 构造，便于离线验证；保留 shell/工作目录切换/compaction 等禁用项，显式禁用 apply_patch、read_image。SDK server 依赖守卫标记，`maxTokensAsSuccess:false`。模型入口仍是容器 loopback→stdio→宿主固定 DeepSeek；重试上限为0，子进程只收到白名单环境和非秘密占位 token。
3. `deploy/harness/worker.mjs`：复用以上配置；使用真实 SDK `finalResponse`、`finishReason`。写 stdio 结果现在等待 write callback 完成后才退出，避免较大文件结果被 `process.exit()` 截断。未在宿主直接运行该 worker。
4. `deploy/harness/Dockerfile`、`app/creative_studio/harness.py`：取消可覆盖源码 revision 的 build arg，固定提交；复制新守卫与配置文件。增加 `org.songban.harness.contract=2026-11-03-files-v1`，运行环境检查同时要求上游 revision 与此标签，拒绝只有旧 worker 的同 revision 镜像。**需要重新构建镜像；新标签不是已经通过构建的证明。**
5. `scripts/verify_harness_sdk.mjs`：接续已有脚本，实际打包未修改的 SDK client 及其精确值依赖，使用上游 scripted runtime 执行13个协议场景。采用当前 worker 的 options，并新增缺失结束原因、坏 prompt、坏 event、运行时退出等场景；证据可重复运行，并保留上游许可。
6. `scripts/verify_harness_contracts.mjs`（新增）：从固定源码提取原样的纯 `applyEntryPatches` 函数，与实际 sdk-minimal YAML 和当前 patch 组合。YAML `!!js` 只解析成惰性数据，绝不执行；还校验集成使用字段、guard契约、子进程环境、取消回答、路径策略和实际 worker 的输出冲刷函数。类型检查只覆盖选择的集成字段，不冒充完整上游类型检查。
7. `scripts/verify_harness_container.py`（新增）：为具备 Linux Docker 的部署环境准备真实容器＋虚构 provider smoke。仅使用内存 `httpx.MockTransport`，不读取真实密钥或项目库；脚本预期让真实 agent 拒绝越界写、写一个允许文件、正常结束，验证实际隔离参数与容器删除。本机仅运行不可用分支，成功分支尚未运行。
8. `tests/test_creative_studio.py`：新增旧 worker 镜像拒绝、未知任务核对证据与状态限制、保留调用账本且不重派发检查。既有 `close_unknown(..., con=None)` 与外层事务回滚测试已存在，因此只核验，没有重复修改 `service.py`。
9. `deploy/harness/README.md`、`upstream.json`：补充准确的验证范围、标签、操作顺序、外部前提与未验收事项。保留上游 MIT 与 2292576833 版权；派生验证输出也复制了上游 LICENSE。

## close_unknown 交接给管理会话

签名已存在并验证：`StudioService.close_unknown(job_id, *, evidence, authority, con=None)`。

- `con` 省略时自行开启事务；传入现有连接时通过 `nullcontext(con)` 复用，不创建嵌套事务。
- 只允许 unknown→failed，并写 `creative_reconciliations`；保留 `creative_calls` 的所有内容、当前代码版本与原调用额度，不自动发送模型请求。
- 外层事务因授权复核失败而抛错时，状态与审计一并回滚；默认 server-only 入口仍保留。
- 证据要求非空、去空白后10～3000字符，authority非空。真实管理员身份、证据可信性与审计可见范围由管理路由负责；此函数不把任意传入字符串当成通过身份认证。本会话未改管理路由或 UI。

## 本次实际命令与结果

工作目录均为 `E:/松伴/songban-pr7-fix`。Python 为已给定的 clean-env。以下无需真实账号或收费模型。

```powershell
node scripts/verify_harness_sdk.mjs E:\松伴\outputs\harness-source-20261102 E:\松伴\outputs\harness-t03-20261103\sdk
```

结果：退出0，13个场景通过。`completed`、六个不完整结束原因、initialize坏帧、request超时、缺失结束原因、prompt坏帧、event坏帧、runtime中途退出。**这是实际 SDK client＋上游 scripted server；不是实际 agent/容器/模型。**

```powershell
node scripts/verify_harness_contracts.mjs E:\松伴\outputs\harness-source-20261102 E:\松伴\outputs\harness-t03-20261103\contracts E:\松伴\songban-materials\.browser-cache\materials\full-audit-20261031\clean-env\Scripts\python.exe
```

结果：退出0，5组检查通过；选取字段的 TypeScript 检查0诊断，含负向类型哨兵。字段范围为 SDK 启动与结果、provider标量配置、model标量配置、重试策略及工具调用名／参数；上游 pi-ai 外部依赖和完整运行服务不在此类型检查范围内。

```powershell
$env:PYTHONIOENCODING='utf-8'
& 'E:\松伴\songban-materials\.browser-cache\materials\full-audit-20261031\clean-env\Scripts\python.exe' -m unittest tests.test_creative_studio tests.test_creative_integration -v 2>&1 | Tee-Object -FilePath E:\松伴\outputs\harness-t03-20261103\python-tests.log
```

结果：退出0，**26项通过，14.716秒**（创作域21项＋既有中央接线5项）。包含真实ASGI/SQLite隔离数据测试，但模型/容器采用替身；不要计入真实模型或容器验收。出现现有 Starlette/httpx deprecation warning，未导致失败。较早单跑的19项是增加本轮2项前的子集，不重复累加。

```powershell
node --check deploy/harness/worker.mjs
node --check deploy/harness/profile.mjs
node --check deploy/harness/file-guard.mjs
& 'E:\松伴\songban-materials\.browser-cache\materials\full-audit-20261031\clean-env\Scripts\python.exe' -m py_compile scripts/verify_harness_container.py
& 'E:\松伴\songban-materials\.browser-cache\materials\full-audit-20261031\clean-env\Scripts\python.exe' scripts/verify_harness_container.py --output E:\松伴\outputs\harness-t03-20261103\container-readiness
$LASTEXITCODE
```

语法检查通过；最后的容器探针按预期为 **2**，报告 `passed:false`、`real_container:false`、`real_agent_runtime:false`、`real_model_calls:0`，原因是 Docker／当前镜像不可用。**不能把这条探针记成容器测试通过。**

## 证据路径

- `E:/松伴/outputs/harness-t03-20261103/sdk/results.json`：13场景及每次initialize记录；同目录实际打包SDK、上游scripted server与LICENSE。
- `E:/松伴/outputs/harness-t03-20261103/contracts/results.json`：5组检查及固定源码SHA256；`selected-source-contracts.ts`、`typecheck.log`、`composed-profile.json`、`pinned-patch-composer.mjs`可审阅。
- `E:/松伴/outputs/harness-t03-20261103/python-tests.log`：26项测试完整结果。
- `E:/松伴/outputs/harness-t03-20261103/container-readiness/results.json`：容器缺失的实际探针结果。
- `E:/松伴/outputs/harness-t03-20261103/environment.json`：Docker/Podman/默认Docker Desktop缺失、源码依赖与CLI构建产物缺失。本轮没有重跑WSL安装检查，沿用委派给出的“WSL尚未安装”结论。

## 外部前提与未完成事项

1. 本机没有 Docker/Podman，不能构建或运行隔离镜像；固定源码也没有上游 node_modules 和 CLI 构建产物。未在宿主安装上游依赖、执行完整构建、启动 dsh 或运行任何生成代码／任意系统命令。
2. 完整上游 `pnpm install --frozen-lockfile && pnpm run build`、全量类型检查、实际 profile loader／pi-ai／agent 组合、文件工具真实回合及隔离有效性，需要在受控 Linux Docker 环境完成。当前源码契约证据不能替代这些步骤。部署操作见 `deploy/harness/README.md`。
3. Linux 构建机先构建新镜像并核对两个标签，再运行 `python scripts/verify_harness_container.py --output <证据目录>` 的零计费回合；还需补真实容器超时、异常退出和大结果回收验收。本机未验证这些成功路径。
4. 新的真实模型调用预算尚未授权，不能自动发送真实请求；零计费 provider成功也不代表DeepSeek端点/模型可用。真实模型小回合、实际教学复核和孩子试点仍需分别验收。
5. 未修改 `app/main.py`、server_admin、学习前端或图片服务；未 reset/stash/提交/推送/新建工作树；未重启8894、8895；未启动临时HTTP验证服务，因此没有遗留本会话服务需要停止。总集成、服务切换及现场验收仍由主会话负责。
