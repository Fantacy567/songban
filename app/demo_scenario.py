"""Explicit, offline fixture responses for the isolated demo. Never used in real service."""
import json,re

def interview(_system,payload):
    users=[m for m in payload['transcript'] if m['role']=='user']
    questions=[('你最想做什么作品？','want_to_make'),('你已经会做什么？','experience'),('你可以投入多少时间？','time')]
    if len(users)<3 and payload['mode']!='profile_only':
        q,d=questions[len(users)];return json.dumps({'type':'ask','question':q,'purpose':'演示访谈','dimension':d},ensure_ascii=False),'demo-fixture'
    result={k:[] for k in ['interests','goals','experiences','possible_strengths','roles_to_try','help_needed','next_practice','conflicts','unknowns']};result.update(type='profile_draft',time_available=None)
    for i,key in enumerate(['goals','experiences','time_available']):
        if i>=len(users):continue
        value={'text':users[i]['text'][:60],'basis':'self_reported','evidence':[users[i]['id']]};result[key]=value if key=='time_available' else [value]
    return json.dumps(result,ensure_ascii=False),'demo-fixture'

def plan(ctx):
    members=ctx['members'];tasks=[]
    for index,member in enumerate(members):
        tasks.append({'key':'T'+str(index+1),'owner_id':member['id'],'title':'画出并说明首页草图' if index==0 else '制作可运行演示页','acceptance':'检查输入作业、生成安排、完成打勾三个步骤','depends_on':[],'source_ids':['direction']})
    return {'summary':'演示样例：设计和实现并行，完成后互相检查。','findings':[],'tasks':tasks,'questions':['真实使用时，请按实际可投入时间核对任务范围。']}

def ranking(ctx):
    return {'assessments':[{'idea_id':s['id'],'capability':90 if '作业' in s['title'] else 60,'time':85,'rubric':80,'reasons':{'capability':'演示：设计与网页实现能力可覆盖最小版本。','time':'演示：两人各6小时，先完成一页。','rubric':'演示：对应用户价值、完成度和协作。'},'risks':['这是假设方案，尚需真实用户验证。'],'source_ids':[s['id'],'M1','R']} for s in ctx['sources'] if s['kind']=='idea']}

def recap(ctx):
    return {'summary':'演示样例：孩子参与设计并完成同伴协作，开始主动核对AI建议。','observations':[{'title':'把想法变成具体步骤','text':'根据本人记录，尝试解释页面流程；有AI和队友协助，不能据此推断独立开发能力。','source_ids':['reflection']}],'next_steps':['下次邀请一名同学试用，再修改不清楚的步骤。'],'limitations':['演示数据，不是真实孩子能力评估；比赛结果未经核验。']}

def extract_sample(text):
    fields={}
    labels={'name':'比赛','event_time':'时间','location':'地点','rubric':'评分','requirements':'材料','deadline':'截止'}
    for key,label in labels.items():
        match=re.search(r'(?:^|\n)'+label+r'[:：]([^\n]+)',text)
        if match:fields[key]=match[1].strip()
    return fields


def workbench(ctx):
    return {'text':'演示样例：先画出输入作业、生成安排、完成打勾三个步骤。请队友试用一次，再根据反馈修改。此回复为预置演示，不代表真实模型分析。','actions':[]}

def materials(ctx):
    items=[]
    for source in ctx.get('sources',[]):
        for segment in source.get('segments',[]):
            quote=segment['text'][:80]
            if quote.strip():items.append({'category':'演示材料','text':quote,'kind':'statement','importance':'normal','citations':[{'source_id':source['id'],'segment_id':segment['id'],'quote':quote}],'member_ids':[],'conflict':''})
    return {'summary':'演示样例：以下内容来自本次输入的材料，请逐项核对。','items':items[:60]}
