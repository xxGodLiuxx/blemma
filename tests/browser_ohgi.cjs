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
  const virtual = {Enter:13, Escape:27, Backspace:8, ArrowRight:39, ArrowLeft:37, ' ':32}[key] || key.charCodeAt(0);
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
  // With gaze dwell on, holding a button (selecting text, dragging) and resting on a blade must never answer.
  const heldBlade=await point('#fan [data-key="opt:0"]');
  await mouse({x:5,y:5});
  await mouse({x:5,y:5},'mousePressed');
  await mouse({...heldBlade,buttons:1});
  await sleep(700);
  assert.equal((await api('/pending')).card.state,'shown','Dwell does not count while a button is held');
  await mouse(heldBlade,'mouseReleased');
  await sleep(700);
  assert.equal((await api('/pending')).card.state,'shown','After release the blade must be re-entered first');
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
  await click('#gear-btn');                    // The settings need room: the remembered size comes back.
  await until(`window.__sizes.length>=1`);
  await key('Escape');                         // Waiting again in the small window, which is never taken for the full size.
  await until(`window.__sizes.length>=2`);
  const reloaded=await card(2);
  await until(`window.__sizes.length>=3`);
  assert.deepEqual(await evaluate(`window.__sizes`),[outer,[320,120],outer],'After a reload in the waiting size, the settings and the card open at the remembered size');
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
  // Inside one card the person moves on by pressing (Deny, then a reason): those two presses can follow each other
  // at once. The quiet moment is only for a view that changed from the board's side.
  const quick=(await api('/ask',{kind:'permission',from:{cwd:'repo'},payload:{head:'Bash',text:'ls',blocks:[{label:'command',text:'ls',mono:true}]}})).id;
  await until(`document.querySelectorAll('.btn[data-key="deny"]').length === 1`);
  await key('2','Digit2');                       // Deny… opens the reasons (waits for the quiet moment of the new card).
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'1',code:'Digit1',windowsVirtualKeyCode:49});   // The reason, typed right behind it.
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'1',code:'Digit1',windowsVirtualKeyCode:49});
  await until(`!document.querySelector('#undo-zone').hidden`);
  assert.equal((await api('/pending')).card.state,'deciding','Two quick presses inside one card both count');
  await sleep(1050); await api('/wait?id='+quick);
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
  assert.deepEqual(errors,[]);
  console.log('browser checks passed'); ws.close();
})().catch(error=>{
  if (!ready) console.log('browser unavailable: isolated renderer did not start');
  else {console.error(error.stack || error.message || error.error?.message || String(error)); process.exitCode=1;}
  for (const entry of pending.values()) clearTimeout(entry.timer);
  pending.clear(); ws.close();
});
