"""Start a real automatic demonstration; never manually creates an agent task."""
import argparse,json,time
from uuid import uuid4
from pathlib import Path
from configure import read_env,request

parser=argparse.ArgumentParser();parser.add_argument('--timeout-seconds',type=int,default=600);parser.add_argument('--core-url',default='http://127.0.0.1:8000/api');parser.add_argument('--output',default='docs/verification/factory/end-to-end.json');args=parser.parse_args()
env=read_env();base='http://127.0.0.1:8110';token=env['FACTORY_API_TOKEN']
state=request(base,'/api/state',token=token)
if state['mode']!='RUNNING' or state['faults']:raise RuntimeError('Demo requires running line with no active faults; reset explicitly in Simulation Settings first')
if not state['policy']['auto_stop_allowed']:raise RuntimeError('Run configure.py --demo-stop explicitly and recreate core/factory first')
request(base,'/api/actions',{'kind':'clock','arguments':{'paused':False,'speed':60,'automatic_faults':False},'idempotency_key':str(uuid4())},token=token)
request(base,'/api/actions',{'kind':'fault','arguments':{'fault_id':'gearbox_vibration','mode':'gradual','duration_minutes':60},'idempotency_key':str(uuid4())},token=token)
print('Injected gradual synthetic gearbox deterioration. Monitoring/outbox/task engine own every subsequent step.',flush=True)
start=time.monotonic();last=None;trace=[]
while time.monotonic()-start<args.timeout_seconds:
    try:state=request(base,'/api/state',token=token)
    except Exception:
        time.sleep(2);continue # A service restart must not terminate observation.
    alarm=next((a for a in state['alarms'] if a['epoch']==state['epoch']),None)
    point={'elapsed_minutes':round(state['clock']['elapsed_seconds']/60,2),'mode':state['mode'],'condition':state['condition'],'monitoring':state['monitoring']['status'],'alarm_id':alarm['id'] if alarm else None,'task_id':alarm['agent_task_id'] if alarm else None,'task_status':alarm['agent_status'] if alarm else None,'latest_tool':alarm.get('agent_activity',{}).get('latestTool') if alarm and alarm.get('agent_activity') else None}
    signature=json.dumps({k:v for k,v in point.items() if k!='elapsed_minutes'},sort_keys=True)
    if signature!=last:trace.append(point);print(json.dumps(point),flush=True);last=signature
    if alarm and alarm['agent_status'] in ('COMPLETED','FAILED','PAUSED','WAITING_APPROVAL'):
        task=request(args.core_url,'/tasks/'+alarm['agent_task_id'])
        operations=[o for o in task['operations'] if o['status']=='SUCCEEDED' and o['action'].get('serverId')==env['FACTORY_SERVER_ID']]
        writes={o['action'].get('tool'):o for o in operations}
        action_checks={name:name in writes and writes[name]['result'].get('structuredContent',{}).get('success') is True for name in ('inspect_component','stop_manufacturing_line','acknowledge_alarm')}
        inspection=state['last_inspections'].get('gearbox',{})
        matching_inspection=inspection.get('action_id')==writes.get('inspect_component',{}).get('result',{}).get('structuredContent',{}).get('action_id')
        result={'synthetic_only':True,'automatic_task_creation':True,'operator_intervention':False,'trace':trace,'final_state':state,'task':task,'action_checks':action_checks,'pass':alarm['agent_status']=='COMPLETED' and state['mode']=='STOPPED' and bool(inspection) and matching_inspection and all(action_checks.values()) and all(v['passed'] for v in task['verifications'][-len(task['criteria']):])}
        Path(args.output).write_text(json.dumps(result,indent=2))
        if result['pass']:print('PASS: automatic agent task, RAG evidence, actual stop/inspection, immutable verification and final report.',flush=True);break
        raise RuntimeError('Agent did not complete; saved exact state/history to output. Review actual limitations, never fabricate success.')
    time.sleep(2)
else:
    Path(args.output).write_text(json.dumps({'pass':False,'trace':trace,'final_state':state},indent=2));raise TimeoutError('Automatic demonstration still pending; saved evidence')
