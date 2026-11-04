/* One companion host outside the legacy render root; private state follows identity. */
(() => {
  'use strict';
  let current=null, handle=null, host=null, serial=0, signature='', verified='', dirty=false, leaveApproved=false;
  const sessionKey=s=>s?`${s.id}:${s.mode_epoch}:${s.mode}:${s.actor_id}:${s.learner_id||''}`:'participant';
  const problem=(status,code)=>Object.assign(Error('请重新核对当前身份和记录。'),{status,code});
  async function session(){
    const r=await fetch('/api/learning/v2/session',{credentials:'same-origin',cache:'no-store',redirect:'error'});
    if(r.status===401)return null;
    if(!r.ok)throw problem(r.status,'identity_unavailable');
    return r.json();
  }
  function reset(){++serial;signature='';verified='';dirty=false;handle?.unmount();handle=null;host?.remove();host=null;}
  function canLeave(){if(!dirty)return true;const approved=window.confirm('和松伴的输入或回应还没有核对完，确定离开这个页面吗？已发送的记录仍会保留。');if(approved){leaveApproved=true;setTimeout(()=>{leaveApproved=false;},0);}return approved;}
  async function request(path,method='GET',body){
    const captured=current, fence=serial, token=captured?.token;
    if(!captured||captured.restricted)throw problem(401,'identity_unavailable');
    let before;try{before=await session();}catch{reset();throw problem(401,'identity_unavailable');}
    if(serial!==fence||current?.token!==token||sessionKey(before)!==verified||before?.mode==='learner'){
      reset();throw problem(401,'identity_changed');
    }
    const headers={Accept:'application/json'};
    if(before&&method!=='GET'){
      const boot=await fetch('/api/learning/v2/session-bootstrap',{credentials:'same-origin',cache:'no-store',redirect:'error'});
      if(!boot.ok)throw problem(boot.status,'identity_unavailable');
      headers['X-CSRF-Token']=(await boot.json()).csrf_token;
    } else if(!before&&token)headers.Authorization='Bearer '+token;
    if(method!=='GET')headers['Content-Type']='application/json';
    if(serial!==fence)throw problem(401,'identity_changed');
    let r,data;
    try{
      r=await fetch('/api/platform/v1'+path,{method,headers,credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(20000),...(body===undefined?{}:{body:JSON.stringify(body)})});
      data=await r.json();
    }catch{throw problem(0,'network_unknown');}
    let after;try{after=await session();}catch{reset();throw problem(401,'identity_unavailable');}
    if(serial!==fence||current?.token!==token||verified!==sessionKey(after)){reset();throw problem(401,'identity_changed');}
    if(!r.ok){if([401,403,404].includes(r.status))reset();throw problem(r.status,data.error?.code||'request_failed');}
    return data;
  }
  const transport={
    open:body=>request('/companion/sessions','POST',body),
    read:id=>request('/companion/sessions/'+encodeURIComponent(id)),
    send:(id,body)=>request('/companion/sessions/'+encodeURIComponent(id)+'/messages','POST',body),
    readMessage:(id,message)=>request('/companion/sessions/'+encodeURIComponent(id)+'/messages/'+encodeURIComponent(message)),
  };
  async function update(value){
    const old=current;current=value;
    if(old&&(old.token!==value.token||old.epoch!==value.epoch))reset();
    if(value.restricted||value.page==='workbench'||!window.SongbanCompanion){reset();return;}
    const ticket=serial;
    let who;try{who=await session();}catch{reset();return;}
    if(ticket!==serial||current!==value)return;
    if(who?.mode==='learner'||who?.mode==='staff'||(!who&&!value.token)){reset();return;}
    const identity=sessionKey(who);
    if(verified&&identity!==verified){reset();}
    verified=identity;
    const context=who?{domain:'hall',resource_id:'hackathon'}:
      value.team&&!['login','hackathon','hackathonIntro','events','event','interview','onboarding'].includes(value.page)
        ?{domain:'competition',resource_id:value.team}:{domain:'hall',resource_id:'hackathon'};
    const next=JSON.stringify([identity,value.epoch,context]);
    if(host)host.hidden=false;
    if(signature===next&&handle)return;
    signature=next;
    if(!host){host=document.createElement('div');host.id='platform-companion-host';document.body.append(host);}
    const props={identityKey:identity+':'+value.epoch,context,transport,presentation:'floating',onDirty:value=>{dirty=value;},onAction:action=>{
      if(action.kind==='open_course_hall'){if(canLeave())location.assign('/learning-prep#/learn/courses');}
      else if(action.kind==='open_portfolio'){if(canLeave())location.assign('/learning-prep#/portfolio');}
      else if(action.kind==='open_hackathon_hall')current.onNavigate('hackathon');
      else if(action.kind==='open_competition_team'&&action.resource_id===current.team)current.onNavigate('work');
    }};
    if(handle)handle.update(props);else handle=window.SongbanCompanion.mount(host,props);
  }
  window.SongbanPlatformNative={update,reset,canLeave};
  // Hide cached private UI while away, then recheck identity before revealing it.
  // A normal tab switch must not discard an unsent draft.
  document.addEventListener('visibilitychange',()=>{if(document.hidden){if(host)host.hidden=true;}else if(current)void update(current);});
  window.addEventListener('beforeunload',event=>{if(dirty&&!leaveApproved){event.preventDefault();event.returnValue='';}});
  if(typeof BroadcastChannel!=='undefined'){const channel=new BroadcastChannel('songban-learning-identity');channel.onmessage=()=>{reset();if(current)void update(current);};}
})();
