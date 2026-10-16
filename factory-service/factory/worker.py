import logging,threading,time
from datetime import datetime,timezone,timedelta
from uuid import uuid4
import httpx
from sqlalchemy import text
from .domain import advance,measurement,SCENARIOS,severity
from .store import encode,jsonrow

logger=logging.getLogger('factory')

class Worker:
    def __init__(self,store):self.store=store;self.settings=store.settings;self.stop_event=threading.Event();self.threads=[]
    def start(self):
        if not self.settings.worker_enabled:return
        for fn in (self.clock_loop,self.services_loop):
            thread=threading.Thread(target=fn,daemon=True);thread.start();self.threads.append(thread)
    def stop(self):
        self.stop_event.set()
        for t in self.threads:t.join(timeout=20)
    def clock_loop(self):
        while not self.stop_event.is_set():
            try:
                with self.store.engine.connect() as lock:
                    acquired=lock.scalar(text('SELECT pg_try_advisory_lock(91320261031)'));lock.commit()
                    if not acquired:self.stop_event.wait(1);continue
                    last=time.monotonic()
                    try:
                        while not self.stop_event.wait(.25):
                            now=time.monotonic();self.tick(now-last);last=now
                    finally:lock.execute(text('SELECT pg_advisory_unlock(91320261031)'));lock.commit()
            except Exception:logger.warning('factory_clock_unavailable');self.stop_event.wait(1)
    def tick(self,elapsed):
        with self.store.engine.begin() as c:
            s,_=self.store.load(c,True);s,events=advance(s,elapsed,s.get('automatic_faults',self.settings.automatic_faults))
            for kind,p in events:
                if kind=='machine.action.completed':
                    result={'success':True,'completed':True,'action_id':p['id'],'status':'completed','timestamp':s['clock']['timestamp'],'new_state':{'mode':s['mode'],'condition':s['condition'],'technician':s['technician']},'execution_evidence':s['last_inspections'].get(p.get('component_id'),{'state_confirmed':True}),'error':None}
                    c.execute(text("UPDATE factory_actions SET status='completed',completed_at=now(),new_state=CAST(:s AS jsonb),result=result||CAST(:r AS jsonb) WHERE id=CAST(:id AS uuid)"),{'s':encode(result['new_state']),'r':encode(result),'id':p['id']})
                self.store.event(c,s,kind,p)
            # Bounded catch-up never moves the sampling cursor past uncommitted readings.
            for _ in range(50):
                minute=s['last_sample_minute']+5
                if minute>s['clock']['elapsed_seconds']/60:break
                row=measurement(s,minute)
                cols=list(row);identifier=c.scalar(text(f"INSERT INTO zsk_unlabeled_measurements({','.join(cols)},provenance) VALUES({','.join(':'+k for k in cols)},'synthetic') ON CONFLICT(machine_id,timestamp) DO NOTHING RETURNING id"),row)
                if identifier is None:raise RuntimeError('Simulation timestamp collision')
                c.execute(text('INSERT INTO factory_measurements(id,epoch,simulation_timestamp,machine_state,simulation_minute) VALUES(:id,CAST(:e AS uuid),:t,:s,:m)'),{'id':identifier,'e':s['epoch'],'t':row['timestamp'],'s':s['mode'],'m':minute})
                faults=[f for f in s['faults'] if severity(f,minute)>=.7]
                c.execute(text('INSERT INTO factory_ground_truth VALUES(:id,:label,CAST(:f AS jsonb),true)'),{'id':identifier,'label':0 if faults else 1,'f':encode([f['fault_id'] for f in faults])})
                s['last_sample_minute']=minute;s['latest_measurement']=row|{'id':identifier,'simulation_timestamp':row['timestamp'],'ingested_at':datetime.now(timezone.utc).isoformat(),'machine_state':s['mode']}
                self.store.event(c,s,'machine.measurement.created',{'measurement_id':identifier})
            self.store.save(c,s)
    def services_loop(self):
        while not self.stop_event.wait(.5):
            try:
                with self.store.engine.connect() as lock:
                    acquired=lock.scalar(text('SELECT pg_try_advisory_lock(91320261032)'));lock.commit()
                    if not acquired:continue
                    try:self.monitor();self.deliver();self.task_updates()
                    finally:lock.execute(text('SELECT pg_advisory_unlock(91320261032)'));lock.commit()
            except Exception:logger.warning('factory_services_unavailable')
    def ml(self,path,payload=None):
        with httpx.Client(timeout=15,follow_redirects=False) as client:
            response=client.request('POST' if payload else 'GET',self.settings.ml_url+path,headers={'Authorization':'Bearer '+self.settings.ml_api_token.get_secret_value()},json=payload)
            if response.status_code!=200:raise RuntimeError('ML service unavailable')
            result=response.json()
        if not isinstance(result,dict):raise RuntimeError('Malformed ML output')
        return result
    def monitor(self):
        with self.store.engine.connect() as c:
            s,_=self.store.load(c)
            checkpoint=c.execute(text('SELECT * FROM monitoring_checkpoints WHERE epoch=CAST(:e AS uuid)'),{'e':s['epoch']}).mappings().one()
            if s['last_sample_minute']<checkpoint['next_due_minute'] or (checkpoint['retry_at'] and checkpoint['retry_at']>datetime.now(timezone.utc)):return
            # Resolve ALL newly sampled readings up to this due interval; no silent skipping.
            rows=c.execute(text('SELECT m.*,f.machine_state FROM factory_measurements f JOIN zsk_unlabeled_measurements m ON m.id=f.id WHERE f.epoch=CAST(:e AS uuid) AND f.id>:last AND f.simulation_minute<=:due ORDER BY m.timestamp'),{'e':s['epoch'],'last':checkpoint['last_measurement_id'],'due':checkpoint['next_due_minute']}).mappings().all()
        try:
            for target in rows:
                with self.store.engine.connect() as c:
                    if c.scalar(text('SELECT count(*) FROM factory_predictions WHERE measurement_id=:id'),{'id':target['id']}):continue
                    preceding=c.execute(text('SELECT * FROM zsk_unlabeled_measurements WHERE machine_id=:m AND timestamp<:t ORDER BY timestamp DESC LIMIT 2'),{'m':s['machine_id'],'t':target['timestamp']}).mappings().all()
                from zsk.zsk_model import MEASURED
                keys=['timestamp','machine_id','recipe',*MEASURED]
                clean=lambda r:{k:r[k].isoformat() if k=='timestamp' else r[k] for k in keys}
                payload={'measurement':clean(target),'recent_history':[clean(r) for r in reversed(preceding)]}
                current=self.ml('/api/model/predict',payload)
                if current.get('predicted_health_label') not in (0,1) or not isinstance(current.get('fault_probability'),(int,float)) or not 0<=current['fault_probability']<=1 or not current.get('model_version'):raise RuntimeError('Malformed classifier output')
                times=[r['timestamp'] for r in reversed(preceding)]+[target['timestamp']]
                cadence=len(times)==3 and all(abs((b-a).total_seconds()-300)<.01 for a,b in zip(times,times[1:]))
                forecast=self.ml('/api/forecast/predict',payload) if cadence and target['machine_state']=='RUNNING' and current['predicted_health_label']==1 else {'status':'not_applicable','reason':'current classification is faulty, line not running, or three five-minute readings unavailable'}
                if 'risk_score' in forecast and (not isinstance(forecast['risk_score'],(int,float)) or not 0<=forecast['risk_score']<=1 or not forecast.get('model_version')):raise RuntimeError('Malformed forecast output')
                with self.store.engine.begin() as c:
                    current_state,_=self.store.load(c,True)
                    c.execute(text('INSERT INTO factory_predictions(measurement_id,current_condition,forecast) VALUES(:id,CAST(:p AS jsonb),CAST(:f AS jsonb)) ON CONFLICT DO NOTHING'),{'id':target['id'],'p':encode(current),'f':encode(forecast)})
                    if current_state['epoch']==s['epoch'] and target['machine_state']=='RUNNING':
                        alarm_type='current_detected_fault' if current['predicted_health_label']==0 else 'predicted_future_fault' if forecast.get('risk_score',0)>=self.settings.forecast_alarm_threshold else None
                        if alarm_type:self.alarm(c,current_state,target,current,forecast,alarm_type)
                        elif current['predicted_health_label']==1:
                            # Resolution requires fresh healthy model evidence;
                            # acknowledgement alone never clears an alarm.
                            resolved=c.execute(text("UPDATE machine_alarms SET status='resolved',updated_at=now(),details=details||CAST(:evidence AS jsonb) WHERE epoch=CAST(:e AS uuid) AND status!='resolved' AND agent_status IN ('COMPLETED','CANCELLED') RETURNING id"),{'e':s['epoch'],'evidence':encode({'resolution_measurement_id':target['id'],'resolution_model_version':current['model_version'],'resolution_simulation_timestamp':target['timestamp'].isoformat()})}).all()
                            for alarm in resolved:self.store.event(c,current_state,'machine.alarm.resolved',{'alarm_id':str(alarm[0]),'measurement_id':target['id']})
            with self.store.engine.begin() as c:
                c.execute(text("UPDATE monitoring_checkpoints SET last_measurement_id=:last,next_due_minute=next_due_minute+:interval,status='ready',last_error=NULL,attempts=0,retry_at=NULL,updated_at=now() WHERE epoch=CAST(:e AS uuid)"),{'last':rows[-1]['id'] if rows else checkpoint['last_measurement_id'],'interval':self.settings.monitor_interval_minutes,'e':s['epoch']})
        except Exception:
            with self.store.engine.begin() as c:
                c.execute(text("UPDATE monitoring_checkpoints SET status='retrying',last_error='ML inference unavailable or invalid; unprocessed readings retained',attempts=attempts+1,retry_at=now()+interval '5 seconds',updated_at=now() WHERE epoch=CAST(:e AS uuid)"),{'e':s['epoch']})
            logger.warning('factory_monitor_retry')
    def alarm(self,c,s,target,current,forecast,kind):
        # Component hypothesis uses OBSERVED deviations, never simulator truth.
        from zsk.synthetic import BASE
        component='gearbox' if target['gearbox_vibration_rms_mm_s']>BASE['gearbox_vibration_rms_mm_s']+.3 or target['gearbox_oil_temp_c']>BASE['gearbox_oil_temp_c']+10 else 'die' if target['melt_pressure_bar']>120 else 'motor' if target['motor_current_a']>110 else 'cooling' if abs(target['barrel_zone_temp_c']-190)>15 else 'barrel'
        old=c.execute(text("SELECT * FROM machine_alarms WHERE epoch=CAST(:e AS uuid) ORDER BY (status!='resolved') DESC,simulation_timestamp DESC LIMIT 1"),{'e':s['epoch'],'comp':component}).mappings().first()
        if old and (old['status']!='resolved' or (target['timestamp'].replace(tzinfo=timezone.utc)-old['simulation_timestamp']).total_seconds()<self.settings.alarm_cooldown_minutes*60):return
        identifier=str(uuid4());details={'event_type':'manufacturing.alert','event_id':identifier,'machine_id':s['machine_id'],'epoch':s['epoch'],'alarm_type':kind,'component':component,'component_hypothesis':True,'severity':'high','prediction':current if kind=='current_detected_fault' else forecast,'simulation_timestamp':target['timestamp'].isoformat(),'measurement_ids':[target['id']],'synthetic_only':True,'rag_device_id':self.settings.rag_device_id}
        c.execute(text('INSERT INTO machine_alarms(id,epoch,machine_id,alarm_type,component,severity,details,simulation_timestamp) VALUES(CAST(:id AS uuid),CAST(:e AS uuid),:m,:k,:comp,\'high\',CAST(:d AS jsonb),:t)'),{'id':identifier,'e':s['epoch'],'m':s['machine_id'],'k':kind,'comp':component,'d':encode(details),'t':target['timestamp']})
        c.execute(text('INSERT INTO factory_outbox(event_id,payload) VALUES(CAST(:id AS uuid),CAST(:p AS jsonb))'),{'id':identifier,'p':encode({'template':self.settings.task_template,'eventId':identifier,'variables':details})})
        self.store.event(c,s,'machine.alarm.created',details)
    def deliver(self):
        with self.store.engine.connect() as c:rows=c.execute(text("SELECT * FROM factory_outbox WHERE status='pending' AND next_attempt_at<=now() ORDER BY next_attempt_at LIMIT 5")).mappings().all()
        for row in rows:
            try:
                with httpx.Client(timeout=15,follow_redirects=False) as client:
                    response=client.post(self.settings.meta_harness_url+'/internal/task-events',headers={'Authorization':'Bearer '+self.settings.task_service_token.get_secret_value()},json=row['payload'])
                    if response.status_code not in (200,201):raise RuntimeError('Task endpoint rejected delivery')
                    task_id=response.json()['taskId']
                with self.store.engine.begin() as c:
                    s,_=self.store.load(c)
                    c.execute(text("UPDATE factory_outbox SET status='delivered',task_id=CAST(:t AS uuid),delivered_at=now(),last_error=NULL WHERE event_id=:id"),{'t':task_id,'id':row['event_id']})
                    c.execute(text("UPDATE machine_alarms SET agent_task_id=CAST(:t AS uuid),agent_status='PENDING',status=CASE WHEN status='new' THEN 'investigating' ELSE status END WHERE id=:id"),{'t':task_id,'id':row['event_id']})
                    self.store.event(c,s,'agent.task.created',{'alarm_id':str(row['event_id']),'task_id':task_id})
            except Exception:
                with self.store.engine.begin() as c:c.execute(text("UPDATE factory_outbox SET attempts=attempts+1,last_error='Authenticated task delivery unavailable; durable event retained',next_attempt_at=now()+least(60,power(2,least(attempts+1,6)))*interval '1 second' WHERE event_id=:id"),{'id':row['event_id']})
    def task_updates(self):
        with self.store.engine.connect() as c:alarms=c.execute(text("SELECT id,agent_task_id,agent_status FROM machine_alarms WHERE agent_task_id IS NOT NULL AND agent_status NOT IN ('COMPLETED','CANCELLED') ORDER BY simulation_timestamp DESC LIMIT 5")).mappings().all()
        for alarm in alarms:
            try:
                with httpx.Client(timeout=5,follow_redirects=False) as client:
                    response=client.get(self.settings.meta_harness_url+'/internal/task-events/'+str(alarm['id']),headers={'Authorization':'Bearer '+self.settings.task_service_token.get_secret_value()})
                    if response.status_code!=200:continue
                    activity=response.json()
                with self.store.engine.begin() as c:
                    s,_=self.store.load(c)
                    c.execute(text('UPDATE machine_alarms SET agent_status=:s,agent_activity=CAST(:a AS jsonb),updated_at=now() WHERE id=:id'),{'s':activity['status'],'a':encode(activity),'id':alarm['id']})
                    if activity['status']!=alarm['agent_status']:self.store.event(c,s,'agent.task.'+activity['status'].lower(),activity)
            except Exception:continue
