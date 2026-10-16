"""Run after starting the test-only fixture container. Requires Docker CLI."""
import json, subprocess, time, urllib.request, os
from pathlib import Path
BASE=os.environ.get('RESTART_FIXTURE_URL','http://127.0.0.1:18098')
CONTAINER=os.environ.get('RESTART_FIXTURE_CONTAINER','meta-harness-task-restart-test')
URL=BASE+'/state'
def state():
    with urllib.request.urlopen(URL,timeout=3) as response:return json.load(response)
def wait(predicate,seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            current=state()
            if predicate(current):return current
        except Exception:pass
        time.sleep(.25)
    raise AssertionError('Fixture did not reach required checkpoint')
wait(lambda s:s['task']['status']=='PENDING')
with urllib.request.urlopen(BASE+'/begin',timeout=3) as response:response.read()
before=wait(lambda s:s['count']==1 and any(o['action'].get('tool')=='verify_record' and o['status']=='DISPATCHING' for o in s['task']['operations']))
assert before['task']['status']=='RUNNING'
subprocess.run(['docker','kill','--signal','KILL',CONTAINER],check=True,capture_output=True)
subprocess.run(['docker','start',CONTAINER],check=True,capture_output=True)
after=wait(lambda s:s['task']['status']=='COMPLETED',90)
assert after['count']==1,'Completed write was replayed'
writes=[o for o in after['task']['operations'] if o['action'].get('tool')=='write_record']
assert len(writes)==1 and writes[0]['attempts']==1
reads=[o for o in after['task']['operations'] if o['action'].get('tool')=='verify_record']
assert len(reads)==1 and reads[0]['attempts']==2
assert all(v['passed'] for v in after['task']['verifications'][-1:])
result={'scenario':'real container SIGKILL during read, after completed MCP write','before_status':before['task']['status'],'after_status':after['task']['status'],'write_count':after['count'],'write_attempts':writes[0]['attempts'],'read_attempts':reads[0]['attempts'],'verified':True}
Path(os.environ.get('RESTART_REPORT_PATH','docs/verification/task-restart.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
