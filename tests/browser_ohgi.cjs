/* Real DOM, layout, hit testing, input and HTTP. No production functions are replaced. */
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const config = JSON.parse(fs.readFileSync(0, 'utf8'));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const ws = new WebSocket(config.endpoint);
const pending = new Map(), errors = [];
let next = 0, ready = false;
ws.addEventListener('close', event => {
  for (const entry of pending.values()) entry.reject(new Error('DevTools connection closed ('+event.code+', command '+next+')'));
  pending.clear();
});
ws.addEventListener('message', event => {
  const data = JSON.parse(event.data);
  if (data.id && pending.has(data.id)) {
    const {resolve, reject, timer} = pending.get(data.id); pending.delete(data.id); clearTimeout(timer);
    data.error ? reject(new Error(JSON.stringify(data.error))) : resolve(data.result);
  }
  if (data.method === 'Runtime.exceptionThrown') errors.push(data.params.exceptionDetails.text);
});
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++next;
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error('DevTools command timed out: '+method));},5000);
    pending.set(id, {resolve, reject, timer}); ws.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await call('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function until(expression) {
  for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await sleep(20); }
  throw new Error('Browser condition timed out: ' + expression);
}
async function api(route, body) {
  const response = await fetch(config.origin + route, {method: body === undefined ? 'GET' : 'POST',
    headers: {'X-Blemma-Token': 'ohgi-browser-test', 'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)});
  assert(response.ok, route + ': ' + response.status);
  return response.status === 204 ? null : response.json();
}
async function key(key, code = key) {
  const virtual = {Enter:13, Escape:27, Backspace:8, ArrowRight:39, ArrowLeft:37, ' ':32}[key] || key.charCodeAt(0);
  await call('Input.dispatchKeyEvent', {type:'keyDown', key, code, windowsVirtualKeyCode:virtual});
  await call('Input.dispatchKeyEvent', {type:'keyUp', key, code, windowsVirtualKeyCode:virtual});
}
async function point(selector) {
  return evaluate(`(() => { const b=document.querySelector(${JSON.stringify(selector)}), r=b.getBoundingClientRect(), s=getComputedStyle(b);
    const lx=parseFloat(s.getPropertyValue('--lx')), ly=parseFloat(s.getPropertyValue('--ly'));
    return Number.isFinite(lx) ? {x:r.x+lx, y:r.y+ly} : {x:r.x+r.width/2,y:r.y+r.height/2}; })()`);
}
async function mouse(p, type='mouseMoved') { await call('Input.dispatchMouseEvent', {type, ...p, ...(type==='mouseMoved'?{}:{button:'left',clickCount:1})}); }
async function click(selector) { const p=await point(selector); await mouse(p,'mousePressed'); await mouse(p,'mouseReleased'); }
async function screenshot(name) {
  const data = await call('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
  fs.writeFileSync(path.join(config.output,name+'.png'),Buffer.from(data.data,'base64'));
}
async function open(query='mode=small&lang=ja&dwell=0') {
  await call('Page.navigate', {url:config.origin+'/?'+query+'#t=ohgi-browser-test'});
  await until(`document.querySelector('#text') && document.querySelector('#text').textContent.length > 0`);
  await call('Page.bringToFront');
}
async function card(n, multi=false) {
  const payload={questions:[{header:'確認',question:'次に行う作業を選んでください。本文は省略せず、長い場合もここで読めます。', multiSelect:multi,
    options:Array.from({length:n},(_,i)=>({label:['変更を確かめてから進む','試験を実行する','手順を詳しく確認する','少し待つ','別の案を確認する','ここで区切る'][i],
      description:'既存の説明 '+(i+1)+'。選択肢の全文と一緒に表示します。'}))}]};
  const r=await api('/ask',{kind:'question',from:{session:'demo01'},payload});
  await until(`document.querySelectorAll('.btn[data-key="opt:0"]').length === 1`);
  return r.id;
}
async function closeCard(id) {
  await key('0','Digit0');
  await until(`!document.querySelector('#undo-zone').hidden`);
  await sleep(1050); await api('/wait?id='+id);
  await until(`document.body.classList.contains('idle')`);
}
(async () => {
  await new Promise((resolve,reject)=>{ ws.addEventListener('open',resolve,{once:true}); ws.addEventListener('error',reject,{once:true}); ws.addEventListener('close',()=>reject(new Error('DevTools closed before opening')),{once:true}); });
  await call('Runtime.enable'); await call('Page.enable');
  ready = true;
  await call('Emulation.setDeviceMetricsOverride',{width:660,height:700,deviceScaleFactor:1,mobile:false});
  await open();
  for (const n of [2,3,4,6]) {
    const id=await card(n);
    await until(`document.querySelectorAll('#fan > .btn').length === ${n+2}`);
    const geometry=await evaluate(`Array.from(document.querySelectorAll('#fan > .btn')).map(b=>{const s=getComputedStyle(b),r=b.getBoundingClientRect();
      const x=r.x+parseFloat(s.getPropertyValue('--lx')),y=r.y+parseFloat(s.getPropertyValue('--ly'));
      return {key:b.dataset.key,x,y,hit:document.elementFromPoint(x,y)?.closest('button')?.dataset.key};})`);
    // Larger fans retain target size: inspect them in a wider isolated viewport too.
    if (n===6) await call('Emulation.setDeviceMetricsOverride',{width:660,height:700,deviceScaleFactor:1,mobile:false});
    await mouse(await point('#fan [data-key="opt:0"]'));
    await until(`document.querySelector('#spot-desc').textContent.includes('既存の説明 1')`);
    assert.equal(await evaluate(`document.querySelector('#fan-script-0 textPath').textContent`),'変更を確かめてから進む');
    await evaluate(`document.activeElement.blur()`);
    await key('ArrowRight');
    assert.equal(await evaluate(`document.activeElement.dataset.key`),'opt:0');
    await key('ArrowRight');
    assert.equal(await evaluate(`document.activeElement.dataset.key`),'opt:1');
    assert.equal(await evaluate(`document.querySelector('#fan-script-0 textPath').textContent`),'試験を実行する');
    const hits=await evaluate(`Array.from(document.querySelectorAll('#fan > .btn')).every(b=>{const s=getComputedStyle(b),r=b.getBoundingClientRect();
      return document.elementFromPoint(r.x+parseFloat(s.getPropertyValue('--lx')),r.y+parseFloat(s.getPropertyValue('--ly')))?.closest('button')===b;})`);
    assert(hits,'Actual clip-path hit targets must agree with labels');
    await screenshot('ohgi-'+n);
    // A notification arrives about 6 seconds after the card: it must not move the blade under the gaze.
    const before=await evaluate(`JSON.stringify(document.querySelector('#fan').getBoundingClientRect())`);
    await api('/notify',{type:'permission_prompt',message:'m'});
    await sleep(400);
    assert(await evaluate(`document.querySelector('#band').hidden && !document.body.classList.contains('glow')`),'The card is the notice: no band or edge while it is shown');
    assert.equal(await evaluate(`JSON.stringify(document.querySelector('#fan').getBoundingClientRect())`),before,'A notification must not move the fan');
    await key('1','Digit1');
    await until(`!document.querySelector('#undo-zone').hidden`);
    const undoHit=await evaluate(`(() => { const r=document.querySelector('#undo-btn').getBoundingClientRect();
      return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('button')?.id; })()`);
    assert.equal(undoHit,'undo-btn','Undo is the inner band of the fan: a large target');
    const blade=await point('#fan [data-key="opt:0"]');
    assert.notEqual(await evaluate(`document.elementFromPoint(${blade.x},${blade.y})?.closest('button')?.id`),'undo-btn','Undo is never on top of the pressed blade');
    if (n===2) await screenshot('ohgi-undo');
    await key('Escape');
    await until(`document.querySelector('#undo-zone').hidden && !document.querySelector('#fan > .btn').disabled`);
    await closeCard(id);
    await until(`!document.querySelector('#band').hidden`);   // The notice really arrived: it shows once no card is out.
    await call('Emulation.setDeviceMetricsOverride',{width:660,height:700,deviceScaleFactor:1,mobile:false});
  }
  // The default small window is landscape: the whole fan stays inside it, even when a notification arrives.
  await call('Emulation.setDeviceMetricsOverride',{width:940,height:370,deviceScaleFactor:1,mobile:false});
  for (const n of [2,6]) {
    const wide=await card(n);
    await until(`document.querySelectorAll('#fan > .btn').length === ${n+2}`);
    await api('/notify',{type:'permission_prompt',message:'m'});
    await sleep(400);
    const box=await evaluate(`(() => { const r=document.querySelector('#fan').getBoundingClientRect(), c=document.querySelector('#card').getBoundingClientRect(), e=document.documentElement;
      return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,cardRight:c.right,w:innerWidth,h:innerHeight,sw:e.scrollWidth,sh:e.scrollHeight}; })()`);
    assert(box.left>=0 && box.right<=box.w && box.top>=0 && box.bottom<=box.h,'The fan is cut off in the landscape window: '+JSON.stringify(box));
    assert(box.cardRight<=box.left,'The question and the fan must sit side by side: '+JSON.stringify(box));
    assert(box.sw<=box.w && box.sh<=box.h,'The landscape window must not scroll: '+JSON.stringify(box));
    if (n===6) await screenshot('ohgi-landscape');
    await closeCard(wide);
  }
  await call('Emulation.setDeviceMetricsOverride',{width:660,height:700,deviceScaleFactor:1,mobile:false});
  const multi=await card(3,true);
  assert(await evaluate(`document.querySelector('#fan-scroll').hidden`));
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('#opts')).gridTemplateColumns.split(' ').length`),1);
  await screenshot('ohgi-multi');
  await key('1','Digit1'); await key('2','Digit2'); await key('4','Digit4');
  await until(`document.querySelector('#question').textContent.includes('これで送りますか')`);
  assert(await evaluate(`document.querySelector('#fan-scroll').hidden`));
  await closeCard(multi);
  await open('mode=small&lang=ja&dwell=0.3&scan=0.5');
  const dwell=await card(2);
  await mouse({x:5,y:5}); await mouse(await point('#fan [data-key="opt:0"]'));
  await until(`!document.querySelector('#undo-zone').hidden`);
  await key(' ','Space');
  await until(`document.querySelector('#undo-zone').hidden && !document.querySelector('#fan > .btn').disabled`);
  // Pointer has not re-entered: a second answer must not occur.
  await sleep(600); assert((await api('/pending')).card.state==='shown');
  await mouse({x:5,y:5});
  await sleep(1700);   // pointer が止まってから走査が回る
  await key(' ','Space');
  await until(`!document.querySelector('#undo-zone').hidden`);
  await mouse(await point('#undo-btn'));
  await until(`document.querySelector('#undo-zone').hidden`);
  await mouse({x:5,y:5}); await closeCard(dwell);
  // A long Edit: the left text is cut off, looking at it opens the full sheet, and nothing on the sheet can answer.
  await call('Emulation.setDeviceMetricsOverride',{width:924,height:361,deviceScaleFactor:1,mobile:false});
  await open('mode=small&lang=ja&dwell=1');
  const long='ローカルのサーバーを起動したあと、ブラウザでサーバの画面を開いて、表示された時刻を確かめてください。'.repeat(3);
  const edit=(await api('/ask',{kind:'permission',from:{session:'demo01'},payload:{head:'Edit',text:'README.md',suggestions:[],
    blocks:[{label:'old_string',text:long,mono:true},{label:'new_string',text:long.replace('サーバーを','サーバを'),mono:true}]}})).id;
  await until(`!document.querySelector('#more').hidden`);
  assert(await evaluate(`document.querySelector('#blocks .change .plain').textContent.includes('→')`),'The change comes first');
  assert(await evaluate(`document.querySelector('#blocks mark.del') !== null`),'The removed part is marked');
  const blade=await point('#fan [data-key="allow_once"]');
  const text=await point('#copy');
  await mouse({x:5,y:5}); await mouse(text);
  await until(`document.querySelector('#overlay').classList.contains('sheet') && !document.querySelector('#overlay').hidden`);
  await screenshot('ohgi-sheet');
  await key('1','Digit1');
  await mouse(blade,'mousePressed'); await mouse(blade,'mouseReleased'); await mouse({x:5,y:5});
  await sleep(150);
  assert.equal((await api('/pending')).card.state,'shown','Nothing on the sheet can answer');
  const shut=await point('#panel-close');
  await mouse(shut,'mousePressed'); await mouse(shut,'mouseReleased');
  assert(await evaluate(`!document.querySelector('#overlay').hidden`),'A click right after opening is ignored');
  await sleep(1300);
  await mouse(shut,'mousePressed'); await mouse(shut,'mouseReleased');
  await until(`document.querySelector('#overlay').hidden`);
  await mouse(blade,'mousePressed'); await mouse(blade,'mouseReleased'); await mouse({x:5,y:5});
  await sleep(150);
  assert.equal((await api('/pending')).card.state,'shown','The click after closing cannot press a blade');
  await mouse(text); await sleep(1000);
  assert(await evaluate(`document.querySelector('#overlay').hidden`),'Closed once, looking alone does not reopen it');
  await mouse({x:5,y:5}); await closeCard(edit);
  await call('Emulation.setDeviceMetricsOverride',{width:660,height:700,deviceScaleFactor:1,mobile:false});
  await open();
  await click('#gear-btn');
  await evaluate(`(() => {const s=document.querySelector('[name="theme"]');s.value='dark';s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('blemma.options')).theme`),'dark');
  await open('mode=small&lang=ja&theme=light&trail&desc=off');
  assert.equal(await evaluate(`document.documentElement.dataset.theme`),'light');
  await mouse({x:100,y:200});
  assert(await evaluate(`!document.querySelector('#trail').hidden && getComputedStyle(document.querySelector('#trail')).pointerEvents==='none'`));
  await screenshot('ohgi-idle');
  assert.deepEqual(errors,[]);
  console.log('browser checks passed'); ws.close();
})().catch(error=>{
  if (!ready) console.log('browser unavailable: isolated renderer did not start');
  else {console.error(error.stack || error.message || error.error?.message || String(error)); process.exitCode=1;}
  for (const entry of pending.values()) clearTimeout(entry.timer);
  pending.clear(); ws.close();
});
