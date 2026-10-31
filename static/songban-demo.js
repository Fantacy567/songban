'use strict';
// Only activated by the separate loopback demo server. Production has no demo bootstrap.
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
