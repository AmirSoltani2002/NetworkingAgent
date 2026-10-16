"""Requested automated rendered-UI verification and genuine screenshots via CDP."""
import subprocess,time,urllib.request,json,websocket,base64,pathlib,os
os.environ['NO_PROXY']='localhost,127.0.0.1'
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
root=pathlib.Path('docs/verification/factory');root.mkdir(parents=True,exist_ok=True)
p=subprocess.Popen(['/opt/google/chrome/chrome','--headless','--no-sandbox','--no-proxy-server','--disable-dev-shm-usage','--remote-debugging-port=9238','--remote-allow-origins=*','--user-data-dir=/tmp/factory-ui-test-browser','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(50):
  try:tabs=json.load(urllib.request.urlopen('http://127.0.0.1:9238/json',timeout=1));break
  except Exception:time.sleep(.2)
 ws=websocket.create_connection(next(t for t in tabs if t['type']=='page')['webSocketDebuggerUrl'],origin='http://127.0.0.1:9238',timeout=10);seq=0;errors=[]
 def call(method,params=None):
  global seq
  seq+=1;ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
  while True:
   r=json.loads(ws.recv())
   if r.get('method')=='Runtime.exceptionThrown':errors.append(r['params']['exceptionDetails'].get('text','UI exception'))
   if r.get('id')==seq:
    if 'error' in r:raise RuntimeError(r['error'])
    return r.get('result',{})
 def evaluate(code):return call('Runtime.evaluate',{'expression':code,'returnByValue':True}).get('result',{}).get('value')
 def wait(code):
  for _ in range(60):
   if evaluate(code):return
   time.sleep(.2)
  raise AssertionError('UI condition did not appear')
 def click(text):
  assert evaluate('(()=>{const b=Array.from(document.querySelectorAll("button")).find(b=>b.textContent.trim()==='+json.dumps(text)+');if(b){b.click();return true;}return false;})()'),text
 def shot(name):
  data=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})['data'];(root/name).write_bytes(base64.b64decode(data))
 call('Runtime.enable');call('Emulation.setDeviceMetricsOverride',{'width':1600,'height':1000,'deviceScaleFactor':1,'mobile':False});call('Page.navigate',{'url':'http://127.0.0.1:8080'})
 wait('!!document.querySelector("textarea")')
 evaluate('(()=>{const t=document.querySelector("textarea");Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set.call(t,"Factory navigation preserves this draft");t.dispatchEvent(new Event("input",{bubbles:true}));})()')
 click('Factory Simulation');wait('!!document.querySelector("canvas")');wait('document.querySelector(".factory-live")?.textContent==="Live"');time.sleep(.6);shot('factory-running.png')
 bounds=evaluate('(()=>{const r=document.querySelector("canvas").getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};})()')
 x=bounds['x']+320/1280*bounds['width'];y=bounds['y']+350/640*bounds['height']
 for kind in ['mousePressed','mouseReleased']:call('Input.dispatchMouseEvent',{'type':kind,'x':x,'y':y,'button':'left','clickCount':1})
 wait('!!document.querySelector(".factory-inspector")');shot('factory-component.png')
 click('Machine Monitoring');wait('!!document.querySelector(".factory-trends")');time.sleep(.7);shot('factory-monitoring.png')
 click('Simulation Settings');wait('!!document.querySelector(".factory-injection")');shot('factory-settings.png')
 click('Alarms');wait('document.querySelector(".factory-workspace h1")?.textContent==="Alarms"');shot('factory-alarms.png')
 click('← Back to chat');assert evaluate('document.querySelector("textarea").value')=='Factory navigation preserves this draft'
 click('Factory Simulation');wait('!!document.querySelector("canvas")');time.sleep(.5)
 call('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False});time.sleep(.3);shot('factory-1280.png')
 assert not errors,errors
 (root/'browser-check.json').write_text(json.dumps({'pass':True,'websocket_live':True,'component_click':True,'chat_draft_preserved':True,'console_exceptions':errors,'screenshots':6},indent=2));print('PASS: rendered Phaser, live WS, component click, monitoring/settings/alarms, preserved draft; no runtime exceptions.')
 ws.close()
finally:p.terminate();p.wait(timeout=10)
