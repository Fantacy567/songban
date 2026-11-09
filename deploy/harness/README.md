# 松伴创作运行层

固定 DeepSeek Harness 源码提交 `ce7073d51254c26cd63b22a60835b8f948deb447`，版本 `0.2.2-alpha.2`。上游为 MIT；Docker 构建保留原始 LICENSE、第三方许可证和源码。松伴适配代码版权为 2292576833，项目共同所有权沿用仓库 COPYRIGHT.md。未复制上游 UI 并冒充已适配。

在独立 Linux Docker 构建机执行 `docker build -t songban-harness:ce7073d51254 -f deploy/harness/Dockerfile deploy/harness`。构建会下载固定源码及锁定依赖，运行时不下载依赖。源码 revision 在 Dockerfile 中固定，不能用 build-arg 改成别的源码仍保留原标签。镜像还须带 `org.songban.harness.contract=2026-11-03-files-v1`；旧 worker 镜像即使上游 revision 相同也不再视为就绪。

服务端显式构造 `HarnessRunner()` 并把管理员内部 `runtime_config('text')` 回调交给 `register_studio`。运行时 Docker 无网络、无主机卷、只读根目录、非 root、限制内存/CPU/PID；只将三个项目文件通过 stdin 传入临时工作目录。禁用 shell/工作目录切换工具，允许 Harness 文件读写。`file-guard.mjs` 使用固定版 `tools.guard()`，只准 `read/write/edit` 访问三个项目文件，拒绝目录、其他路径、符号链接、权限升级和过大输入；SDK server 显式依赖守卫就绪。`fs-local.cwd` 本身不是路径隔离，不能删除此守卫。模型请求通过 stdio 转给宿主固定 DeepSeek HTTPS 端点，宿主逐次预留额度并注入凭据；容器只有占位 token。每次小步骤最多四次模型请求，未知结果不得自动重试。

项目数据库保存不可变版本与儿童操作/AI 修改来源；预览在 opaque-origin sandbox iframe 执行浏览器代码，不在 API 主进程运行用户代码。服务器不声称已在浏览器检查、已掌握或已过关。

调用已预留但结果不明时为 unknown，不自动重发；孩子仍能手工编辑、预览、恢复和归档。服务端部署运维可在核对供应商与进程记录后使用 `StudioService.close_unknown(job_id, evidence=..., authority=..., con=None)` 留痕关闭未知状态；不会退还预留额度或声称调用成功。它只允许 unknown→failed，不接受浏览器自报的管理员身份。管理员路由负责真实身份校验，并可传当前事务 `con`，让核对、审计及授权复核原子提交；默认省略 `con` 时仍由函数自行开启事务。证据长度校验不代表证据已经被机器确认，管理员须实际核对进程、派发及供应商记录。确认从未预留任何模型请求的本地启动失败标为 failed，可正常继续。

2026-11-04 U04 现场自检仍无 Docker/Podman；`wsl --status` 退出50，明确报告 WSL 未安装；没有安装系统组件。2026-11-03 已从固定 TypeScript 源码打包实际 SDK 客户端，用上游 scripted runtime 验证13个协议场景，另完成纯补丁组合、所用字段类型及守卫回归。**尚未完成完整上游 pnpm 构建／全量类型检查、真实 CLI/agent 握手、镜像构建、容器文件工具回合或真实模型费用验收。** 源码 checkout 没有上游 node_modules，未在宿主启动 `dsh`。模型按钮仍应显示隔离环境未就绪。首轮 curriculum 为教研草稿。

U04 修复宿主适配器的容器清理退出码检查：即使 SDK 回合完成，`rm -f` 失败也不能返回成功；CLI 进程与管道仍收尾。relay 仅接受供应商 HTTP 200，不将重定向或错误正文转交容器。通过的是进程/HTTP 替身回归，实际容器清理失败场景仍需隔离部署机验收。

## 只读部署自检

在实际 API 运行身份下执行（不启动容器，不读取项目数据库/密钥，不安装系统组件）：

```text
python scripts/verify_harness_environment.py --source <已有固定源码绝对目录> --output <证据绝对目录>/environment
```

`--source` 可省略。脚本检查 Docker/Podman 常见路径、Linux engine、镜像 revision/contract、WSL、Node 和已有源码构建条件；不会执行 pnpm shim，避免诊断时隐式下载。退出2表示缺少前提；退出0只表示可以开始下一步真实容器验证，**不代表隔离或 agent 已通过**。报告不输出全量 Docker inspect 环境或供应商信息。

