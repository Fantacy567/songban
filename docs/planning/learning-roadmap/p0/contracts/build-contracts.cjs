// P0 specification generator only. No application imports, network or DB access.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const schemas = {};
const str = {type:'string', minLength:1, maxLength:8000};
const id = {type:'string', minLength:1, maxLength:100};
const int = {type:'integer', minimum:0};
const bool = {type:'boolean'};
const en = (...values) => ({type:'string', enum:values});
const ref = name => ({$ref:'#/components/schemas/'+name});
const arr = items => ({type:'array', items, maxItems:100});
const nil = value => ({anyOf:[value,{type:'null'}]});
const obj = (properties, optional=[]) => ({type:'object', additionalProperties:false, properties, required:Object.keys(properties).filter(k=>!optional.includes(k))});
const put = (name,properties,optional=[]) => schemas[name]=obj(properties,optional);
const req = (name,properties={},revision=true,optional=[]) => put(name,{request_id:{...id,minLength:8},...(revision?{expected_revision:int}:{}),...properties},optional);
const stamp = {id,revision:int};
const mode = en('mock','live','replay');
const role = en('guide','tool_guide','creation_coach','review_coach');
const stage = en('clarify','create','review');
const status = en('pending','running','succeeded','failed','unknown');
const time = {type:'string',format:'date-time'};
const startFields=['age_band','experience','interests','help_preference','mini_attempt_text','chosen_start'];
const startChoice=en('guided','try_first','challenge');
function answer(name,value,allowDefault=false){
  schemas[name]={oneOf:[obj({state:en('unanswered','skipped'),value:{type:'null'}}),obj({state:{type:'string',const:'answered'},value}),...(allowDefault?[obj({state:{type:'string',const:'accepted_default'},value,recommendation_revision:int})]:[])]};
}
answer('AgeAnswer',id); answer('ExperienceAnswer',en('none','some','regular'));
answer('InterestsAnswer',arr(id)); answer('HelpPreferenceAnswer',startChoice);
answer('MiniAttemptAnswer',{...str,pattern:'\\S'}); answer('StartChoiceAnswer',startChoice,true);
const startAnswers={age_band:ref('AgeAnswer'),experience:ref('ExperienceAnswer'),interests:ref('InterestsAnswer'),help_preference:ref('HelpPreferenceAnswer'),mini_attempt_text:ref('MiniAttemptAnswer'),chosen_start:ref('StartChoiceAnswer')};
put('StartAnswers',startAnswers);
put('StartAnswerPatch',startAnswers,startFields); schemas.StartAnswerPatch.minProperties=1;
schemas.StartAnswerPatch.allOf=[{if:{required:['chosen_start'],properties:{chosen_start:{properties:{state:{const:'accepted_default'}}}}},then:{maxProperties:1}}];
put('ErrorDetail',{code:id,message:str,retryable:bool,recovery:en('reauthenticate','reload','merge','poll','contact_support','none'),current_revision:nil(int)});
put('Error',{error:ref('ErrorDetail')});
put('Source',{source_id:id,source_version:id,source_domain:en('learning_v2','competition_parent_v1','competition_recap_v1'),nature:en('child_statement','system_record','ai_suggestion','human_review','legacy_unversioned')});
put('Action',{type:en('start_profile','start_run','continue_run','save_attempt','run_model','save_artifact','check','revise','reflect','wait_review','view_report','contact_support'),resource_id:nil(id),label:str});
put('Bootstrap',{csrf_token:id,browser_revision:int});
put('Config',{contract_version:id,learning_enabled:bool,live_enabled:bool,publication_enabled:bool,age_band_options:arr(id),consent_version:id,notice:str});
put('Session',{...stamp,mode:en('manager','learner','staff'),actor_id:id,learner_id:nil(id),mode_epoch:int,scopes:arr(id),expires_at:time});
put('LoggedOut',{revoked:bool,mode_epoch:int});
req('Authenticate',{browser_revision:int,method:en('password','verified_challenge'),account:id,proof:{...str,writeOnly:true}},false);
req('EnterLearner',{learner_id:id}); req('Logout');
put('GuardianLink',{...stamp,learner_id:id,status:en('pending','verified','rejected','revoked'),declared_relationship:str,verification_method:nil(id)});
put('Learner',{...stamp,family_id:id,display_name:{...str,maxLength:60},age_band:nil(id),guardian_link:ref('GuardianLink')});
put('Family',{...stamp,learners:arr(ref('Learner'))});
put('Families',{items:{...arr(ref('Family')),maxItems:1},next_cursor:{type:'null'}});
req('NewFamily',{},false);
req('NewLearner',{display_name:{...str,maxLength:60},age_band:nil(id),declared_relationship:str},true);
req('EditProfile',{display_name:{...str,maxLength:60},age_band:nil(id)});
put('Consent',{...stamp,learner_id:id,consent_version:id,scopes:arr(en('learning','live_model','parent_summary','report_publication')),status:en('active','revoked'),recorded_at:time});
const consentScope=en('learning','live_model','parent_summary','report_publication');
const sha256={type:'string',pattern:'^[a-f0-9]{64}$'};
put('ConsentSummary',{...schemas.Consent.properties,text_sha256:sha256,effective_scopes:arr(consentScope)});
schemas.ConsentSummary.allOf=[{if:{properties:{status:{const:'revoked'}}},then:{properties:{effective_scopes:{maxItems:0}}}}];
put('Consents',{learner_id:id,relationship_status:en('pending','verified','rejected','revoked'),visibility:en('own_submissions','linked_learner','assigned_case'),items:arr(ref('ConsentSummary')),next_cursor:nil(id)});
schemas.Consents.allOf=[{if:{properties:{relationship_status:en('pending','rejected','revoked')}},then:{properties:{items:{items:{properties:{effective_scopes:{maxItems:0}}}}}}}];
put('ConsentText',{consent_version:id,locale:id,title:str,text:str,text_sha256:sha256,scope_purposes:arr(obj({scope:consentScope,purpose:str})),approval_status:en('draft','approved_for_pilot','withdrawn'),approved_at:nil(time),acceptance_enabled:bool,notice:str});
schemas.ConsentText.allOf=[
 {if:{properties:{approval_status:en('draft','withdrawn')}},then:{properties:{acceptance_enabled:{const:false}}}},
 {if:{properties:{approval_status:{const:'draft'}}},then:{properties:{approved_at:{type:'null'}}}},
 {if:{properties:{approval_status:{const:'approved_for_pilot'}}},then:{properties:{approved_at:time}}}
];
req('NewConsent',{consent_version:id,scopes:arr(en('learning','live_model','parent_summary','report_publication')),acknowledged:{const:true,type:'boolean'}});
req('Reason',{reason:str});
put('Enrollment',{...stamp,learner_id:id,course_version_id:id,entitlement_id:id,status:en('active','expired','revoked'),parent_revision:int});
req('NewEnrollment',{course_version_id:id,entitlement_id:id});
put('Start',{...stamp,learner_id:id,answers:ref('StartAnswers'),completion_status:en('not_started','draft','completed','completed_with_skips'),mini_attempt_status:en('not_attempted','skipped','answered'),recommendation:startChoice,recommendation_basis:en('rules','insufficient_evidence'),recommendation_revision:int,recommendation_rule_version:id,recommendation_source_fields:arr(en(...startFields)),missing_fields:arr(en(...startFields)),skipped_fields:arr(en(...startFields)),effective_start:startChoice,effective_start_source:en('learner_choice','accepted_default','conservative_fallback'),saved_at:nil(time)});
req('SaveStart',{answers:ref('StartAnswerPatch')});
put('Progress',{lesson_version_id:id,stage,state:en('locked','available','in_progress','pending_review','needs_practice','passed'),artifact_version_id:nil(id),check_id:nil(id),recheck_required:bool});
put('Home',{learner_id:id,revision:int,current_action:ref('Action'),run_id:nil(id),progress:arr(ref('Progress')),entitlements:arr(ref('Enrollment'))});
put('TaskCard',{id,version:id,stage,goal:str,instructions:arr(str),material_version_ids:arr(id),tool_card_ids:arr(id),rubric_version_id:id,help_levels:arr(str)});
put('ToolCard',{id,version:id,steps:arr(str),prompt_template:str,checks:arr(str),notice:str});
put('Course',{...stamp,title:str,state:en('published','archived'),lesson_version_ids:arr(id),task_cards:arr(ref('TaskCard')),tool_cards:arr(ref('ToolCard'))});
put('Run',{...stamp,learner_id:id,enrollment_id:id,course_version_id:id,progress:arr(ref('Progress')),current_action:ref('Action'),parent_revision:int});
req('NewRun',{enrollment_id:id});
put('Attempt',{...stamp,run_id:id,lesson_version_id:id,kind:en('practice','transfer'),material_version_id:id,input_text:str,help_event_ids:arr(id),parent_revision:int});
req('NewAttempt',{lesson_version_id:id,kind:en('practice','transfer'),material_version_id:id,input_text:str});
req('EditAttempt',{input_text:str,declared_help:en('none_reported','adult_transcription','peer_help','other_reported')});
put('Usage',{status:en('available','exhausted','held_for_review','unconfigured'),available_units:nil(int),held_units:nil(int),settled_units:nil(int),cost_estimate:nil({type:'number',minimum:0}),usage_source:en('provider','estimated','unknown','mock','replay'),notice:str});
put('ModelRun',{...stamp,attempt_id:nil(id),report_id:nil(id),help_event_id:nil(id),mode,status,requested_model:nil(id),actual_model:nil(id),config_version:id,input_revision:int,output_text:nil(str),reservation_id:nil(id),usage:ref('Usage'),reconciliation_case_id:nil(id),visibility:en('normal','restricted'),parent_revision:int});
req('NewModelRun',{mode,config_version:id,replay_of:nil(id)});
put('Help',{...stamp,run_id:id,role_id:role,prompt_version:id,help_level:{type:'integer',minimum:1,maximum:3},mode:en('static','mock','live','replay'),text:nil(str),sources:arr(ref('Source')),actions:arr(en('open_tool_card','save_candidate','request_human_help')),model_run_id:nil(id),parent_revision:int});
req('NewHelp',{role_id:role,help_level:{type:'integer',minimum:1,maximum:3},mode:en('static','mock','live','replay'),question:str,source_ids:arr(id)});
put('CardText',{title:{...str,maxLength:40},audience:{...str,maxLength:200},date:id,start_time:id,end_time:id,place:{...str,maxLength:200},preparation:{...str,maxLength:200},invitation_line:{...str,maxLength:160}});
put('ArtifactVersion',{id,artifact_id:id,version:int,content:ref('CardText'),attempt_id:id,model_run_id:nil(id),help_event_ids:arr(id),authorship:en('child_edit','ai_candidate_edited','adult_transcription'),created_at:time});
put('Artifact',{...stamp,learner_id:id,run_id:id,current_version:ref('ArtifactVersion'),check_status:en('unchecked','pending_review','needs_practice','passed','recheck_required'),parent_revision:int});
req('NewArtifact',{attempt_id:id,model_run_id:nil(id),help_event_ids:arr(id),authorship:en('child_edit','ai_candidate_edited','adult_transcription'),content:ref('CardText')});
req('NewArtifactVersion',{attempt_id:id,model_run_id:nil(id),help_event_ids:arr(id),authorship:en('child_edit','ai_candidate_edited','adult_transcription'),content:ref('CardText'),change_explanation:str});
put('Check',{...stamp,run_id:id,learner_id:id,lesson_version_id:id,artifact_version_id:id,rubric_version_id:id,rule_result:en('pass','needs_practice','manual_required'),human_result:nil(en('passed','needs_practice')),missing_evidence:arr(id),feedback:arr(str),case_id:nil(id),evidence_hash:id,stale:bool,parent_revision:int});
req('NewCheck',{lesson_version_id:id,artifact_version_id:id,rubric_version_id:id,reflection_id:nil(id),transfer_attempt_id:nil(id)});
put('Reflection',{...stamp,run_id:id,artifact_version_id:id,change_explanation:str,judgement:str,transfer_attempt_id:id,declared_help:en('none_reported','adult_transcription','peer_help','other_reported'),parent_revision:int});
req('NewReflection',{artifact_version_id:id,change_explanation:str,judgement:str,transfer_attempt_id:id,declared_help:en('none_reported','adult_transcription','peer_help','other_reported')});
put('Case',{...stamp,kind:en('relationship','learning_review','report_review','support'),target_id:id,status:en('open','claimed','resolved','escalated'),owner_display_name:str,due_at:time,feedback:nil(str),next_action:ref('Action'),parent_revision:int});
req('NewCase',{message:str}); req('Claim'); req('Transfer',{assignee_id:id,reason:str});
req('ResolveCase',{decision:en('verified','rejected','passed','needs_practice','answered'),evidence_ids:arr(id),target_revision:int,note:str});
put('Observation',{text:str,source_ids:{...arr(id),minItems:1},nature:en('child_statement','system_record','ai_suggestion','human_review')});
put('Report',{...stamp,learner_id:id,run_id:id,status:en('draft','pending_review','published','failed','revoked'),generation_status:status,source_snapshot_id:id,source_hash:id,observations:arr(ref('Observation')),limitations:arr(str),evidence_changed:bool,review_id:nil(id),publication_id:nil(id),parent_revision:int});
req('NewReport',{reflection_id:id,artifact_version_id:id,check_id:id,mode});
req('Dispute',{source_ids:arr(id),note:str});
put('DisputeRecord',{...stamp,report_id:id,status:en('open','resolved'),parent_revision:int});
req('SubmitReview',{facts_confirmed:bool});
req('ReviewReport',{decision:en('approved','changes_requested'),source_hash:id,corrected_observations:arr(ref('Observation')),note:str,resolved_dispute_ids:arr(id)});
req('PublishReport',{review_id:id,source_hash:id});
put('Publication',{...stamp,report_id:id,published_revision:int,published_at:time,parent_revision:int});
put('Reconciliation',{...stamp,model_run_id:id,status:en('open','escalated','resolved'),owner_display_name:str,due_at:time,usage:ref('Usage'),resolution:nil(en('accepted_result','confirmed_no_charge','confirmed_charge_no_output','administrative_adjustment'))});
req('ResolveReconciliation',{resolution:en('accepted_result','confirmed_no_charge','confirmed_charge_no_output','administrative_adjustment'),evidence_ids:{...arr(id),minItems:1},settled_units:nil(int),adjustment_units:nil({type:'integer'}),reason:str});
for (const [name,item] of [['Courses','Course'],['Artifacts','Artifact'],['Helps','Help'],['Reports','Report'],['Cases','Case']]) put(name,{items:arr(ref(item)),next_cursor:nil(id)});

