import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine,text
from .domain import initial,transition,Denied,InvalidAction,COMPONENTS,fault_definitions

NOTICE='SIMULATION ONLY — synthetic ZSK-style equipment; no physical machine connection.'
def encode(x):return json.dumps(x,default=str,sort_keys=True,separators=(',',':'))
def jsonrow(row):return json.loads(encode(dict(row)))

class Store:
    def __init__(self,settings):
        self.settings=settings
        self.engine=create_engine(settings.database_url,pool_pre_ping=True,pool_size=8,max_overflow=4,connect_args={'connect_timeout':5,'options':'-c statement_timeout=15000'})
    def initialize(self):
        with self.engine.begin() as c:
            c.execute(text('SELECT pg_advisory_xact_lock(91320261030)'))
            c.execute(text('CREATE TABLE IF NOT EXISTS factory_migrations(name TEXT PRIMARY KEY,checksum TEXT NOT NULL)'))
            for p in sorted(self.settings.migrations.glob('*.sql')):
                sql=p.read_text();sha=hashlib.sha256(sql.encode()).hexdigest()
                old=c.scalar(text('SELECT checksum FROM factory_migrations WHERE name=:n'),{'n':p.name})
                if old and old!=sha:raise RuntimeError('Applied factory migration changed')
                if not old:
                    c.connection.driver_connection.execute(sql,prepare=False)
                    c.execute(text('INSERT INTO factory_migrations VALUES(:n,:s)'),{'n':p.name,'s':sha})
            if not c.scalar(text('SELECT count(*) FROM factory_state')):
                latest=c.scalar(text('SELECT max(timestamp) FROM zsk_unlabeled_measurements WHERE machine_id=:m'),{'m':self.settings.machine_id})
                start=(latest.replace(tzinfo=timezone.utc) if latest else datetime.now(timezone.utc)).isoformat()
                s=initial(self.settings.machine_id,start)
                c.execute(text('INSERT INTO factory_state(id,state) VALUES(1,CAST(:s AS jsonb))'),{'s':encode(s)})
                c.execute(text('INSERT INTO monitoring_checkpoints(epoch,next_due_minute) VALUES(CAST(:e AS uuid),:d)'),{'e':s['epoch'],'d':self.settings.monitor_interval_minutes})
                self.event(c,s,'simulation.created',{'synthetic_only':True})
    def load(self,c,lock=False):
        row=c.execute(text('SELECT * FROM factory_state WHERE id=1'+(' FOR UPDATE' if lock else ''))).mappings().one()
        return row['state'],row['version']
    def save(self,c,state):
        return c.scalar(text('UPDATE factory_state SET state=CAST(:s AS jsonb),version=version+1,updated_at=now() WHERE id=1 RETURNING version'),{'s':encode(state)})
    def event(self,c,s,kind,payload):
        c.execute(text('INSERT INTO simulation_events(event_id,type,epoch,simulation_timestamp,payload) VALUES(CAST(:id AS uuid),:t,CAST(:e AS uuid),:time,CAST(:p AS jsonb))'),{'id':str(uuid4()),'t':kind,'e':s['epoch'],'time':s['clock']['timestamp'],'p':encode(payload)})
    def policy(self):return {k:getattr(self.settings,k) for k in ('auto_stop_allowed','auto_restart_allowed','auto_maintenance_allowed')}
    def state(self):
        with self.engine.connect() as c:
            s,version=self.load(c)
            alarms=c.execute(text('SELECT * FROM machine_alarms WHERE epoch=CAST(:e AS uuid) ORDER BY simulation_timestamp DESC LIMIT 12'),{'e':s['epoch']}).mappings().all()
            actions=c.execute(text('SELECT * FROM factory_actions ORDER BY created_at DESC LIMIT 12')).mappings().all()
            checkpoint=c.execute(text('SELECT * FROM monitoring_checkpoints WHERE epoch=CAST(:e AS uuid)'),{'e':s['epoch']}).mappings().first()
            prediction=c.execute(text('SELECT p.* FROM factory_predictions p JOIN factory_measurements m ON m.id=p.measurement_id WHERE m.epoch=CAST(:e AS uuid) ORDER BY m.simulation_timestamp DESC LIMIT 1'),{'e':s['epoch']}).mappings().first()
            seq=c.scalar(text('SELECT coalesce(max(sequence),0) FROM simulation_events'))
        return s|{'version':version,'sequence':seq,'components':COMPONENTS,'alarms':[jsonrow(a) for a in alarms],'actions':[jsonrow(a) for a in actions],'monitoring':jsonrow(checkpoint) if checkpoint else {},'prediction':jsonrow(prediction) if prediction else None,'policy':self.policy(),'scenarios':fault_definitions(),'notice':NOTICE}
    def measurements(self,machine,start=None,end=None,limit=50):
        if machine!=self.settings.machine_id:raise InvalidAction('Unknown simulation machine')
        if not 1<=limit<=100:raise InvalidAction('Limit must be 1–100')
        with self.engine.connect() as c:
            rows=c.execute(text('SELECT m.*,f.simulation_timestamp,f.ingested_at,f.machine_state,f.epoch FROM zsk_unlabeled_measurements m LEFT JOIN factory_measurements f ON f.id=m.id WHERE m.machine_id=:m AND (CAST(:start AS timestamp) IS NULL OR m.timestamp>=CAST(:start AS timestamp)) AND (CAST(:end AS timestamp) IS NULL OR m.timestamp<=CAST(:end AS timestamp)) ORDER BY m.timestamp DESC LIMIT :lim'),{'m':machine,'start':start,'end':end,'lim':limit}).mappings().all()
        return {'items':[jsonrow(r) for r in reversed(rows)],'machine_id':machine,'notice':NOTICE,'ground_truth_excluded':True}
    def action(self,kind,args,key,operator=False):
        if not isinstance(key,str) or not 8<=len(key)<=160:raise InvalidAction('Stable idempotency key of 8–160 characters required')
        fingerprint=hashlib.sha256(encode([kind,args]).encode()).hexdigest()
        with self.engine.begin() as c:
            c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,10))'),{'key':key})
            old=c.execute(text('SELECT * FROM factory_actions WHERE idempotency_key=:k'),{'k':key}).mappings().first()
            if old:
                if old['fingerprint']!=fingerprint:raise InvalidAction('Idempotency key arguments conflict')
                return old['result']
            s,_=self.load(c,True);previous={'mode':s['mode'],'condition':s['condition'],'technician':s['technician'].copy(),'epoch':s['epoch']}
            policy=self.policy() if not operator else dict(auto_stop_allowed=True,auto_restart_allowed=True,auto_maintenance_allowed=True)
            action_id=str(uuid4());updated,response=transition(s,kind,args,policy,action_id)
            if kind=='acknowledge':
                alarm=c.execute(text("UPDATE machine_alarms SET status='acknowledged',updated_at=now() WHERE id=CAST(:id AS uuid) AND epoch=CAST(:e AS uuid) RETURNING id"),{'id':args['alarm_id'],'e':s['epoch']}).first()
                if not alarm:raise InvalidAction('Unknown current alarm')
            if kind=='reset':
                c.execute(text("UPDATE machine_alarms SET status='resolved',updated_at=now() WHERE epoch=CAST(:e AS uuid)"),{'e':s['epoch']})
                c.execute(text('INSERT INTO monitoring_checkpoints(epoch,next_due_minute) VALUES(CAST(:e AS uuid),:d)'),{'e':updated['epoch'],'d':self.settings.monitor_interval_minutes})
            version=self.save(c,updated)
            new={'mode':updated['mode'],'condition':updated['condition'],'technician':updated['technician'],'epoch':updated['epoch'],'version':version}
            result={'success':True,'completed':response['status']=='completed','action_id':action_id,'status':response['status'],'previous_state':previous,'new_state':new,'timestamp':updated['clock']['timestamp'],'execution_evidence':{'committed_state_version':version,'synthetic_only':True},'error':None}
            c.execute(text('INSERT INTO factory_actions(id,idempotency_key,fingerprint,kind,arguments,status,previous_state,new_state,result,simulation_timestamp) VALUES(CAST(:id AS uuid),:key,:fp,:kind,CAST(:args AS jsonb),:status,CAST(:prev AS jsonb),CAST(:new AS jsonb),CAST(:r AS jsonb),:t)'),{'id':action_id,'key':key,'fp':fingerprint,'kind':kind,'args':encode(args),'status':response['status'],'prev':encode(previous),'new':encode(new),'r':encode(result),'t':updated['clock']['timestamp']})
            self.event(c,updated,'machine.action.'+('completed' if result['completed'] else 'started'),result)
            return result
    def action_status(self,identifier,epoch=None,component_id=None,alarm_id=None):
        with self.engine.connect() as c:row=c.execute(text('SELECT * FROM factory_actions WHERE id=CAST(:id AS uuid)'),{'id':identifier}).mappings().first()
        if not row:raise InvalidAction('Unknown action ID')
        if epoch and row['previous_state']['epoch']!=epoch:raise InvalidAction('Action belongs to another episode')
        if component_id and (row['kind']!='inspect' or row['arguments'].get('component_id')!=component_id):raise InvalidAction('Inspection component mismatch')
        if alarm_id:
            with self.engine.connect() as c:alarm=c.execute(text('SELECT * FROM machine_alarms WHERE id=CAST(:id AS uuid)'),{'id':alarm_id}).mappings().first()
            if not alarm or str(alarm['epoch'])!=row['previous_state']['epoch'] or alarm['component']!=component_id or row['simulation_timestamp']<alarm['simulation_timestamp']:raise InvalidAction('Inspection must follow the matching alarm in the same episode')
        return row['result']|{'status':row['status'],'completed':row['status']=='completed'}
