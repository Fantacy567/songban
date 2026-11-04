# H1 大厅组件交接

日期：2026-11-02。约束：[项目宪法2.0.0](../../../docs/planning/learning-roadmap/01-项目宪法.md)、[UI层级与页面规范](../../../docs/planning/learning-roadmap/platform/01-UI层级与页面规范.md)。

本目录实现两个大厅和“认识黑客松”内容页。页面只接受已核对的展示投影、发出动作意图，不读取 API、浏览器凭据、团队缓存或当前 hash，不创建课次、队伍或比赛状态。尚须中央会话完成导航、鉴权投影、构建产物与实际服务接入；本目录测试通过不代表统一演示站已经验收。

## 导出与接入

`Halls.tsx` 导出 `HallView`、`LearningHall`、`HackathonHall`、`HackathonIntro`；`types.ts` 导出 `HallAction`、`HallViewState` 等展示契约。React 页面可直接导入，沿用中央的身份与离页保护：

```tsx
import { HallView } from '../platform/halls/Halls';
import type { HallViewState, HallAction } from '../platform/halls/types';

// state 必须由当前身份、服务端课程与本人进度投影得出。
function CurrentHall({ state, contextKey }: { state: HallViewState; contextKey: string }) {
  async function onAction(action: HallAction) {
    if (!(await confirmLeavingUnsavedWork())) return false;
    return handleExistingAuthorizedRoute(action);
  }
  return <HallView key={contextKey + ':' + state.page} state={state} onAction={onAction} />;
}
```

示例里的路由函数由中央提供，不是新增 API。异步回调执行期间按钮防重复；回调返回 `false` 表示取消离开，不显示错误。抛错会显示可重试说明。成功与否、资源归属、课程授权和任何写操作仍由中央及后端校验。

原生壳可使用 `index.tsx` 的 `mountHalls`，也可在独立 IIFE 构建后通过 `window.SongbanHalls.mount` 使用：

```js
const hall = window.SongbanHalls.mount(document.getElementById('platform-hall'), {
  contextKey: 'current-authorized-identity-and-scope',
  state: {
    page: 'hackathon',
    status: 'ready',
    practice: {
      teamId: currentAuthorizedTeam.id,
      title: currentAuthorizedTeam.name,
      stageLabel: currentAuthorizedPractice.stageLabel
    },
    practiceEnabled: currentCapabilities.canResumePractice
  },
  onAction: centralHallAction
});

// 异步读取完成后替换整个投影。身份/家庭/队伍变更时也更新 contextKey。
hall.update({ contextKey: nextScopeKey, state: nextAuthorizedProjection, onAction: centralHallAction });

// 离开本挂载点时调用；重复调用安全。更新已卸载句柄不会再次挂载。
hall.unmount();
```

同一宿主重复 `mountHalls` 会先卸载旧根。宿主不可同时由 learning React 根和此桥接根控制。中央先清除旧根、丢弃旧身份迟到响应，再挂载新投影；不能只靠改变 `contextKey` 实现业务鉴权。组件本身不增加聊天窗，继续由中央控制同一个松伴入口。

## 精确投影示例

AI 大厅当前只应收到实际已发布的邀请卡课程；组件没有唯一课程 ID 限制，将来课程须先具备材料与发布依据，再进入投影。以下是从服务端已授权对象生成的示例，不是可执行的固定目录：

```ts
import type { LearningHallState } from './types';

const state: LearningHallState = {
  page: 'ai',
  status: 'ready',
  courses: authorizedPublishedCourses.map(course => ({
    id: course.id,
    state: course.state,
    title: course.title,
    goal: course.presentation.goal,
    stage: {
      id: course.presentation.stage.id,
      title: course.presentation.stage.title,
      description: course.presentation.stage.description,
      order: course.presentation.stage.order
    },
    experience: course.presentation.experience,
    preparation: course.presentation.preparation,
    steps: course.presentation.steps,
    cover: course.presentation.cover,
    statusLabel: course.canStart ? '可以开始' : '先完成准备',
    action: course.canStart
      ? { label: '开始我的作品', action: { type: 'start-course', courseId: course.id } }
      : undefined,
    unavailableReason: course.canStart ? undefined : course.preparationNotice
  })),
  resume: authorizedCurrentRun ? {
    title: authorizedCurrentRun.workTitle,
    description: authorizedCurrentRun.nextStep,
    action: {
      label: '继续我的作品',
      action: { type: 'continue-learning', runId: authorizedCurrentRun.id }
    }
  } : null
};
```

