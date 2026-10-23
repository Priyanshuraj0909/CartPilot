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
    if await js(expression):return
    await asyncio.sleep(.1)
   raise AssertionError('Timed out: '+expression)
  async def click(text):
   await js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+"); if(!b) throw Error('Missing button'); b.click();})()")
  await call('Runtime.enable');await call('Page.enable')
  await call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
  await call('Page.navigate',{'url':f'http://127.0.0.1:5177/shop/{merchant}'})
  await until("document.querySelectorAll('.buyer-product').length===6")
  Path(ROOT/'docs/screenshots/16_buyer_storefront.png').write_bytes(base64.b64decode((await call('Page.captureScreenshot',{'captureBeyondViewport':False}))['data']))
  await js("(()=>{const s=document.querySelector('.buyer-quantity select');const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;setter.call(s,'1');s.dispatchEvent(new Event('change',{bubbles:true}));})()")
  await until("!([...document.querySelectorAll('button')].find(b=>b.textContent==='Review server-priced cart')).disabled")
  await click('Review server-priced cart');await until("document.body.innerText.includes('Approve this cart')")
  await click('Approve this cart');await until("document.body.innerText.includes('Confirm simulation')")
  await click('Confirm simulation');await until("document.body.innerText.includes('Simulation recorded.')")
  assert await js("document.body.innerText.includes('Audit chain verified')")
  await call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
  await asyncio.sleep(.3)
  mobile_overflow=await js('document.documentElement.scrollWidth>window.innerWidth')
  Path(ROOT/'docs/screenshots/17_buyer_mobile.png').write_bytes(base64.b64decode((await call('Page.captureScreenshot',{'captureBeyondViewport':False}))['data']))
  await call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1100,'deviceScaleFactor':1,'mobile':False})
  await js('sessionStorage.setItem("cartpilot-token",'+json.dumps(identity['token'])+')')
  await call('Page.navigate',{'url':'http://127.0.0.1:5177/growth'})
  await until("document.body.innerText.includes('Merchant controls')")
  Path(ROOT/'docs/screenshots/18_growth_console.png').write_bytes(base64.b64decode((await call('Page.captureScreenshot',{'captureBeyondViewport':False}))['data']))
  report={'storefront_products':6,'simulation_flow':'passed','audit_chain':'verified','mobile_width':390,'mobile_horizontal_overflow':mobile_overflow,'growth_console':'passed','runtime_exceptions':failures,'data':'disposable synthetic SQLite account and catalog; no external providers'}
  (ROOT/'docs/examples/commerce-browser.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report))
  assert not mobile_overflow and not failures
asyncio.run(main())
