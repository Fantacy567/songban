/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md. */
'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validateTeachers} = require('../scripts/validate_ai_teachers.cjs');
const manifest = require('../curriculum/ai-courses/teachers.json');
const evidence = require('../curriculum/ai-courses/source-checks.json');
const check = (m = manifest, e = evidence) => validateTeachers(m, e, '2026-11-04');
function rejects(change, pattern) {
  const m = structuredClone(manifest), e = structuredClone(evidence);
  change(m, e);
  assert.throws(() => check(m,e), pattern);
}
test('current seven teachers are compatible with the frozen IDs and evidence', () => check());
test('rejects copied role content and loss of a frozen course', () => {
  rejects(m => {m.teachers[1].help_strategy = m.teachers[0].help_strategy;}, /Distinct teacher/);
  rejects(m => {m.teachers[1].system_prompt = m.teachers[0].system_prompt;}, /Distinct teaching context/);
  rejects(m => {m.teachers[6].course_id = 'new-course';}, /frozen course IDs/);
});
test('first encounter must demonstrate revision and saving, without an exam gate', () => {
  rejects(m => {m.teachers[0].opening = m.teachers[0].opening.replace('追问', '忽略');}, /First lesson demonstrates/);
  rejects(m => {m.teachers[0].suggestions.push('答完全部题才能保存');}, /mandatory quiz/);
});
test('sources cannot silently become unsupported, undated or future checked claims', () => {
  rejects(m => {m.teachers[0].sources[0].url = 'https://docs.github.com/unread-page';}, /Missing source evidence/);
  rejects(m => {m.teachers[0].sources[0].supports = '已经证明孩子学会了';}, /Source evidence mismatch/);
  rejects((m,e) => {e.checked_at = '2027-01-01';}, /future/);
});
test('teacher tools cannot grow into arbitrary URL actions or another lesson capability', () => {
  rejects(m => {m.teachers[1].tools.push('https://example.com/run');}, /tool scope/);
  rejects(m => {m.teachers[3].tools.push('api-lab');}, /tool scope/);
});
test('fixed material cannot claim real model comparison or actual plugin installation', () => {
  rejects(m => {m.teachers[4].system_prompt = m.teachers[4].system_prompt.replace('固定样例台，不会自动调用两个供应商', '已经实时比较两个供应商');}, /固定样例台/);
  rejects(m => {m.teachers[3].system_prompt = m.teachers[3].system_prompt.replace('课程内白名单功能', '已经安装浏览器插件');}, /课程内白名单功能/);
});
test('technical reading must leave teacher and child validation pending', () => {
  rejects(m => {m.teachers[0].review.education = 'approved';}, /certification/);
  rejects(m => {m.teachers[1].review.pilot = 'passed';}, /certification/);
});
