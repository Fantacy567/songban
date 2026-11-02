// Deliberately offline: checks this proposal's schema subset and consistency only.
// It does NOT import FastAPI, open a database, send requests or certify implementation.
const fs=require('node:fs'), path=require('node:path'), crypto=require('node:crypto'), assert=require('node:assert/strict');
const {isDeepStrictEqual}=require('node:util');
const dir=__dirname, read=f=>JSON.parse(fs.readFileSync(path.join(dir,f),'utf8'));
const api=read('openapi.proposed.json'), ops=read('operations.json'), examples=read('examples.json').examples, scenarios=read('acceptance.json').scenarios;
let assertions=0; const check=(condition,message)=>{assert.ok(condition,message);assertions++};
function resolve(ref){check(ref.startsWith('#/components/schemas/'),'local schema refs only');const s=api.components.schemas[ref.split('/').at(-1)];check(!!s,'reference resolves '+ref);return s;}
function walk(v){if(Array.isArray(v))return v.forEach(walk);if(!v||typeof v!=='object')return;if(v.$ref)resolve(v.$ref);if(v.type==='object'){check(v.additionalProperties===false,'objects reject undeclared fields');check((v.required||[]).every(k=>k in v.properties),'required fields exist');}Object.values(v).forEach(walk);}
walk(api);
function valid(schema,value){
 if(schema.$ref&&!valid(resolve(schema.$ref),value))return false;
 if(schema.anyOf&&!schema.anyOf.some(s=>valid(s,value)))return false;
 if(schema.oneOf&&schema.oneOf.filter(s=>valid(s,value)).length!==1)return false;
 if(schema.allOf&&!schema.allOf.every(s=>valid(s,value)))return false;
 if(schema.if){const branch=valid(schema.if,value)?schema.then:schema.else;if(branch&&!valid(branch,value))return false;}
 if('const' in schema && JSON.stringify(value)!==JSON.stringify(schema.const))return false;
 if(schema.enum&&!schema.enum.includes(value))return false;
 const isObject=value!==null&&typeof value==='object'&&!Array.isArray(value);
 if(schema.type&& !({null:value===null,object:isObject,array:Array.isArray(value),string:typeof value==='string',integer:Number.isInteger(value),number:typeof value==='number'&&Number.isFinite(value),boolean:typeof value==='boolean'}[schema.type]))return false;
 if(isObject){
  if(!(schema.required||[]).every(k=>k in value))return false;
  if(schema.minProperties!==undefined&&Object.keys(value).length<schema.minProperties)return false;
  if(schema.maxProperties!==undefined&&Object.keys(value).length>schema.maxProperties)return false;
  if(!Object.keys(value).every(k=>k in (schema.properties||{})?valid(schema.properties[k],value[k]):schema.additionalProperties!==false))return false;
 }
 if(Array.isArray(value)){
  if(schema.minItems!==undefined&&value.length<schema.minItems||schema.maxItems!==undefined&&value.length>schema.maxItems)return false;
  if(schema.items&&!value.every(v=>valid(schema.items,v)))return false;
  if(schema.contains){const count=value.filter(v=>valid(schema.contains,v)).length;if(count<(schema.minContains??1)||count>(schema.maxContains??Infinity))return false;}
 }
 if(typeof value==='string'&&(schema.minLength!==undefined&&[...value].length<schema.minLength||schema.maxLength!==undefined&&[...value].length>schema.maxLength||schema.format==='date-time'&&!(/T.*(?:Z|[+-]\d\d:\d\d)$/.test(value)&&!Number.isNaN(Date.parse(value)))))return false;
 if(typeof value==='string'&&schema.pattern&&!new RegExp(schema.pattern,'u').test(value))return false;
 if(typeof value==='number'&&(schema.minimum!==undefined&&value<schema.minimum||schema.maximum!==undefined&&value>schema.maximum))return false;
 return true;
}
const startFields=['age_band','experience','interests','help_preference','mini_attempt_text','chosen_start'];
const sameSet=(a,b)=>a.length===new Set(a).size&&JSON.stringify([...a].sort())===JSON.stringify([...b].sort());
function validStartProjection(v){
 const missing=startFields.filter(k=>v.answers[k].state==='unanswered'),skipped=startFields.filter(k=>v.answers[k].state==='skipped');
 const completion=missing.length===startFields.length?'not_started':missing.length?'draft':skipped.length?'completed_with_skips':'completed';
 const mini={unanswered:'not_attempted',skipped:'skipped',answered:'answered'}[v.answers.mini_attempt_text.state];
 const selected=v.answers.chosen_start,source=selected.state==='answered'?'learner_choice':selected.state==='accepted_default'?'accepted_default':'conservative_fallback';
 const inputsReady=['experience','mini_attempt_text'].every(k=>v.answers[k].state==='answered');
 if(v.recommendation_basis==='rules'&&(!inputsReady||!sameSet(v.recommendation_source_fields,['experience','mini_attempt_text'])))return false;
 if(v.recommendation_basis==='insufficient_evidence'&&(v.recommendation!=='guided'||v.recommendation_source_fields.length!==0))return false;
 return sameSet(v.missing_fields,missing)&&sameSet(v.skipped_fields,skipped)&&v.completion_status===completion&&v.mini_attempt_status===mini&&v.recommendation_revision===v.revision&&v.effective_start_source===source&&v.effective_start===(source==='conservative_fallback'?'guided':selected.value);
}
function validStartPatch(v){const choice=v.answers.chosen_start;return !choice||choice.state!=='accepted_default'||choice.recommendation_revision===v.expected_revision;}
check(api.openapi==='3.1.0','OpenAPI version marker');check(api['x-implementation-status']==='not_registered','honest proposal status');
check(api.info.version==='0.2.1','revision version');
const frozen=read('frozen-0.2.0.json');
for(const [name,hash] of Object.entries(frozen.schema_sha256))check(crypto.createHash('sha256').update(JSON.stringify(api.components.schemas[name])).digest('hex')===hash,'0.2.0 frozen start/check schema unchanged: '+name);
check(isDeepStrictEqual(api.paths['/families'].get['x-authorized-actors'],['manager']),'family discovery manager only');
check(api.paths['/families'].get.parameters.length===0,'family discovery accepts no user/owner filter or cursor');
check(!api.paths['/learners/{learner_id}/consents'].get['x-authorized-actors'].includes('learner'),'consent management not exposed to learner sessions');
const textExample=examples.find(x=>x.operation_id==='consentText').response;
const textPayload={locale:textExample.locale,title:textExample.title,text:textExample.text,scope_purposes:textExample.scope_purposes};
check(crypto.createHash('sha256').update(JSON.stringify(textPayload)).digest('hex')===textExample.text_sha256,'consent text digest matches immutable content');
const consentExample=examples.find(x=>x.operation_id==='listConsents').response.items[0];
check(consentExample.consent_version===textExample.consent_version&&consentExample.text_sha256===textExample.text_sha256,'recovered consent binds exact text version/digest');
check(!!api.paths['/learners/{learner_id}/start'].patch&&!api.paths['/learners/{learner_id}/start'].put,'PATCH proposal has unambiguous merge semantics');
check(new Set(ops.map(o=>o.operation_id)).size===ops.length,'unique operation ids');
for(const o of ops){
 const route=o.path.replace('/api/learning/v2',''), operation=api.paths[route]?.[o.method.toLowerCase()];
 check(operation?.operationId===o.operation_id,'catalog matches OpenAPI '+o.operation_id);
 check(!!operation.responses[String(o.status)],'success response exists');check(operation['x-authorized-actors'].length>0,'authorization declared');
 for(const m of route.matchAll(/\{(\w+)\}/g))check(operation.parameters.some(p=>p.in==='path'&&p.name===m[1]&&p.required),'path parameter bound');
 if(o.method!=='GET'){
  const schema=api.components.schemas[o.request_schema];check(schema.required.includes('request_id'),'mutation request_id');
  if(!['authenticate','createFamily'].includes(o.operation_id))check(schema.required.includes('expected_revision'),'mutation expected_revision');
  check(operation.parameters.some(p=>p.in==='header'&&p.name==='X-CSRF-Token'&&p.required),'mutation CSRF');
 }
}
for(const example of examples){const o=ops.find(o=>o.operation_id===example.operation_id);if(example.request)check(valid(api.components.schemas[o.request_schema],example.request),'request example '+example.name);if(example.response)check(valid(api.components.schemas[example.schema||o.response_schema],example.response),'response example '+example.name);}
const offlineCases=read('contract-cases.json').cases, caseResults=[];
for(const test of offlineCases){
 let result=valid(api.components.schemas[test.schema],test.payload);
 if(result&&test.semantics==='start_projection')result=validStartProjection(test.payload);
 if(result&&test.semantics==='start_patch')result=validStartPatch(test.payload);
 if(result&&test.semantics==='start_transition'){
  result=validStartProjection(test.payload)&&valid(api.components.schemas.SaveStart,test.patch)&&test.patch.expected_revision===test.before.revision&&test.payload.revision===test.before.revision+1&&startFields.every(k=>isDeepStrictEqual(test.payload.answers[k],k in test.patch.answers?test.patch.answers[k]:test.before.answers[k]));
 }
 check(result===test.expect_valid,'offline contract condition '+test.id);
 caseResults.push({id:test.id,expected_valid:test.expect_valid,actual_valid:result,result:'passed'});
}
const sample=examples.find(x=>x.operation_id==='createArtifact').request;
check(!valid(api.components.schemas.NewArtifact,{...sample,passed:true}),'reject client-passed injection');
check(!valid(api.components.schemas.NewArtifact,{...sample,content:{...sample.content,html:'<script>x</script>'}}),'reject undeclared executable template field');
check(!valid(api.components.schemas.NewArtifact,{...sample,expected_revision:-1}),'reject invalid revision');
check(!valid(api.components.schemas.NewArtifact,{...sample,attempt_id:''}),'resource IDs cannot be empty');
check(!valid(api.components.schemas.CardText,{...sample.content,title:''}),'saved artifact title required');
check(api.components.schemas.NewHelp.properties.role_id.enum.join(',')==='guide,tool_guide,creation_coach,review_coach','separate four learning roles');
check(api.components.schemas.NewCheck.properties.artifact_version_id.anyOf.some(s=>s.type==='null'),'first gate accepts no artifact structurally');
check(api.components.schemas.NewCheck.required.includes('requirements_ref')&&api.components.schemas.NewCheck.required.includes('transfer_attempt_ref'),'revision-bound evidence refs');
check(api.components.schemas.ModelRun.properties.actual_model.anyOf.some(s=>s.type==='null'),'actual model can remain unknown');
check(scenarios.length>=26&&scenarios.every(s=>s.status==='not_run'),'acceptance scenarios are not claimed as executed');
check(ops.every(o=>o.path.startsWith('/api/learning/v2/')),'all routes remain proposed v2');
const ui=read('ui-actions.json');
check(ui.length===18&&new Set(ui.map(x=>x.ui_action)).size===18,'UIA-01 through UIA-18 covered');
check(ui.every(x=>x.operation_ids.every(id=>ops.some(o=>o.operation_id===id))),'UI action operation references resolve');
check(Object.values(api.components.securitySchemes).every(s=>s.type==='apiKey'&&s.in==='cookie'),'cookie security scheme only, no bearer exchange');
// Cross-artifact consistency against S01; never modify another session's files.
// contracts and content are siblings under p0.
const actualContentFile=path.resolve(dir,'../content/虚构材料与样例.json');
let contentCheck='not_available';
if(fs.existsSync(actualContentFile)){
 const content=JSON.parse(fs.readFileSync(actualContentFile,'utf8'));
 check(JSON.stringify([...content.artifact_fields].sort())===JSON.stringify(Object.keys(api.components.schemas.CardText.properties).sort()),'S01 artifact fields match exactly');
 check(content.rule_ids.length===8&&content.manual_rubric_ids.join(',')===api.components.schemas.ManualFinding.properties.rubric_id.enum.join(','),'S01 manual criteria match');
 contentCheck='passed';
}
const files=['openapi.proposed.json','operations.json','examples.json','acceptance.json','ui-actions.json','contract-cases.json','frozen-0.2.0.json'];
const result={date:'2026-11-02',contract_version:'0.2.1',validation:'passed',scope:'offline proposal structure, local references, schema-subset conditions/examples, cross-field invariants, S01 field alignment; NOT API/runtime/permissions/transaction tests',structural_assertions:assertions,offline_contract_cases:caseResults,operations:ops.length,schemas:Object.keys(api.components.schemas).length,examples:examples.length,acceptance_scenarios:scenarios.length,acceptance_scenarios_executed:0,content_alignment:contentCheck,frozen_0_2_0_schemas:Object.keys(frozen.schema_sha256).length,api_registered:false,db_migrated:false,paid_calls:0,checks:files.map(file=>({file,sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(dir,file))).digest('hex')})),limitations:['自带校验器仅覆盖本契约使用的schema子集（含组合/条件/contains），不是完整OpenAPI 3.1规范认证','离线条件案例检查提案内部约束，不执行后端起点存储/关卡推进/派单/数据库事务','未执行真实身份/旧Bearer/并发/模型/报告端到端验收','G0仍须S00与产品/教研审阅']};
fs.writeFileSync(path.join(dir,'validation-result.json'),JSON.stringify(result,null,2)+'\n','utf8');console.log(JSON.stringify(result,null,2));
