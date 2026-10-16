"""Authoritative simulation domain: pure transitions, no browser/LLM dependency."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import copy,math
from zsk.synthetic import SCENARIOS,severity,sensors

COMPONENTS=[
 {'id':'hopper','name':'Material hopper','x':435,'y':220},
 {'id':'feeder','name':'Metering feeder','x':440,'y':330},
 {'id':'motor','name':'Main drive motor','x':190,'y':350},
 {'id':'gearbox','name':'Gearbox / bearings / lubrication','x':320,'y':350},
 {'id':'barrel','name':'Twin-screw segmented barrel','x':625,'y':350},
 {'id':'cooling','name':'Heating and cooling zones','x':645,'y':250},
 {'id':'die','name':'Extrusion die','x':825,'y':350},
 {'id':'conveyor','name':'Output conveyor','x':990,'y':400},
 {'id':'control','name':'Operator control panel','x':1095,'y':280}]

class InvalidAction(Exception):pass
class Denied(Exception):pass

def initial(machine,start):
    return {'epoch':str(uuid4()),'machine_id':machine,'clock':{'timestamp':start,'origin_timestamp':start,'elapsed_seconds':0.,'paused':False,'speed':1},
     'mode':'RUNNING','condition':'NORMAL','faults':[],'residual':0.,'last_sample_minute':0.,'next_auto_fault_minute':60.,
     'technician':{'id':'tech-01','name':'Maintenance technician','x':1100.,'y':480.,'mode':'IDLE','destination':None},
     'pending_actions':[],'last_inspections':{},'latest_measurement':None,'monitoring':{'status':'ready'},'seed':13}

def fault_definitions():
    return [{'fault_id':key,'component':v[0],'name':v[1],'sensor_effects':v[2],
     'fault_threshold_severity':.7,'progression':'gradual or sudden, synthetic engineering only',
     'consequence':'warning/fault state; no automatic physical control',
     'corrective_actions':['inspect','stop','repair'],'recovery':'stopped, completed component inspection and explicit maintenance policy; residuals decay'} for key,v in SCENARIOS.items()]

def advance(state,wall_seconds,auto_faults):
    s=copy.deepcopy(state);clock=s['clock']
    if clock['paused']:return s,[]
    clock.setdefault('origin_timestamp',(datetime.fromisoformat(clock['timestamp'])-timedelta(seconds=clock['elapsed_seconds'])).isoformat())
    seconds=wall_seconds*clock['speed'];clock['elapsed_seconds']+=seconds
    clock['timestamp']=(datetime.fromisoformat(clock['origin_timestamp'])+timedelta(seconds=clock['elapsed_seconds'])).isoformat()
    minute=clock['elapsed_seconds']/60
    events=[]
    if auto_faults and minute>=s['next_auto_fault_minute'] and s['mode']=='RUNNING' and not s['faults']:
        key=list(SCENARIOS)[int(s['next_auto_fault_minute']/180)%8]
        s['faults'].append({'fault_id':key,'start_minute':minute,'duration_minutes':60,'mode':'gradual'})
        s['next_auto_fault_minute']=minute+180;events.append(('simulation.fault.injected',{'fault_id':key,'automatic':True}))
    maximum=max((severity(f,minute) for f in s['faults']),default=0)
    s['condition']='FAULT' if maximum>=.7 else 'WARNING' if maximum>=.2 else 'NORMAL'
    s['residual']*=math.exp(-seconds/600)
    tech=s['technician'];dest=tech['destination']
    if dest:
        x=next(c['x'] for c in COMPONENTS if c['id']==dest);distance=x-tech['x'];step=seconds*10
        tech['x']+=math.copysign(min(abs(distance),step),distance)
        if abs(tech['x']-x)<.1:tech['mode']='INSPECTING' if any(p['kind']=='inspect' for p in s['pending_actions']) else 'MAINTENANCE' if any(p['kind']=='maintenance' for p in s['pending_actions']) else 'IDLE';tech['destination']=None
    for job in list(s['pending_actions']):
        if clock['elapsed_seconds']<job['complete_at'] or (job['kind'] in ('inspect','maintenance','move') and tech['destination']):continue
        if job['kind']=='stop':s['mode']='STOPPED'
        if job['kind']=='inspect':
            relevant=[f for f in s['faults'] if SCENARIOS[f['fault_id']][0]==job['component_id']]
            s['last_inspections'][job['component_id']]={'action_id':job['id'],'timestamp':clock['timestamp'],'observation':'Simulated deterioration detected; physical cause unconfirmed' if relevant else 'No visible simulated defect','fault_scenarios':[f['fault_id'] for f in relevant],'synthetic_only':True}
        if job['kind']=='maintenance':
            s['faults']=[f for f in s['faults'] if SCENARIOS[f['fault_id']][0]!=job['component_id']];s['residual']=1.;s['mode']='STOPPED'
        if job['kind'] in ('inspect','move','maintenance'):tech['mode']='IDLE'
        s['pending_actions'].remove(job);events.append(('machine.action.completed',job))
    return s,events

def measurement(state,minute):
    running=state['mode'] in ('RUNNING','STOPPING')
    origin=state['clock'].get('origin_timestamp')
    start=datetime.fromisoformat(origin) if origin else datetime.fromisoformat(state['clock']['timestamp'])-timedelta(seconds=state['clock']['elapsed_seconds'])
    timestamp=start+timedelta(minutes=minute)
    return sensors(minute,state['faults'],running,state['seed'],state['residual'])|{'machine_id':state['machine_id'],'timestamp':timestamp.replace(tzinfo=None).isoformat(),'recipe':'A','alarm_active':0}

def transition(state,kind,args,policy,action_id):
    s=copy.deepcopy(state);now=s['clock']['elapsed_seconds'];component=args.get('component_id','gearbox')
    if args.get('machine_id',s['machine_id'])!=s['machine_id']:raise InvalidAction('Unknown simulation machine')
    if args.get('epoch',s['epoch'])!=s['epoch']:raise InvalidAction('Simulation episode changed; stale actions are rejected')
    if kind in ('stop','pause_line') and not policy['auto_stop_allowed']:raise Denied('Automatic simulation stop is disabled')
    if kind=='start' and not policy['auto_restart_allowed']:raise Denied('Automatic simulation restart is disabled')
    if kind in ('maintenance','reset') and not policy['auto_maintenance_allowed']:raise Denied('Automatic simulation maintenance/reset is disabled')
    if kind in ('inspect','maintenance','move'):
        if component not in [c['id'] for c in COMPONENTS]:raise InvalidAction('Unknown component')
        if args.get('character_id','tech-01')!='tech-01':raise InvalidAction('Unknown technician')
        if s['technician']['mode']!='IDLE' or s['technician']['destination']:raise InvalidAction('Technician busy; inspect status before another assignment')
    if kind=='start':
        if s['mode']!='STOPPED' or s['pending_actions'] or max((severity(f,now/60) for f in s['faults']),default=0)>=.7:raise InvalidAction('Restart requires stopped line, no active maintenance/actions and no severe fault')
        s['mode']='RUNNING'
    if kind in ('stop','pause_line'):
        if s['mode']=='STOPPED':return s,{'status':'completed','already_stopped':True}
        if s['mode']!='RUNNING':raise InvalidAction('Stop requires running line')
        s['mode']='STOPPING';s['pending_actions'].append({'id':action_id,'kind':'stop','complete_at':now+5})
    if kind=='maintenance':
        if s['mode']!='STOPPED' or component not in s['last_inspections']:raise InvalidAction('Maintenance requires stopped line and a recorded component inspection')
        if args.get('maintenance_action')!='repair':raise InvalidAction('Only simulated repair is supported')
        s['mode']='MAINTENANCE'
    if kind in ('inspect','maintenance','move'):
        s['technician'].update(mode='WALKING',destination=component)
        s['pending_actions'].append({'id':action_id,'kind':kind,'component_id':component,'complete_at':now+(120 if kind=='maintenance' else 40 if kind=='inspect' else 0)})
    if kind=='fault':
        key=args.get('fault_id')
        if key not in SCENARIOS or args.get('mode','gradual') not in ('gradual','sudden'):raise InvalidAction('Unknown scenario/progression')
        if any(f['fault_id']==key for f in s['faults']):raise InvalidAction('Scenario already active')
        duration=float(args.get('duration_minutes',60))
        if not 5<=duration<=240:raise InvalidAction('Progression must be 5–240 minutes')
        s['faults'].append({'fault_id':key,'start_minute':now/60,'duration_minutes':duration,'mode':args.get('mode','gradual')})
    if kind=='clock':
        if set(args)-{'paused','speed','automatic_faults'}:raise InvalidAction('Unknown clock setting')
        if 'speed' in args:
            if args['speed'] not in (1,5,10,60):raise InvalidAction('Supported speeds: 1,5,10,60')
            s['clock']['speed']=args['speed']
        if 'paused' in args:
            if type(args['paused']) is not bool:raise InvalidAction('Paused must be boolean')
            s['clock']['paused']=args['paused']
        if 'automatic_faults' in args:
            if type(args['automatic_faults']) is not bool:raise InvalidAction('Automatic faults must be boolean')
            s['automatic_faults']=args['automatic_faults']
    if kind=='reset':
        if s['pending_actions']:raise InvalidAction('Wait for pending actions before reset')
        s=initial(s['machine_id'],s['clock']['timestamp']);s['clock']['paused']=True
    if kind not in ('start','stop','pause_line','move','inspect','maintenance','fault','clock','reset','acknowledge'):raise InvalidAction('Unknown simulation action')
    return s,{'status':'accepted' if any(p['id']==action_id for p in s['pending_actions']) else 'completed'}
