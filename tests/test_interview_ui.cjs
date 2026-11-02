// Browser fixtures for the real interview view and shared form handler. No live model or user data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..');
const shell = fs.readFileSync(path.join(root, 'static/songban.js'), 'utf8');
const bindForm = shell.slice(shell.indexOf('function bindForm('), shell.indexOf('function captureDrafts('));
const journey = fs.readFileSync(path.join(root, 'static/songban-journey.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'static/songban.css'), 'utf8');
const output = process.env.SONGBAN_INTERVIEW_EVIDENCE;
const results = [];

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.setDefaultTimeout(7000);
    await page.route('http://127.0.0.1:18889/**', route => route.fulfill({contentType:'text/html',body:`<html lang="zh-CN"><head><meta charset="utf-8"><style>${css}</style></head><body><main style="max-width:900px;margin:auto;padding:20px"><div id="content"></div></main></body></html>`}));
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    async function setup(number=2, manual=false) {
      await page.goto('http://127.0.0.1:18889/');
      await page.evaluate(({ number, manual }) => {
        window.state = { busy:false, team:'synthetic', drafts:new Map() };
        window.$ = selector => document.querySelector(selector);
        window.esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
        window.head = (_eyebrow,title,text) => `<h1>${esc(title)}</h1><p>${esc(text)}</p>`;
        window.values = data => Object.fromEntries(data.entries());
        window.toast = text => { window.toastText = text; };
        window.formError = (form,error) => { const p=document.createElement('p');p.className='error';p.textContent=error.message;form.append(p); };
        window.load = async () => {};
        window.go = target => { window.nextRoute = target; };
        window.calls=[];window.failNext=false;window.delayMs=0;
        window.record={status:'asking',version:number,asked_count:number,max_questions:8,source:{kind:manual?'manual':'model'},
          current_question:{id:`q${number}`,number,text:'你想做什么小作品？'},
          messages:Array.from({length:number-1},(_,i)=>({id:`u${i}`,role:'user',text:'虚构已保存回答'}))};
        window.api=async (url,body) => {
          if(!body)return structuredClone(window.record);
          window.calls.push({url,body:structuredClone(body)});
          await new Promise(resolve=>setTimeout(resolve,window.delayMs));
          if(window.failNext){window.failNext=false;throw new Error('模拟整理失败，请重试。');}
          if(body.text)window.record.messages.push({id:'last',role:'user',text:body.text});
          window.record={...window.record,status:'pending_confirmation',current_question:null,
            profile:{draft:{goals:[{text:body.text||'之前已经保存的想法'}]}}};
          return structuredClone(window.record);
        };
      }, { number, manual });
      await page.addScriptTag({ content: bindForm + '\n' + journey });
      await page.evaluate(() => interviewPage());
    }
    async function run(name, action) { await action(); results.push(name); }
    const summary = () => page.getByRole('heading', {name:'核对你的起点'}).waitFor();

    await run('blank early finish bypasses required answer and waits for user confirmation', async () => {
      await setup();
      await page.getByRole('button',{name:'先到这里，查看总结'}).click();
      await summary();
      const calls=await page.evaluate(()=>window.calls);
      assert.equal(calls.length,1);assert.ok(calls[0].url.endsWith('/finish'));
      assert.equal('text' in calls[0].body,false);
      assert.equal(await page.evaluate(()=>window.nextRoute),undefined);
    });
    await run('typed answer is included in finish without an extra answer request', async () => {
      await setup();await page.locator('textarea').fill('我想设计一个虚构故事卡。');
      await page.getByRole('button',{name:'先到这里，查看总结'}).click();await summary();
      const calls=await page.evaluate(()=>window.calls);
      assert.equal(calls.length,1);assert.equal(calls[0].body.text,'我想设计一个虚构故事卡。');
      assert.equal(calls[0].body.question_id,'q2');
    });
    await run('legacy question 17 can finish without another answer', async () => {
      await setup(17);
      assert.match(await page.locator('#content').innerText(),/已保存 16 次回答/);
      assert.equal(await page.getByRole('button',{name:'保存回答，继续'}).count(),0);
      await page.getByRole('button',{name:'先到这里，查看总结'}).click();await summary();
      assert.equal(await page.evaluate(()=>window.record.messages.length),16);
    });
    await run('summary failure preserves input and reuses the request id on retry', async () => {
      await setup();await page.locator('textarea').fill('失败后保留我的文字');
      await page.evaluate(()=>{window.failNext=true;});
      await page.getByRole('button',{name:'先到这里，查看总结'}).click();
      await page.locator('.error').waitFor();assert.equal(await page.locator('textarea').inputValue(),'失败后保留我的文字');
      await page.getByRole('button',{name:'先到这里，查看总结'}).click();await summary();
      const calls=await page.evaluate(()=>window.calls);
      assert.equal(calls[0].body.request_id,calls[1].body.request_id);
    });
    await run('pending submission prevents duplicate finish and input changes', async () => {
      await setup();await page.evaluate(()=>{window.delayMs=200;document.querySelector('#iv-finish').click();document.querySelector('#iv-finish').click();});
      assert.equal(await page.locator('textarea').evaluate(e=>e.readOnly),true);await summary();
      assert.equal(await page.evaluate(()=>window.calls.length),1);
    });
    await run('last question states the limit and normal submit requests a summary', async () => {
      await setup(8);assert.match(await page.locator('#content').innerText(),/第 8 问 · 最多 8 问/);
      await page.locator('textarea').fill('最后一题的虚构回答');
      await page.getByRole('button',{name:'保存回答，查看总结',exact:true}).click();await summary();
      assert.ok((await page.evaluate(()=>window.calls[0].url)).endsWith('/answer'));
    });
    await run('manual flow retains a three-question limit', async () => {
      await setup(3,true);assert.match(await page.locator('#content').innerText(),/第 3 问 · 最多 3 问/);
      await page.getByRole('button',{name:'先到这里，查看总结'}).click();await summary();
    });
    await run('mobile and desktop layouts have no horizontal overflow', async () => {
      for(const width of [390,768,1440]){
        await page.setViewportSize({width,height:900});await setup(17);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        assert.ok(await page.getByRole('button',{name:'先到这里，查看总结'}).isVisible());
        if(output){fs.mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,`legacy-${width}.png`),fullPage:true});}
      }
    });
    assert.deepEqual(errors,[]);
    if(output)fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:results.length,results,errors},null,2));
    console.log(JSON.stringify({passed:results.length,results,errors}));
  } finally { await browser.close(); }
})().catch(error=>{ console.error(error);process.exitCode=1; });