const paths = {}, operations = [];
function endpoint(method,url,operationId,request,response,actors,description,code=200) {
  const parameters = [...url.matchAll(/\{(\w+)\}/g)].map(m=>({name:m[1],in:'path',required:true,schema:id}));
  if (method==='get' && ['Courses','Artifacts','Helps','Reports','Cases','Consents'].includes(response)) parameters.push({name:'cursor',in:'query',schema:id},{name:'limit',in:'query',schema:{type:'integer',minimum:1,maximum:100,default:20}});
  if (method!=='get') parameters.push({name:'X-CSRF-Token',in:'header',required:true,schema:id});
  const operation = {operationId,summary:description,'x-status':'proposed_not_registered','x-authorized-actors':actors,parameters,
    security:actors.includes('public')?[]:[{ScopedSession:[]}],
    responses:{[code]:{description:'拟议成功响应；异步受理后通过 GET 查询资源。',content:{'application/json':{schema:ref(response)}}},default:{description:'按规格鉴权/幂等/版本/业务错误，绝不包装成功。',content:{'application/json':{schema:ref('Error')}}}}};
  if(request) operation.requestBody={required:true,content:{'application/json':{schema:ref(request)}}};
  if(['authenticate','enterLearner','logout'].includes(operationId)) operation['x-cookie-transition']='事务校验 mode_epoch；禁止重放凭证明文；参见规格第3节';
  paths[url] ??= {}; paths[url][method]=operation;
  operations.push({operation_id:operationId,method:method.toUpperCase(),path:'/api/learning/v2'+url,request_schema:request,response_schema:response,status:code});
}
const e=endpoint, M=['manager'], L=['learner'], ML=['manager','learner'], R=['assigned:learning_review'], S=['assigned:support'];
e('get','/session-bootstrap','bootstrap',null,'Bootstrap',['public'],'建立匿名浏览器绑定与 CSRF');
e('get','/config','config',null,'Config',['public'],'公开功能状态与版本标识；版本标识不证明已批准，不返回供应商秘密');
e('post','/sessions/authenticate','authenticate','Authenticate','Session',['public'],'新鲜认证证明建立受限范围会话');
e('get','/session','session',null,'Session',['manager','learner','staff'],'当前权威身份及 mode_epoch');
e('post','/sessions/enter-learner','enterLearner','EnterLearner','Session',M,'事务撤销旧管理与旧 Bearer 并进入指定孩子');
e('post','/sessions/logout','logout','Logout','LoggedOut',['manager','learner','staff'],'撤销当前会话，不恢复旧凭证');
e('post','/families','createFamily','NewFamily','Family',M,'为本人建立家庭资源',201);
e('get','/families','listFamilies',null,'Families',M,'仅当前manager本人拥有家庭，MVP至多1；清缓存后由服务端恢复');
e('get','/families/{family_id}','getFamily',null,'Family',M,'仅本人有效关联家庭的最小档案');
e('post','/families/{family_id}/learners','createLearner','NewLearner','Learner',M,'新建孩子与 pending 关系核验案件',201);
e('get','/learners/{learner_id}/profile','getProfile',null,'Learner',ML,'本人档案按 scope 投影；孩子不含家庭管理字段');
e('patch','/learners/{learner_id}/profile','editProfile','EditProfile','Learner',M,'修改关联档案且不覆盖学习事实');
e('post','/learners/{learner_id}/consents','createConsent','NewConsent','Consent',M,'verified 关系提交版本化同意',201);
e('get','/learners/{learner_id}/consents','listConsents',null,'Consents',['manager','assigned:consent_read'],'本人关联授权记录；pending仅本人提交；孩子不能读取成人管理信息');
e('get','/consent-texts/{consent_version}','consentText',null,'ConsentText',['public'],'读取确切版本授权文本与用途，研发草案不代表真实试点批准');
paths['/families'].get['x-business-rules']=['owner_person_id由当前有效manager会话确定；不接受user_id/owner_id/actor_id查询，不枚举其他人的家庭','MVP每账号最多一个家庭；空列表才显示创建入口，不能把失权/故障当无家庭；已存在家庭时POST新建不能产生第二个家庭','GET只读且no-store，不以localStorage保存的family_id为恢复前提；孩子/staff不能使用此入口'];
paths['/learners/{learner_id}/consents'].get['x-business-rules']=['manager须本人有效guardian_link；verified可看该learner获准授权摘要，pending仅提交者为当前actor的既有记录，无记录则items=[]','staff须显式consent_read及当前案件分配，按必要用途投影；不因教师/运营角色获得全量读取','learner会话拒绝；跨家庭或无关系404，不返回其他监护人身份/联系方式、证件、原始核验材料','按recorded_at降序稳定游标读取，返回consent_id/revision/scopes/text版本；effective_scopes由服务端按当前关系、文本状态与撤回状态算出，不把active记录当已生效授权'];
paths['/consent-texts/{consent_version}'].get['x-business-rules']=['版本对应不可变locale/title/text/scope_purposes内容和SHA-256；草案修改须新版本，不用最新文本解释历史同意','Config.consent_version仅指当前建议展示版本，不证明已批准；读取历史ConsentSummary必须用其consent_version','真实授权提交须文本approved_for_pilot且acceptance_enabled=true、有效关系与相应范围；draft/withdrawn不得签发真实权限','UI逐字呈现服务端文本和用途，不自行撰写或由模型补授权条款；文本缺失或未获批准时只说明待确认，不显示可确认的正式授权'];
paths['/learners/{learner_id}/consents'].post['x-business-rules']=['consent_version必须解析到同一不可变文本；服务器保存内容hash与选择范围，客户端不能自传改写文本或批准状态','真实记录仅在文本approved_for_pilot且acceptance_enabled=true及verified关系下提交；草案仅可作隔离fixture，不能据此授予真实权限','pending可读本人既有记录不新增其提交授权；scopes必须属于该文本的scope_purposes'];
e('post','/consents/{consent_id}/revoke','revokeConsent','Reason','Consent',M,'撤回授权并失效派生权限');
e('post','/learners/{learner_id}/enrollments','enroll','NewEnrollment','Enrollment',M,'仅兑换已有授权权益，不能核款/自行开通',201);
e('get','/learners/{learner_id}/home','home',null,'Home',ML,'下一动作与进度；家长仅摘要');
e('get','/learners/{learner_id}/start','getStart',null,'Start',L,'读取本人起点或 revision=0 空记录');
e('patch','/learners/{learner_id}/start','saveStart','SaveStart','Start',L,'逐主题合并起点草稿：缺失不变，null有明确未答/跳过状态');
e('get','/courses','courses',null,'Courses',['public'],'已发布课程目录');
e('get','/courses/{course_version_id}','course',null,'Course',['manager','learner','staff'],'授权内固定课程版本');
e('post','/learners/{learner_id}/runs','createRun','NewRun','Run',L,'无团队建立课次',201);
e('get','/runs/{run_id}','run',null,'Run',L,'当前任务、进度和下一动作');
e('post','/runs/{run_id}/attempts','createAttempt','NewAttempt','Attempt',L,'先持久保存尝试再调用',201);
e('get','/attempts/{attempt_id}','attempt',null,'Attempt',L,'取回本人已保存输入');
e('patch','/attempts/{attempt_id}','saveAttempt','EditAttempt','Attempt',L,'乐观锁保存新输入修订');
e('post','/attempts/{attempt_id}/model-runs','createModelRun','NewModelRun','ModelRun',L,'授权校验、预算预占与持久派发',202);
e('get','/model-runs/{model_run_id}','modelRun',null,'ModelRun',['learner','assigned:usage_reconcile'],'轮询模型状态；撤回授权时内容受限');
e('post','/runs/{run_id}/help','help','NewHelp','Help',L,'分级帮助；live 帮助复用预算/unknown 引擎',202);
e('get','/runs/{run_id}/help','helps',null,'Helps',L,'本人帮助记录；不含他人私聊');
e('post','/runs/{run_id}/artifacts','createArtifact','NewArtifact','Artifact',L,'显式保存首个结构化作品版本',201);
e('get','/learners/{learner_id}/artifacts','artifacts',null,'Artifacts',ML,'本人或经授权家长的已保存作品');
e('get','/artifacts/{artifact_id}','artifact',null,'Artifact',[...ML,...R],'当前作品，最小授权投影');
e('post','/artifacts/{artifact_id}/versions','versionArtifact','NewArtifactVersion','Artifact',L,'不可变版本；旧检查不自动继承',201);
e('post','/runs/{run_id}/checks','checkArtifact','NewCheck','Check',L,'规则检查或创建有负责人案件',201);
e('get','/checks/{check_id}','check',null,'Check',[...ML,...R],'检查版本、结果与补练反馈');
e('post','/runs/{run_id}/reflections','reflect','NewReflection','Reflection',L,'保存解释、改动与迁移引用',201);
e('post','/runs/{run_id}/cases','askHuman','NewCase','Case',L,'按值班配置请求人工，未配置则503',201);
e('get','/cases','cases',null,'Cases',['learner','staff'],'本人案件或 scope 内待分配/已分配案件；无全局私聊');
e('get','/cases/{case_id}','case',null,'Case',['learner','staff'],'本人公开状态或分配工作人员最小案卷');
e('post','/cases/{case_id}/claim','claimCase','Claim','Case',['eligible:staff'],'原子认领 scope 与班期内案件');
e('post','/cases/{case_id}/transfer','transferCase','Transfer','Case',['assigned:staff'],'转交有资格工作人员，保留原截止时间');
e('post','/cases/{case_id}/resolve','resolveCase','ResolveCase','Case',['assigned:relationship_review',...R,...S],'按 case kind 校验决议枚举，报告另走reviews');
e('post','/runs/{run_id}/reports','createReport','NewReport','Report',L,'固定证据生成草稿，不重跑孩子实验',202);
e('get','/reports/{report_id}','report',null,'Report',['learner','manager:published_only','assigned:report_review','assigned:report_publish'],'草稿与已发布按角色投影，不暴露原始私聊');
e('post','/reports/{report_id}/disputes','disputeReport','Dispute','DisputeRecord',L,'本人事实异议，发布前必须处理',201);
e('post','/reports/{report_id}/submit-review','submitReport','SubmitReview','Report',L,'本人核对后创建复核案件');
e('post','/reports/{report_id}/reviews','reviewReport','ReviewReport','Report',['assigned:report_review'],'引用校验后审核固定版本');
e('post','/reports/{report_id}/publications','publishReport','PublishReport','Publication',['assigned:report_publish'],'审批、来源、同意原子核对后发布',201);
e('post','/reports/{report_id}/revocations','revokeReport','Reason','Report',['manager','assigned:report_publish'],'撤回后停止后续家长访问');
e('get','/learners/{learner_id}/reports','reports',null,'Reports',['learner','manager:published_only'],'学习报告列表，不合并比赛结果');
e('get','/learners/{learner_id}/usage','usage',null,'Usage',ML,'孩子仅用量状态投影，成人额度明细');
e('get','/reconciliation-cases/{case_id}','reconciliation',null,'Reconciliation',['assigned:usage_reconcile'],'未知用量核对案');
e('post','/reconciliation-cases/{case_id}/resolve','resolveReconciliation','ResolveReconciliation','Reconciliation',['assigned:usage_reconcile'],'凭证据结算或有审计调整，不声称未知成本零');

