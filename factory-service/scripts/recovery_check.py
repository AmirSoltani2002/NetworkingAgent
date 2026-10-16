"""Actual container restart/outage checks against isolated *_tests database only."""
import json,subprocess,time,os
from pathlib import Path
from uuid import uuid4
from urllib.parse import quote
from configure import read_env,request,ROOT

env=read_env();compose=['docker','compose','--env-file',str(ROOT/'.env'),'-f',str(ROOT/'factory-service/docker-compose.recovery-tests.yml')]
def command(*args):subprocess.run(compose+list(args),check=True,stdout=subprocess.DEVNULL)
def wait(fn,seconds=90):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except Exception:pass
        time.sleep(1)
    raise AssertionError('Recovery check timed out')
base='http://127.0.0.1:18110';token=env['FACTORY_API_TOKEN']
def state():return request(base,'/api/state',token=token)
def act(kind,args,key=None):return request(base,'/api/actions',{'kind':kind,'arguments':args,'idempotency_key':key or str(uuid4())},token=token)
command('up','-d');s=wait(state,180)
act('reset',{})
act('clock',{'speed':60,'automatic_faults':False,'paused':False});act('fault',{'fault_id':'gearbox_vibration','mode':'sudden'})
key=str(uuid4());result=act('inspect',{'component_id':'gearbox'},key)
wait(lambda:state()['last_inspections'].get('gearbox'))
alarm=wait(lambda:next((a for a in state()['alarms'] if a['agent_task_id'] is None),None))
before=state();command('stop','ml');checkpoint=state()['monitoring']['last_measurement_id']
wait(lambda:state()['monitoring']['status']=='retrying',45)
assert state()['monitoring']['last_measurement_id']==checkpoint
command('restart','factory','database');after=wait(state)
assert after['epoch']==before['epoch'] and after['clock']['elapsed_seconds']>=before['clock']['elapsed_seconds']
assert after['last_inspections']['gearbox']['action_id']==result['action_id']
replay=act('inspect',{'component_id':'gearbox'},key);assert replay['action_id']==result['action_id'] and replay['completed']
command('start','ml');wait(lambda:state()['monitoring']['status']=='ready' and state()['monitoring']['last_measurement_id']>checkpoint)
final=state();assert len(final['alarms'])==1 and final['alarms'][0]['id']==alarm['id']
# Run the actual core PostgreSQL tests on this isolated database. No real core
# tasks, credentials or saved chat records are accessed by these test fixtures.
child=os.environ.copy();child['CORE_TEST_DATABASE_URL']='postgresql://manufacturing:'+quote(env['FACTORY_TEST_DB_PASSWORD'],safe='')+'@127.0.0.1:15437/factory_recovery_tests'
subprocess.run(['node','--test','--test-concurrency=1','core/tests/database.test.cjs','core/tests/tasks-database.test.cjs','core/tests/integration-database.test.cjs'],cwd=ROOT,env=child,check=True)
report={'pass':True,'database':'factory_recovery_tests','epoch':final['epoch'],'inspection_id':result['action_id'],'alarm_id':alarm['id'],'checks':['browser-independent measurements','ML outage retains cursor','factory and database container restart','stable epoch and clock','completed inspection not repeated','pending alarm retained with core unavailable','ML recovers unprocessed measurements','one alarm after replay','core approvals/leases/restart/receipts regression']}
(ROOT/'docs/verification/factory/recovery-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
command('down') # Preserve isolated volumes for inspection; never touch runtime data.
