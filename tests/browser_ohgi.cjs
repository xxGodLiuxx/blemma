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
// Right after the view changes the page counts no press for a moment (a late press must not land on the new card).
// The page marks that moment on the body, so every press here waits until it is over.
const READY=`!document.body.classList.contains('settling')`;
async function key(key, code = key) {
  await until(READY);
  const virtual = {Enter:13, Escape:27, Backspace:8, Tab:9, ArrowRight:39, ArrowLeft:37, ' ':32}[key] || key.charCodeAt(0);
  await call('Input.dispatchKeyEvent', {type:'keyDown', key, code, windowsVirtualKeyCode:virtual});
  await call('Input.dispatchKeyEvent', {type:'keyUp', key, code, windowsVirtualKeyCode:virtual});
}
async function point(selector) {
  return evaluate(`(() => { const b=document.querySelector(${JSON.stringify(selector)}), r=b.getBoundingClientRect(), s=getComputedStyle(b);
    const lx=parseFloat(s.getPropertyValue('--lx')), ly=parseFloat(s.getPropertyValue('--ly'));
    const k=b.offsetWidth ? r.width/b.offsetWidth : 1;   // The fan follows the window, so the label is scaled too.
    return Number.isFinite(lx) ? {x:r.x+lx*k, y:r.y+ly*k} : {x:r.x+r.width/2,y:r.y+r.height/2}; })()`);
}
async function mouse(p, type='mouseMoved') { if (type==='mousePressed') await until(READY); await call('Input.dispatchMouseEvent', {type, ...p, ...(type==='mouseMoved'?{}:{button:'left',clickCount:1})}); }
async function click(selector) { await until(READY); const p=await point(selector); await mouse(p,'mousePressed'); await mouse(p,'mouseReleased'); }
async function screenshot(name) {
  const data = await call('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
  fs.writeFileSync(path.join(config.output,name+'.png'),Buffer.from(data.data,'base64'));
}
const WAITING=`document.querySelector('#text') && document.querySelector('#text').textContent.length > 0`;
const FIRST_BLADE=`document.querySelectorAll('.btn[data-key="opt:0"]').length === 1`;
async function open(query='mode=small&lang=ja&dwell=0', ready=WAITING) {
  // The same address again is only a jump inside the page (the part after #), not a reload: go through a blank page.
  await call('Page.navigate', {url:'about:blank'});
  await call('Page.navigate', {url:config.origin+'/?'+query+'#t=ohgi-browser-test'});
  await until(ready);
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
  // Waiting: only the closed fan shows, with the state written on it. A card opens the fan.
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('#closed')).display`),'flex');
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('#fan-scroll')).display`),'none');
  await until(`document.querySelector('#closed-state').textContent.length > 0`);
  for (const n of [2,3,4,6]) {
    const id=await card(n);
    await until(`document.querySelectorAll('#fan > .btn').length === ${n+2}`);
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('#closed')).display`),'none');
    const geometry=await evaluate(`Array.from(document.querySelectorAll('#fan > .btn')).map(b=>{const s=getComputedStyle(b),r=b.getBoundingClientRect();
      const k=r.width/b.offsetWidth,x=r.x+parseFloat(s.getPropertyValue('--lx'))*k,y=r.y+parseFloat(s.getPropertyValue('--ly'))*k;
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
      const k=r.width/b.offsetWidth;
      return document.elementFromPoint(r.x+parseFloat(s.getPropertyValue('--lx'))*k,r.y+parseFloat(s.getPropertyValue('--ly'))*k)?.closest('button')===b;})`);
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
  // With gaze dwell on, holding a button (selecting text) and resting on a blade must never answer.
  // The press starts on the question text. A press on the fan background grabs the window instead: while it drags, the
  // page only moves the window and never sees the pointer reach the blade, so these checks would pass with no guard.
  const textAt=await point('#question'), heldBlade=await point('#fan [data-key="opt:0"]');
  assert(await evaluate(`(() => { const e=document.elementFromPoint(${textAt.x},${textAt.y});
    return !!e?.closest('#question') && !e.closest('#fan-scroll, #closed, [data-key]'); })()`),'The press starts on the question text, not on the fan background');
  await mouse(textAt);
  await mouse(textAt,'mousePressed');
  await mouse({...heldBlade,buttons:1});
  // Read at once: a pointer that rests for 1.5 s lets the scan light the blades, which shows the same description.
  assert((await evaluate(`document.querySelector('#spot-desc').textContent`)).includes('既存の説明 1'),'The page sees the held pointer on the blade');
  await sleep(700);
  assert.equal((await api('/pending')).card.state,'shown','Dwell does not count while a button is held');
  await mouse(heldBlade,'mouseReleased');
  await sleep(700);
  assert.equal((await api('/pending')).card.state,'shown','After release the blade must be re-entered first');
  // Re-entering = off the blades for longer than the 150 ms a gaze may shake off a blade's edge.
  await mouse({x:5,y:5}); await sleep(300); await mouse(heldBlade);
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
  // Long text sits on the washi above the fan and pages with "more". One click on a blade only selects it.
  await call('Emulation.setDeviceMetricsOverride',{width:624,height:688,deviceScaleFactor:1,mobile:false});
  await open('mode=small&lang=ja&dwell=0');
  const long='ローカルのサーバーを起動したあと、ブラウザでサーバの画面を開いて、表示された時刻を確かめてください。'.repeat(6);
  const edit=(await api('/ask',{kind:'permission',from:{session:'demo01'},payload:{head:'Edit',text:'README.md',suggestions:[],
    blocks:[{label:'old_string',text:long,mono:true},{label:'new_string',text:long.replace('サーバーを','サーバを'),mono:true}]}})).id;
  await until(`!document.querySelector('#more').hidden`);
  assert(await evaluate(`document.querySelector('#blocks .change .plain').textContent.includes('→')`),'The change comes first');
  assert(await evaluate(`document.querySelector('#blocks mark.del') !== null`),'The removed part is marked');
  const paper=await evaluate(`(() => { const t=document.querySelector('.top').getBoundingClientRect(), c=document.querySelector('#card').getBoundingClientRect(), f=document.querySelector('#fan').getBoundingClientRect();
    return {paperTop:t.top,cardBottom:c.bottom,fanTop:f.top,fanBottom:f.bottom,h:innerHeight,sh:document.documentElement.scrollHeight}; })()`);
  assert(paper.fanBottom<=paper.paperTop,'The fan sits above the washi: '+JSON.stringify(paper));
  assert(paper.cardBottom<=paper.h && paper.fanTop>=0 && paper.sh<=paper.h,'Nothing is cut off: '+JSON.stringify(paper));
  await screenshot('ohgi-washi');
  // Dragging the window bigger makes the fan and the text follow; the fan never leaves the window.
  const small=await evaluate(`[document.querySelector('#fan').getBoundingClientRect().width, parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font'))]`);
  await call('Emulation.setDeviceMetricsOverride',{width:900,height:1000,deviceScaleFactor:1,mobile:false});
  await until(`document.querySelector('#fan').getBoundingClientRect().width > ${small[0]*1.2}`);
  const big=await evaluate(`(() => { const f=document.querySelector('#fan').getBoundingClientRect(); return {w:f.width,right:f.right,bottom:f.bottom,iw:innerWidth,ih:innerHeight,font:parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font'))}; })()`);
  assert(big.right<=big.iw && big.bottom<=big.ih,'The bigger fan stays inside: '+JSON.stringify(big));
  assert(big.font>small[1],'The text follows the window');
  await call('Emulation.setDeviceMetricsOverride',{width:624,height:688,deviceScaleFactor:1,mobile:false});
  await until(`Math.abs(document.querySelector('#fan').getBoundingClientRect().width-${small[0]})<1`);
  const top0=await evaluate(`document.querySelector('#copy').scrollTop`);
  await click('#more');
  assert((await evaluate(`document.querySelector('#copy').scrollTop`))>top0,'More pages the text');
  // Resting the pointer on "more" pages on its own, and the arrow key pages too.
  await mouse({x:5,y:5}); await evaluate(`document.querySelector('#copy').scrollTop=0`);
  await mouse(await point('#more'));
  await until(`document.querySelector('#copy').scrollTop>0`);
  await mouse({x:5,y:5}); await evaluate(`document.querySelector('#copy').scrollTop=0`);
  await key('ArrowDown');
  assert((await evaluate(`document.querySelector('#copy').scrollTop`))>0,'The arrow key pages the text');
  // Dragging the fan background moves the window and never answers.
  await evaluate(`window.moveTo=(x,y)=>{window.__moved=[x,y];}`);
  const hub=await evaluate(`(() => { const r=document.querySelector('#fan').getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height*0.62}; })()`);
  await mouse(hub); await mouse(hub,'mousePressed');
  await mouse({x:hub.x+40,y:hub.y+20,buttons:1});   // A real mouse reports the held button while it drags.
  await mouse({x:hub.x+40,y:hub.y+20},'mouseReleased');
  assert(await evaluate(`Array.isArray(window.__moved)`),'Dragging the fan background moves the window');
  await evaluate(`window.__moved=null`);
  await mouse({x:hub.x+80,y:hub.y+20});
  assert.equal(await evaluate(`window.__moved`),null,'The drag ends with the button');
  assert.equal((await api('/pending')).card.state,'shown','Dragging never answers');
  // On a 150% screen the browser grows the window by a pixel on every move to an odd position: the drag only moves
  // to positions the screen can show exactly, and a window that grew anyway goes back to the size it was grabbed at.
  const size=await evaluate(`[window.outerWidth, window.outerHeight]`);
  await evaluate(`window.__keep={ow:Object.getOwnPropertyDescriptor(window,'outerWidth'),dpr:Object.getOwnPropertyDescriptor(window,'devicePixelRatio'),resize:window.resizeTo};
    Object.defineProperty(window,'devicePixelRatio',{value:1.5,configurable:true}); window.__moves=[]; window.__resized=[];
    window.moveTo=(x,y)=>window.__moves.push([x,y]); window.resizeTo=(w,h)=>window.__resized.push([w,h]); 0`);
  await mouse(hub); await mouse(hub,'mousePressed');
  for (const d of [[11,7],[23,9],[37,15]]) await mouse({x:hub.x+d[0],y:hub.y+d[1],buttons:1});
  const moves=await evaluate(`window.__moves`);
  assert(moves.length>=3 && moves.every(p=>p[0]%2===0 && p[1]%2===0),'A drag on a 150% screen moves to even positions only: '+JSON.stringify(moves));
  assert.deepEqual(await evaluate(`window.__resized`),[],'A window that kept its size is left alone');
  await evaluate(`Object.defineProperty(window,'outerWidth',{value:${size[0]+9},configurable:true}); 0`);
  await mouse({x:hub.x+41,y:hub.y+15,buttons:1});
  assert.deepEqual(await evaluate(`window.__resized`),[size],'A window that grew during the drag goes back to its size');
  await evaluate(`window.__resized=[]; Object.defineProperty(window,'outerWidth',{value:${size[0]+2},configurable:true}); 0`);
  await mouse({x:hub.x+41,y:hub.y+15},'mouseReleased');
  assert.deepEqual(await evaluate(`window.__resized`),[size],'Letting go puts the last pixels back');
  await evaluate(`for (const [k,d] of [['outerWidth',window.__keep.ow],['devicePixelRatio',window.__keep.dpr]]) { if (d) Object.defineProperty(window,k,d); else delete window[k]; }
    window.resizeTo=window.__keep.resize; window.__moved=null; window.moveTo=(x,y)=>{window.__moved=[x,y];}; 0`);
  assert.deepEqual(await evaluate(`[window.outerWidth, window.outerHeight]`),size,'The test put the real window size back');
  assert.equal((await api('/pending')).card.state,'shown','A drag on a 150% screen never answers either');
  // The copy button copies the whole text and never answers.
  await evaluate(`Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:t=>{window.__copied=t;return Promise.resolve();}}})`);
  await click('#copy-btn');
  await until(`document.querySelector('#copy-btn').textContent==='コピーしました'`);
  const copied=await evaluate(`window.__copied`);
  assert(copied.includes('old_string: ローカル') && copied.includes('new_string: ローカル') && !copied.includes('→'),'The whole text is copied');
  await key('c','KeyC');
  assert.equal((await api('/pending')).card.state,'shown','Copying never answers');
  const blade=await point('#fan [data-key="allow_once"]');
  await mouse(blade); await mouse(blade,'mousePressed'); await mouse(blade,'mouseReleased');
  await sleep(150);
  assert.equal((await api('/pending')).card.state,'shown','One click only selects');
  assert(await evaluate(`document.querySelector('#fan [data-key="allow_once"]').classList.contains('armed')`));
  await sleep(1600);
  assert(await evaluate(`!document.querySelector('#fan [data-key="allow_once"]').classList.contains('armed')`),'The selection lapses');
  await mouse(blade,'mousePressed'); await mouse(blade,'mouseReleased');
  await sleep(150);
  assert.equal((await api('/pending')).card.state,'shown','A lapsed selection does not confirm');
  // A redraw between the two clicks (a new card, a state change, a setting) clears the selection:
  // the click that follows only selects again, however soon it comes.
  const theme=await evaluate(`document.documentElement.dataset.theme`);
  await evaluate(`document.querySelector('#theme-btn').focus()`);
  assert.equal(await evaluate(`document.activeElement.id`),'theme-btn');
  await key('Enter');
  await until(`document.documentElement.dataset.theme !== ${JSON.stringify(theme)}`);
  await mouse(blade,'mousePressed'); await mouse(blade,'mouseReleased');
  await sleep(150);
  assert.equal((await api('/pending')).card.state,'shown','A redraw clears the selection: one click still only selects');
  await mouse(blade,'mousePressed'); await mouse(blade,'mouseReleased');
  await until(`!document.querySelector('#undo-zone').hidden`);
  await key('Escape');
  await until(`document.querySelector('#undo-zone').hidden && !document.querySelector('#fan > .btn').disabled`);
  // A key press on a page button keeps the focus where the person put it. Pressing the theme button twice (change it,
  // change it back) must not send the second press to the first blade (Allow), where the focus used to jump.
  await evaluate(`document.querySelector('#theme-btn').focus()`);
  const themeNow=await evaluate(`document.documentElement.dataset.theme`);
  await key('Enter');
  await until(`document.documentElement.dataset.theme !== ${JSON.stringify(themeNow)}`);
  assert.equal(await evaluate(`document.activeElement.id`),'theme-btn','The focus stays on the button the person pressed');
  await key('Enter');                            // key() waits until presses count again.
  await until(`document.documentElement.dataset.theme === ${JSON.stringify(themeNow)}`);
  await sleep(150);
  assert.equal((await api('/pending')).card.state,'shown','The second press on the theme button does not answer the card');
  await mouse({x:5,y:5}); await closeCard(edit);
  // In an app window the waiting fan is a small window, and the next card brings the remembered size back.
  const stubs=`window.matchMedia=()=>({matches:true}); window.__sizes=[]; window.__ops=[]; window.resizeTo=(w,h)=>{window.__sizes.push([w,h]);window.__ops.push('resize');Object.defineProperty(window,'outerWidth',{value:w,configurable:true});Object.defineProperty(window,'outerHeight',{value:h,configurable:true});}; window.moveTo=()=>window.__ops.push('move');`;
  await evaluate(stubs);
  const outer=await evaluate(`[window.outerWidth, window.outerHeight]`);
  const first=await card(2);
  await sleep(200);
  assert.deepEqual(await evaluate(`window.__sizes`),[],'A card that arrives before any size is known keeps the window as it is');
  await closeCard(first);
  await until(`window.__sizes.length>=1`);
  assert.deepEqual(await evaluate(`window.__sizes[0]`),[320,120],'Waiting shrinks to the closed fan');
  // Shrinking resizes first and moves second: a large window moved into the corner is pushed back by the screen edge.
  assert.deepEqual(await evaluate(`window.__ops`),['resize','move'],'Shrink, then move into the corner');
  const again=await card(2);
  await until(`window.__sizes.length>=2`);
  assert.deepEqual(await evaluate(`window.__sizes[1]`),outer,'The next card brings the remembered size back');
  assert.deepEqual(await evaluate(`window.__ops.slice(2)`),['move','resize'],'Move back first, then grow');
  await closeCard(again);
  // A reload while the window is the small waiting fan must not take that size for the full one.
  await open();
  await evaluate(stubs+`Object.defineProperty(window,'outerWidth',{value:320,configurable:true}); Object.defineProperty(window,'outerHeight',{value:120,configurable:true}); 0`);
  // The page fits the window on its next side tick (every 0.25 s): idle in the waiting size, it stays the waiting size.
  // Wait for that fit first, so the order below does not depend on whether the click or the tick comes first.
  await until(`window.__sizes.length>=1`);
  await click('#gear-btn');                    // The settings need room: the remembered size comes back.
  await until(`window.__sizes.length>=2`);
  await key('Escape');                         // Waiting again in the small window, which is never taken for the full size.
  await until(`window.__sizes.length>=3`);
  const reloaded=await card(2);
  await until(`window.__sizes.length>=4`);
  assert.deepEqual(await evaluate(`window.__sizes`),[[320,120],outer,[320,120],outer],'After a reload in the waiting size, the settings and the card open at the remembered size');
  await closeCard(reloaded);
  // A reload in the middle of a card keeps the window the user made larger: the size remembered before is not forced back.
  const kept=await card(2);
  await evaluate(`window.__mark=1; sessionStorage.setItem('blemma.full','500,600'); 0`);
  await open(undefined, FIRST_BLADE);          // The card is still waiting on the board: the page comes back with it.
  assert.equal(await evaluate(`window.__mark`),undefined,'open() really loads the page again');
  await evaluate(stubs);
  await sleep(400);
  assert.deepEqual(await evaluate(`window.__ops`),[],'A reload during a card leaves the window as it is');
  await closeCard(kept);
  // While the page is still loading the window reports no size at all: nothing may move it then (it would jump to a screen corner).
  await open();
  await evaluate(stubs+`Object.defineProperty(window,'outerWidth',{value:0,configurable:true}); Object.defineProperty(window,'outerHeight',{value:0,configurable:true}); 0`);
  const early=await card(2);
  await sleep(500);
  assert.deepEqual(await evaluate(`window.__ops`),[],'No window size yet: the window is left alone');
  await evaluate(`Object.defineProperty(window,'outerWidth',{value:320,configurable:true}); Object.defineProperty(window,'outerHeight',{value:120,configurable:true}); 0`);
  await until(`window.__sizes.length>=1`);                 // The next tick picks it up once the size is known.
  await closeCard(early);
  // A press right behind a change of the view is not counted: a late press meant for the view before, or a bouncing
  // switch, must not land on what just appeared. Here: the answer is in, the Undo band has just come up, and a second
  // press arrives at once. It must not undo the answer; the same key does once the page counts presses again.
  await open();
  const bounce=await card(2);
  await key('1','Digit1');
  await until(`!document.querySelector('#undo-zone').hidden`);
  assert((await evaluate(`document.querySelector('#undo-btn').getAttribute('aria-label')||''`)).startsWith('取り消す'),'In the fan the Undo target has a spoken name');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await sleep(150);
  assert.equal((await api('/pending')).card.state,'deciding','A press right behind the answer does not undo it');
  await key('Escape');                           // key() waits for the page to count presses again.
  await until(`document.querySelector('#undo-zone').hidden`);
  assert.equal((await api('/pending')).card.state,'shown','The same key undoes once the moment is over');
  await closeCard(bounce);
  // Inside one card the person moves on by pressing (Deny, then a reason). Typed by number, a press that names where it
  // goes, those two presses can follow each other at once.
  const quick=(await api('/ask',{kind:'permission',from:{cwd:'repo'},payload:{head:'Bash',text:'ls',blocks:[{label:'command',text:'ls',mono:true}]}})).id;
  await until(`document.querySelectorAll('.btn[data-key="deny"]').length === 1`);
  await key('2','Digit2');                       // Deny… opens the reasons (waits for the quiet moment of the new card).
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'1',code:'Digit1',windowsVirtualKeyCode:49});   // The reason, typed right behind it.
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'1',code:'Digit1',windowsVirtualKeyCode:49});
  await until(`!document.querySelector('#undo-zone').hidden`);
  assert.equal((await api('/pending')).card.state,'deciding','Two quick presses inside one card both count');
  await sleep(1050); await api('/wait?id='+quick);
  await until(`document.body.classList.contains('idle')`);
  // Enter on the focused button is different: where it goes depends on what has the focus. Deny… then Back by Enter, and
  // a second Enter 30 ms behind it (a bounce, or a press made again). Back puts the focus where the person came from
  // (Deny…), and a press right behind a step inside the card is not counted: it must not send the Allow of the first screen.
  const enter={key:'Enter',code:'Enter',windowsVirtualKeyCode:13};
  const twice=(await api('/ask',{kind:'permission',from:{cwd:'repo'},payload:{head:'Bash',text:'ls',blocks:[{label:'command',text:'ls',mono:true}]}})).id;
  await until(`document.querySelectorAll('.btn[data-key="deny"]').length === 1`);
  await key('2','Digit2');                       // Deny… opens the reasons.
  await until(`document.querySelectorAll('[data-key="back"]').length === 1`);
  await evaluate(`document.querySelector('[data-key="back"]').focus()`);
  await until(READY);                            // A press that goes by the focus is not counted right behind a step made by number.
  await call('Input.dispatchKeyEvent',{type:'keyDown',...enter}); await call('Input.dispatchKeyEvent',{type:'keyUp',...enter});   // Back.
  await sleep(30);
  await call('Input.dispatchKeyEvent',{type:'keyDown',...enter}); await call('Input.dispatchKeyEvent',{type:'keyUp',...enter});   // The second Enter.
  await sleep(300);
  assert.equal((await api('/pending')).card.state,'shown','An Enter right behind Back does not land on Allow');
  assert.equal(await evaluate(`document.querySelectorAll('[data-key="back"]').length`),0,'Back returned to the first screen');
  assert.equal(await evaluate(`document.activeElement.dataset.key`),'deny','Back puts the focus on Deny…, where the person came from');
  await key('Enter');                            // Later (key() waits for the quiet moment), Enter on Deny… opens the reasons again.
  await until(`document.querySelectorAll('[data-key="back"]').length === 1`);
  assert.equal((await api('/pending')).card.state,'shown','Enter on Deny… only opens the reasons');
  await closeCard(twice);
  // Where the key focus goes when a card gives way to the next one. Answering card after card by Enter is unchanged:
  // the person answered by their own press, so the page puts the focus on the first blade of the next card as before.
  const perm=text=>({kind:'permission',from:{cwd:'repo'},payload:{head:'Bash',text,blocks:[{label:'command',text,mono:true}]}});
  const shows=text=>`document.querySelector('#text').textContent===${JSON.stringify(text)} && document.querySelectorAll('.btn[data-key="deny"]').length===1 && ${READY}`;
  const focusOn=key=>evaluate(`document.querySelector('#fan [data-key="${key}"]').focus()`);
  const focused=()=>evaluate(`document.activeElement===document.body ? 'body' : (document.activeElement.dataset.key||document.activeElement.id||document.activeElement.localName)`);
  const twoCards=async()=>[(await api('/ask',perm('A-card'))).id,(await api('/ask',perm('B-card'))).id];
  const [own1,own2]=await twoCards();
  await until(shows('A-card'));
  await key('Tab');                              // The person uses the keys.
  await focusOn('allow_once');
  await key('Enter');                            // Answers the first card.
  await until(`!document.querySelector('#undo-zone').hidden`);
  await sleep(1050);
  assert.deepEqual((await api('/wait?id='+own1)).answer,{type:'allow_once'},'The first card is answered by Enter');
  await until(shows('B-card'));
  assert.equal(await focused(),'allow_once','After the person\'s own answer the next card gets the key focus on its first blade');
  await key('Enter');                            // The same key answers the second card too.
  await until(`!document.querySelector('#undo-zone').hidden`);
  await sleep(1050);
  assert.deepEqual((await api('/wait?id='+own2)).answer,{type:'allow_once'},'Enter answers card after card');
  await until(`document.body.classList.contains('idle')`);
  // Another page answers the card while the key focus rests on its Deny…: this page takes that focus away, so it must
  // not put it on the first blade (Allow) of the next card. An Enter meant for the Deny… of the card before sends nothing.
  const [other1,other2]=await twoCards();
  await until(shows('A-card'));
  await key('Tab');
  await focusOn('deny');
  const seq=(await api('/pending')).card.view_seq;
  await api('/answer',{id:other1,seq,choice:{type:'allow_once'},by:'click'});   // Not from this page.
  await until(`!document.querySelector('#undo-zone').hidden`);
  await sleep(1050); await api('/wait?id='+other1);
  await until(shows('B-card'));
  await sleep(600);
  assert.equal(await focused(),'body','A card answered elsewhere leaves the key focus nowhere on the next card');
  await call('Input.dispatchKeyEvent',{type:'keyDown',...enter}); await call('Input.dispatchKeyEvent',{type:'keyUp',...enter});   // The late Enter.
  await sleep(300);
  assert.equal((await api('/pending')).card.state,'shown','A late Enter does not land on the Allow of the next card');
  await key('Tab');                              // Moving the focus by Tab is the person's own doing again.
  await closeCard(other2);
  // Undo left unpressed: the key focus rests on Undo, the grace runs out and the page hides the button. The focus the
  // page took away does not turn up on the first blade of the next card, and a late Enter (meant as Undo) sends nothing.
  const [undo1,undo2]=await twoCards();
  await until(shows('A-card'));
  await key('1','Digit1');                       // Allow, by number.
  await until(`!document.querySelector('#undo-zone').hidden && !document.querySelector('#undo-btn').disabled`);
  await evaluate(`document.querySelector('#undo-btn').focus()`);
  assert.equal(await focused(),'undo','The Undo target takes the key focus');
  await sleep(1050); await api('/wait?id='+undo1);
  await until(shows('B-card'));
  await sleep(600);
  assert.equal(await focused(),'body','The focus the page took from Undo does not move to the next card');
  await call('Input.dispatchKeyEvent',{type:'keyDown',...enter}); await call('Input.dispatchKeyEvent',{type:'keyUp',...enter});
  await sleep(300);
  assert.equal((await api('/pending')).card.state,'shown','A late Enter meant as Undo does not land on the Allow of the next card');
  await key('Tab');
  await closeCard(undo2);
  // In the fan every redraw puts the Undo target back into the fan, which drops its focus before the page could see it
  // there. Another page takes the answer back while the key focus rests on Undo: the focus that went away with the
  // redraw must not turn up on the first blade of the card that follows.
  const [re1,re2]=await twoCards();
  await until(shows('A-card'));
  await key('1','Digit1');                       // Allow, by number.
  await until(`!document.querySelector('#undo-zone').hidden && !document.querySelector('#undo-btn').disabled`);
  await evaluate(`document.querySelector('#undo-btn').focus()`);
  await api('/undo',{id:re1,by:'click'});        // Not from this page.
  await until(`document.querySelector('#undo-zone').hidden && !document.querySelector('.btn[data-key="deny"]').disabled && ${READY}`);
  assert.equal(await focused(),'body','Undo by another page leaves the key focus nowhere');
  const seq2=(await api('/pending')).card.view_seq;
  await api('/answer',{id:re1,seq:seq2,choice:{type:'allow_once'},by:'click'});   // …and answers the card again.
  await until(`!document.querySelector('#undo-zone').hidden`);
  await sleep(1050); await api('/wait?id='+re1);
  await until(shows('B-card'));
  await sleep(600);
  assert.equal(await focused(),'body','The focus a redraw took from Undo does not move to the next card');
  await call('Input.dispatchKeyEvent',{type:'keyDown',...enter}); await call('Input.dispatchKeyEvent',{type:'keyUp',...enter});
  await sleep(300);
  assert.equal((await api('/pending')).card.state,'shown','A late Enter does not land on the Allow of the next card after a redraw took the focus');
  await key('Tab');
  await closeCard(re2);
  // The top buttons (theme, always on top) are hidden by CSS while the small window waits. A key focus resting on one of
  // them goes away with the last card: it must not turn up on the first blade of the card that comes next.
  const top1=(await api('/ask',perm('A-card'))).id;
  await until(shows('A-card'));
  await key('Tab');
  await evaluate(`document.querySelector('#theme-btn').focus()`);
  assert.equal(await focused(),'theme','The theme button takes the key focus');
  const seq3=(await api('/pending')).card.view_seq;
  await api('/answer',{id:top1,seq:seq3,choice:{type:'allow_once'},by:'click'});   // Answered elsewhere.
  await until(`!document.querySelector('#undo-zone').hidden`);
  await sleep(1050); await api('/wait?id='+top1);
  await until(`document.body.classList.contains('idle')`);
  await sleep(100);
  assert.equal(await focused(),'body','The waiting window hides the top buttons, and the focus on one of them goes away');
  const top2=(await api('/ask',perm('B-card'))).id;
  await until(shows('B-card'));
  await sleep(600);
  assert.equal(await focused(),'body','A focus hidden with the waiting window does not move to the next card');
  await call('Input.dispatchKeyEvent',{type:'keyDown',...enter}); await call('Input.dispatchKeyEvent',{type:'keyUp',...enter});
  await sleep(300);
  assert.equal((await api('/pending')).card.state,'shown','An Enter meant for a hidden top button does not land on the Allow of the next card');
  await closeCard(top2);
  // From a switch the same two presses are different: the second is a bounce, not a choice on a screen the person has
  // seen. Deny… then Back, and a press 50 ms behind it, must not land on Allow, the first blade of the screen they return to.
  const space={key:' ',code:'Space',windowsVirtualKeyCode:32};
  const lit=async key=>{ for (let i=0;i<400;i++) { if (await evaluate(`!!document.querySelector('[data-key="${key}"].scan')`)) return; await sleep(20); } throw new Error('The scan light never reached '+key); };
  await open('mode=small&lang=ja&dwell=0&scan=0.5');
  const sw=(await api('/ask',{kind:'permission',from:{cwd:'repo'},payload:{head:'Bash',text:'ls',blocks:[{label:'command',text:'ls',mono:true}]}})).id;
  await until(`document.querySelectorAll('.btn[data-key="deny"]').length === 1`);
  await lit('deny');
  await key(' ','Space');                        // Deny… opens the reasons.
  await until(`document.querySelectorAll('[data-key="back"]').length === 1`);
  await lit('back');
  await call('Input.dispatchKeyEvent',{type:'keyDown',...space}); await call('Input.dispatchKeyEvent',{type:'keyUp',...space});   // Back.
  await sleep(50);
  await call('Input.dispatchKeyEvent',{type:'keyDown',...space}); await call('Input.dispatchKeyEvent',{type:'keyUp',...space});   // The bounce.
  await sleep(300);
  assert.equal(await evaluate(`document.querySelectorAll('.btn[data-key="deny"]').length`),1,'Back returned to the first screen');
  assert.equal((await api('/pending')).card.state,'shown','A switch bounce right behind Back does not land on Allow');
  await closeCard(sw);
  // With both dwell and scan on, the scan light scrolls a long list to the button it lights. A pointer left resting
  // between two buttons must not, by dwell, press the button that scrolls in under it: nobody pressed anything.
  await open('mode=small&lang=ja&dwell=0.5&scan=0.5');
  const many=(await api('/ask',{kind:'elicitation',from:{cwd:'repo'},payload:{head:'blemma',text:'どれにしますか',fields:[{name:'choice',title:'どれにしますか',multi:false,required:true,
    options:Array.from({length:12},(_,i)=>({label:'選択肢 '+(i+1)+' — 長めの文を入れて釦の高さを確かめる',value:String(i+1)}))}]}})).id;
  await until(`document.querySelectorAll('#opts .btn').length >= 12 && ${READY}`);
  const list=await evaluate(`(() => { const bs=Array.from(document.querySelectorAll('#opts .btn')).map(b => { const r=b.getBoundingClientRect(); return {top:r.top,bottom:r.bottom,x:r.left+r.width/2}; }); return {h:innerHeight,bs}; })()`);
  const seen=list.bs.filter(b=>b.top>=0&&b.bottom<=list.h);
  let rest=null;
  for (let i=seen.length-2;i>=1&&!rest;i--) { const gap=seen[i+1].top-seen[i].bottom; if (gap>=4) rest={x:seen[i].x,y:seen[i].bottom+gap/2}; }
  assert(rest && list.bs[list.bs.length-1].bottom>list.h,'The list is longer than the window and has a gap to rest the pointer in');
  await mouse(rest);
  let moved=false;
  for (let i=0;i<500&&!moved;i++) { moved=Math.abs((await evaluate(`document.querySelector('#opts .btn').getBoundingClientRect().top`))-list.bs[0].top)>2; if (!moved) await sleep(30); }
  assert(moved,'The scan light scrolled the list');
  await sleep(2000);                             // Four dwell times with the pointer left where it was.
  assert.equal((await api('/pending')).card.state,'shown','A button that scrolls in under a resting pointer is not pressed');
  await key('Escape');
  await until(`!document.querySelector('#undo-zone').hidden`);
  await sleep(1050); await api('/wait?id='+many);
  await until(`document.body.classList.contains('idle')`);
  // Assistive technology (a screen reader's "activate", voice control) presses with a click that carries no pointer.
  // It counts as one press, like a key: no second press is asked for, and the Undo period still follows.
  const assist=await card(2);
  await until(READY);
  await evaluate(`document.querySelector('.btn[data-key="opt:0"]').click()`);
  await until(`!document.querySelector('#undo-zone').hidden`);
  assert.equal((await api('/pending')).card.state,'deciding','A click without a pointer answers in one press');
  await sleep(1050); await api('/wait?id='+assist);
  await until(`document.body.classList.contains('idle')`);
  // A long "don't ask again" rule: the full text under the fan grows up to four lines, so its end
  // (how far the rule is saved) is not cut off.
  const longRule=(await api('/ask',{kind:'permission',from:{cwd:'repo'},payload:{head:'Bash',text:'npm run test:unit -- --watch=false',
    suggestions:[{type:'addRules',rules:[{toolName:'Bash',ruleContent:'npm run test:unit -- --watch=false:*'}],behavior:'allow',destination:'projectSettings'}],
    blocks:[{label:'command',text:'npm run test:unit -- --watch=false',mono:true}]}})).id;
  await until(`document.querySelectorAll('#fan [data-key="sugg:0"]').length === 1`);
  await mouse(await point('#fan [data-key="sugg:0"]'));
  await until(`document.querySelector('#spot-label').textContent.includes('commit')`);
  const spot=await evaluate(`(() => { const b=document.querySelector('#spotlight'); return [b.scrollHeight, b.clientHeight]; })()`);
  assert(spot[0]<=spot[1]+1,'The full text of a long rule is not cut off: '+JSON.stringify(spot));
  // With forced colours (a Windows contrast theme) background pictures are dropped: the blade under the pointer
  // keeps its own highlight colours instead of vanishing into the others.
  await call('Emulation.setEmulatedMedia',{features:[{name:'forced-colors',value:'active'}]});
  assert.equal(await evaluate(`getComputedStyle(document.querySelector('#fan [data-key="sugg:0"]')).forcedColorAdjust`),'none','With forced colours the blade under the pointer keeps a visible highlight');
  await call('Emulation.setEmulatedMedia',{features:[{name:'forced-colors',value:'none'}]});
  await mouse({x:5,y:5});
  await closeCard(longRule);
  // A wheel scrolls an element: in a wide window the list of a card that does not fit the fan is its own scrolling box,
  // and the scroll event of an element does not bubble (only a capturing listener hears it). A pointer resting in a gap
  // must not, by dwell, press the button the wheel brings under it.
  await call('Emulation.setDeviceMetricsOverride',{width:940,height:370,deviceScaleFactor:1,mobile:false});
  await open('mode=small&lang=ja&dwell=0.5');
  const wheel=(await api('/ask',{kind:'elicitation',from:{cwd:'repo'},payload:{head:'blemma',text:'どれにしますか',fields:[{name:'choice',title:'どれにしますか',multi:false,required:true,
    options:Array.from({length:12},(_,i)=>({label:'選択肢 '+(i+1)+' — 長めの文を入れて釦の高さを確かめる',value:String(i+1)}))}]}})).id;
  await until(`document.querySelectorAll('#opts .btn').length >= 12 && ${READY}`);
  const grid=await evaluate(`(() => { const o=document.querySelector('#opts'), r=o.getBoundingClientRect();
    const bs=Array.from(o.querySelectorAll('.btn')).map(b=>{const q=b.getBoundingClientRect();return {top:q.top,bottom:q.bottom,left:q.left,right:q.right};});
    return {scrolls:o.scrollHeight>o.clientHeight+2 && getComputedStyle(o).overflowY==='auto', top:r.top, bottom:r.bottom, bs}; })()`);
  assert(grid.scrolls,'In a wide window the list is its own scrolling box: '+JSON.stringify(grid));
  const column=grid.bs.filter(b=>b.left===grid.bs[0].left && b.top>=grid.top && b.bottom<=grid.bottom).sort((a,b)=>a.top-b.top);
  let gapAt=null;
  for (let i=0;i+1<column.length&&!gapAt;i++) { const g=column[i+1].top-column[i].bottom; if (g>=4) gapAt={x:(column[i].left+column[i].right)/2,y:column[i].bottom+g/2,pitch:column[i+1].top-column[i].top}; }
  assert(gapAt,'The list has a gap between two rows to rest the pointer in: '+JSON.stringify(grid));
  await mouse({x:gapAt.x,y:gapAt.y});
  await sleep(800);                              // Resting in the gap presses nothing.
  assert.equal((await api('/pending')).card.state,'shown','Resting in a gap presses nothing');
  await call('Input.dispatchMouseEvent',{type:'mouseWheel',x:gapAt.x,y:gapAt.y,deltaX:0,deltaY:Math.round(gapAt.pitch/2)});
  await until(`document.querySelector('#opts').scrollTop>0`);
  await sleep(300);
  assert(await evaluate(`!!document.elementFromPoint(${gapAt.x},${gapAt.y})?.closest('#opts .btn')`),'The wheel brought a button under the resting pointer');
  await sleep(1500);                             // Three dwell times with the pointer left where it was.
  assert.equal((await api('/pending')).card.state,'shown','A button the wheel scrolls in under a resting pointer is not pressed');
  await key('Escape');
  await until(`!document.querySelector('#undo-zone').hidden`);
  await sleep(1050); await api('/wait?id='+wheel);
  await until(`document.body.classList.contains('idle')`);
  // The text size fitted to the window survives the replies of window calls (clear=on asks the board to cut the window).
  await call('Emulation.setDeviceMetricsOverride',{width:900,height:1000,deviceScaleFactor:1,mobile:false});
  await open('mode=small&lang=ja&dwell=0&clear=on&font=1.3');
  const fitted=await card(2);
  await sleep(500);
  const font=await evaluate(`parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font'))`);
  assert(font>1.35,'A window reply must not reset the fitted text size: '+font);
  await closeCard(fitted);
  await call('Emulation.setDeviceMetricsOverride',{width:660,height:700,deviceScaleFactor:1,mobile:false});
  await open();
  await click('#gear-btn');
  await evaluate(`(() => {const s=document.querySelector('[name="theme"]');s.value='dark';s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('blemma.options')).theme`),'dark');
  // The washi follows the theme.
  await open('mode=small&lang=ja&theme=dark');
  const darkPaper=await evaluate(`getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()`);
  await open('mode=small&lang=ja&theme=light&trail&desc=off');
  assert.equal(await evaluate(`document.documentElement.dataset.theme`),'light');
  assert.notEqual(await evaluate(`getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()`),darkPaper);
  await mouse({x:100,y:200});
  assert(await evaluate(`!document.querySelector('#trail').hidden && getComputedStyle(document.querySelector('#trail')).pointerEvents==='none'`));
  await screenshot('ohgi-idle');
  // While the scan light runs, the blade under a resting pointer (:hover) and the blade with the key focus (:focus-visible)
  // must not look like the light: the next switch press goes to the lit blade only. All three looked the same (final
  // debugging, round 1 #3), so a late press meant for the blade the person saw lit could send Allow.
  await call('Emulation.setDeviceMetricsOverride',{width:640,height:720,deviceScaleFactor:1,mobile:false});
  await open('mode=small&lang=ja&dwell=0&scan=1.5&theme=light&trail=off');
  const runs=(await api('/ask',perm('scan-light'))).id;
  await until(shows('scan-light'));
  const bladeOf=key=>`document.querySelector('#fan [data-key="${key}"]')`;
  // A point inside a blade, on the line from the pivot through its mark, dr fan pixels out from the mark (the fan is scaled).
  const inside=(key,dr)=>evaluate(`(() => { const b=${bladeOf(key)}, r=b.getBoundingClientRect(), s=getComputedStyle(b), k=r.width/b.offsetWidth;
    const lx=parseFloat(s.getPropertyValue('--lx')), ly=parseFloat(s.getPropertyValue('--ly')), cx=parseFloat(s.getPropertyValue('--cx')), cy=parseFloat(s.getPropertyValue('--cy'));
    const t=1+${dr}/Math.hypot(lx-cx,ly-cy);
    return {x:Math.round(r.x+(cx+(lx-cx)*t)*k), y:Math.round(r.y+(cy+(ly-cy)*t)*k)}; })()`);
  // The colour really painted at a point = a 1x1 screenshot. In a one-pixel PNG every row filter leaves the pixel as it is.
  const paint=async p=>{
    const png=Buffer.from((await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false,clip:{x:p.x,y:p.y,width:1,height:1,scale:1}})).data,'base64');
    const idat=[];
    for (let at=8; at<png.length; ) { const n=png.readUInt32BE(at); if (png.toString('ascii',at+4,at+8)==='IDAT') idat.push(png.subarray(at+8,at+8+n)); at+=12+n; }
    const row=require('zlib').inflateSync(Buffer.concat(idat)); return [row[1],row[2],row[3]];
  };
  const apart=(a,b)=>Math.max(...a.map((v,i)=>Math.abs(v-b[i])));
  const look=key=>evaluate(`(() => { const b=${bladeOf(key)}, s=getComputedStyle(b), a=getComputedStyle(b.querySelector('.dwell-arc path'));
    return {lit:b.classList.contains('scan'), bg:s.backgroundImage, color:s.backgroundColor, ring:parseFloat(a.strokeDashoffset)===0}; })()`);
  // The moment the light is on `on`: how `on` and `other` look, and the colour painted inside each.
  const compare=async(on,other)=>{
    await lit(on);
    const seen={on:await look(on), other:await look(other), fill:[await paint(await inside(on,-30)),await paint(await inside(other,-30))]};
    assert(await evaluate(`${bladeOf(on)}.classList.contains('scan')`),'The looks were taken while the light was still on '+on);
    return seen;
  };
  await mouse(await point('#fan [data-key="deny"]'));     // The pointer rests on 二 (Deny…).
  await until(`!document.querySelector('#fan .scan')`);   // A moving pointer stops the light.
  for (const on of ['allow_once','fixed','terminal','allow_once']) {   // 1.5 s after it stops the light runs from 一 round to 一.
    const seen=await compare(on,'deny');
    assert(seen.on.lit && seen.on.bg!=='none','The lit blade shows the light: '+JSON.stringify(seen));
    assert.equal(seen.other.bg,'none','While the light runs, the blade under the pointer does not light up: '+JSON.stringify(seen));
    assert(apart(...seen.fill)>60,'The lit blade and the blade under the pointer are painted apart: '+JSON.stringify(seen));
  }
  await mouse({x:5,y:5});                                  // The pointer leaves the fan,
  await until(`!document.querySelector('#fan .scan')`);
  await key('ArrowRight'); await key('ArrowRight');        // and the key focus moves to 二 (Deny…).
  assert.equal(await evaluate(`document.activeElement.dataset.key`),'deny');
  assert(await evaluate(`document.activeElement.matches(':focus-visible')`),'The key focus is shown');
  {
    const seen=await compare('allow_once','deny');
    const ring=[await paint(await inside('deny',43)), seen.fill[1]];   // On the outer edge of 二, and inside it.
    assert.equal(seen.other.bg,'none','While the light runs, the key focus does not take the fill of the light: '+JSON.stringify(seen));
    assert(seen.other.ring && apart(...ring)>60,'The key focus shows as a ring along the outer edge: '+JSON.stringify([seen,ring]));
    assert(apart(...seen.fill)>60,'The lit blade and the blade with the key focus are painted apart: '+JSON.stringify(seen));
  }
  // With forced colours (a Windows contrast theme) the light keeps the system highlight; the key focus and the pointer do not.
  await call('Emulation.setEmulatedMedia',{features:[{name:'forced-colors',value:'active'}]});
  {
    const seen=await compare('fixed','deny');              // The key focus is still on 二.
    assert(seen.other.ring && seen.on.color!==seen.other.color && apart(...seen.fill)>60,'With forced colours the key focus is not the light: '+JSON.stringify(seen));
  }
  await evaluate(`document.activeElement.blur()`);
  await mouse(await point('#fan [data-key="deny"]'));     // The pointer rests on 二 again.
  await until(`!document.querySelector('#fan .scan')`);
  {
    const seen=await compare('allow_once','deny');
    assert(seen.on.color!==seen.other.color && apart(...seen.fill)>60,'With forced colours the blade under the pointer is not the light: '+JSON.stringify(seen));
  }
  await call('Emulation.setEmulatedMedia',{features:[{name:'forced-colors',value:'none'}]});
  await mouse({x:5,y:5}); await closeCard(runs);
  // The terminal's habit: there "No" is the third line, reached by ↓↓Enter. With the key focus in the fan the same keys reach
  // "don't ask again" (a rule saved for good). Enter / Space on the focus takes two presses there, like a number: one alone
  // only selects it, and the same key again within 1.5 s confirms.
  await call('Emulation.setDeviceMetricsOverride',{width:660,height:700,deviceScaleFactor:1,mobile:false});
  await open();
  const habit=(await api('/ask',{kind:'permission',from:{cwd:'repo'},payload:{head:'Bash',text:'git status',
    suggestions:[{type:'addRules',rules:[{toolName:'Bash',ruleContent:'git status'}],behavior:'allow',destination:'localSettings'}],
    blocks:[{label:'command',text:'git status',mono:true}]}})).id;
  await until(`document.querySelectorAll('#fan [data-key="sugg:0"]').length === 1 && document.querySelector('#more').hidden`);
  await click('#head');                          // The person clicks the fan window (not a blade) to type into it.
  await key('ArrowDown'); await key('ArrowDown');
  assert.equal(await evaluate(`document.activeElement.dataset.key`),'sugg:0','↓↓ reaches "don\'t ask again" in the fan');
  await key('Enter');
  await sleep(300);
  assert.equal((await api('/pending')).card.state,'shown','One Enter on "don\'t ask again" only selects it');
  assert(await evaluate(`document.querySelector('#fan [data-key="sugg:0"]').classList.contains('armed')`),'The blade shows it is selected');
  await key('Enter');                            // The same key again confirms.
  await until(`!document.querySelector('#undo-zone').hidden`);
  assert.deepEqual((await api('/pending')).card.choice,{type:'allow_always',suggestion:0},'Two Enters confirm it');
  await key('Escape');                           // Undo, then answer at the terminal.
  await until(`document.querySelector('#undo-zone').hidden && !document.querySelector('#fan > .btn').disabled`);
  await closeCard(habit);
  // A line that comes or goes above the buttons ("1 waiting" in the header, "cannot reach the board" in the status line)
  // moves the column under a pointer left where it was. Nobody looked at the button that comes under it: dwell must not
  // press it (the same guard as a scrolled list). Moving out and back in counts again.
  await call('Emulation.setDeviceMetricsOverride',{width:640,height:720,deviceScaleFactor:1,mobile:false});
  await open('mode=small&lang=ja&dwell=1');
  const seven=(await api('/ask',{kind:'elicitation',from:{cwd:'repo'},payload:{head:'blemma',text:'どれにしますか',fields:[{name:'choice',title:'どれにしますか',multi:false,required:true,
    options:Array.from({length:7},(_,i)=>({label:'選択肢 '+(i+1),value:String(i+1)}))}]}})).id;
  await until(`document.querySelectorAll('#opts .btn').length>=7 && ${READY}`);
  await mouse({x:5,y:5});
  const rowTop=await evaluate(`document.querySelector('#opts [data-key="opt:1"]').getBoundingClientRect().top`);
  const edge={x:200,y:rowTop+5};
  await mouse(edge);                             // On the top edge of the second choice.
  await sleep(600);
  const later=(await api('/ask',{kind:'question',from:{session:'other'},payload:{questions:[{header:'次',question:'次の問い',multiSelect:false,options:[{label:'a'},{label:'b'}]}]}})).id;
  await until(`document.querySelector('#queue').textContent.length>0`);
  assert(await evaluate(`document.querySelector('#opts [data-key="opt:1"]').getBoundingClientRect().top`)>edge.y,'"1 waiting" moved the column down');
  assert.equal(await evaluate(`document.elementFromPoint(${edge.x},${edge.y})?.closest('[data-key]')?.dataset.key`),'opt:0','The first choice came under the resting pointer');
  await sleep(1500);
  const rested=(await api('/pending')).card;
  assert.equal(rested.state,'shown','A button the column moves under a resting pointer is not pressed: '+JSON.stringify(rested.choice));
  await mouse({x:5,y:5}); await sleep(300); await mouse(edge);   // Out and back in: dwell counts again.
  await until(`!document.querySelector('#undo-zone').hidden`);
  assert.equal((await api('/pending')).card.state,'deciding','Looking at it again presses it');
  await mouse({x:5,y:5});
  await sleep(1050); await api('/wait?id='+seven);
  await until(`document.querySelectorAll('#fan .btn[data-key="opt:0"]').length===1`);
  await closeCard(later);
  // The large board in a narrow window: "cannot reach the board" pushes the column down, and reconnecting pulls it back
  // up. A pointer resting in the gap between Allow and "don't ask again" ends up on "don't ask again" (a rule saved for good).
  await open('mode=large&lang=ja&dwell=2');
  const wired=(await api('/ask',{kind:'permission',from:{cwd:'repo'},payload:{head:'Bash',text:'ls',
    suggestions:[{type:'addRules',rules:[{toolName:'Bash',ruleContent:'ls'}],behavior:'allow',destination:'localSettings'}],
    blocks:[{label:'command',text:'ls',mono:true}]}})).id;
  await until(`document.querySelectorAll('#opts [data-key="sugg:0"]').length===1 && ${READY}`);
  await mouse({x:5,y:5});
  const colTop=await evaluate(`document.querySelector('#opts').getBoundingClientRect().top`);
  await call('Network.enable');
  await call('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await until(`document.querySelector('#status').textContent.length>0`);
  assert(await evaluate(`document.querySelector('#opts').getBoundingClientRect().top`)>colTop+5,'The status line moved the column down');
  const between=await evaluate(`(() => { const a=document.querySelector('#opts [data-key="allow_once"]').getBoundingClientRect(), s=document.querySelector('#opts [data-key="sugg:0"]').getBoundingClientRect();
    return {x:a.left+a.width/2, y:(a.bottom+s.top)/2}; })()`);
  await mouse(between);                          // Resting in the gap presses nothing.
  await sleep(500);
  await call('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await call('Network.disable');
  for (let i=0; i<300 && await evaluate(`document.querySelector('#status').textContent.length>0`); i++) await sleep(20);
  assert.equal(await evaluate(`document.elementFromPoint(${between.x},${between.y})?.closest('[data-key]')?.dataset.key`),'sugg:0','Back online, "don\'t ask again" came under the resting pointer');
  await sleep(2600);                             // More than the dwell time with the pointer left where it was.
  const still=(await api('/pending')).card;
  assert.equal(still.state,'shown','A button the column moves under a resting pointer is not pressed, not even "don\'t ask again": '+JSON.stringify(still.choice));
  await mouse({x:5,y:5});
  await closeCard(wired);
  // Resting the pointer on "▼ more" pages by itself (after 0.35 s, then every 1.5 s, and it stops at the end). With dwell on,
  // the dwell on "more" must not page a second time on top of that: the text would jump on (two pages 0.65 s apart) or, at
  // the end, go back to the top while the person is still reading.
  await call('Emulation.setDeviceMetricsOverride',{width:624,height:688,deviceScaleFactor:1,mobile:false});
  for (const d of [1,2]) {
    await open('mode=small&lang=ja&dwell='+d);
    for (const lines of [80,10]) {
      const text=Array.from({length:lines},(_,i)=>'echo line '+(i+1)).join('\n');
      const paged=(await api('/ask',{kind:'permission',from:{cwd:'repo'},payload:{head:'Bash',text:'run the script',blocks:[{label:'command',text,mono:true}]}})).id;
      await until(`!document.querySelector('#more').hidden && ${READY}`);
      await sleep(900);
      await mouse({x:5,y:5});
      await evaluate(`(() => { const c=document.querySelector('#copy'); window.__pages=[];
        if (window.__pager) c.removeEventListener('scroll',window.__pager);   // One listener per page, card after card.
        window.__pager=()=>window.__pages.push([Math.round(performance.now()),c.scrollTop]);
        c.addEventListener('scroll',window.__pager,{passive:true}); })()`);
      await mouse(await point('#more'));
      await sleep(4300);
      const pages=await evaluate(`window.__pages`);
      await mouse({x:5,y:5});
      const gaps=pages.slice(1).map((p,i)=>p[0]-pages[i][0]);
      assert(pages.length>=1 && pages[0][1]>0,'Resting on "more" pages the text: '+JSON.stringify(pages));
      if (lines===80) assert(pages.length>=2,'A long text keeps paging while the pointer rests on "more": '+JSON.stringify(pages));
      assert(gaps.every(g=>g>=1400),'Dwell '+d+': "more" pages at most every 1.5 s, not twice in a row: '+JSON.stringify(pages));
      assert(pages.every(p=>p[1]>0),'Dwell '+d+': resting on "more" never sends the text back to the top: '+JSON.stringify(pages));
      await closeCard(paged);
    }
  }
  assert.deepEqual(errors,[]);
  console.log('browser checks passed'); ws.close();
})().catch(error=>{
  if (!ready) console.log('browser unavailable: isolated renderer did not start');
  else {console.error(error.stack || error.message || error.error?.message || String(error)); process.exitCode=1;}
  for (const entry of pending.values()) clearTimeout(entry.timer);
  pending.clear(); ws.close();
});
