import hashlib, json, logging, os, threading, time
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from .db import TABLES, COLUMNS, audit, seed
from .errors import ServiceError
from .schemas import AddInput, BatchInput, Filters, PredictInput, TrainInput, RollbackInput, UNITS
from . import zsk_model

logger=logging.getLogger('zsk')
NOTICE='SYNTHETIC DEMO ONLY. 0=Faulty, 1=Healthy. Probabilities are not validated industrial failure risks; no equipment control.'

def encode(value):
    return json.dumps(value,sort_keys=True,default=str,separators=(',',':'))
def uuid(value):
    try: return str(UUID(str(value)))
    except (ValueError,TypeError): raise ServiceError('INVALID_ID','Provide a valid job/model UUID') from None

def conditions(filters, prefix=''):
    sql=[];params={}
    for key,op,column in [('machine_id','=','machine_id'),('start_time','>=','timestamp'),('end_time','<=','timestamp')]:
        value=getattr(filters,key)
        if value is not None:
            sql.append(f'{prefix}{column} {op} :{key}');params[key]=value
    return ' AND '.join(sql) or 'TRUE',params

def model_row(row):
    result=dict(row);value=result['timestamp']
    result['timestamp']=value.isoformat() if isinstance(value,datetime) else str(value)
    return result

class Service:
    def __init__(self,engine,settings):
        self.engine,self.settings=engine,settings
        self._stop=threading.Event(); self._thread=None
        self._cache={}; self._cache_lock=threading.Lock()
    def idempotent(self,conn,key,kind,request,callback):
        # Lock by the stable key across all operations; completed responses are committed with effects.
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':key})
        fingerprint=hashlib.sha256(encode(request).encode()).hexdigest()
        old=conn.execute(text('SELECT * FROM zsk_requests WHERE key=:key'),{'key':key}).mappings().first()
        if old:
            if old['kind']!=kind or old['fingerprint']!=fingerprint:
                raise ServiceError('IDEMPOTENCY_CONFLICT','This key was already used with different arguments',409)
            return old['response']
        result=callback()
        conn.execute(text('INSERT INTO zsk_requests(key,kind,fingerprint,response) VALUES(:key,:kind,:fingerprint,CAST(:response AS jsonb))'),{'key':key,'kind':kind,'fingerprint':fingerprint,'response':encode(result)})
        return result
    def records(self,filters: Filters,labeled=False):
        where,params=conditions(filters); table=TABLES['labeled' if labeled else 'unlabeled']
        with self.engine.connect() as conn:
            count=conn.scalar(text(f'SELECT count(*) FROM {table} WHERE {where}'),params)
            rows=conn.execute(text(f'SELECT * FROM {table} WHERE {where} ORDER BY timestamp,machine_id,id LIMIT :limit OFFSET :offset'),params|{'limit':filters.page_size,'offset':(filters.page-1)*filters.page_size}).mappings().all()
        return {'items':[model_row(r) for r in rows],'total':count,'page':filters.page,'page_size':filters.page_size,'units':UNITS,'notice':NOTICE}
    def add(self,request:AddInput):
        def apply(conn):
            accepted=[];rejected=[]
            for index,reading in enumerate(request.readings):
                source='labeled' if reading.health_label is not None else 'unlabeled';table=TABLES[source]
                # Serialization also enforces append-only per-machine time order across concurrent imports.
                conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,1))'),{'key':table+reading.machine_id})
                last=conn.scalar(text(f'SELECT max(timestamp) FROM {table} WHERE machine_id=:machine'),{'machine':reading.machine_id})
                timestamp=reading.timestamp.replace(tzinfo=None)
                if last and timestamp<=last:
                    rejected.append({'index':index,'code':'DUPLICATE_OR_OUT_OF_ORDER','message':'Append a timestamp after the last stored reading for this machine/source'});continue
                row=reading.row(); row.pop('units');label=row.pop('health_label')
                fields=COLUMNS+['provenance']
                if source=='labeled':fields+=['health_label'];row['health_label']=label
                result=conn.scalar(text(f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join(':'+k for k in fields)}) RETURNING id"),row)
                accepted.append({'id':result,'source':source,'machine_id':reading.machine_id,'timestamp':row['timestamp']})
            response={'accepted_count':len(accepted),'rejected_count':len(rejected),'accepted':accepted,'rejected':rejected}
            audit(conn,'append_measurements',{'accepted_count':len(accepted),'rejected_count':len(rejected)})
            return response
        with self.engine.begin() as conn:
            return self.idempotent(conn,request.idempotency_key,'append',request.model_dump(mode='json'),lambda:apply(conn))
    def active(self,conn=None):
        if conn is None:
            with self.engine.connect() as c:return self.active(c)
        row=conn.execute(text('SELECT m.* FROM zsk_state s JOIN zsk_models m ON m.version=s.active_version WHERE s.id=1')).mappings().first()
        if not row:raise ServiceError('MODEL_NOT_READY','Initial training is pending; inspect model status',503)
        return dict(row)
    def artifact(self,version):
        version=uuid(version)
        path=self.settings.artifact_dir/f'{version}.joblib'
        with self.engine.connect() as conn:
            digest=conn.scalar(text('SELECT artifact_sha256 FROM zsk_models WHERE version=CAST(:v AS uuid)'),{'v':version})
        if not digest or not path.is_file() or path.is_symlink() or path.stat().st_uid!=os.getuid():
            raise ServiceError('UNTRUSTED_ARTIFACT','Only service-owned registered model artifacts can be loaded',503)
        # Hash every load boundary; only trusted registered artifacts ever reach joblib.
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ServiceError('ARTIFACT_CHANGED','Model checksum does not match registered version',503)
        return path
    def loaded(self,version):
        path=self.artifact(version)
        with self._cache_lock:
            if version not in self._cache:
                model=zsk_model.joblib.load(path)
                if model.get('feature_names')!=zsk_model.FEATURES or list(model['model'].classes_)!=[0,1]:
                    raise ServiceError('FEATURE_MISMATCH','Model does not match the supplied feature schema',503)
                self._cache={version:model}
            return self._cache[version]
    def predict_rows(self,rows,version):
        artifact=self.loaded(version);X=zsk_model.feature_matrix(rows)
        model=artifact['model'];labels=model.predict(X);prob=model.predict_proba(X);fault_index=list(model.classes_).index(0)
        return [{'timestamp':r['timestamp'],'machine_id':r['machine_id'],'predicted_health_label':int(label),'predicted_status':zsk_model.LABELS[int(label)],'fault_probability':round(float(p[fault_index]),6),'model_version':version,'notice':NOTICE} for r,label,p in zip(rows,labels,prob)]
    def history(self,conn,source,row):
        rows=conn.execute(text(f'SELECT * FROM {TABLES[source]} WHERE machine_id=:machine AND timestamp<:time ORDER BY timestamp DESC LIMIT 2'),{'machine':row['machine_id'],'time':row['timestamp']}).mappings().all()
        return [model_row(r) for r in reversed(rows)]
    def predict(self,request:PredictInput):
        with self.engine.connect() as conn:
            version=str(self.active(conn)['version'])
            if request.measurement_id:
                target=conn.execute(text(f'SELECT * FROM {TABLES[request.source]} WHERE id=:id'),{'id':request.measurement_id}).mappings().first()
                if not target:raise ServiceError('NOT_FOUND','Measurement not found',404)
                target=model_row(target)
            else:target=request.measurement.row()
            history=[r.row() for r in request.recent_history] if request.recent_history is not None else self.history(conn,request.source,target)
        if any(r['machine_id']!=target['machine_id'] or r['timestamp']>=target['timestamp'] for r in history):
            raise ServiceError('INVALID_HISTORY','History must precede the target and belong to the same machine')
        if not request.measurement_id and len(history)<2:
            raise ServiceError('MISSING_HISTORY','Provide two preceding readings or use a stored measurement; early stored rows explicitly use warmup windows')
        result=self.predict_rows(history+[target],version)[-1]
        result['history_count']=len(history);result['warmup_window']=len(history)<2
        return result
    def queue(self,request,kind,bootstrap=False):
        body=request.model_dump(mode='json') if hasattr(request,'model_dump') else request
        key=body['idempotency_key']
        with self.engine.begin() as conn:
            def create():
                conn.execute(text('SELECT pg_advisory_xact_lock(91320261010)'))
                if kind=='train':
                    if conn.scalar(text("SELECT count(*) FROM zsk_jobs WHERE kind='train' AND status IN ('queued','running')")):
                        raise ServiceError('TRAINING_BUSY','A training job is already in progress',409)
                    if conn.scalar(text('SELECT count(*) FROM zsk_labeled_measurements'))<100:
                        raise ServiceError('NO_TRAINING_LABELS','Training labels were removed as requested; add at least 100 verified labeled readings with both classes before retraining',409)
                else:
                    version=str(self.active(conn)['version']);body['model_version']=version
                    filters=BatchInput.model_validate({k:v for k,v in body.items() if k!='model_version'})
                    where,params=conditions(filters);table=TABLES[filters.source]
                    # Freeze the membership, ordering and model version before returning the job.
                    ids=list(conn.execute(text(f'SELECT id FROM {table} WHERE {where} ORDER BY timestamp,machine_id,id LIMIT 100001'),params).scalars())
                    if len(ids)>100000:raise ServiceError('DATASET_TOO_LARGE','Narrow batch filters to at most 100000 rows')
                    if not ids:raise ServiceError('EMPTY_BATCH','No measurements match the filters')
                    body['measurement_ids']=ids
                job=str(uuid4());body['bootstrap']=bootstrap
                conn.execute(text("INSERT INTO zsk_jobs(id,kind,status,request) VALUES(CAST(:id AS uuid),:kind,'queued',CAST(:request AS jsonb))"),{'id':job,'kind':kind,'request':encode(body)})
                audit(conn,'queue_'+kind,{'job_id':job,'bootstrap':bootstrap})
                return {'job_id':job,'status':'queued','kind':kind}
            # Fingerprint original request, not internal generated IDs/version.
            return self.idempotent(conn,key,kind,dict(body),create)
    def job(self,job_id):
        with self.engine.connect() as conn:
            row=conn.execute(text('SELECT id AS job_id,kind,status,progress,result,error,attempts,created_at,updated_at FROM zsk_jobs WHERE id=CAST(:id AS uuid)'),{'id':uuid(job_id)}).mappings().first()
        if not row:raise ServiceError('NOT_FOUND','Job not found',404)
        return dict(row)
    def status(self):
        with self.engine.connect() as conn:
            row=conn.execute(text('SELECT * FROM zsk_state WHERE id=1')).mappings().one()
            jobs=conn.execute(text('SELECT id AS job_id,kind,status,progress,error FROM zsk_jobs ORDER BY created_at DESC LIMIT 10')).mappings().all()
            counts={source:conn.scalar(text(f'SELECT count(*) FROM {table}')) for source,table in TABLES.items()}
        return dict(row)|{'counts':counts,'jobs':[dict(j) for j in jobs],'notice':NOTICE}
    def metrics(self,version=None):
        with self.engine.connect() as conn:
            row=conn.execute(text('SELECT * FROM zsk_models WHERE version=CAST(:v AS uuid)'),{'v':uuid(version)}).mappings().first() if version else self.active(conn)
        if not row:raise ServiceError('NOT_FOUND','Model version not found',404)
        return {'model_version':str(row['version']),'created_at':row['created_at'],'metrics':row['metrics'],'notice':NOTICE}
    def predictions(self,filters:Filters,job_id=None,model_version=None):
        where,params=conditions(filters,'m.')
        if job_id:where+=' AND EXISTS(SELECT 1 FROM zsk_job_predictions jp WHERE jp.prediction_id=p.id AND jp.job_id=CAST(:job AS uuid))';params['job']=uuid(job_id)
        if model_version:where+=' AND p.model_version=CAST(:version AS uuid)';params['version']=uuid(model_version)
        # IDs from two distinct source tables remain disambiguated.
        query="FROM zsk_predictions p JOIN (SELECT id,timestamp,machine_id,'zsk_unlabeled_measurements' AS source FROM zsk_unlabeled_measurements UNION ALL SELECT id,timestamp,machine_id,'zsk_labeled_measurements' AS source FROM zsk_labeled_measurements) m ON m.id=p.measurement_id AND m.source=p.source_table"
        with self.engine.connect() as conn:
            total=conn.scalar(text(f'SELECT count(*) {query} WHERE {where}'),params)
            items=conn.execute(text(f'SELECT p.*,m.timestamp,m.machine_id {query} WHERE {where} ORDER BY m.timestamp,m.machine_id,p.id LIMIT :limit OFFSET :offset'),params|{'limit':filters.page_size,'offset':(filters.page-1)*filters.page_size}).mappings().all()
        return {'items':[dict(r)|{'predicted_status':zsk_model.LABELS[r['predicted_health_label']]} for r in items],'total':total,'page':filters.page,'page_size':filters.page_size,'notice':NOTICE}
    def rollback(self,request:RollbackInput):
        self.loaded(uuid(request.model_version))
        with self.engine.begin() as conn:
            def activate():
                conn.execute(text('UPDATE zsk_state SET active_version=CAST(:v AS uuid) WHERE id=1'),{'v':uuid(request.model_version)})
                audit(conn,'rollback',{'model_version':uuid(request.model_version)})
                return {'model_version':uuid(request.model_version),'status':'active'}
            return self.idempotent(conn,request.idempotency_key,'rollback',request.model_dump(),activate)
    def start(self):
        with self.engine.connect() as conn:phase=conn.scalar(text('SELECT phase FROM zsk_state WHERE id=1'))
        if phase=='training':
            try:self.queue({'idempotency_key':'zsk-initial-training-v1','evaluation_config':{'test_fraction':.2,'gap':20}},'train',True)
            except ServiceError as error:
                if error.code!='TRAINING_BUSY':raise
        self._thread=threading.Thread(target=self.worker,name='zsk-jobs',daemon=True);self._thread.start()
    def stop(self):
        self._stop.set()
        if self._thread:self._thread.join(timeout=30)
    def worker(self):
        while not self._stop.is_set():
            try:
                # Dedicated session advisory lock: only its holder may recover or execute jobs.
                with self.engine.connect() as lock:
                    acquired=lock.scalar(text('SELECT pg_try_advisory_lock(91320261011)'));lock.commit()
                    if not acquired:self._stop.wait(.5);continue
                    try:
                        with self.engine.begin() as conn:
                            conn.execute(text("UPDATE zsk_jobs SET status='queued',updated_at=now() WHERE status='running'"))
                        while not self._stop.is_set():
                            with self.engine.begin() as conn:
                                job=conn.execute(text("SELECT * FROM zsk_jobs WHERE status='queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED")).mappings().first()
                                if not job:break
                                job=dict(job)
                                conn.execute(text("UPDATE zsk_jobs SET status='running',attempts=attempts+1,error=NULL,updated_at=now() WHERE id=:id"),{'id':job['id']})
                            try:
                                if job['kind']=='train':self.train_job(job)
                                else:self.batch_job(job)
                            except Exception as error:
                                transient=isinstance(error,OperationalError)
                                code=str(error) if isinstance(error,(ServiceError,ValueError)) else 'Job execution failed; inspect service health'
                                # Never log raw DB exception text, documents, connection credentials or feature values.
                                with self.engine.begin() as conn:
                                    status='queued' if transient and job['attempts']+1<self.settings.job_attempts else 'failed'
                                    conn.execute(text('UPDATE zsk_jobs SET status=:status,error=:error,updated_at=now() WHERE id=:id'),{'status':status,'error':code[:500],'id':job['id']})
                                logger.error(encode({'event':'job_error','job_id':str(job['id']),'transient':transient}))
                                if transient:self._stop.wait(min(30,2**(job['attempts']+1)))
                    finally:
                        lock.execute(text('SELECT pg_advisory_unlock(91320261011)'));lock.commit()
            except Exception:
                logger.error(encode({'event':'worker_unavailable'}));self._stop.wait(2)
            self._stop.wait(.25)
    def train_job(self,job):
        version=str(job['id']);directory=self.settings.artifact_dir
        path=directory/f'{version}.joblib';temp=directory/f'{version}.tmp.joblib';csv_path=directory/f'{version}.training.csv';metrics_path=directory/f'{version}.tmp.json'
        try:
            with self.engine.connect() as conn:
                registered=conn.scalar(text('SELECT count(*) FROM zsk_models WHERE version=:v'),{'v':job['id']})
                rows=[model_row(r) for r in conn.execute(text('SELECT * FROM zsk_labeled_measurements ORDER BY timestamp,machine_id,id LIMIT 100001')).mappings()]
            if len(rows)>100000:raise ServiceError('TRAINING_LIMIT','Training is limited to 100000 labeled rows')
            if not registered:
                job['request']['training_ids']=[r['id'] for r in rows]
                with self.engine.begin() as conn:
                    conn.execute(text('UPDATE zsk_jobs SET request=CAST(:request AS jsonb) WHERE id=:id'),{'request':encode(job['request']),'id':job['id']})
            if registered:
                self.finish_training(job,self.metrics(version)['metrics']);return
            if len(rows)<100:raise ServiceError('NO_TRAINING_LABELS','Not enough labeled measurements for chronological evaluation')
            zsk_model.save_csv(csv_path,rows)
            config=job['request'].get('evaluation_config',{})
            metrics=zsk_model.train(str(csv_path),str(temp),str(metrics_path),test_fraction=config.get('test_fraction',.2),gap=config.get('gap',20))
            # Smoke-test the actual new artifact before activation. No untrusted artifact upload route exists.
            smoke=zsk_model.predict(rows[:3],str(temp))
            if len(smoke)!=3:raise ValueError('Artifact validation failed')
            with temp.open('rb') as stream:os.fsync(stream.fileno())
            os.replace(temp,path)
            fd=os.open(directory,os.O_RDONLY);os.fsync(fd);os.close(fd)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.engine.begin() as conn:
                conn.execute(text('INSERT INTO zsk_models(version,artifact_sha256,metrics) VALUES(:v,:hash,CAST(:metrics AS jsonb)) ON CONFLICT(version) DO NOTHING'),{'v':job['id'],'hash':digest,'metrics':encode(metrics)})
            self.finish_training(job,metrics)
        finally:
            # User requested training data removal. Never retain temporary labeled snapshots.
            for item in (temp,csv_path,metrics_path):item.unlink(missing_ok=True)
    def finish_training(self,job,metrics):
        with self.engine.begin() as conn:
            conn.execute(text('UPDATE zsk_state SET active_version=:v WHERE id=1'),{'v':job['id']})
            if job['request'].get('bootstrap'):
                seed(conn,TABLES['unlabeled'],self.settings.data_dir/'zsk_unlabeled_1000.csv',False)
                conn.execute(text("DELETE FROM zsk_predictions WHERE source_table='zsk_labeled_measurements' AND measurement_id=ANY(:ids)"),{'ids':job['request']['training_ids']})
                conn.execute(text('DELETE FROM zsk_labeled_measurements WHERE id=ANY(:ids)'),{'ids':job['request']['training_ids']})
                # Explicitly authorized replacement of the previous manufacturing dataset only.
                conn.execute(text('DROP TABLE IF EXISTS manufacturing_products'))
                conn.execute(text('DROP TABLE IF EXISTS evaluation_products'))
                conn.execute(text("UPDATE zsk_state SET phase='inference' WHERE id=1"))
                audit(conn,'replace_training_with_unlabeled',{'labeled_remaining':0,'seeded_unlabeled':1000,'legacy_tables_removed':['manufacturing_products','evaluation_products']})
            else:
                conn.execute(text("DELETE FROM zsk_predictions WHERE source_table='zsk_labeled_measurements' AND measurement_id=ANY(:ids)"),{'ids':job['request']['training_ids']})
                conn.execute(text('DELETE FROM zsk_labeled_measurements WHERE id=ANY(:ids)'),{'ids':job['request']['training_ids']})
                audit(conn,'purge_training_labels',{'model_version':str(job['id'])})
            result={'model_version':str(job['id']),'metrics':metrics,'notice':NOTICE}
            conn.execute(text("UPDATE zsk_jobs SET status='completed',progress=100,result=CAST(:result AS jsonb),updated_at=now() WHERE id=:id"),{'result':encode(result),'id':job['id']})
            audit(conn,'activate_model',{'model_version':str(job['id']),'training_rows':metrics['labeled_rows']})
    def batch_job(self,job):
        request=job['request'];ids=request['measurement_ids'];source=request['source'];version=request['model_version'];size=request['page_size']
        # Checkpoint contains the durable number of processed target IDs, not invented percent.
        with self.engine.connect() as conn:
            progress=conn.scalar(text('SELECT progress FROM zsk_jobs WHERE id=:id'),{'id':job['id']})
        for offset in range(progress,len(ids),size):
            if self._stop.is_set():return
            target_ids=ids[offset:offset+size];predictions=[]
            with self.engine.connect() as conn:
                rows=conn.execute(text(f'SELECT * FROM {TABLES[source]} WHERE id=ANY(:ids) ORDER BY timestamp,machine_id,id'),{'ids':target_ids}).mappings().all()
                if len(rows)!=len(target_ids):raise ServiceError('MEASUREMENT_REMOVED','Batch snapshot measurements are no longer available')
                # Include preceding two rows for each machine, including rows outside the requested date filter/page.
                history={}
                for row in rows:
                    machine=row['machine_id']
                    if machine not in history:history[machine]=self.history(conn,source,model_row(row))
                combined=sorted([r for hist in history.values() for r in hist]+[model_row(r) for r in rows],key=lambda r:(r['timestamp'],r['machine_id']))
                by_key={(r['machine_id'],r['timestamp']):r for r in combined}
                combined=sorted(by_key.values(),key=lambda r:(r['timestamp'],r['machine_id']))
                outputs=self.predict_rows(combined,version)
                wanted={(r['machine_id'],model_row(r)['timestamp']):r['id'] for r in rows}
                for output in outputs:
                    identity=(output['machine_id'],output['timestamp'])
                    if identity in wanted:predictions.append({'source':TABLES[source],'measurement':wanted[identity],'version':version,'label':output['predicted_health_label'],'probability':output['fault_probability'],'job':job['id']})
            with self.engine.begin() as conn:
                conn.execute(text('INSERT INTO zsk_predictions(source_table,measurement_id,model_version,predicted_health_label,fault_probability,job_id) VALUES(:source,:measurement,CAST(:version AS uuid),:label,:probability,:job) ON CONFLICT(source_table,measurement_id,model_version) DO UPDATE SET job_id=EXCLUDED.job_id'),predictions)
                for prediction in predictions:
                    conn.execute(text('INSERT INTO zsk_job_predictions(job_id,prediction_id) SELECT :job,id FROM zsk_predictions WHERE source_table=:source AND measurement_id=:measurement AND model_version=CAST(:version AS uuid) ON CONFLICT DO NOTHING'),prediction)
                conn.execute(text('UPDATE zsk_jobs SET progress=:p,updated_at=now() WHERE id=:id'),{'p':offset+len(target_ids),'id':job['id']})
        with self.engine.begin() as conn:
            result={'processed_rows':len(ids),'model_version':version,'job_id':str(job['id']),'notice':NOTICE}
            conn.execute(text("UPDATE zsk_jobs SET status='completed',result=CAST(:result AS jsonb),updated_at=now() WHERE id=:id"),{'result':encode(result),'id':job['id']})
            audit(conn,'batch_completed',{'job_id':str(job['id']),'count':len(ids)})
