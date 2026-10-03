// Optional real Chrome/CDP walkthrough; disposable release-demo API only.
import { writeFile } from 'node:fs/promises';
const frontendUrl=process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5174';
const reportPath=process.env.DEMO_BROWSER_REPORT || 'docs/examples/release-browser.json';
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
const report={pages:[],analyses:[],viewportChecks:[]};
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
 await merchant('Four-product Demo');await nav('/products');await wait(`document.querySelectorAll('tbody tr').length===4`);
 for(const [name,agent] of [['Wireless Mouse','Pricing'],['Wireless Mouse','Restock'],['Bluetooth Speaker Desktop Audio','Promotion'],['Headphones','Listing']]){
  await evaluate(`document.querySelector('button[aria-label="Analyze ${name}"]').click()`);await click(`Run ${agent} Analysis`);
  await wait(`document.querySelector('.drawer .recommendation')!==null`);report.analyses.push({agent,result:await evaluate(`document.querySelector('.drawer .recommendation').textContent`)});
  await closeDrawer();
 }
 await nav('/ai-manager');await click('Analyze Store');await wait(`document.querySelector('.intelligent-plan > .panel')!==null`);
 report.balancedGrowth=await evaluate(`document.querySelector('.intelligent-plan > .panel').textContent`);
 await nav('/products');await wait(`document.querySelectorAll('tbody tr').length===4`);
 await evaluate(`document.querySelector('button[aria-label="Analyze Wireless Mouse"]').click()`);await click('Run Pricing Analysis');await wait(`document.querySelector('.drawer .recommendation')!==null`);
 await click('Create Action for Review');await wait(`document.querySelector('.drawer .action-creation a')!==null`);
 await evaluate(`document.querySelector('.drawer .action-creation a').click()`);await wait(`document.querySelector('.guarded-action')!==null`);
 await evaluate(`Array.from(document.querySelectorAll('button')).find(button=>button.textContent.startsWith('Approve Action #')).click()`);
 await wait(`Array.from(document.querySelectorAll('button')).some(button=>button.textContent.startsWith('Execute Approved Action #'))`);
 await evaluate(`Array.from(document.querySelectorAll('button')).find(button=>button.textContent.startsWith('Execute Approved Action #')).click()`);
 await wait(`document.querySelector('.confirmation')!==null`);report.confirmation=await evaluate(`document.querySelector('.confirmation').textContent`);
 await click('Execute');await wait(`document.querySelector('main')?.textContent.includes('Executed Successfully')`);
 report.execution=await evaluate(`document.querySelector('.guarded-action .action-result').textContent`);
 await nav('/action-history');await wait(`document.querySelector('main')?.textContent.includes('execution completed')`);
 report.auditVisible=true;
 await nav('/integrations');await merchant('Shopify Offline Demo');await wait(`document.querySelector('main')?.textContent.includes('Connected. Shopify is the source')`);
 await click('Sync Now');await wait(`document.querySelector('main')?.textContent.includes('Synchronization completed')`);
 report.shopify=await evaluate(`document.querySelector('main').textContent`);
 for(const width of [1440,768,390]){
  await call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width===390});
  report.viewportChecks.push({width,overflow:await evaluate(`document.documentElement.scrollWidth>window.innerWidth`)});
 }
 const screenshot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
 await writeFile('/private/tmp/cartpilot-phase12-mobile.png',Buffer.from(screenshot.data,'base64'));
 expectedFailure=true;await call('Network.setBlockedURLs',{urls:['*127.0.0.1:8012*']});
 await call('Page.reload');await wait(`document.querySelector('main')?.textContent.includes('Connection failed')`);
 report.backendUnavailableHandled=true;
 await call('Network.setBlockedURLs',{urls:[]});
 report.consoleErrors=consoleErrors;report.networkFailures=networkFailures;
 await writeFile(reportPath,JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({pages:report.pages.length,agents:report.analyses.length,execution:report.auditVisible,shopify:!!report.shopify,backendUnavailable:report.backendUnavailableHandled,consoleErrors,networkFailures,viewportChecks:report.viewportChecks}));
}finally{ws.close();}