故障处理：找不到 engine 时提供 Linux 隔离构建机；engine 无法连接时由运维确认 daemon 和当前 API 账号权限；镜像缺失/标签不匹配时按下文重新构建，不更改标签掩盖旧 worker。WSL 命令存在不等于 Linux 子系统可用。不得因为探针失败转为宿主执行生成代码。

## 离线验证与证据

在仓库根目录、已有 Node/esbuild/TypeScript 与 Python/PyYAML 环境执行；不会安装依赖或调用供应商：

```text
node scripts/verify_harness_sdk.mjs <固定源码绝对目录> <证据目录>/sdk
node scripts/verify_harness_contracts.mjs <固定源码绝对目录> <证据目录>/contracts <Python可执行文件>
python -m unittest tests.test_harness_safety tests.test_harness_environment tests.test_creative_studio tests.test_creative_integration -v
```

第一项使用真实 SDK client 和上游脚本替身 server；不执行 agent、生成代码或 shell。第二项只提取执行上游纯补丁函数，YAML 的 `!!js` 保持惰性数据；类型检查仅含集成实际使用的字段，不是全仓 `pnpm typecheck`。报告保留源码路径、哈希与范围声明，生成的上游派生文件旁保留 MIT LICENSE。

历史协议证据：`E:/松伴/outputs/harness-t03-20261103/`；U04 自检和针对性回归：`E:/松伴/outputs/u04-harness-admin-20261104/`。准确命令与结论分别见 T03 历史交接及 `docs/planning/learning-roadmap/unified-workbench/handoffs/U04.md`。U04 没有把历史协议通过次数累计成新的容器验收。

## 外部部署与验收顺序

1. 准备受控 Linux Docker Engine 构建机、所需镜像仓库/GitHub/npm 构建网络，以及足够的内存和磁盘。镜像内采用 Node 24.11.0、pnpm 11.28.5，`pnpm install --frozen-lockfile && pnpm run build` 会覆盖上游构建/检查流程；构建失败必须处理，不能换成主机执行 Harness。不得向构建传供应商凭据或孩子数据。
2. 在仓库根目录执行上述 `docker build`，保存完整构建日志。用 `docker image inspect songban-harness:ce7073d51254` 核对上游 revision 和当前 worker contract 标签。发布固定镜像时记录 image ID／仓库 digest，避免标签漂移。
3. 在能访问同一 Docker Engine 的 API 环境、现有 Python 依赖中执行下面的零计费工具回合。这是为部署机准备的脚本，本机只执行了不可用分支；真实成功分支还未验收。

```text
python scripts/verify_harness_container.py --output <证据绝对目录>/container
```

使用已配置好的 Podman 时可显式传 `--engine podman`，构建使用相同 Dockerfile 和镜像标签；API 部署构造 `HarnessRunner(docker=<Podman绝对路径>)`。这是兼容入口，本机未运行 Podman 成功分支，隔离参数和清理必须同样验证。

它只通过 `httpx.MockTransport` 提供三个虚构响应：让真实 Harness 拒绝写 `/tmp/songban.patch.yml`，再真实写 `script.js`，最后结束；同时核对广告工具集合、容器实际隔离参数、文件回收和删除容器。不会访问真实 DeepSeek；API key 为脚本内明确虚构占位。无 Docker／正确镜像时报告 `passed:false` 并退出 2，不退化执行宿主代码。完整成功才退出 0。

4. 在隔离环境做超时、异常退出及大结果回收验证；保持累计额度、并发和未知任务不可自动重发的行为。确认实际运行进程的 Docker 权限仅供服务端受控命令使用；容器不挂 Docker socket、数据库或密钥目录。
5. 经主会话备份并切换服务后，用管理员后台配置服务端密钥、启用状态和明确预算。2026-11-04 的10次 DeepSeek、每次最多800输出 tokens 授权由主会话独占；U04 和上述验证脚本不发送真实请求。豆包暂未配置，真实出图待配置验收；保存配置或零计费 smoke 不算真实模型成功。实际教学复核、孩子试点与公开发布也未包含。

新工作台复用 `lambda *, con=None: admin.runtime_config('text', con=con)` 时，保留运行域自己的持久预留及配置版本复核。该回调只读配置，不会汇总旧 `creative_calls` 和新工作台账本，主会话须统一跨域累计预算，详见 U04 交接；不能把同一个 `max_calls` 分别当成两份额度。
