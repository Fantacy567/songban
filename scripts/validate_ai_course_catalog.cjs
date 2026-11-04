/* Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
 * Technical checks only. No provider calls, server changes, or education certification.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const expected = ['ai-tools','imagination','first-project','plugins','models','api','model-powered-app'];
const kinds = ['tool-sort','idea-builder','project','plugin-lab','model-compare','api-lab','model-app'];
const digest = data => crypto.createHash('sha256').update(data).digest('hex');
const nonempty = value => assert.ok(typeof value === 'string' && value.trim(), 'Expected nonempty text');
function validateCatalog(catalog) {
  assert.deepEqual(Object.keys(catalog).sort(), ['courses','version']);
  assert.equal(catalog.version, '1');
  assert.deepEqual(catalog.courses.map(c => c.id), expected, 'Seven unique frozen IDs in order');
  const fields = ['id','version','title','chapter','order','status','goal','preparation','duration','cover','intro','steps','activity','sources','review'].sort();
  for (const [i,c] of catalog.courses.entries()) {
    assert.deepEqual(Object.keys(c).sort(), fields, `${c.id}: frozen fields`);
    assert.equal(c.version, '1'); assert.equal(c.order, i+1); assert.equal(c.status, 'trial');
    assert.deepEqual(c.chapter, i<4 ? {id:'tools',title:'AI 工具篇',order:1} : {id:'advanced',title:'进阶篇',order:2});
    for(const k of ['title','goal','preparation','duration','intro'])nonempty(c[k]);
    assert.deepEqual(Object.keys(c.cover).sort(), ['alt','src']); nonempty(c.cover.alt);
    assert.equal(c.cover.src, `/static/platform/illustrations/course-${c.id}.svg`);
    assert.deepEqual(c.steps.map(s=>s.id), ['understand','try','reflect']);
    for(const s of c.steps) {
      assert.deepEqual(Object.keys(s).sort(), ['example','id','instruction','prompt','title']);
      for(const k of ['title','instruction','example','prompt'])nonempty(s[k]);
    }
    assert.deepEqual(Object.keys(c.activity).sort(), ['instruction','kind','title']);
    assert.equal(c.activity.kind,kinds[i]);nonempty(c.activity.title);nonempty(c.activity.instruction);
    assert.deepEqual(c.review,{technical:'draft',education:'pending',pilot:'pending'}, 'No fabricated teaching or pilot review');
    assert.ok(c.sources.length>0);
    for(const s of c.sources) {
      assert.deepEqual(Object.keys(s).sort(), ['supports','title','url']);nonempty(s.title);nonempty(s.supports);
      const url=new URL(s.url); assert.equal(url.protocol,'https:');
      assert.ok(['docs.github.com','github.blog','developer.mozilla.org','developers.google.com','cloud.google.com','docs.cloud.google.com','www.anthropic.com'].includes(url.hostname), 'Reviewed primary source domain');
    }
  }
  for(const field of ['title','goal','intro','preparation'])assert.equal(new Set(catalog.courses.map(c=>c[field])).size,7,`Independent ${field}`);
  for(const step of [0,1,2])for(const field of ['instruction','example','prompt'])assert.equal(new Set(catalog.courses.map(c=>c.steps[step][field])).size,7,`Independent step ${step} ${field}`);
  const text=id=>JSON.stringify(catalog.courses.find(c=>c.id===id));
  assert.match(text('ai-tools'),/五个动作/); assert.match(text('plugins'),/重点高亮/);
  for(const id of ['models','model-powered-app'])assert.match(text(id),/固定/);
  assert.match(text('api'),/固定规则/);assert.match(text('api'),/没有调用大模型/);
  return catalog;
}
async function renderAndCheck(catalog,out) {
  const {chromium}=require('playwright');
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  const evidence={scope:'Catalog and local SVG/snippet checks only; education/pilot pending.',courses:[],checks:[],outsideRequests:[]};
  try {
    const context=await browser.newContext({viewport:{width:1000,height:700},deviceScaleFactor:1});
    await context.route('**/*', route=>{evidence.outsideRequests.push(route.request().url());return route.abort();});
    const page=await context.newPage(); const errors=[];page.on('pageerror',e=>errors.push(e.message));
    fs.mkdirSync(out,{recursive:true});
    const images=[];
    for(const c of catalog.courses) {
      const file=path.join(root,c.cover.src.replace(/^\//,'')); const svg=fs.readFileSync(file,'utf8');
      const info=await page.evaluate(svg=>{
        const doc=new DOMParser().parseFromString(svg,'image/svg+xml');
        if(doc.querySelector('parsererror'))throw Error('Malformed SVG');
        const el=doc.documentElement;
        const prohibited=[...doc.querySelectorAll('script,foreignObject,image,use,animate,animateTransform,set,a,style')].length;
        const attributes=[...doc.querySelectorAll('*')].flatMap(e=>[...e.attributes].map(a=>[a.name,a.value]));
        const external=attributes.some(([k,v])=>/^on/i.test(k)||/(?:href|src)$/i.test(k)||/url\s*\(/i.test(v));
        return {width:el.getAttribute('width'),height:el.getAttribute('height'),viewBox:el.getAttribute('viewBox'),role:el.getAttribute('role'),label:el.getAttribute('aria-labelledby'),title:doc.querySelector('#title')?.textContent,desc:doc.querySelector('#desc')?.textContent,metadata:doc.querySelector('metadata')?.textContent,prohibited,external};
      },svg);
      assert.equal(info.width,'900');assert.equal(info.height,'600');assert.equal(info.viewBox,'0 0 900 600');
      assert.equal(info.role,'img');assert.equal(info.label,'title desc');nonempty(info.title);nonempty(info.desc);
      for(const name of ['2292576833','Fantacy567','andorwu5-dev','Original','COPYRIGHT.md'])assert.ok(info.metadata.includes(name));
      assert.equal(info.prohibited,0);assert.equal(info.external,false);
      const src=`data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;images.push({src,title:c.title});
      await page.setContent(`<style>body{margin:0}</style><img alt="course cover" width="900" height="600" src="${src}">`);
      await page.locator('img').evaluate(async img=>{await img.decode();if(img.naturalWidth!==900||img.naturalHeight!==600)throw Error('Image failed');});
      const png=await page.locator('img').screenshot({path:path.join(out,`${c.id}.png`)});
      // Ignore colors, labels and metadata when detecting a reused scene.
      const geometry=svg.replace(/<(title|desc|metadata)\b[^>]*>[\s\S]*?<\/\1>/g,'').replace(/(?:fill|stroke)="[^"]*"/g,'');
      evidence.courses.push({id:c.id,svgSha256:digest(svg),geometrySha256:digest(geometry),pngSha256:digest(png),loaded:true,width:900,height:600});
    }
    for(const key of ['svgSha256','geometrySha256','pngSha256'])assert.equal(new Set(evidence.courses.map(c=>c[key])).size,7,`Distinct ${key}`);
    await page.setViewportSize({width:1440,height:1120});
    await page.setContent(`<style>body{margin:0;padding:24px;background:#fffdf7;font:20px sans-serif;color:#574563}main{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}figure{margin:0}img{display:block;width:100%;height:auto;border-radius:12px}figcaption{padding:8px 0 14px}</style><main>${images.map(i=>`<figure><img src="${i.src}"><figcaption>${i.title}</figcaption></figure>`).join('')}</main>`);
    await page.locator('img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));
    await page.screenshot({path:path.join(out,'all-covers.png'),fullPage:true});
    evidence.checks.push('7 XML documents, local decoding, 900x600 dimensions, accessible metadata, static-only elements, unique file/geometry/render hashes');
    const example=catalog.courses.find(c=>c.id==='first-project').steps[1].example;
    const html=example.slice(example.indexOf('<button'));
    assert.ok(html.startsWith('<button'));
    await page.setContent(html);assert.equal(await page.locator('#message').textContent(),'');
    await page.locator('#hello').click();assert.equal(await page.locator('#message').textContent(),'你好，小松');
    await page.setContent(html.replace('你好，小松','你好，森林'));await page.locator('#hello').click();assert.equal(await page.locator('#message').textContent(),'你好，森林');
    await page.locator('#hello').evaluate(el=>{el.textContent='向森林问好';});await page.locator('#hello').click();assert.equal(await page.locator('#message').textContent(),'你好，森林');
    evidence.checks.push('Exact catalog starter HTML runs; changing output changes behavior; changing button label alone preserves output');
    assert.deepEqual(errors,[]);assert.deepEqual(evidence.outsideRequests,[]);
    evidence.checkedAt=new Date().toISOString();evidence.catalogSha256=digest(fs.readFileSync(path.join(root,'curriculum/ai-courses/catalog.json')));
    fs.writeFileSync(path.join(out,'evidence.json'),JSON.stringify(evidence,null,2)+'\n');
    console.log(`PASS: 7 catalog courses + 7 rendered covers + starter behavior. Evidence: ${out}`);
  } finally {await browser.close();}
}
if(require.main===module) {
  const catalog=validateCatalog(JSON.parse(fs.readFileSync(path.join(root,'curriculum/ai-courses/catalog.json'),'utf8')));
  if(process.argv.includes('--render'))renderAndCheck(catalog,path.resolve(root,'curriculum/ai-courses/evidence')).catch(e=>{console.error(e);process.exitCode=1;});
  else console.log('PASS: seven-course frozen content contract and independent content. Add --render for browser checks.');
}
module.exports={validateCatalog};
