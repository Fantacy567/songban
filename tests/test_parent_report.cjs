const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const context = {module:{exports:{}}, Date};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/songban-parent-report.js'),'utf8'), context);
const {build, render, plainText, documentHtml} = context.module.exports;

function fixture(){
  return {
    person:{id:'child-a',name:'林同学'},
    preferences:{interests:['校园生活'],skills:['画画或设计'],experience:'第一次做交互原型',time:'一个周末'},
    snapshot:{me:{id:'child-a'},team:{id:'team-a',name:'创作小队'},direction:{goal:'做一个活动推荐作品'},
      members:[{id:'child-a',willingness:'我想把三页原型连接起来',strengths:'原型设计'},{id:'child-b',name:'队友'}],
      active_plan:{tasks:[
        {title:'页面草图',owner_id:'child-a',status:'reported_done',handoff_state:'accepted',latest_progress:{summary:'完成草图',evidence:['三页原型']},handoff:{note:'正常和返回流程均已核对'}},
        {title:'原型连接',owner_id:'child-a',status:'reported_done',handoff_state:'waiting_review',latest_progress:{summary:'已连接原型',evidence:['可点击的原型']}},
        {title:'其他孩子的任务',owner_id:'child-b',status:'reported_done',handoff_state:'accepted',latest_progress:{summary:'其他孩子的成果'}},
        {title:'仅建议本人负责',owner_id:'',suggested_owner_id:'child-a',status:'todo'},
      ]},
      reports:[{seq:1,user_id:'child-a',summary:'复盘：我学会先画草图'}, {seq:2,user_id:'child-b',summary:'复盘：其他孩子的个人经历'}, {seq:3,user_id:'child-a',summary:'复盘：我还想练习讲解原型'}],
    },
    event:{title:'创作周末',date:'11月7日—8日',location:'上海'},
    analysis:{summary:'林同学参与了页面草图和原型连接，当前一项成果有同伴核对记录。',observations:[{title:'把想法变成作品',detail:'有页面草图的成果记录。',source:'本人任务：页面草图'}],suggestions:['请孩子讲解页面草图。','一起讨论原型还可以怎样改进。']},
    model:{mode:'fixture',actual_model:'fixture'},
    generatedAt:'2026-10-31T13:00:00Z',
  };
}

{
  const report=build(fixture());
  assert.equal(report.tasks.length,2);
  assert.equal(report.checked,1,'self-reported completion must not be counted as reviewed');
  assert.equal(report.tasks[1].status,'已报告完成，待同伴核对');
  assert.equal(report.reflection,'我还想练习讲解原型');
  assert.equal(report.reflectionSource,'来自已保存的本人复盘');
  const output=plainText(report);
  assert(!output.includes('其他孩子'));
  assert(!output.includes('仅建议本人负责'));
  assert(output.includes('第一次做交互原型'));
}
{
  const input=fixture();input.draft='我今天遇到了返回后选择丢失的问题';
  const report=build(input);
  assert.equal(report.reflection,input.draft);
  assert.equal(report.reflectionSource,'来自本页复盘草稿');
  input.draftIsExample=true;
  assert.equal(build(input).reflection,'我还想练习讲解原型','demo defaults must not replace saved personal reflections');
  input.snapshot.reports=[];
  assert.equal(build(input).reflectionSource,'来自本页演示复盘');
}
{
  const input=fixture();input.preferences=null;input.draft='';input.snapshot.reports=[];input.snapshot.active_plan={tasks:[]};
  const report=build(input);
  assert.equal(report.tasks.length,0);assert.equal(report.checked,0);assert.equal(report.reflection,'');
  assert(render(report).includes('尚未记录本人领取或承担的任务'));
  assert(render(report).includes('还没有个人复盘'));
}
{
  const input=fixture();input.snapshot.me.id='child-b';
  assert.throws(()=>build(input),/成员已切换/);
  input.snapshot.me.id='child-a';input.snapshot.members=[];
  assert.throws(()=>build(input),/没有这位成员/);
}
{
  const input=fixture();input.person.name='<img src=x onerror=alert(1)>';input.draft='<script>window.bad=true</script>';
  const report=build(input),html=documentHtml(report,'.parent-report{color:green}');
  assert(!html.includes('<script>'));assert(!html.includes('<img'));
  assert(html.includes('&lt;script&gt;'));assert(html.includes('color:green'));
  assert(!html.includes('<script src='));assert(html.includes('虚构参赛样例'));
}
console.log('PASS: member isolation, task status, latest saved reflection, draft priority, empty states, identity changes, safe standalone export.');
{
  const input=fixture();delete input.analysis;
  assert.throws(()=>build(input),/模型没有返回完整/,'No template fallback without an AI response');
}
