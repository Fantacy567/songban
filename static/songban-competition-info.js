'use strict';

// A compact projection of saved competition facts, not a new model response.
const SongbanCompetitionInfo = (() => {
  const fields = [
    ['time', '比赛时间', /^(?:比赛时间|活动时间|活动日期|比赛日期|举办时间)\s*[：:]\s*(.+)$/],
    ['location', '比赛地点', /^(?:比赛地点|活动地点|举办地点|地点|地址)\s*[：:]\s*(.+)$/],
    ['track', '主题 / 赛道', /^(?:比赛主题|活动主题|主题|参赛赛道|赛道)\s*[：:]\s*(.+)$/],
    ['deadline', '提交截止', /^(?:提交截止(?:时间)?|作品截止(?:时间)?|交稿截止(?:时间)?|截止时间|提交时间)\s*[：:]\s*(.+)$/],
    ['team', '组队要求', /^(?:参赛要求|参赛资格|组队要求|组队人数|团队规模)\s*[：:]\s*(.+)$/],
    ['presentation', '展示安排', /^(?:路演安排|展示安排|展示时长|路演时长|现场展示)\s*[：:]?\s*(.+)$/],
    ['deliverables', '提交内容', /^(?:提交内容|提交材料|提交要求|交付要求|交付清单|提交物)\s*[：:]\s*(.+)$/],
    ['rubric', '评分标准', /^(?:评分标准|评分维度|评审标准|评分关注|评分依据)\s*[：:]\s*(.+)$/],
  ];
  const unknown = /未知|未提供|未明确|未公布|待.*确认|待补充|待定|不详|请.*核实|需.*确认|另行通知/;
  const normalize = value => value.replace(/[\s。，、；;：:—–-]/g, '');
  function collect(data = {}, event = null) {
    const rows = fields.map(([key, label]) => ({key, label, values:[], itemIds:[]}));
    const sources = (data.sources || []).filter(s => ['ready','partial'].includes(s.status));
    const active = new Set(sources.map(s => s.id));
    const usable = (data.result?.items || []).filter(i => i.kind === 'statement' && !['source_withdrawn','needs_review','deferred'].includes(i.verification) &&
      i.citations?.length && i.citations.every(c => active.has(c.source_id)));
    // Sample materials for other activities must not overwrite this event's sample.
    const scoped = event ? sources.filter(s => s.metadata?.nature !== 'sample' ||
      !/【(?:虚构赛规|虚构演示材料)[｜】]/.test(s.segments?.map(x=>x.text).join('\n') || '') ||
      s.segments?.some(x=>x.text.includes(event.title))) : sources;
    const sourceIds = new Set(scoped.map(s=>s.id));
    const items = usable.filter(i=>i.citations.every(c=>sourceIds.has(c.source_id)));
    const add = (key, text, id) => {
      const value = String(text || '').trim().replace(/[。；;]+$/, '');
      if (!value || unknown.test(value)) return;
      const row = rows.find(r=>r.key===key);
      if (!row.values.some(v=>normalize(v)===normalize(value))) row.values.push(value);
      if (id && !row.itemIds.includes(id)) row.itemIds.push(id);
    };
    function extract(text, id) {
      // Split only on sentence boundaries or before another explicit field label.
      for (const raw of String(text || '').split(/\n|[。；;]|[，,](?=\s*(?:地点|地址|赛道|主题|提交截止|截止时间|评分标准)\s*[：:])/)) {
        const line = raw.trim().replace(/^(?:[-*•]\s*|\d+[.、]\s*)/, '');
        let matched = false;
        for (const [key,,pattern] of fields) {
          const match = line.match(pattern);
          if (match) { add(key, match[1], id); matched = true; break; }
        }
        if (matched || unknown.test(line)) continue;
        if (/^(?:支持|允许|需|每队).*\d.*人.*组队/.test(line)) add('team', line, id);
        else if (/^提交(?!截止|时间|日期)/.test(line)) add('deliverables', line.replace(/^提交\s*/, ''), id);
        else if (/^(?:教育|校园|开放学习|AI|人工智能).*主题/.test(line)) {
          add('track', line.split(/[，,]/)[0], id);
          const team = line.match(/(?:支持|允许).*\d.*人.*组队/); if (team) add('team', team[0], id);
        }
      }
    }
    if (!data.stale && items.length) items.forEach(i=>extract(i.text, i.id));
    // When material has changed, use the newly saved original, never outdated AI items.
    // Also recover explicit labels omitted by an earlier summary.
    const missing = new Set(rows.filter(r=>!r.values.length).map(r=>r.key));
    const before = rows.map(r=>({values:r.values.slice(), itemIds:r.itemIds.slice()}));
    scoped.forEach(s=>s.segments?.forEach(segment=>extract(segment.text)));
    rows.forEach((r,index)=>{if(!missing.has(r.key)){r.values=before[index].values;r.itemIds=before[index].itemIds;}});
    if (event) {
      if (!scoped.length) extract(event.rules);
      // Event dates are deliberately never used as a submission deadline.
      if (!rows.find(r=>r.key==='time').values.length) add('time', event.date);
      if (!rows.find(r=>r.key==='location').values.length) add('location', event.location);
      if (!rows.find(r=>r.key==='track').values.length && /主题/.test(event.summary || '')) add('track', event.summary.split(/[，,。]/)[0]);
    }
    const itemIds = [...new Set(rows.flatMap(r=>r.itemIds))];
    return {rows, itemIds, sample:scoped.length ? scoped.every(s=>s.metadata?.nature==='sample') : Boolean(event), hasInfo:rows.some(r=>r.values.length)};
  }
  return {collect};
})();
