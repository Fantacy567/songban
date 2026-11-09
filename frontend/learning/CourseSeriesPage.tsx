// Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, errorText, requestId, type LearningApi } from './api';
import type { Config, CourseActivity, CourseExperiment, CourseId, CourseProgress, CourseSave, Route, SeriesCourse, Session } from './types';
import { Notice, useGuard, type LeaveGuard, type SetGuard } from './ui';
import { CourseWorkbench } from './workbench/CourseWorkbench';
import './course-series.css';

const blank = () => ({ answers: { understand: '', try: '', reflect: '' }, activity: {} as CourseActivity, project_id: null as string | null });
type Draft = ReturnType<typeof blank>;
const draftOf = (p: CourseProgress): Draft => ({ answers: { ...p.answers }, activity: { ...p.activity }, project_id: p.project_id });
// Key order from JSON responses is not part of the progress contract.
const fingerprint = (d: Draft) => JSON.stringify([d.answers.understand,d.answers.try,d.answers.reflect,Object.keys(d.activity).sort().map(k=>[k,d.activity[k]]),d.project_id]);
function Field({ label, value, onChange, max = 500, placeholder }: { label: string; value: string; onChange: (v:string)=>void; max?: number; placeholder?: string }) {
  return <label className="cs-field">{label}<textarea aria-label={label} rows={3} value={value} maxLength={max} placeholder={placeholder} onChange={e=>onChange(e.target.value)} /><span className="cs-caption">{value.length} / {max}</span></label>;
}
const toolNames: Record<string,string> = { describe:'描述目标', generate:'请 AI 生成', run:'运行', check:'检查', improve:'亲自修改再试' };

