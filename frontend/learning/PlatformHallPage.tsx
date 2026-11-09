import { useEffect, useRef, useState } from 'react';
import { HallView } from '../platform/halls/Halls';
import type { HallAction, HallCourse, HallViewState } from '../platform/halls/types';
import type { LearningApi } from './api';
import { courseIds, type Config, type Route, type Session, type LearningCatalog, type CourseId } from './types';
import type { Course, Home, Run } from './contracts';
import { coursePresentation } from './course-covers';
import { readPages, lessonError } from './workspace';
import { courseRoute, runRoute } from './routes';
import { useGuard, type SetGuard } from './ui';

export function PlatformHallPage({api,session,config,page,navigate,canLeave,setGuard,creativeEnabled=false}: {
  api:LearningApi; session:Session|null; config:Config|null; page:'ai'|'hackathon'|'hackathon-intro';
  navigate:(route:Route)=>Promise<boolean>; canLeave:()=>Promise<boolean>; setGuard:SetGuard; creativeEnabled?:boolean;
}) {
  const [state,setState]=useState<HallViewState>({page:'ai',status:'loading',courses:[]});
  const [retry,setRetry]=useState(0); const epoch=useRef(0);
  useGuard(setGuard,false);
  useEffect(()=>{
    const current=++epoch.current;
    if(page!=='ai') {
      const preparationNotice=session?.mode==='learner'?'先了解比赛。开始团队实践前，请家长帮忙准备比赛账号。':undefined;
      setState(page==='hackathon'?{page:'hackathon',status:'ready',practiceEnabled:true,preparationNotice}
        :{page:'hackathon-intro',practiceEnabled:true,preparationNotice});
      return;
    }
    setState({page:'ai',status:'loading',courses:[]});
    (async()=>{
      try {
        // Catalogue is public; private resume data is fetched only for this learner.
        const [catalogResult, legacyResult] = await Promise.allSettled([
          api.publicCatalog<LearningCatalog>(),
          session?.mode === 'learner' ? readPages<Course>(api,'/courses') : Promise.resolve([] as Course[]),
        ]);
        const courses = legacyResult.status === 'fulfilled' ? legacyResult.value : [];
        let home:Home|null=null,run:Run|null=null,notice='';
        if(session?.mode==='learner'&&session.learner_id){
          try {
            home=await api.request<Home>(`/learners/${encodeURIComponent(session.learner_id)}/home`);
            if(home.learner_id!==session.learner_id)throw new Error('身份不匹配');
            if(home.run_id)run=await api.request<Run>(`/runs/${encodeURIComponent(home.run_id)}`);
            if(run&&run.learner_id!==session.learner_id)throw new Error('身份不匹配');
          } catch(e){home=null;run=null;notice='本人的进度暂时没读完整，已保存的作品仍可从原入口查看。';}
        }
        const cards:HallCourse[]=courses.filter(c=>c.state==='published').map(c=>{
          const p=coursePresentation(c.id), own=run?.course_version_id===c.id?run:null;
          const complete=!!own?.progress.length&&own.progress.every(p=>p.state==='passed');
          const allowed=!home?.run_id&&config?.learning_enabled&&home?.entitlements.some(e=>e.course_version_id===c.id&&e.status==='active')&&home.allowed_actions.includes('createRun');
          return {id:c.id,state:c.state,title:c.title,goal:p?.goal||'跟着课程任务，动手留下自己的作品。',
            stage:{id:'first-work',title:'以前的练习',order:3,description:'旧课程和已经保存的作品仍可从这里继续。'},
            preparation:p?.preparation,experience:p?.experience,steps:p?.steps,
            cover:p?{src:p.image,alt:p.alt,label:'课程作品示例 · 虚构活动'}:undefined,
            statusLabel:own?complete?'已经完成':own.progress.some(p=>p.state==='pending_review')?'等待老师反馈':'正在创作':allowed?'可以开始':'需要学习准备',
            action:own?{label:complete?'看看我的作品':'继续创作',action:complete&&own.current_artifact_id?{type:'view-work',artifactId:own.current_artifact_id}:{type:'continue-learning',runId:own.id}}
              :allowed?{label:'开始这个作品',action:{type:'start-course',courseId:c.id}}:{label:'准备开始',action:{type:'prepare-learning'}}};
        });
        const series: HallCourse[] = catalogResult.status === 'fulfilled' ? catalogResult.value.courses.filter(c => courseIds.includes(c.id) && c.status === 'trial').sort((a,b) => a.order-b.order).map(c => ({
          id:c.id,state:'trial',title:c.title,goal:c.goal,stage:c.chapter,preparation:c.preparation,experience:c.duration,
          steps:c.steps.map(s=>s.title),cover:{...c.cover,label:'松伴原创教学插画'},statusLabel:'试学',
          action:{label:'开始这门课',action:{type:'start-course',courseId:c.id}},
        })) : [];
        if(current===epoch.current)setState({page:'ai',status:catalogResult.status === 'fulfilled'?'ready':'error',courses:[...series,...cards],notice,
          error:catalogResult.status === 'rejected'?'新课程目录暂时没有读到，请重试。以前的作品仍可从原入口继续。':undefined,
          resume:home?.run_id?{title:'继续上次的作品',description:'从上次保存的位置接着做。',action:{label:'打开上次的作品',action:{type:'continue-learning',runId:home.run_id}}}:null});
      }catch(e){if(current===epoch.current)setState({page:'ai',status:'error',courses:[],error:lessonError(e)});}
    })();
    return ()=>{++epoch.current;};
  },[api,session?.id,session?.learner_id,session?.mode,session?.mode_epoch,page,config?.learning_enabled,retry]);
  async function act(action:HallAction){
    if(action.type==='retry'){setRetry(n=>n+1);return;}
    if(action.type==='continue-learning')return navigate(runRoute(action.runId));
    if(action.type==='view-work')return navigate(`#/learn/works?id=${encodeURIComponent(action.artifactId)}`);
    if(action.type==='start-course')return navigate(courseIds.includes(action.courseId as CourseId)?courseRoute(action.courseId as CourseId):'#/learn/first');
    if(action.type==='prepare-learning')return navigate('#/learn/first');
    if(action.type==='hackathon-intro')return navigate('#/hackathon/intro');
    if(action.type==='hackathon-hall')return navigate('#/hackathon');
    if(action.type==='begin-practice'||action.type==='resume-practice'){
      if(session?.mode==='learner')return navigate('#/family');
      if(await canLeave())location.assign('/#/events');
    }
  }
  return <><HallView state={state} onAction={act}/>{page==='ai'&&<section className="lp-card"><h2>以前的练习与作品</h2><button onClick={()=>void navigate('#/learn/first')}>打开以前的练习</button><button onClick={()=>void navigate('#/portfolio')}>打开作品集</button></section>}{page==='ai'&&creativeEnabled&&<section className="lp-card"><p className="lp-eyebrow">已经有了小想法？</p><h2>从一个想法开始</h2><p>做一个能点击的小网页或小游戏，跟松伴一起预测、运行、观察，再改一处试试。</p><button className="lp-primary" onClick={()=>void navigate('#/learn/create')}>从我的想法开始</button></section>}</>;
}