`presentation`、`canStart`、`preparationNotice` 是中央适配层命名示例，不宣称现有 API 已返回这些字段。阶段文案可由已核对的课程内容配置映射，出版状态、本人课次、准备条件和动作授权须以现有服务端事实为准。不能把无权限页面的数据映射成“可以开始”，也不能用前端状态证明过关。

可用状态：

- AI 大厅：`page:'ai'`，`status:'loading'|'ready'|'error'`，`courses` 必填；`resume` 可独立保留本人有权继续的作品。加载或失败时不显示可开始的旧目录。空目录说明课程仍在准备，不创建假课程。
- 黑客松大厅：`page:'hackathon'`，同样三种状态；`practice` 仅放当前有权限的原实践，`practiceEnabled:false` 禁用开始或继续。加载/失败时仍可读认识内容，实践动作关闭并提供重试。
- 认识页：`page:'hackathon-intro'`，`practice` 与 `practiceEnabled` 可选；不发阅读完成写入、不设强制测验或锁关。
- 封面：`HallCover` 是 `{src,alt,label?}`；替代文字必须说明画面，示例图片须标示示例。当前仅接受 `/static/platform/illustrations/`、`/static/learning/covers/` 的本地路径。外部路径或路径穿越会回退到本地插图；合法本地图片失败则显示文字回退，仍可操作。接入 H4 私有图片资源时，由中央核对授权 URL 后扩充白名单，不能传外部用户 URL 来绕过归属校验。

`HallAction` 逐项由中央接线：

- `start-course(courseId)`：使用现有授权开始/恢复课次路径。
- `continue-learning(runId)`：恢复本人原课次，不重新报名。
- `view-work(artifactId)`：进入已授权的原作品详情。
- `prepare-learning`：保留学习去向，进入现有必要准备流程。
- `hackathon-intro` / `hackathon-hall`：认识页与黑客松大厅内切换。
- `begin-practice`：进入原赛事选择或必要起点准备，不另建比赛状态机。
- `resume-practice(teamId)`：恢复原队伍当前阶段，不固定跳向新建组队或重新选题。
- `retry(page)`：中央重新读取对应投影；不等同自动重跑模型。

## 构建建议

中央负责正式构建脚本和静态路由。React 主入口已导入组件时，CSS 会随现有 esbuild 产物生成。原生壳独立构建可采用：

```js
await esbuild.build({
  entryPoints: ['frontend/platform/halls/index.tsx'],
  bundle: true,
  jsx: 'automatic',
  format: 'iife',
  outfile: 'static/platform/halls.js',
  minify: true,
  define: { 'process.env.NODE_ENV': '"production"' }
});
```

此例产出 `halls.js` 和 `halls.css`；页面须同时加载 CSS。使用已有同源 `/static/` 资源规则，保留三个 SVG 的绝对资源路径。模块没有新增服务器、iframe、包依赖或供应商配置；所有 CSS 都限制在 `[data-platform-halls]` 作用域下。

## 素材与验证

`static/platform/illustrations/` 内三个 SVG 为本轮直接编写的原创代码素材，版权遵循仓库 `COPYRIGHT.md` 中三方共同所有的声明；无外部字体、远程图片、脚本或真人资料。

- `hackathon-intro.svg`：虚构小队讨论草图。
- `hackathon-practice.svg`：虚构小队制作、解释小原型。
- `course-work.svg`：邀请卡课程示例封面，不是孩子已完成作品。

验证命令：

```text
node node_modules/typescript/bin/tsc --project frontend/platform/halls/tests/tsconfig.json
node frontend/platform/halls/tests/halls.cjs
```

浏览器用拦截的同源虚构投影，14 项场景覆盖两卡顺序与恢复动作、失败/加载/空态、仅发布课程与通用版本 ID、准备条件、错误重试/取消/防重复、图片回退和外部 URL 拒绝、文本转义、样式隔离、键盘、390/768/1440 和 200% 缩放、减少动效、卸载及身份范围更新。证据默认在 `E:/松伴/outputs/platform-halls-h1/`，可通过 `SONGBAN_HALLS_EVIDENCE` 指定目录。

本轮没有调用真实模型、使用真实账号、写入数据库或发布真实课程；没有将认识故事转换成学习证据。实际统一站、旧比赛流程、身份投影及松伴跨页上下文须由中央集成验收。