function CourseActivityView({ id, activity, update, api, navigate, creativeEnabled }: {
  id:CourseId; activity:CourseActivity; update:(a:CourseActivity)=>void; api:LearningApi; navigate:(r:Route)=>Promise<boolean>; creativeEnabled:boolean;
}) {
  const [validation,setValidation]=useState('');
  const [experiment,setExperiment]=useState<CourseExperiment|null>(null), [experimentError,setExperimentError]=useState('');
  const [busy,setBusy]=useState(false), [sent,setSent]=useState<{request_id:string;operation:'greet';name:string}|null>(null);
  const pending=useRef<typeof sent>(null), alive=useRef(true), lock=useRef(false);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const value=(key:string)=>typeof activity[key]==='string'?activity[key] as string:'';
  const defaults: Record<CourseId,CourseActivity> = {
    'ai-tools': {sequence:[]}, imagination:{audience:'',problem:'',feature:'',check:''},
    'first-project':{change:'',observation:''},plugins:{enabled:false,before:'',after:''},models:{choice:'undecided',reason:''},
    api:{name:'',message:''},'model-powered-app':{input:'',role:'',output:'',fallback:''},
  };
  const put=(key:string,v:string|boolean|string[])=>{setValidation('');update({...defaults[id],...activity,[key]:v});};
  const field=(key:string,label:string,max=500,placeholder?:string)=><Field key={key} label={label} value={value(key)} max={max} placeholder={placeholder} onChange={v=>put(key,v)}/>;
  async function callExperiment() {
    if(lock.current)return;
    lock.current=true;setBusy(true);setExperimentError('');setExperiment(null);
    const body=pending.current || {request_id:requestId(),operation:'greet' as const,name:value('name')};
    pending.current=body;setSent(body);
    try {
      const result=await api.platform<CourseExperiment>('/learning-courses/api/experiment','POST',body);
      if(!alive.current)return;
      pending.current=null;setExperiment(result);put('message',result.response.message.slice(0,200));
    } catch(e) {
      if(!alive.current)return;
      if(!(e instanceof ApiError && e.unknown))pending.current=null;
      setExperimentError(e instanceof ApiError ? `HTTP ${e.status || '未确认'} · ${e.code}。${e.status===422?'名字去掉空白后需要 1–40 个字符。':errorText(e)}` : errorText(e));
    } finally {lock.current=false;if(alive.current)setBusy(false);}
  }
  if(id==='ai-tools') {
    const sequence=Array.isArray(activity.sequence)?activity.sequence:[];
    return <div role="group" aria-label="工具步骤排序"><p>点选加入步骤，再用上移、下移调整。运行之后检查，发现问题再修改并重新运行。</p><div className="lp-actions">{Object.entries(toolNames).map(([key,label])=><button type="button" key={key} disabled={sequence.includes(key)} onClick={()=>put('sequence',[...sequence,key])}>加入{label}</button>)}</div><ol>{sequence.map((key,i)=><li key={key} className="cs-sort-row"><strong>{toolNames[key]}</strong><div className="lp-actions"><button type="button" aria-label={`上移${toolNames[key]}`} disabled={i===0} onClick={()=>{const s=[...sequence];[s[i-1],s[i]]=[s[i],s[i-1]];put('sequence',s);}}>上移</button><button type="button" aria-label={`下移${toolNames[key]}`} disabled={i===sequence.length-1} onClick={()=>{const s=[...sequence];[s[i+1],s[i]]=[s[i],s[i+1]];put('sequence',s);}}>下移</button><button type="button" aria-label={`移除${toolNames[key]}`} onClick={()=>put('sequence',sequence.filter(x=>x!==key))}>移除</button></div></li>)}</ol><button type="button" onClick={()=>setValidation(sequence.join(',')==='describe,generate,run,check,improve'?'这是一种可用的起步顺序。修改以后，还要再次运行与检查。':'检查一下：有没有描述目标、生成、运行、检查和修改？这些步骤可以反复进行。')}>检查我的顺序</button><p role="status">{validation}</p></div>;
  }
  if(id==='imagination')return <div role="group" aria-label="想法构建">{field('audience','为谁做',500,'例如：参加读书会的同学')}{field('problem','想解决什么困难',500,'例如：记不清带哪本书')}{field('feature','先做一个功能',500,'例如：一张可以勾选的带书清单')}{field('check','怎样检查有用',500,'例如：让同学找出明天要带的书')}</div>;
  if(id==='first-project')return <div role="group" aria-label="小项目记录"><p>去创作工作台尝试做一个带按钮的小网页。运行后改一处，再检查效果。实际生成需要工作台已配置的运行环境；打开工作台不代表已经生成作品。</p><button type="button" disabled={!creativeEnabled} onClick={()=>void navigate('#/learn/create')}>进入创作工作台</button>{!creativeEnabled&&<p>创作工作台暂未开放，你仍可先记录自己的设计。</p>}{field('change','我亲自改的一处',1000)}{field('observation','运行后观察到了什么',1000)}<p className="cs-caption">先保存本课记录，再去创作；返回这门课可继续读取。课程记录不自动绑定或创建作品。</p></div>;
  if(id==='plugins')return <div role="group" aria-label="课程内插件实验"><p>这是课程内可开关的高亮功能，没有安装外部插件。切换开关，看同一块画布发生了什么变化。</p><label className="cs-toggle"><input type="checkbox" checked={activity.enabled===true} onChange={e=>put('enabled',e.target.checked)}/>启用重点高亮扩展</label><div className={`cs-plugin-canvas${activity.enabled===true?' cs-highlight':''}`} aria-label="插件预览画布"><h3>读书会小卡片</h3><p>周五放学后一起分享故事。</p><strong>记得带一本喜欢的书。</strong></div>{field('before','关闭时的观察',1000)}{field('after','开启后的变化',1000)}</div>;
  if(id==='models')return <div role="group" aria-label="固定模型样例对比"><p>以下是两份固定教学样例，非实时模型调用，也不代表任何真实供应商排名。</p><p><strong>共同任务：</strong>写一条提醒：周五 15:00，图书角，带一本书。不要添加未提供的信息。</p><div className="cs-samples"><article><h3>样例 A</h3><p>周五 15:00 在图书角见！带上一本书，我们一起分享。</p></article><article><h3>样例 B</h3><p>周六 15:00 来操场，带上三本书，现场还有免费奖品！</p></article></div><label className="cs-field">选择更符合任务的样例<select aria-label="选择更符合任务的样例" value={value('choice')||'undecided'} onChange={e=>put('choice',e.target.value)}><option value="undecided">还没决定</option><option value="sample-a">样例 A</option><option value="sample-b">样例 B</option></select></label>{field('reason','我的依据与需要核对的地方',1000)}</div>;
  if(id==='api')return <div role="group" aria-label="API 请求实验"><p>按钮会实际 POST 到本站教学接口。返回由固定规则产生，没有调用大模型；不需要 API 密钥。可以清空名字观察服务器的校验错误。</p><label className="cs-field">请求中的名字<input maxLength={40} value={value('name')} onChange={e=>put('name',e.target.value)} disabled={busy||!!pending.current}/></label><button type="button" disabled={busy} onClick={()=>void callExperiment()}>{busy?'正在发送请求…':pending.current?'用原请求编号核对结果':'发送教学 API 请求'}</button>{sent&&<div><h3>实际发送的 request</h3><pre aria-label="API request">{JSON.stringify(sent,null,2)}</pre></div>}{experiment&&<><h3>服务器 response</h3><pre aria-label="API response">{JSON.stringify(experiment.response,null,2)}</pre><p role="status">{experiment.notice}</p></>}{experimentError&&<Notice error>{experimentError}</Notice>}{field('message','我记录的响应消息',200)}<p className="cs-caption">只在点击发送时访问接口；修改记录不会重新请求。</p></div>;
  return <div role="group" aria-label="模型增强方案">{field('input','应用接收什么输入',500,'例如：活动的时间、地点、要带的物品')}{field('role','模型负责哪一小步',500,'例如：整理成一句提醒，不添加事实')}{field('output','应用期待什么输出',500,'例如：一条待我检查的提醒')}{field('fallback','失败时怎样回退',500,'例如：显示原始信息，让我手动填写')}<p>下面用固定规则检查方案是否齐全，并模拟正常与失败两条路径。没有接通在线模型，不会验证内容的真实性。</p><button type="button" onClick={()=>setValidation(['input','role','output','fallback'].every(k=>value(k).trim())?`固定规则模拟：收到「${value('input')}」→ 按职责「${value('role')}」交给待检查输出区「${value('output')}」。模拟失败 → ${value('fallback')}`:'请把输入、模型职责、输出和失败回退都写清楚后再试。')}>用固定规则验证方案</button><p role="status">{validation}</p></div>;
}

