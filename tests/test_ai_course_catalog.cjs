/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validateCatalog}=require('../scripts/validate_ai_course_catalog.cjs');
const original=require('../curriculum/ai-courses/catalog.json');
test('seven independent course records satisfy frozen content contract',()=>validateCatalog(original));
const reject=(title,change)=>test(title,()=>{const catalog=structuredClone(original);change(catalog);assert.throws(()=>validateCatalog(catalog));});
reject('rejects one course reusing another ID',c=>{c.courses[6].id=c.courses[0].id;});
reject('rejects activity kind crossed between courses',c=>{c.courses[5].activity.kind='project';});
reject('rejects seven entrances sharing one goal',c=>{c.courses[6].goal=c.courses[0].goal;});
reject('rejects copied practice question',c=>{c.courses[6].steps[1].prompt=c.courses[0].steps[1].prompt;});
reject('rejects shared first-course cover',c=>{c.courses[6].cover.src=c.courses[0].cover.src;});
reject('rejects fabricated pilot completion',c=>{c.courses[6].review.pilot='approved';});
reject('rejects unsupported source domain',c=>{c.courses[6].sources[0].url='https://example.com/claim';});
reject('rejects missing reference support statement',c=>{c.courses[6].sources[0].supports='';});
