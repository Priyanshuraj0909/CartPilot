// Optional real Chrome/CDP walkthrough; disposable release-demo API only.
import { writeFile, mkdir } from 'node:fs/promises';
const frontendUrl=process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5174';
const reportPath='docs/examples/submission-browser.json';
const screenshotDir='docs/screenshots';await mkdir(screenshotDir,{recursive:true});
if(!['127.0.0.1','localhost'].includes(new URL(frontendUrl).hostname))throw new Error('Use a loopback demo frontend.');
const health=await(await fetch('http://127.0.0.1:8012/api/v1/health/detailed')).json();if(health.environment!=='test')throw new Error('Use a disposable test-mode demo.');
const tabs=await (await fetch('http://127.0.0.1:9227/json/list')).json();
const ws=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);
await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
let serial=0,expectedFailure=false;
const waiting=new Map(),consoleErrors=[],networkFailures=[];
ws.addEventListener('message',event=>{
 const data=JSON.parse(event.data);
 if(data.id){const entry=waiting.get(data.id);if(entry){waiting.delete(data.id);data.error?entry.reject(new Error(JSON.stringify(data.error))):entry.resolve(data.result);}}
 if(!expectedFailure&&data.method==='Runtime.exceptionThrown')consoleErrors.push(data.params.exceptionDetails.text);
 if(!expectedFailure&&data.method==='Runtime.consoleAPICalled'&&['error','warning'].includes(data.params.type))consoleErrors.push(data.params.args.map(arg=>arg.value??arg.description).join(' '));
 if(!expectedFailure&&data.method==='Network.responseReceived'&&data.params.response.status>=400)networkFailures.push({url:data.params.response.url,status:data.params.response.status});
});
function call(method,params={}){return new Promise((resolve,reject)=>{const id=++serial;waiting.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));setTimeout(()=>{if(waiting.has(id)){waiting.delete(id);reject(new Error('CDP timeout: '+method));}},12000).unref();});}
async function evaluate(expression){const result=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
async function wait(expression){await evaluate(`new Promise((resolve,reject)=>{const until=Date.now()+10000;const timer=setInterval(()=>{if(${expression}){clearInterval(timer);resolve(true);}else if(Date.now()>until){clearInterval(timer);reject(new Error('UI wait timed out: '+${JSON.stringify(expression)}));}},50);})`);}
async function click(text){await evaluate(`Array.from(document.querySelectorAll('button')).find(button=>button.textContent.trim()===${JSON.stringify(text)})?.click()`);}
async function nav(path){await evaluate(`document.querySelector('nav a[href="${path}"]').click()`);}
async function merchant(label){await evaluate(`(()=>{const select=document.querySelector('select[aria-label="Merchant"]');const option=Array.from(select.options).find(option=>option.textContent===${JSON.stringify(label)});Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(select,option.value);select.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
async function closeDrawer(){await evaluate(`document.querySelector('button[aria-label="Close product details"]')?.click()`);}
const report={pages:[],analyses:[],viewportChecks:[],screenshots:[]};
async function capture(name,full=false,selector=null){await evaluate(`new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);const params={format:'png',captureBeyondViewport:full};if(selector){params.clip=await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1};})()`);}else if(full){const metrics=await call('Page.getLayoutMetrics');params.clip={x:0,y:0,width:metrics.cssContentSize.width,height:metrics.cssContentSize.height,scale:1};}const result=await call('Page.captureScreenshot',params);await writeFile(`${screenshotDir}/${name}`,Buffer.from(result.data,'base64'));report.screenshots.push(name);}
try{
 await call('Runtime.enable');await call('Network.enable');await call('Page.enable');
 await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await call('Page.navigate',{url:frontendUrl+'/dashboard'});
 await wait(`document.querySelector('select[aria-label="Merchant"]')?.options.length===4`);
 for(const path of ['/dashboard','/products','/inventory','/ai-manager','/recommendations','/agent-activity','/approvals','/action-history','/integrations']){
  await nav(path);await wait(`document.querySelector('main h1')?.textContent.length>0`);
  await call('Page.navigate',{url:frontendUrl+path});await wait(`document.querySelector('main h1')?.textContent.length>0`);
  report.pages.push({directNavigation:true,path,title:await evaluate(`document.querySelector('main h1').textContent`)});
 }
 await merchant('Four-product Demo');await nav('/dashboard');await wait(`document.querySelector('main')?.textContent.includes('Wireless Mouse')`);await capture('01_dashboard.png');await nav('/products');await wait(`document.querySelectorAll('tbody tr').length===4`);
 await capture('02_products.png');let agentIndex=4;
 for(const [name,agent] of [['Wireless Mouse','Pricing'],['Wireless Mouse','Restock'],['Bluetooth Speaker Desktop Audio','Promotion'],['Headphones','Listing']]){
  await evaluate(`document.querySelector('button[aria-label="Analyze ${name}"]').click()`);if(agentIndex===4)await capture('03_product_detail.png');await click(`Run ${agent} Analysis`);
  await wait(`document.querySelector('.drawer .recommendation')!==null`);report.analyses.push({agent,result:await evaluate(`document.querySelector('.drawer .recommendation').textContent`)});
  await evaluate(`document.querySelector('.drawer .recommendation').scrollIntoView({block:'end'})`);await capture(`${String(agentIndex++).padStart(2,'0')}_${agent.toLowerCase()}_agent.png`);await closeDrawer();
 }
 await nav('/ai-manager');await click('Analyze Store');await wait(`document.querySelector('.intelligent-plan > .panel')!==null`);
 await capture('08_ai_manager.png');await evaluate(`document.querySelector('.intelligent-plan').scrollIntoView()`);await capture('09_priority_plan.png',true,'ol[aria-label="Priority actions"]');await evaluate(`Array.from(document.querySelectorAll('h2,h3')).find(e=>e.textContent.includes('Conflicts, Synergies'))?.scrollIntoView()`);await capture('10_cross_agent_intelligence.png',true,'.relationship.conflict');
 report.balancedGrowth=await evaluate(`document.querySelector('.intelligent-plan > .panel').textContent`);
 await nav('/products');await wait(`document.querySelectorAll('tbody tr').length===4`);
 await evaluate(`document.querySelector('button[aria-label="Analyze Wireless Mouse"]').click()`);await click('Run Pricing Analysis');await wait(`document.querySelector('.drawer .recommendation')!==null`);
 await click('Create Action for Review');await wait(`document.querySelector('.drawer .action-creation a')!==null`);
 await evaluate(`document.querySelector('.drawer .action-creation a').click()`);await wait(`document.querySelector('.guarded-action')!==null`);
 await capture('11_approval_workflow.png');
 await evaluate(`Array.from(document.querySelectorAll('button')).find(button=>button.textContent.startsWith('Approve Action #')).click()`);
 await wait(`Array.from(document.querySelectorAll('button')).some(button=>button.textContent.startsWith('Execute Approved Action #'))`);
 await evaluate(`Array.from(document.querySelectorAll('button')).find(button=>button.textContent.startsWith('Execute Approved Action #')).click()`);
 await wait(`document.querySelector('.confirmation')!==null`);report.confirmation=await evaluate(`document.querySelector('.confirmation').textContent`);
 await capture('12_execution_confirmation.png');await click('Execute');await wait(`document.querySelector('main')?.textContent.includes('Executed Successfully')`);
 report.execution=await evaluate(`document.querySelector('.guarded-action .action-result').textContent`);
 await nav('/action-history');await wait(`document.querySelector('main')?.textContent.includes('execution completed')`);
 report.auditVisible=true;await capture('13_audit_history.png');
 const blocked=await evaluate(`(async()=>{const ms=await(await fetch('http://127.0.0.1:8012/api/v1/merchants')).json();const mid=ms.find(m=>m.store_name==='Four-product Demo').id;const catalog=await(await fetch('http://127.0.0.1:8012/api/v1/products?merchant_id='+mid)).json();const pid=catalog.products.find(p=>p.name==='Wireless Mouse').id;const rec=await(await fetch('http://127.0.0.1:8012/api/v1/pricing/recommend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_id:pid,merchant_id:mid})})).json();return await(await fetch('http://127.0.0.1:8012/api/v1/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({merchant_id:mid,agent:'pricing',recommendation:{...rec,recommended_price:Number((Number(rec.current_price)*1.5).toFixed(2)),price_change_percent:50}})})).json();})()`);
 if(blocked.status!=='failed'||blocked.policy.is_valid)throw new Error('Unsafe proposal was not blocked');
 report.unsafePolicy={status:blocked.status,valid:blocked.policy.is_valid,violations:blocked.policy.violations};
 await nav('/approvals');await wait(`document.querySelector('main').textContent.includes('Price change exceeds')`);await capture('14_policy_block.png',true);
 await nav('/integrations');await merchant('Shopify Offline Demo');await wait(`document.querySelector('main')?.textContent.includes('Connected. Shopify is the source')`);
 await click('Sync Now');await wait(`document.querySelector('main')?.textContent.includes('Synchronization completed')`);
 await capture('15_shopify_read_only_mock.png');
 report.shopify=await evaluate(`document.querySelector('main').textContent`);
 for(const width of [1440,768,390]){
  await call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width===390});
  report.viewportChecks.push({width,overflow:await evaluate(`document.documentElement.scrollWidth>window.innerWidth`)});
 }
 const screenshot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
 await writeFile('/private/tmp/cartpilot-phase14-mobile.png',Buffer.from(screenshot.data,'base64'));
 expectedFailure=true;await call('Network.setBlockedURLs',{urls:['*127.0.0.1:8012*']});
 await call('Page.reload');await wait(`document.querySelector('main')?.textContent.includes('Connection failed')`);
 report.backendUnavailableHandled=true;
 await call('Network.setBlockedURLs',{urls:[]});
 report.consoleErrors=consoleErrors;report.networkFailures=networkFailures;
 await writeFile(reportPath,JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({screenshots:report.screenshots.length,unsafePolicyBlocked:!report.unsafePolicy.valid,pages:report.pages.length,agents:report.analyses.length,execution:report.auditVisible,shopify:!!report.shopify,backendUnavailable:report.backendUnavailableHandled,consoleErrors,networkFailures,viewportChecks:report.viewportChecks}));
}finally{ws.close();}