export function LegacyCoursePractice({api,id,session,config,setGuard,navigate,entry,creativeEnabled=false}: {
  api:LearningApi;id:CourseId;session:Session|null;config:Config|null;setGuard:SetGuard;navigate:(r:Route)=>Promise<boolean>;entry?:ReactNode;creativeEnabled?:boolean;
}) {
  const [course,setCourse]=useState<SeriesCourse|null>(null), [catalogError,setCatalogError]=useState(''), [reload,setReload]=useState(0);
  const [record,setRecord]=useState<CourseProgress|null>(null), [draft,setDraft]=useState<Draft>(blank), [busy,setBusy]=useState(false), [error,setError]=useState('');
  const [pending,setPending]=useState<CourseSave|null>(null), [remote,setRemote]=useState<CourseProgress|null>(null), [checked,setChecked]=useState(false);
  const [coverFailed,setCoverFailed]=useState(false);
  const alive=useRef(true), lock=useRef(false);
  const learner=session?.mode==='learner'?session.learner_id:null;
  const path=`/learning-courses/${id}/progress`;
  const dirty=!!record&&fingerprint(draft)!==fingerprint(draftOf(record));
  const editable=!!learner&&!!record&&!!config?.learning_enabled&&!busy&&!pending&&!remote;
  function validate(p:CourseProgress) {if(p.course_id!==id||p.learner_id!==learner)throw new Error('课程记录身份不匹配');return p;}
  function adopt(p:CourseProgress){setRecord(p);setDraft(draftOf(p));setPending(null);setRemote(null);setChecked(false);setError('');}
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  useEffect(()=>{
    let live=true;setCourse(null);setCatalogError('');setCoverFailed(false);
    void api.publicCatalog<SeriesCourse>(id).then(c=>{if(c.id!==id)throw new Error('课程不匹配');if(live)setCourse(c);}).catch(e=>{if(live)setCatalogError(errorText(e));});
    return()=>{live=false;};
  },[api,id,reload]);
  useEffect(()=>{
    let live=true;setRecord(null);setDraft(blank());setPending(null);setRemote(null);setError('');
    if(learner)void api.platform<CourseProgress>(path).then(validate).then(p=>{if(live)adopt(p);}).catch(e=>{if(live)setError(errorText(e));});
    return()=>{live=false;};
  },[api,id,learner,session?.id,session?.mode_epoch,reload]);
  async function save():Promise<boolean> {
    if(lock.current||!record||!learner||!config?.learning_enabled||remote||(pending&&!checked))return false;
    lock.current=true;setBusy(true);setError('');
    const body=pending||{request_id:requestId(),expected_revision:record.revision,...draft};
    try {const p=validate(await api.platform<CourseProgress>(path,'POST',body));if(!alive.current)return false;adopt(p);return true;}
    catch(e){if(alive.current){setError(errorText(e));if(e instanceof ApiError&&(e.unknown||e.status===409)){setPending(body);setChecked(false);}}return false;}
    finally{lock.current=false;if(alive.current)setBusy(false);}
  }
  async function reconcile(){
    if(lock.current||!record)return;lock.current=true;setBusy(true);setError('');
    try {
      const p=validate(await api.platform<CourseProgress>(path));if(!alive.current)return;
      if(fingerprint(draftOf(p))===fingerprint(draft)){adopt(p);}
      else if(p.revision===record.revision){setChecked(true);setError('已核对：服务器尚未保存这次修改。可使用原请求编号重试。');}
      else {setRemote(p);setChecked(false);setError('服务器已有不同版本。请核对后选择保留哪份内容。');}
    }catch(e){if(alive.current)setError(errorText(e));}finally{lock.current=false;if(alive.current)setBusy(false);}
  }
  useGuard(setGuard,dirty||busy||!!pending,editable&&!pending?save:undefined);
  return <section className="cs-page" aria-label="独立课程" aria-busy={busy}>
    <button onClick={()=>void navigate('#/learn/courses')}>返回 AI 教学大厅</button>
    {catalogError&&<><Notice error>{catalogError}</Notice><button onClick={()=>setReload(n=>n+1)}>重新读取课程</button></>}
    {!course&&!catalogError&&<Notice>正在读取这门课…</Notice>}
    {course&&<>
      <header className="cs-hero"><div><p className="lp-eyebrow">{course.chapter.title} · 独立试学课程</p><h1>{course.title}</h1><p>{course.intro}</p><p><strong>学完能做：</strong>{course.goal}</p><p>{course.duration}</p><p className="cs-caption">试学课程。保存记录和完成练习不等于已经掌握。</p></div><figure>{coverFailed?<div role="img" aria-label={`${course.title}：教学插画暂未加载`}>教学插画暂未加载，可继续阅读与练习。</div>:<img src={`/static/platform/illustrations/course-${id}.svg`} alt={course.cover.alt} width="900" height="600" onError={()=>setCoverFailed(true)}/>}<figcaption>松伴原创教学插画 · 非孩子成果或真实项目截图</figcaption></figure></header>
      <p className="cs-preparation"><strong>开始前：</strong>{course.preparation}</p>
      {!learner&&<><Notice>课程内容可以直接阅读。准备记录与保存时，请先进入学习者身份。</Notice>{session?.mode==='staff'?<p>当前为工作人员身份，仅可阅读公开课程；不会自动切换或授予学习权限。</p>:entry}</>}
      {learner&&!record&&!error&&<Notice>正在读取这门课的已保存记录…</Notice>}
      {error&&<Notice error>{error}</Notice>}
      {learner&&!record&&error&&<button onClick={()=>setReload(n=>n+1)}>重新读取课程记录</button>}
      {!config?.learning_enabled&&<Notice>学习记录暂时不可修改，已读到的记录仍可查看。</Notice>}
      <ol className="cs-steps">{course.steps.map((step,i)=><li key={step.id} className="lp-card"><h2>{i+1}. {step.title}</h2><p>{step.instruction}</p><blockquote><strong>起步示例：</strong>{step.example}</blockquote><p>{step.prompt}</p><fieldset disabled={!editable}><Field label={`${step.title}：我的记录`} value={draft.answers[step.id]} max={2000} onChange={v=>setDraft(d=>({...d,answers:{...d.answers,[step.id]:v}}))}/></fieldset>{step.id==='try'&&<section className="cs-activity"><h3>{course.activity.title}</h3><p>{course.activity.instruction}</p><fieldset disabled={!editable}><CourseActivityView key={`${id}:${learner}`} id={id} api={api} activity={draft.activity} update={activity=>setDraft(d=>({...d,activity}))} navigate={navigate} creativeEnabled={creativeEnabled}/></fieldset></section>}</li>)}</ol>
      {remote&&<section className="lp-card" aria-label="服务器记录核对"><h2>服务器已保存的版本 {remote.revision}</h2><pre>{JSON.stringify({answers:remote.answers,activity:remote.activity},null,2)}</pre><button disabled={busy} onClick={()=>adopt(remote)}>使用服务器记录，放弃本次修改</button><button disabled={busy} onClick={()=>{setRecord(remote);setRemote(null);setPending(null);setChecked(false);setError('已保留你的输入，请检查后再次保存。');}}>保留我的输入，稍后保存覆盖</button></section>}
      {learner&&<footer className="cs-save"><p role="status">{dirty?'有未保存的修改':record?.status==='saved'?`已保存本课记录 · 版本 ${record.revision}`:'本课还没有保存记录'}{record?.updated_at&&` · ${record.updated_at}`}</p><div className="lp-actions"><button className="lp-primary" disabled={busy||!record||!config?.learning_enabled||!!remote||(!!pending&&!checked)||(!dirty&&!pending)} onClick={()=>void save()}>{busy?'正在核对…':pending?'使用原请求编号重试保存':'保存本课记录'}</button>{pending&&<button disabled={busy} onClick={()=>void reconcile()}>核对服务器保存结果</button>}</div></footer>}
      <details className="cs-sources"><summary>本课资料与试学说明</summary><ul>{course.sources.map(s=><li key={s.url}>{/^https:\/\//.test(s.url)?<a href={s.url} target="_blank" rel="noreferrer">{s.title}</a>:s.title}<p>{s.supports}</p></li>)}</ul><p>{course.review.technical==='draft'?'技术核对中':'技术核对状态待确认'} · {course.review.education==='pending'?'待教研审阅':'教研审阅状态待确认'} · {course.review.pilot==='pending'?'待试学观察':'试学观察状态待确认'}。</p></details>
    </>}
  </section>;
}

/** Both panels contribute to one leave guard; collapsing tools does not discard edits. */
export function CourseSeriesPage(props: Parameters<typeof LegacyCoursePractice>[0]) {
  const guards = useRef<{ chat: LeaveGuard; tools: LeaveGuard }>({ chat: { dirty: false }, tools: { dirty: false } });
  const publish = useCallback((key: 'chat' | 'tools', guard: LeaveGuard) => {
    guards.current[key] = guard;
    const { chat, tools } = guards.current;
    props.setGuard({ dirty: chat.dirty || tools.dirty, save: chat.dirty ? undefined : tools.save });
  }, [props.setGuard]);
  const chatGuard = useCallback<SetGuard>(g => publish('chat', g), [publish]);
  const toolsGuard = useCallback<SetGuard>(g => publish('tools', g), [publish]);
  return <CourseWorkbench {...props} setGuard={chatGuard} tools={<LegacyCoursePractice {...props} setGuard={toolsGuard} entry={undefined}/>} />;
}
