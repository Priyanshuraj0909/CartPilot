"""Real Chrome/CDP shopping walkthrough. Use only a disposable test database.

Requires the existing backend development dependencies (websockets) and an isolated
Chrome profile on port 9227; backend 8017 and frontend 5177. Never targets cloud URLs.
"""
import asyncio,base64,json,secrets,time,urllib.request
from pathlib import Path
import httpx,websockets
ROOT=Path(__file__).resolve().parents[1]
async def main():
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8017') as api:
  health = await api.get('/api/v1/health/detailed')
  if health.json().get('environment') != 'test':
   raise RuntimeError('Browser helper requires a disposable test-mode backend on port 8017.')
  r=await api.post('/api/v1/auth/signup',json={'name':'CartPilot Studio','store_name':'The Everyday Edit','email':f'preview-{secrets.token_hex(4)}@example.test','password':secrets.token_urlsafe(24)})
  r.raise_for_status();identity=r.json();merchant=identity['user']['merchant_id'];headers={'Authorization':'Bearer '+identity['token']}
  r=await api.post('/api/v1/commerce/catalog/import',headers=headers,json={'csv_text':(ROOT/'docs/examples/commerce-catalog.csv').read_text()});r.raise_for_status()
  r=await api.put('/api/v1/commerce/policy',headers=headers,json={'published':True,'max_spend_paise':1000000,'blocked_categories':[],'boosted_product_ids':[]});r.raise_for_status()
  r=await api.put('/api/v1/commerce/merchant/rules',headers=headers,json={'compatibility':[], 'growth_rules':[{'id':'browser-offer','kind':'recovery_offer','category':'Electronics','discount_percent':10,'enabled':True}], 'scheduler_enabled':False,'interval_seconds':300});r.raise_for_status()
 targets=json.load(urllib.request.urlopen('http://127.0.0.1:9227/json'))
 target=next(t for t in targets if t['type']=='page')
 async with websockets.connect(target['webSocketDebuggerUrl'],max_size=20_000_000) as ws:
  sequence=0;failures=[]
  async def call(method,params=None):
   nonlocal sequence
   sequence+=1;request_id=sequence
   await ws.send(json.dumps({'id':request_id,'method':method,'params':params or {}}))
   while True:
    response=json.loads(await ws.recv())
    if response.get('method')=='Runtime.exceptionThrown':failures.append(response['params']['exceptionDetails'].get('text'))
    if response.get('id')==request_id:
     if 'error' in response:raise RuntimeError(response['error'])
     return response.get('result',{})
  async def js(expression):
   result=await call('Runtime.evaluate',{'expression':expression,'awaitPromise':True,'returnByValue':True})
   if 'exceptionDetails' in result:raise RuntimeError(result['exceptionDetails'])
   return result.get('result',{}).get('value')
  async def until(expression):
   for _ in range(100):
    if await js("Boolean("+expression+")"):return
    await asyncio.sleep(.1)
   raise AssertionError('Timed out: '+expression)
  async def click(text):
   await js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+"); if(!b) throw Error('Missing button'); b.click();})()")

  async def fill(label,value):
   await js("(()=>{const e=document.querySelector('[aria-label='+"+json.dumps(json.dumps(label))+"+']');if(!e)throw Error('Missing input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,"+json.dumps(value)+");e.dispatchEvent(new Event('input',{bubbles:true}));})()")
  async def capture(name):
   await asyncio.sleep(.2)
   (ROOT/'docs/screenshots'/name).write_bytes(base64.b64decode((await call('Page.captureScreenshot',{'captureBeyondViewport':False}))['data']))
  await call('Runtime.enable');await call('Page.enable')
  await call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
  await js('window.__workflowNavigationMarker=1')
  await call('Page.navigate',{'url':f'http://127.0.0.1:5177/shop/{merchant}'})
  await until("window.__workflowNavigationMarker===undefined && document.querySelectorAll('.buyer-product').length===6")
  await click('Chat with CartPilot · saved carts')
  await until("document.querySelector('[aria-label=\"Message to shopping assistant\"]') && ![...document.querySelectorAll('button')].find(b=>b.textContent==='Send message').disabled")
  await fill('Message to shopping assistant','add a mouse and a journal under ₹2,000')
  await click('Send message')
  await until("document.querySelectorAll('.buyer-cart-detail .buyer-cart-line').length===2")
  await js('window.scrollTo(0,500)')
  await capture('19_conversational_shopping.png')
  await click('Check recovery offer')
  await until("document.body.innerText.includes('Accept recovery offer as new draft')")
  await click('Accept recovery offer as new draft')
  await until("document.querySelector('.buyer-total strong')?.textContent.includes('1,108.10')")
  await click('Approve this cart')
  await until("document.body.innerText.includes('Confirm simulation')")
  await click('Confirm simulation')
  await until("document.body.innerText.includes('Simulation recorded.')")
  await click('Recovery, cancellation & refunds')
  await until("document.querySelector('[aria-label=\"Refund amount in INR\"]')")
  await fill('Refund amount in INR','1.00')
  await js("document.querySelector('.cart-resolution input[type=checkbox]').click()")
  await click('Confirm refund')
  await until("document.body.innerText.includes('refund: succeeded')")
  await js("document.querySelector('.cart-resolution input[type=checkbox]').click()")
  await click('Confirm return review')
  await until("document.body.innerText.includes('return review: review required')")
  await js("document.querySelector('.cart-resolution').scrollIntoView({block:'start'})")
  await capture('20_refund_return_review.png')
  await js('window.__workflowNavigationMarker=1')
  await call('Page.reload')
  await until("window.__workflowNavigationMarker===undefined && document.querySelectorAll('.buyer-product').length===6")
  await click('Chat with CartPilot · saved carts')
  await until("document.querySelectorAll('.buyer-chat-log article').length===2")
  await js("document.querySelector('.buyer-chat details').open=true;[...document.querySelectorAll('.buyer-chat details button')].find(b=>b.textContent.startsWith('simulated ·')).click()")
  await until("document.querySelector('.buyer-status')?.textContent==='simulated'")
  await call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
  await asyncio.sleep(.2)
  overflow=await js('document.documentElement.scrollWidth>window.innerWidth')
  assert not overflow
  await call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
  await js('sessionStorage.setItem("cartpilot-token",'+json.dumps(identity['token'])+')')
  await js('window.__workflowNavigationMarker=1')
  await call('Page.navigate',{'url':'http://127.0.0.1:5177/growth'})
  await until("window.__workflowNavigationMarker===undefined && document.body.innerText.includes('Commerce Studio')")
  await click('Manage growth rules')
  await until("document.body.innerText.includes('Save growth controls')")
  await click('Compare baseline and hybrid')
  await until("document.body.innerText.includes('Ranking comparison only;')")
  await click('Transaction ledger')
  await until("document.body.innerText.includes('Scoped transaction ledger')")
  await js("document.querySelector('.commerce-studio').scrollIntoView({block:'start'})")
  await capture('21_commerce_studio.png')
  report={'multi_item_chat':'passed','recovery_discount':'passed','separate_approval_and_simulation':'passed','partial_refund':'passed','return_review_without_automatic_refund':'passed','session_restore':'passed','mobile_horizontal_overflow':overflow,'merchant_ranking_preview_and_ledger':'passed','runtime_exceptions':failures,'data':'synthetic test database; no external providers or real money'}
  (ROOT/'docs/examples/commerce-workflows-browser.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report))
  assert not failures
asyncio.run(main())
