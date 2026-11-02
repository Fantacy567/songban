// Copyright (c) 2026 2292576833 — AI 工作台模块。
// 项目共同所有权及其他贡献者权利见仓库 COPYRIGHT.md。
import type { CardText } from './contracts';
import type { Route } from './types';
import { candidate, Preview, type Snapshot } from './workspace';

export interface StudioDraft { content: CardText; label: string }
/** A view of candidates and saved versions; rendering never records a readback. */
export function StudioPreview({ snapshot: s, draft, navigate }: {
  snapshot: Snapshot; draft: StudioDraft | null; navigate: (route: Route) => Promise<boolean>;
}) {
  const artifact = s.artifact;
  const generated = !artifact && s.model?.status === 'succeeded' && s.model.visibility === 'normal' ? candidate(s.model.output_text) : null;
  const label = draft?.label || (artifact ? `我的已保存版本 v${artifact.current_version.version}` : `${s.model?.mode === 'live' ? '真实 AI' : s.model?.mode === 'replay' ? '历史回放' : '模拟工具'}候选 · 尚未保存`);
  const content = draft?.content || artifact?.current_version.content || generated;
  return <section className="lp-studio-preview" aria-labelledby="lp-studio-preview-title">
    <div className="lp-studio-panel-title"><div><span className="lp-eyebrow">每一步，都看得见</span><h2 id="lp-studio-preview-title">看我的作品</h2></div><span className={`lp-studio-save ${draft ? 'is-draft' : ''}`}>{draft ? '修改尚未保存' : artifact ? `已保存 v${artifact.current_version.version}` : generated ? '等待你决定保存' : '还没开始制作'}</span></div>
    {content ? <Preview content={content} label={label} /> : <div className="lp-studio-blank" aria-label="作品预览占位，还没有生成作品">
      <img src="/static/design/pine-mascot.png" alt="" width="92" height="92" />
      <p className="lp-eyebrow">我的第一张邀请卡</p><h3>你的想法，会在这里长出来</h3><p>先和松伴说清楚想邀请谁。<br />做出一版后，就能在这里看到它。</p>
      <div className="lp-studio-skeleton" aria-hidden="true"><span /><span /><span /></div>
      <p className="lp-caption">这里只是空白预览，不是已完成作品。</p>
    </div>}
    <p className="lp-caption">{draft ? '现在看到的是你的修改草稿。点击“保存改进为新版本”后才会留下正式记录。' : artifact ? '预览不代替打开确认或自查。回到当前步骤，记录你自己的判断。' : generated ? '这是工具给出的候选。先核对内容，再决定是否保存。' : '想一想、做出来、再改一改。生成和保存都由你来决定。'}</p>
    {artifact && <div className="lp-actions"><button onClick={() => void navigate(`#/learn/works?id=${encodeURIComponent(artifact.id)}`)}>查看作品与历史版本</button></div>}
  </section>;
}
