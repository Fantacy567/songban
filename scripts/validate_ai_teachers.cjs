/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
 * Offline content lint: never calls a provider and never certifies teaching quality.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const ids = ['ai-tools', 'imagination', 'first-project', 'plugins', 'models', 'api', 'model-powered-app'];
const courseTools = Object.fromEntries(ids.map((id, i) =>
  [id, i < 2 ? ['text-artifact'] : ['text-artifact', ['','','creative-studio','plugin-lab','model-compare','api-lab','model-app'][i]]]));
const publicFields = ['course_id','name','opening','suggestions','goal','sources','tools'];
const privateFields = ['system_prompt','help_strategy','artifact_instruction','knowledge_points','misconceptions','review'];
const read = name => JSON.parse(fs.readFileSync(path.join(root, 'curriculum/ai-courses', name), 'utf8'));
const nonempty = (v, where) => assert.ok(typeof v === 'string' && v.trim(), where + ': nonempty text required');
const texts = (v, where) => {
  assert.ok(Array.isArray(v) && v.length > 0, where + ': nonempty list required');
  v.forEach(item => nonempty(item, where));
  assert.equal(new Set(v).size, v.length, where + ': duplicated entries');
};
function validDate(date, today) {
  assert.match(date, /^\d{4}-\d{2}-\d{2}$/, 'Source check date must be explicit');
  assert.equal(new Date(date).toISOString().slice(0,10), date, 'Invalid check date');
  assert.ok(date <= today, 'Source check date is in the future');
}
function validateTeachers(manifest, evidence = read('source-checks.json'), today = new Date().toISOString().slice(0,10)) {
  assert.equal(manifest.version, '1');
  assert.deepEqual(Object.keys(manifest).sort(), ['teachers','version']);
  assert.deepEqual(manifest.teachers.map(t => t.course_id), ids, 'Seven frozen course IDs in order');
  assert.equal(evidence.version, '1');
  validDate(evidence.checked_at, today);
  const reviewed = new Map(evidence.sources.map(s => [s.url, s]));
  assert.equal(reviewed.size, evidence.sources.length, 'Duplicate source evidence');
  for (const t of manifest.teachers) {
    assert.deepEqual(Object.keys(t).sort(), [...publicFields,...privateFields].sort(), t.course_id + ': manifest fields');
    for (const key of ['name','opening','goal','system_prompt','help_strategy','artifact_instruction'])
      nonempty(t[key], t.course_id + '.' + key);
    for (const key of ['suggestions','knowledge_points','misconceptions']) texts(t[key], t.course_id + '.' + key);
    assert.deepEqual(t.tools, courseTools[t.course_id], t.course_id + ': authorized course tool scope');
    assert.deepEqual(t.review, {technical:'draft', sources_checked_at:evidence.checked_at, education:'pending', pilot:'pending'},
      'Do not convert source reading into educational/pilot certification');
    assert.ok(Array.isArray(t.sources) && t.sources.length > 0, 'Sources required');
    assert.equal(new Set(t.sources.map(s => s.url)).size, t.sources.length, 'Duplicate teacher source');
    for (const source of t.sources) {
      const url = new URL(source.url);
      assert.equal(url.protocol, 'https:');
      assert.ok(!url.username && !url.password && !url.port && !url.search && !url.hash, 'Plain primary source URL required');
      assert.ok(['docs.github.com','developer.mozilla.org','developers.google.com','www.anthropic.com','docs.cloud.google.com'].includes(url.hostname),
        'Unreviewed primary source domain');
      const record = reviewed.get(source.url);
      assert.ok(record, 'Missing source evidence');
      for (const key of ['title','supports','checked_at']) assert.equal(source[key], record[key], 'Source evidence mismatch: ' + key);
      nonempty(record.section, 'Source reading section'); nonempty(source.supports, 'Source support scope');
      validDate(source.checked_at, today);
      assert.equal(source.checked_at, t.review.sources_checked_at);
    }
    // Guard a known regression (required questionnaires). This is a lint, not semantic proof.
    const learnerText = [t.opening,t.goal,...t.suggestions].join('\n');
    assert.doesNotMatch(learnerText, /必须.{0,12}(答完|答对|填完|通过考试)|答对.{0,10}才能|答完.{0,10}才能|通过考试.{0,10}才能/,
      'No mandatory quiz gate in learner-facing invitation');
    assert.ok(t.system_prompt.includes('孩子可跳过、暂停、改主意或直接要草稿'), 'Preserve learner choice');
  }
  for (const key of ['name','opening','goal','help_strategy','artifact_instruction','knowledge_points','misconceptions'])
    assert.equal(new Set(manifest.teachers.map(t => JSON.stringify(t[key]))).size, 7, 'Distinct teacher ' + key);
  const roleBodies = manifest.teachers.map(t => t.system_prompt.split('共同约束：')[0].replaceAll(t.name, ''));
  assert.equal(new Set(roleBodies).size, 7, 'Distinct teaching context beyond shared safeguards');
  const byId = Object.fromEntries(manifest.teachers.map(t => [t.course_id,t]));
  const opening = byId['ai-tools'].opening;
  assert.match(opening, /事先写好的示例，不是实时模型回复/);
  let position = -1;
  for (const action of ['输入要求并发送','查看回复','追问','检查','保存']) {
    position = opening.indexOf(action, position + 1);
    assert.ok(position >= 0, 'First lesson demonstrates send → view → revise → check → save: ' + action);
  }
  assert.match(byId['ai-tools'].artifact_instruction, /角色介绍卡/);
  assert.match(byId.imagination.system_prompt, /先发散/);
  assert.match(byId.models.system_prompt, /固定样例台，不会自动调用两个供应商/);
  assert.match(byId.api.system_prompt, /不请求模型/);
  assert.match(byId.plugins.system_prompt, /课程内白名单功能/);
  assert.match(byId['model-powered-app'].system_prompt, /固定样例推演/);
  return manifest;
}
if (require.main === module) {
  try {
    validateTeachers(read('teachers.json'));
    console.log('PASS: seven teacher manifests, first-operation flow, source evidence and course tool scope. Offline content lint only; education/pilot pending.');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = {validateTeachers};
