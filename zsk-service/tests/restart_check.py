"""Actual SIGKILL/container restart, exclusively on zsk_restart_tests."""
import subprocess,json,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
compose=['docker','--config','/tmp/networkagent-docker-config','compose','--env-file','../.env','-f','docker-compose.restart-test.yml']
def run(command):return subprocess.check_output(command,cwd=root,text=True)
def sql(query):return run(['docker','exec','zsk-restart-tests-db-1','psql','-U','manufacturing','-d','zsk_restart_tests','-At','-c',query]).strip()
try:
    subprocess.run(compose+['up','-d','--wait'],cwd=root,check=True)
    code="import os,httpx,json; c=httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,headers={'Authorization':'Bearer '+os.environ['ZSK_ADMIN_API_KEY']}); r=c.post('/api/batch-predictions',json={'idempotency_key':'restart-test-batch-v1','page_size':10});r.raise_for_status();print(json.dumps(r.json()))"
    job=json.loads(run(['docker','exec','zsk-restart-tests-api-1','python','-c',code]))['job_id']
    for _ in range(200):
        progress=int(sql("SELECT progress FROM zsk_jobs WHERE id='"+job+"'"))
        if 3<=progress<1000:break
        time.sleep(.05)
    assert 3<=progress<1000,progress
    run(['docker','kill','--signal','KILL','zsk-restart-tests-api-1'])
    run(['docker','start','zsk-restart-tests-api-1'])
    for _ in range(1000):
        state=sql("SELECT status||':'||attempts FROM zsk_jobs WHERE id='"+job+"'")
        if state.startswith(('completed','failed')):break
        time.sleep(.1)
    assert state=='completed:2',state
    assert sql('SELECT count(*) FROM zsk_predictions')=='1000'
    assert sql('SELECT count(*) FROM zsk_labeled_measurements')=='0'
    assert sql('SELECT count(*) FROM zsk_unlabeled_measurements')=='1000'
    assert sql('SELECT count(*) FROM zsk_models')=='1'
    print(json.dumps({'result':'passed','job_id':job,'checkpoint_before_kill':progress,'final_status':'completed','attempts':2,'predictions':1000,'labels_remaining':0,'model_versions':1}))
finally:
    subprocess.run(compose+['down','-v'],cwd=root,check=True)
