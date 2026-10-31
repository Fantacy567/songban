'use strict';
// Only activated by the isolated demo entrance. Real accounts are never prefilled.
const demoText={
 'idea-title':'作业时间小助手','idea-problem':'同学不知道今晚先做哪一项作业。','idea-proposal':'输入科目、截止时间和预计用时，生成可勾选的安排；两人各6小时做一个网页。',
 'recap-feelings':'先画流程再开发让我少走弯路，队友指出了我漏掉的返回按钮。','recap-ideas':'下次更早给同学试用，并核对AI输出是否符合实际。','recap-result':'完成展示，结果尚未公布（虚构演示）。'
};
function demoFill(){
 if(!window.SONGBAN_DEMO)return;
 for(const [id,value] of Object.entries(demoText)){const input=document.getElementById(id);if(input&&!input.value&&!input.dataset.demoFilled){input.value=value;input.dataset.demoFilled='1';}}
 const div=document.getElementById('division-text');if(div&&!div.value&&!div.dataset.demoFilled){const text=document.getElementById('division-answer')?.textContent||'';div.value=div.type==='number'?'6':text.includes('2 / 4')?'我能独立画草图，代码需要AI和队友协助。':text.includes('4 / 4')?'上传三个步骤的草图，请队友按输入、生成、打勾顺序检查。':'我愿意负责界面草图和流程说明。';div.dataset.demoFilled='1';}
 document.querySelectorAll('.finish-task-form textarea, #check-form textarea').forEach(input=>{if(!input.value&&!input.dataset.demoFilled){input.value='虚构演示成果：已核对输入作业、生成安排和完成打勾三个步骤。';input.dataset.demoFilled='1';}});
}
document.addEventListener('DOMContentLoaded',()=>{if(window.SONGBAN_DEMO)new MutationObserver(demoFill).observe(document.getElementById('app'),{subtree:true,childList:true});});

// Demo-only organizer fragments. These are labelled fictional sources, not extracted facts.
const demoContestFixtures={
 author:'松伴周末创造营组委会（虚构）',
 text:'【虚构演示补充公告】\n比赛名称：松伴周末创造营（虚构演示）\n赛道：校园创意网页、学习工具、生活小助手\n办赛理念：鼓励学生发现身边的真实问题，在团队协作中完成一个小而完整的作品。',
 links:[
  {url:'https://demo.songban.invalid/schedule',text:'【虚构演示赛程通知】\n时间：2026年11月1日09:00开营，11月2日15:00作品展示\n地点：线上参加，展示地点为虚构松伴创作空间\n截止：2026年11月2日18:00（北京时间）'},
  {url:'https://demo.songban.invalid/awards',text:'【虚构演示奖励说明】\n奖金：一等奖人民币2000元，二等奖人民币1000元，三等奖人民币500元（均为虚构演示，不构成实际奖励承诺）'}
 ],
 fileName:'松伴虚构赛-提交与评审说明.txt',
 fileText:'【虚构演示文件】\n提交要求：可运行网页、代码链接、项目说明和3分钟展示\n评分标准：用户价值40%、完成度35%、协作与表达25%\n办赛理念：重视真实尝试与合作过程，而不只看最终排名。'
};
function demoContestLinkSource(link){return {kind:'text',name:'示例网页（虚构） · '+link.url,content:'虚构示例链接（使用预置正文，未访问真实网站）：'+link.url+'\n'+link.text,author:demoContestFixtures.author,nature:'sample'};}
function demoContestSourceBodies(){return [
 {kind:'text',name:'文字 / 聊天摘录',content:demoContestFixtures.text,author:demoContestFixtures.author,nature:'sample'},
 ...demoContestFixtures.links.map(demoContestLinkSource),
 {kind:'file',name:demoContestFixtures.fileName,content:btoa(Array.from(new TextEncoder().encode(demoContestFixtures.fileText),b=>String.fromCharCode(b)).join('')),author:demoContestFixtures.author,nature:'sample'}
];}
async function ensureDemoContestMaterials(spaceId){
 if(!window.SONGBAN_DEMO)return;
 const base='/api/materials/spaces/'+encodeURIComponent(spaceId);let saved=await api(base);
 for(const body of demoContestSourceBodies()){
  // Do not resurrect a source that the presenter deliberately withdrew.
  const existing=saved.sources.find(s=>s.metadata.name===body.name);
  if(existing){if(['received','reading','failed'].includes(existing.status)){await api(base+'/sources/'+existing.id+'/parse',{expected_revision:saved.revision});saved=await api(base);}continue;}
  const added=await api(base+'/sources',{...body,request_id:crypto.randomUUID()});saved=await api(base);
  if(['received','reading','failed'].includes(added.source.status)){await api(base+'/sources/'+added.source.id+'/parse',{expected_revision:saved.revision});saved=await api(base);}
 }
}