// Cross-read S01/S02 0.1.0: explicit evidence revisions, first-stage checks without an artifact.
put('EvidenceRef',{id,revision:int});
put('HelpDisclosure',{kind:en('none_reported','reading_or_operation','adult_transcription','adult_content','peer_content','ai_content','example_reference','unknown'),note:{type:'string',maxLength:300},child_confirmed:bool,example_source_ids:arr(id)});
schemas.HelpDisclosure.allOf=[{if:{properties:{kind:{const:'example_reference'}}},then:{properties:{example_source_ids:{minItems:1}}}}];
put('FactSelection',{event_name:{...str,maxLength:120},audience:{...str,maxLength:200},date:id,start_time:id,end_time:id,place:{...str,maxLength:200},preparation:{...str,maxLength:200}});
put('Requirements',{...stamp,run_id:id,material_version_id:id,facts:ref('FactSelection'),purpose:{...str,maxLength:120},expression_preference:{...str,maxLength:120},source_locators:arr(id),confirmed:bool,help_disclosure:ref('HelpDisclosure'),parent_revision:int});
req('SaveRequirements',{material_version_id:id,facts:ref('FactSelection'),purpose:{...str,maxLength:120},expression_preference:{...str,maxLength:120},source_locators:arr(id),confirmed:bool,help_disclosure:ref('HelpDisclosure')});
put('SelfCheck',{...stamp,run_id:id,artifact_version_id:id,field:en('audience','date','start_time','end_time','place','preparation','invitation_line'),source_locator:id,judgement:en('matches','differs','unsure'),reason:{...str,maxLength:300},help_disclosure:ref('HelpDisclosure'),parent_revision:int});
req('NewSelfCheck',{artifact_version_id:id,field:en('audience','date','start_time','end_time','place','preparation','invitation_line'),source_locator:id,judgement:en('matches','differs','unsure'),reason:{...str,maxLength:300},help_disclosure:ref('HelpDisclosure')});
put('Readback',{...stamp,artifact_version_id:id,receipt_id:id,received_at:time,parent_revision:int});
req('ReadbackRequest',{read_receipt_id:id});
put('VersionRead',{artifact_version:ref('ArtifactVersion'),read_receipt_id:id,artifact_revision:int});
put('TransferResponse',{facts:ref('FactSelection'),purpose:{...str,maxLength:120},expression_preference:{...str,maxLength:120},invitation_line:{...str,maxLength:160},changes:{...arr(obj({field:id,explanation:{...str,maxLength:300},source_locator:id})),minItems:2},help_disclosure:ref('HelpDisclosure')});
for(const name of ['Attempt','NewAttempt','EditAttempt']) {
  Object.assign(schemas[name].properties,{task_id:id,requirements_ref:nil(ref('EvidenceRef')),transfer_response:nil(ref('TransferResponse'))});
  schemas[name].required.push('task_id','requirements_ref','transfer_response');
}
for(const name of ['Reflection','NewReflection']) {
  schemas[name].properties.transfer_attempt_revision=int;
  schemas[name].properties.self_check_ref=ref('EvidenceRef');
  schemas[name].properties.help_disclosure=ref('HelpDisclosure');
  schemas[name].required.push('transfer_attempt_revision','self_check_ref','help_disclosure');
}
schemas.NewArtifactVersion.properties.previous_artifact_version_id=id;
schemas.NewArtifactVersion.properties.change_intent={...str,maxLength:300};
schemas.NewArtifactVersion.properties.help_disclosure=ref('HelpDisclosure');
schemas.NewArtifactVersion.required.push('previous_artifact_version_id','change_intent','help_disclosure');
for(const name of ['Check','NewCheck']) {
  schemas[name].properties.artifact_version_id=nil(id);
  Object.assign(schemas[name].properties,{stage,requirements_ref:ref('EvidenceRef'),self_check_ref:nil(ref('EvidenceRef')),reflection_ref:nil(ref('EvidenceRef')),transfer_attempt_ref:nil(ref('EvidenceRef')),readback_ref:nil(ref('EvidenceRef'))});
  schemas[name].required.push('stage','requirements_ref','self_check_ref','reflection_ref','transfer_attempt_ref','readback_ref');
}
delete schemas.NewCheck.properties.reflection_id;
delete schemas.NewCheck.properties.transfer_attempt_id;
schemas.NewCheck.required=schemas.NewCheck.required.filter(x=>!['reflection_id','transfer_attempt_id'].includes(x));
put('ManualFinding',{rubric_id:en('M1','M2','M3','M4'),verdict:en('supported','needs_practice','unclear'),source_ids:{...arr(id),minItems:1},note:{...str,maxLength:300}});
schemas.ResolveCase.properties.decision=en('verified','rejected','passed','needs_practice','answered','needs_information');
schemas.ResolveCase.properties.manual_findings=arr(ref('ManualFinding'));
schemas.ResolveCase.required.push('manual_findings');
put('CaseEvidence',{case_id:id,target_revision:int,sources:arr(obj({ref:ref('Source'),redacted_text:str,visibility:en('assigned_reviewer_only')}))});
req('ExtendCase',{new_due_at:time,reason:str});
req('AppendCase',{message:str,source_ids:arr(id)});
e('get','/runs/{run_id}/requirements','requirements',null,'Requirements',L,'当前要求版本，首次为空时返回404供建草稿');
e('put','/runs/{run_id}/requirements','saveRequirements','SaveRequirements','Requirements',L,'保存/本人确认要求，首次expected_revision=0');
e('post','/runs/{run_id}/self-checks','selfCheck','NewSelfCheck','SelfCheck',L,'保存本人材料定位和判断',201);
e('get','/artifacts/{artifact_id}/versions/{version_id}','readVersion',null,'VersionRead',[...ML,...R],'指定不可变版本及不证明理解的短时回读凭据');
e('post','/artifacts/{artifact_id}/readbacks','readback','ReadbackRequest','Readback',L,'确认本人已取回同版本；回读凭据绑定会话和版本',201);
e('get','/cases/{case_id}/evidence','caseEvidence',null,'CaseEvidence',['assigned:relationship_review',...R,'assigned:report_review','assigned:report_publish',...S],'案件最小材料，不泄漏其他孩子/完整私聊');
e('post','/cases/{case_id}/extensions','extendCase','ExtendCase','Case',['assigned:staff'],'按策略延期待办，保留原期限与审计并告知本人');
e('post','/cases/{case_id}/messages','appendCase','AppendCase','Case',['learner','assigned:staff'],'本人补充已有求助，不重复建案');
put('Material',{id,version:id,source_type:{type:'string',const:'fictional_course_material'},facts:ref('FactSelection'),notice:str,source_locators:arr(id)});
e('get','/courses/{course_version_id}/materials/{material_id}','material',null,'Material',['learner','assigned:learning_review','assigned:report_review'],'仅当前任务获准材料；不返回reviewer_only标准答案');
e('get','/self-checks/{self_check_id}','getSelfCheck',null,'SelfCheck',L,'刷新后取回本人自查记录');
e('get','/reflections/{reflection_id}','getReflection',null,'Reflection',L,'刷新后取回解释及迁移引用');
for(const key of ['current_attempt_ref','current_requirements_ref','current_self_check_ref','current_reflection_ref','current_transfer_attempt_ref']) {
  schemas.Run.properties[key]=nil(ref('EvidenceRef')); schemas.Run.required.push(key);
}
for(const key of ['current_artifact_id','active_model_run_id']) {schemas.Run.properties[key]=nil(id);schemas.Run.required.push(key);}
// Requirements can be saved incomplete; completeness is checked at confirmation/check time.
for(const [key,value] of Object.entries(schemas.FactSelection.properties)) schemas.FactSelection.properties[key]={...value,minLength:0};
for(const name of ['Requirements','SaveRequirements']) for(const key of ['purpose','expression_preference']) schemas[name].properties[key].minLength=0;
// Required capabilities are a projection of actual authorization, never a grant.
for(const name of ['Home','Run','Attempt','Artifact','Check','Report','Case']) {
  schemas[name].properties.allowed_actions=arr(id); schemas[name].required.push('allowed_actions');
}
schemas.Home.properties.missing_fields=arr(id); schemas.Home.required.push('missing_fields');
for(const name of ['Attempt','Requirements','Artifact','Reflection','SelfCheck']) {
  schemas[name].properties.saved_at=time; schemas[name].required.push('saved_at');
}
schemas.NewCase.properties.source_ids=arr(id); schemas.NewCase.properties.reason_category=en('task_unclear','operation_help','service_problem','other');
schemas.NewCase.required.push('source_ids','reason_category');
schemas.Case.properties.support_contact_label=str; schemas.Case.required.push('support_contact_label');
// Staff receive explicit learner/case targets; unpublished raw prompt history is never returned.
schemas.Case.properties.learner_id=id; schemas.Case.required.push('learner_id');
for(const name of ['NewArtifact','NewArtifactVersion','ArtifactVersion']) {
  schemas[name].properties.attempt_revision=int; schemas[name].required.push('attempt_revision');
  schemas[name].properties.template_version_id=id; schemas[name].required.push('template_version_id');
  schemas[name].properties.authorship=en('child_edit','ai_candidate_unedited','ai_candidate_edited','adult_transcription');
  schemas[name].properties.help_disclosure=ref('HelpDisclosure');
  if(!schemas[name].required.includes('help_disclosure'))schemas[name].required.push('help_disclosure');
}
for(const name of ['Attempt','NewAttempt','EditAttempt','Reflection','NewReflection']) {
  delete schemas[name].properties.declared_help;schemas[name].required=schemas[name].required.filter(x=>x!=='declared_help');
  schemas[name].properties.help_disclosure=ref('HelpDisclosure');if(!schemas[name].required.includes('help_disclosure'))schemas[name].required.push('help_disclosure');
}
for(const name of ['NewHelp','Help']) {schemas[name].properties.task_id=id;schemas[name].properties.task_card_version=id;schemas[name].required.push('task_id','task_card_version');}
schemas.ReviewReport.properties.corrected_observations.minItems=1;
schemas.NewModelRun['x-business-rules']=['mode=replay必须给replay_of；mock/live必须为null','固定当前attempt输入、requirements_ref、material版本与授权；不得使用运行后修改的输入','存在pending/running/unknown时不能换request_id重复发出'];
schemas.NewCheck.properties.purpose=en('preflight','advance','submit_review'); schemas.NewCheck.required.push('purpose');
schemas.NewCheck.properties.requirements_ref=nil(ref('EvidenceRef'));
const submitRefs={requirements_ref:ref('EvidenceRef'),artifact_version_id:id,self_check_ref:ref('EvidenceRef'),reflection_ref:ref('EvidenceRef'),transfer_attempt_ref:ref('EvidenceRef'),readback_ref:ref('EvidenceRef')};
schemas.NewCheck.allOf=[
 {if:{properties:{purpose:{const:'advance'}}},then:{properties:{stage:en('clarify','create'),requirements_ref:ref('EvidenceRef')}}},
 {if:{properties:{purpose:{const:'submit_review'}}},then:{properties:{stage:{const:'review'},...submitRefs}}},
 {if:{properties:{purpose:{const:'advance'},stage:{const:'create'}}},then:{properties:{artifact_version_id:id,readback_ref:ref('EvidenceRef')}}}
];
Object.assign(schemas.Check.properties,{purpose:en('preflight','advance','submit_review'),rule_result:en('pass','needs_practice','incomplete','unknown'),requirements_ref:nil(ref('EvidenceRef')),evidence_complete:bool,model_state:en('none','pending','running','succeeded','failed','unknown'),reviewer_available:nil(bool),progress_effect:en('none','passed_and_unlocked','needs_practice','pending_review'),outcome:en('feedback_only','advanced','needs_practice','blocked_evidence','blocked_unknown','blocked_support','awaiting_review')});
schemas.Check.required.push('purpose','evidence_complete','model_state','reviewer_available','progress_effect','outcome');
schemas.Check.allOf=[
 {if:{properties:{purpose:{const:'preflight'}}},then:{properties:{case_id:{type:'null'},human_result:{type:'null'},reviewer_available:{type:'null'},progress_effect:{const:'none'},outcome:{const:'feedback_only'}}}},
 {if:{properties:{purpose:{const:'advance'}}},then:{properties:{stage:en('clarify','create'),case_id:{type:'null'},progress_effect:en('none','needs_practice','passed_and_unlocked')}}},
 {if:{properties:{purpose:{const:'submit_review'}}},then:{properties:{stage:{const:'review'},progress_effect:en('none','needs_practice','pending_review')}}},
 {if:{properties:{progress_effect:{const:'passed_and_unlocked'}}},then:{properties:{purpose:{const:'advance'},rule_result:{const:'pass'},evidence_complete:{const:true},model_state:en('none','succeeded'),outcome:{const:'advanced'}}}},
 {if:{properties:{progress_effect:{const:'passed_and_unlocked'},stage:{const:'create'}}},then:{properties:{model_state:{const:'succeeded'}}}},
 {if:{properties:{progress_effect:{const:'pending_review'}}},then:{properties:{purpose:{const:'submit_review'},case_id:id,rule_result:{const:'pass'},evidence_complete:{const:true},model_state:{const:'succeeded'},reviewer_available:{const:true},outcome:{const:'awaiting_review'}}},else:{properties:{case_id:{type:'null'}}}},
 {if:{properties:{model_state:en('unknown','pending','running')}},then:{properties:{rule_result:{const:'unknown'},progress_effect:{const:'none'},case_id:{type:'null'},outcome:en('feedback_only','blocked_unknown')}}},
 {if:{properties:{outcome:{const:'blocked_support'}}},then:{properties:{purpose:{const:'submit_review'},reviewer_available:{const:false},progress_effect:{const:'none'},case_id:{type:'null'}}}}
];
schemas.NewCheck['x-business-rules']=['preflight可缺证据，仅冻结规则反馈；永不派单、标通过或解锁','advance仅clarify/create；当前证据校验与check/阶段passed/下游available/审计在同一事务，预检通过不能替代该动作','submit_review仅review；当前R01-R08齐备、模型succeeded且值班可用才能建唯一人工案；否则仅保存阻塞反馈','unknown/pending/running保持等待与预算核对，不记录学习失败或自动重试；实际缺失/过期证据须服务端检查'];
schemas.SaveStart['x-business-rules']=['PATCH仅合并answers中的主题；缺失保持原值，unanswered/null显式清空，skipped/null显式暂不答','首次expected_revision=0；不接收completion/recommendation等客户端权威字段','accepted_default仅chosen_start允许，必须单独提交且recommendation_revision等于expected_revision及服务端当前推荐版本；value必须等于该版本推荐','未答/跳过不自动变成answered；effective_start兜底guided不写回chosen_start/help_preference','missing_fields仅列unanswered；completed只指全部主题有回答或明确跳过，不表示掌握；推荐只依据当前非空已答字段，静态小尝试无需模型'];
schemas.ResolveCase['x-business-rules']=['relationship案只允许verified/rejected且操作者具relationship_review','learning_review案允许passed/needs_practice/needs_information；passed必须M1-M4各一条supported且source_ids有效','needs_information持久保存已填/unclear分项，案件保持claimed不结案、不改变过关；其余分项可后续补齐','support案只允许answered；report_review禁止走此入口，必须走reports/reviews','target_revision必须与案件冻结目标当前版本一致'];
schemas.ResolveCase.allOf=[{if:{properties:{decision:{const:'passed'}}},then:{properties:{manual_findings:{minItems:4,maxItems:4,items:{properties:{verdict:{const:'supported'}}},allOf:['M1','M2','M3','M4'].map(rubric=>({contains:{properties:{rubric_id:{const:rubric}}},minContains:1,maxContains:1}))}}}}];
schemas.Check.allOf.push(
 {if:{properties:{evidence_complete:{const:false}}},then:{properties:{progress_effect:{const:'none'},case_id:{type:'null'}}}},
 {if:{properties:{outcome:{const:'advanced'}}},then:{properties:{progress_effect:{const:'passed_and_unlocked'}}}},
 {if:{properties:{outcome:{const:'awaiting_review'}}},then:{properties:{progress_effect:{const:'pending_review'}}}},
 {if:{properties:{purpose:{const:'submit_review'},evidence_complete:{const:true},model_state:{const:'succeeded'},rule_result:{const:'pass'},reviewer_available:{const:false}}},then:{properties:{outcome:{const:'blocked_support'},progress_effect:{const:'none'}}}},
 {if:{properties:{purpose:{const:'submit_review'},evidence_complete:{const:true},model_state:{const:'succeeded'},rule_result:{const:'pass'},reviewer_available:{const:true}}},then:{properties:{outcome:{const:'awaiting_review'},progress_effect:{const:'pending_review'}}}}
);
schemas.SaveRequirements['x-business-rules']=['confirmed=false允许不完整草稿；confirmed=true须全部事实、定位、目的/偏好齐备','首次expected_revision=0，后续为requirements聚合revision；修订并递增run revision'];
// blank drafts are legitimate; individual stage submission validates completeness separately.
for(const name of ['Attempt','NewAttempt','EditAttempt']) schemas[name].properties.input_text={type:'string',maxLength:8000};

