'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/songban-task-progress.js'), 'utf8');
const load = vm.runInThisContext('(function(module){' + source + ';return module.exports;})');
const {summarize, status, sampleTeam, advanceSample} = load({exports:{}});

test('only peer-accepted work contributes to progress, including after dependencies change', () => {
  const tasks = [
    {status:'reported_done', handoff_state:'accepted'},
    {status:'reported_done', handoff_state:'waiting_review'},
    {status:'in_progress'}, {status:'blocked'}, {status:'todo'},
    {status:'reported_done', handoff_state:'changes_requested'},
    {status:'reported_done', handoff_state:'dependency_changed'},
  ];
  assert.deepEqual(summarize(tasks), {accepted:1, waiting:1, active:1, blocked:3, todo:1, total:7, percent:14});
  tasks[0].handoff_state = 'dependency_changed';
  assert.equal(summarize(tasks).percent, 0);
});

test('an empty assignment is 0%, and a fully checked assignment is 100%', () => {
  assert.equal(summarize([]).percent, 0);
  assert.equal(summarize([{handoff_state:'accepted'}]).percent, 100);
});

test('sample members have independent assignments and representative progress', () => {
  const sample = sampleTeam();
  const percentages = sample.members.map(m => summarize(sample.tasks.filter(t => t.owner_id === m.id)).percent);
  assert.deepEqual(percentages, [60,25,75,0]);
  assert.equal(summarize(sample.tasks).percent, 44);
  assert.equal(new Set(sample.tasks.map(t => t.key)).size, sample.tasks.length);
  assert(sample.tasks.every(t => sample.members.some(m => m.id === t.owner_id)));
});

test('demo submission waits for acceptance and cannot affect another demo or a fresh reset', () => {
  const sample = sampleTeam(), independent = sampleTeam();
  const task = sample.tasks.find(t => status(t) === 'active');
  advanceSample(task);
  assert.equal(status(task), 'waiting');
  assert.equal(summarize(sample.tasks).percent, 44);
  advanceSample(task);
  assert.equal(status(task), 'accepted');
  assert.equal(summarize(sample.tasks).percent, 50);
  advanceSample(task);
  assert.equal(summarize(sample.tasks).percent, 50);
  assert.equal(summarize(independent.tasks).percent, 44);
  assert.equal(summarize(sampleTeam().tasks).percent, 44);
});