// Role projections are explicit schemas, not promises to filter undefined fields.
put('LearnerSelf',{id,revision:int,display_name:{...str,maxLength:60},age_band:nil(id)});
put('UsageChild',{status:en('available','exhausted','held_for_review','unconfigured'),notice:str});
for(const p of ['/learners/{learner_id}/profile']) paths[p].get.responses['200'].content['application/json'].schema={oneOf:[ref('Learner'),ref('LearnerSelf')]};
paths['/learners/{learner_id}/usage'].get.responses['200'].content['application/json'].schema={oneOf:[ref('Usage'),ref('UsageChild')]};
// Model output metadata returns usage state only; cost projection uses the separate adult endpoint.
schemas.ModelRun.properties.usage=ref('UsageChild');
put('CaseStaff',{...schemas.Case.properties,assignee_id:nil(id),evidence:arr(ref('Source')),target_revision:int});
paths['/cases/{case_id}'].get.responses['200'].content['application/json'].schema={oneOf:[ref('Case'),ref('CaseStaff')]};

const openapi={openapi:'3.1.0',info:{title:'松伴 Learning v2 — P0 提案（未注册）',version:'0.2.1',description:'仅规格；权限、条件与事务以接口与迁移规格.md为准。schema 通过不等于业务校验通过。'},servers:[{url:'/api/learning/v2',description:'拟议前缀，不宣称可调用'}],paths,components:{securitySchemes:{ScopedSession:{type:'apiKey',in:'cookie',name:'__Host-songban_session',description:'HttpOnly/Secure/SameSite=Strict；写操作另验 CSRF 与 Origin，旧 Bearer 不接受。'}},schemas},'x-implementation-status':'not_registered','x-source-head':'0cf710280869bb920120675b727e543319ea0b88'};
const unknownHelp={kind:'unknown',note:'暂时不确定之前是否有人提供内容。',child_confirmed:true,example_source_ids:[]};
const noReportedHelp={kind:'none_reported',note:'本人当前未报告帮助；不证明线下无人帮助。',child_confirmed:true,example_source_ids:[]};
const initialAnswers=Object.fromEntries(startFields.map(k=>[k,{state:'unanswered',value:null}]));
const firstStartRequest={request_id:'fixture-start-first',expected_revision:0,answers:{age_band:{state:'skipped',value:null}}};
const restoredStart={id:'start-fixture',revision:1,learner_id:'learner-fixture',answers:{...initialAnswers,age_band:{state:'skipped',value:null}},completion_status:'draft',mini_attempt_status:'not_attempted',recommendation:'guided',recommendation_basis:'insufficient_evidence',recommendation_revision:1,recommendation_rule_version:'fixture-start-rules@0.2.0',recommendation_source_fields:[],missing_fields:startFields.filter(k=>k!=='age_band'),skipped_fields:['age_band'],effective_start:'guided',effective_start_source:'conservative_fallback',saved_at:'2026-11-02T08:00:00Z'};
const reviewPreflight={id:'check-preflight-fixture',revision:1,run_id:'run-fixture',learner_id:'learner-fixture',lesson_version_id:'class-activity-invitation@0.1.0',artifact_version_id:'artifact-version-2',rubric_version_id:'invitation-rubric@0.1.0',rule_result:'incomplete',human_result:null,missing_evidence:['reflection_ref','transfer_attempt_ref'],feedback:['自查已保存，完成小迁移后可再提交老师。'],case_id:null,evidence_hash:'fixture-evidence-hash',stale:false,parent_revision:9,stage:'review',requirements_ref:{id:'req-fixture',revision:1},self_check_ref:{id:'self-fixture',revision:1},reflection_ref:null,transfer_attempt_ref:null,readback_ref:{id:'readback-fixture',revision:1},allowed_actions:['reflect'],purpose:'preflight',evidence_complete:false,model_state:'succeeded',reviewer_available:null,progress_effect:'none',outcome:'feedback_only'};
const reviewPreflightRequest={request_id:'fixture-preflight-01',expected_revision:8,purpose:'preflight',lesson_version_id:reviewPreflight.lesson_version_id,artifact_version_id:reviewPreflight.artifact_version_id,rubric_version_id:reviewPreflight.rubric_version_id,stage:'review',requirements_ref:reviewPreflight.requirements_ref,self_check_ref:reviewPreflight.self_check_ref,reflection_ref:null,transfer_attempt_ref:null,readback_ref:reviewPreflight.readback_ref};
const consentTextPayload={locale:'zh-CN',title:'学习用途授权文本（研发草案，未获真实试点批准）',text:'此文本仅供研发审阅。拟议用途包括保存本人的学习过程、按明确选择使用受控模型，以及向获准家长展示整理摘要与经复核报告。具体数据范围、保留期限、撤回处理和责任方仍须由产品与实际负责人确认；当前文本不可用于真实家庭授权。',scope_purposes:[{scope:'learning',purpose:'拟保存该学习者的任务、尝试和作品，以支持学习恢复。'},{scope:'live_model',purpose:'拟将本次必要输入交给已配置的受控模型；供应商和预算尚待批准。'},{scope:'parent_summary',purpose:'拟向有效关联家长展示本人学习摘要，不开放其他孩子或完整私聊。'},{scope:'report_publication',purpose:'拟在人工复核后向有效关联家长发布指定报告快照。'}]};
const consentTextExample={consent_version:'fixture-consent-draft@0.2.1',...consentTextPayload,text_sha256:crypto.createHash('sha256').update(JSON.stringify(consentTextPayload)).digest('hex'),approval_status:'draft',approved_at:null,acceptance_enabled:false,notice:'研发草案，未获真实试点批准；只展示文本，不提供正式授权确认。'};
const familiesExample={items:[{id:'family-fixture',revision:2,learners:[{id:'learner-fixture',revision:1,family_id:'family-fixture',display_name:'虚构学习者',age_band:null,guardian_link:{id:'link-fixture',revision:1,learner_id:'learner-fixture',status:'verified',declared_relationship:'协议测试声明',verification_method:'fixture_only'}}]}],next_cursor:null};
const consentsExample={learner_id:'learner-fixture',relationship_status:'verified',visibility:'linked_learner',items:[{id:'consent-fixture',revision:1,learner_id:'learner-fixture',consent_version:consentTextExample.consent_version,scopes:['learning'],status:'active',recorded_at:'2026-11-02T08:00:00Z',text_sha256:consentTextExample.text_sha256,effective_scopes:[]}],next_cursor:null};
const examples=[
 {name:'清空本地缓存并新鲜认证后，GET发现本人唯一家庭（全部虚构）',operation_id:'listFamilies',response:familiesExample},
 {name:'从家庭里的learner_id读取授权ID/revision/范围；测试草案记录不生效',operation_id:'listConsents',response:consentsExample},
 {name:'按授权记录的consent_version读取确切文本，不把研发草案当获批文件',operation_id:'consentText',response:consentTextExample},
 {name:'pending关系仅查询本人曾提交记录，没有则返回空列表',operation_id:'listConsents',response:{learner_id:'learner-fixture',relationship_status:'pending',visibility:'own_submissions',items:[],next_cursor:null}},
 {name:'第三关先预检，迁移未完成也可获取规则反馈且不派单',operation_id:'checkArtifact',request:reviewPreflightRequest,response:reviewPreflight},
 {name:'首步只选择暂不填年龄，其他主题未答；响应也是后续GET恢复快照',operation_id:'saveStart',request:firstStartRequest,response:restoredStart},
 {name:'明确选择系统推荐与系统兜底分开',operation_id:'saveStart',request:{request_id:'fixture-start-default',expected_revision:1,answers:{chosen_start:{state:'accepted_default',value:'guided',recommendation_revision:1}}}},
 {name:'静态小尝试明确跳过，不伪造答案',operation_id:'saveStart',request:{request_id:'fixture-start-skip',expected_revision:1,answers:{mini_attempt_text:{state:'skipped',value:null}}}},
 {name:'第一关正式推进不伪造作品ID',operation_id:'checkArtifact',request:{request_id:'fixture-gate1-001',expected_revision:2,purpose:'advance',lesson_version_id:'class-activity-invitation@0.1.0',artifact_version_id:null,rubric_version_id:'invitation-rubric@0.1.0',stage:'clarify',requirements_ref:{id:'requirements-fixture',revision:1},self_check_ref:null,reflection_ref:null,transfer_attempt_ref:null,readback_ref:null}},
 {name:'保存邀请卡输入，未知帮助不当无人帮助',operation_id:'saveAttempt',request:{request_id:'fixture-save-0001',expected_revision:1,input_text:'请依据MAT_A为故事交换会写邀请。',help_disclosure:unknownHelp,task_id:'S2.1',requirements_ref:{id:'req-fixture',revision:1},transfer_response:null}},
 {name:'受控生成协议样例，不调用供应商',operation_id:'createModelRun',request:{request_id:'fixture-model-001',expected_revision:2,mode:'mock',config_version:'fixture-text-v1',replay_of:null}},
 {name:'作品显式保存，日期地点为虚构教学资料',operation_id:'createArtifact',request:{request_id:'fixture-artifact-1',expected_revision:4,attempt_id:'attempt-fixture',attempt_revision:2,template_version_id:'invitation-fixed@0.1.0',model_run_id:'model-fixture',help_event_ids:[],help_disclosure:noReportedHelp,authorship:'ai_candidate_unedited',content:{title:'一起分享故事',audience:'松果班同学',date:'2030-05-18',start_time:'14:00',end_time:'15:00',place:'松果活动室',preparation:'带一本愿意分享的故事书',invitation_line:'带上你的故事书，一起分享吧。'}}},
 {name:'结果未知不自动重试',schema:'ModelRun',response:{id:'model-unknown',revision:3,attempt_id:'attempt-fixture',report_id:null,help_event_id:null,mode:'live',status:'unknown',requested_model:null,actual_model:null,config_version:'unconfigured-example',input_revision:2,output_text:null,reservation_id:'reserve-fixture',usage:{status:'held_for_review',notice:'这次结果还在核对，你写的内容已保存。'},reconciliation_case_id:'case-fixture',visibility:'normal',parent_revision:3}},
 {name:'版本冲突保留本地输入',schema:'Error',response:{error:{code:'revision_conflict',message:'内容已在另一个窗口更新，请先核对新版。',retryable:false,recovery:'merge',current_revision:4}}},
 {name:'人工报告审核不等于发布',operation_id:'reviewReport',request:{request_id:'fixture-review-001',expected_revision:2,decision:'approved',source_hash:'fixture-source-hash',corrected_observations:[{text:'孩子把邀请里的地点补充完整；此观察只针对本次作品。',source_ids:['artifact-version-2'],nature:'system_record'}],note:'已核对修改与帮助记录。',resolved_dispute_ids:[]}},
 {name:'无计费证据不能按零元结案',operation_id:'resolveReconciliation',request:{request_id:'fixture-adjust-01',expected_revision:2,resolution:'administrative_adjustment',evidence_ids:['manual-review-record'],settled_units:null,adjustment_units:1,reason:'仅示意授权调整，实际费用仍未知。'}}
];
const scenarios=[
 ['RECOVERY-01','G1','建立两个隔离家庭后清空localStorage/sessionStorage并重新登录manager；从GET families取本人家庭/learner，再GET consents及对应consent-texts；另测pending、孩子、staff未分配和跨家庭ID','仅恢复本人至多一个家庭及获准consent_id/revision/scopes；pending只看本人记录，孩子/越权不得读成人管理；草案禁止正式确认，历史文本按版本匹配，GET不新建家庭或授权'],
 ['START-01','G1','新用户只提交年龄主题后刷新GET start，其余主题从未回答','PATCH只改该主题；其余unanswered/null，missing_fields可恢复，不伪造帮助偏好/小尝试/本人选择'],
 ['START-02','G1','分别省略主题、显式unanswered清空、skipped跳过和answered回答','缺失保留；清空和跳过独立留痕；null/空串不能冒充已答；完成状态由服务器计算'],
 ['START-03','G1','只看系统guided推荐，随后明确accepted_default；提交过期推荐版本','默认兜底不写chosen_start；明确点击才记录采纳，过期返回409不覆盖'],
 ['START-04','G1','小尝试跳过、部分草稿、答完后模拟模型故障','草稿不丢；推荐依据如实，静态小尝试不因模型故障变未完成，问卷完成不等于掌握'],
 ['CHECK-01','G2','review预检缺迁移/有完整证据/无值班均尝试，包括重试','仅保存规则反馈；绝不建人工案、不改阶段passed、不解锁；同请求幂等'],
 ['CHECK-02','G2','clarify/create分别preflight成功后显式advance，同时修改要求版本','仅advance可事务推进；预检不解锁；版本竞争409，无半次推进'],
 ['CHECK-03','G2','review submit_review，分别缺证据、无值班、完整且有值班','缺证据或无值班无案件/无pending_review；完整且可接案才唯一建案并原子变pending_review'],
 ['CHECK-04','G2','模型unknown/pending/running时预检、推进或送审','反馈保留unknown等待，无派单/假失败/通过，预算保持核对且不重跑'],
 ['HELP-01','G2','原样采用AI候选、成人内容帮助、参考示例、帮助unknown分别保存回读','原样不是child_edit；各来源保留，unknown不是none_reported；示例引用需真实获准来源'],
 ['REVIEW-01','G3','老师保存M3 unclear并补问，再补齐M1-M4；重复/缺项或unclear尝试passed','needs_information保存分项且案件保持claimed；仅四项各一条supported并核验当前证据才过关'],
 ['AUTH-01','G1','两个家庭分别尝试读写对方 learner/attempt/artifact/report，含混合归属ID','统一404，未读写任何跨家庭内容'],
 ['AUTH-02','G1','manager 切 learner，使用旧 Bearer、旧 cookie、旧标签调用 v2/旧 core/recap/workbench/account','旧凭证401；child cookie旧账号API403；无新管理副作用'],
 ['AUTH-03','G1','暂停旧写入在认证后，先提交 enter-learner 再恢复旧写入','提交时 fence拒绝；audit无越权写入；旧调用已发则仅受限归档'],
 ['AUTH-04','G1','旧读取响应与cookie轮换迟到，另标签bfcache恢复','epoch失配丢弃；旧cookie已撤销；GET session恢复，不能升权'],
 ['AUTH-05','G1','篡改 role/scopes/learner_id，用sbconn_/v1 session/分享token换家庭授权','拒绝；client字段不能授予scope'],
 ['AUTH-06','G1','跨Origin写入/缺CSRF/旧token exchange/孩子经旧login旁路','拒绝；显式新鲜重新认证成功后才进入管理'],
 ['AUTH-07','G1','关系pending、consent撤回、权益过期与在途调用/报告读取竞态','校验最新授权；拒绝新调用，撤销派生访问，保留账本'],
 ['WRITE-01','G2','并发同request_id同正文、同ID异正文、过期revision','只产生一个资源；异正文409；冲突保留用户输入'],
 ['FLOW-01','G2','无squad/比赛/连接器完整三关；有经验者调整起点','可以独立完成；不生成虚构小队、不强制比赛入门'],
 ['FLOW-02','G2','修改已检查作品，并发人工通过旧check','旧事实保留，新版recheck_required；旧审核不解锁新版本'],
 ['FLOW-03','G2','无迁移/解释/人工帮助记录，客户端强写passed','拒绝或补练；AI建议不等于掌握'],
 ['FLOW-04','G2','保存/检查事务各阶段中断、刷新、重登、SQLite写锁','原子落盘或无副作用，按服务器事实恢复'],
 ['MODEL-01','G3','两个请求争抢最后预算、同尝试换request_id绕unknown','至多一次预占/派发，余额非负，unknown阻塞绕行'],
 ['MODEL-02','G3','dispatch标记前/后进程退出、lease到期、多worker接管','发送前可恢复；可能发送后unknown，不第二次发出'],
 ['MODEL-03','G3','超时后账单/迟到响应/人工核对同时到达','结算唯一；冲突进差异案件；未知成本仍null'],
 ['MODEL-04','G3','mock/live/replay以及模型未提供实际名字','模式可辨；actual_model=null；replay不重新付费'],
 ['MODEL-05','G3','无供应商/费用配置/预算/核对负责人或截止时间','live拒绝配置不足，已保存输入不丢'],
 ['ROLE-01','G3','四角色读其他孩子来源、检索中注入执行命令','归属拒绝；输出白名单，不能改权限/过关/预算'],
 ['REPORT-01','G3','引用不存在来源、队友私聊、未检查作品、重复生成','拒绝或保留失败草稿；不重跑孩子实验'],
 ['REPORT-02','G3','未审核、过期审核、未结异议、跨范围发布','禁止发布；通过固定revision/hash审核后才能发布'],
 ['REPORT-03','G3','家长读draft、撤销后读取、同意撤回与发布竞态','无未发布数据；撤销后失效；发布与撤回原子排序'],
 ['HUMAN-01','G3','案件无排班、重复认领、越scope转交、到期升级','未配置503；仅一次认领；有责任人与可见出口'],
 ['COMPAT-01','G4','v1原样例API、所有旧比赛哈希、两报告、三工作台角色','原语义保留；new v2不会覆盖旧注册和记录'],
 ['COMPAT-02','G4','方向/投票/全员分工/内部AI发布/本人任务/同伴检查顺序','新学习进度不改变原团队权威'],
 ['ROLLBACK-01','G4','关闭三个开关，已有unknown与已撤销session，旧导航恢复','停新派发，继续核对和历史读取；不恢复旧token/删账本'],
 ['MIGRATE-01','G4','增量迁移失败、重复执行、备份恢复，含原报告/比赛数据','整批回滚/版本校验；旧行保持，未知调用不重放']
].map(([id,gate,setup,expected])=>({id,gate,setup,expected,status:'not_run',implementation_test:'待S00登记隔离测试文件'}));
const uiActions=[
 ['UIA-01',['session','home','getProfile','courses','artifacts']],['UIA-02',['home','createRun','run']],['UIA-03',['getStart','saveStart']],
 ['UIA-04',['requirements','saveRequirements','createAttempt','saveAttempt']],['UIA-05',['createModelRun','modelRun']],['UIA-06',['help','helps','course','material']],
 ['UIA-07',['createArtifact','versionArtifact','readVersion','readback']],['UIA-08',['selfCheck','getSelfCheck','checkArtifact','check','run']],['UIA-09',['createAttempt','saveAttempt','reflect','getReflection']],
 ['UIA-10',['run','artifact','check']],['UIA-11',['askHuman','cases','case','appendCase']],['UIA-12',['enterLearner','session']],
 ['UIA-13',['bootstrap','authenticate','listFamilies','getFamily','listConsents','home','reports']],['UIA-14',['config','listFamilies','createFamily','createLearner','getFamily','listConsents','consentText','createConsent','revokeConsent']],
 ['UIA-15',['artifacts','readVersion','reports','report']],['UIA-16',['cases','case','caseEvidence','claimCase','transferCase','extendCase','resolveCase']],
 ['UIA-17',['createReport','disputeReport','submitReport','reviewReport','publishReport','revokeReport']],['UIA-18',['home','enroll','usage']]
].map(([ui_action,operation_ids])=>({ui_action,operation_ids,status:ui_action==='UIA-18'?'entitlement_read_and_existing_grant_only_payment_writes_deferred_to_P5':'proposed_not_implemented'}));
uiActions.find(x=>x.ui_action==='UIA-03').semantics='PATCH逐主题保存；未答/跳过/明确采纳推荐分开；PUT不再是0.2.0拟议入口';
uiActions.find(x=>x.ui_action==='UIA-08').semantics='preflight只反馈；clarify/create用advance；review用submit_review且证据完整/值班可用才派单';
const completeReview={...reviewPreflight,purpose:'submit_review',evidence_complete:true,rule_result:'pass',reflection_ref:{id:'reflection-fixture',revision:1},transfer_attempt_ref:{id:'transfer-fixture',revision:2},reviewer_available:true,case_id:'case-fixture',progress_effect:'pending_review',outcome:'awaiting_review',missing_evidence:[],allowed_actions:['case']};
const supportedFindings=['M1','M2','M3','M4'].map(rubric_id=>({rubric_id,verdict:'supported',source_ids:['evidence-fixture'],note:'仅结构测试，不是实际审核。'}));
const caseDecision={request_id:'fixture-manual-01',expected_revision:2,decision:'needs_information',evidence_ids:['evidence-fixture'],target_revision:9,note:'需要孩子解释修改原因。',manual_findings:[{...supportedFindings[2],verdict:'unclear'}]};
const invariantCases=[];
const c=(id,schema,payload,expect_valid,semantics='schema')=>invariantCases.push({id,schema,payload,expect_valid,semantics});
c('START-first-topic','SaveStart',firstStartRequest,true,'start_patch');
c('START-unanswered-reset','SaveStart',{...firstStartRequest,answers:{mini_attempt_text:{state:'unanswered',value:null}}},true,'start_patch');
c('START-empty-patch','SaveStart',{...firstStartRequest,answers:{}},false);
c('START-answered-null','SaveStart',{...firstStartRequest,answers:{mini_attempt_text:{state:'answered',value:null}}},false);
c('START-answered-empty','SaveStart',{...firstStartRequest,answers:{mini_attempt_text:{state:'answered',value:''}}},false);
c('START-answered-whitespace','SaveStart',{...firstStartRequest,answers:{mini_attempt_text:{state:'answered',value:'  \n '}}},false);
c('START-skipped-with-value','SaveStart',{...firstStartRequest,answers:{help_preference:{state:'skipped',value:'guided'}}},false);
c('START-client-completion','SaveStart',{...firstStartRequest,completion_status:'completed'},false);
c('START-restored-draft','Start',restoredStart,true,'start_projection');
c('START-fake-completion','Start',{...restoredStart,completion_status:'completed'},false,'start_projection');
c('START-hidden-unanswered','Start',{...restoredStart,missing_fields:[]},false,'start_projection');
c('START-fake-learner-choice','Start',{...restoredStart,effective_start_source:'learner_choice'},false,'start_projection');
c('START-default-explicit','SaveStart',{request_id:'fixture-default-02',expected_revision:1,answers:{chosen_start:{state:'accepted_default',value:'guided',recommendation_revision:1}}},true,'start_patch');
c('START-default-stale','SaveStart',{request_id:'fixture-default-02',expected_revision:2,answers:{chosen_start:{state:'accepted_default',value:'guided',recommendation_revision:1}}},false,'start_patch');
c('START-default-mixed-edit','SaveStart',{request_id:'fixture-default-02',expected_revision:1,answers:{chosen_start:{state:'accepted_default',value:'guided',recommendation_revision:1},experience:{state:'answered',value:'some'}}},false);
c('HELP-unknown','HelpDisclosure',unknownHelp,true);
c('HELP-example-without-source','HelpDisclosure',{...unknownHelp,kind:'example_reference'},false);
c('HELP-example-with-source','HelpDisclosure',{...unknownHelp,kind:'example_reference',example_source_ids:['example-fixture']},true);
c('HELP-adult-content','HelpDisclosure',{...unknownHelp,kind:'adult_content'},true);
c('CHECK-review-preflight-input','NewCheck',reviewPreflightRequest,true);
c('CHECK-submit-incomplete-input','NewCheck',{...reviewPreflightRequest,purpose:'submit_review'},false);
c('CHECK-review-advance-forbidden','NewCheck',{...reviewPreflightRequest,purpose:'advance'},false);
c('CHECK-review-preflight-no-dispatch','Check',reviewPreflight,true);
c('CHECK-preflight-illegal-case','Check',{...reviewPreflight,case_id:'case-illegal'},false);
c('CHECK-preflight-illegal-pass','Check',{...reviewPreflight,progress_effect:'passed_and_unlocked',outcome:'advanced'},false);
c('CHECK-preflight-fake-human-result','Check',{...reviewPreflight,human_result:'passed'},false);
c('CHECK-preflight-complete-no-staff','Check',{...reviewPreflight,evidence_complete:true,rule_result:'pass'},true);
c('CHECK-review-submitted','Check',completeReview,true);
c('CHECK-review-no-staff-dispatch','Check',{...completeReview,reviewer_available:false},false);
c('CHECK-review-incomplete-dispatch','Check',{...completeReview,evidence_complete:false},false);
c('CHECK-review-no-staff-blocked','Check',{...completeReview,reviewer_available:false,case_id:null,progress_effect:'none',outcome:'blocked_support'},true);
c('CHECK-unknown-waits','Check',{...reviewPreflight,model_state:'unknown',rule_result:'unknown'},true);
c('CHECK-unknown-fake-failure','Check',{...reviewPreflight,model_state:'unknown',rule_result:'needs_practice'},false);
c('CHECK-unknown-dispatch','Check',{...completeReview,model_state:'unknown'},false);
c('REVIEW-persist-unclear','ResolveCase',caseDecision,true);
c('REVIEW-unclear-cannot-pass','ResolveCase',{...caseDecision,decision:'passed'},false);
c('REVIEW-four-supported','ResolveCase',{...caseDecision,decision:'passed',manual_findings:supportedFindings},true);
c('REVIEW-duplicate-criterion','ResolveCase',{...caseDecision,decision:'passed',manual_findings:[supportedFindings[0],supportedFindings[0],supportedFindings[2],supportedFindings[3]]},false);
const afterExperience={...restoredStart,revision:2,answers:{...restoredStart.answers,experience:{state:'answered',value:'some'}},recommendation_revision:2,missing_fields:restoredStart.missing_fields.filter(k=>k!=='experience')};
c('START-patch-preserves-omitted','Start',afterExperience,true,'start_transition');
Object.assign(invariantCases.at(-1),{before:restoredStart,patch:{request_id:'fixture-next-topic',expected_revision:1,answers:{experience:{state:'answered',value:'some'}}}});
const wipedAge={...afterExperience,answers:{...afterExperience.answers,age_band:{state:'unanswered',value:null}},missing_fields:['age_band',...afterExperience.missing_fields],skipped_fields:[]};
c('START-patch-cannot-wipe-omitted','Start',wipedAge,false,'start_transition');
Object.assign(invariantCases.at(-1),{before:restoredStart,patch:invariantCases.at(-2).patch});
c('RECOVERY-family-discovery','Families',familiesExample,true);
c('RECOVERY-family-limit-one','Families',{items:[familiesExample.items[0],{...familiesExample.items[0],id:'family-second'}],next_cursor:null},false);
c('RECOVERY-consent-minimal','Consents',consentsExample,true);
c('RECOVERY-consent-no-adult-details','Consents',{...consentsExample,items:[{...consentsExample.items[0],guardian_phone:'fixture-not-real'}]},false);
c('RECOVERY-revoked-no-effective-scope','ConsentSummary',{...consentsExample.items[0],status:'revoked',effective_scopes:['learning']},false);
c('RECOVERY-pending-no-effective-scope','Consents',{...consentsExample,relationship_status:'pending',visibility:'own_submissions',items:[{...consentsExample.items[0],effective_scopes:['learning']}]},false);
c('RECOVERY-draft-text-disabled','ConsentText',consentTextExample,true);
c('RECOVERY-draft-cannot-enable','ConsentText',{...consentTextExample,acceptance_enabled:true},false);
for(const [file,data] of Object.entries({'openapi.proposed.json':openapi,'operations.json':operations,'ui-actions.json':uiActions,'examples.json':{notice:'全部虚构，仅校验协议结构，不证明实现/业务状态有效',examples},'contract-cases.json':{version:'0.2.1',notice:'离线契约条件正反例，校验提案一致性；不执行后端/数据库/派单',cases:invariantCases},'acceptance.json':{notice:'实施后验收清单，本轮未运行API测试',scenarios}})) fs.writeFileSync(path.join(__dirname,file),JSON.stringify(data,null,2)+'\n','utf8');
console.log(JSON.stringify({generated:true,operations:operations.length,schemas:Object.keys(schemas).length,scenarios:scenarios.length,registered:false}));
