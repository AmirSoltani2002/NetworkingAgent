"""Isolated actual PostgreSQL/model checks; never run against the manufacturing DB."""
import time, json, tempfile
from pathlib import Path
from sqlalchemy import text
from zsk.config import Settings
from zsk.db import database,initialize
from zsk.service import Service
from zsk.schemas import Filters,PredictInput,BatchInput,TrainInput,Reading,AddInput,UNITS
from zsk.errors import ServiceError
from zsk import zsk_model

settings=Settings()
assert settings.db_name.endswith(('_test','_tests'))
settings.artifact_dir=Path(tempfile.mkdtemp(prefix='zsk-tests-'))
engine=database(settings); initialize(engine,settings)
service=Service(engine,settings)
assert service.status()['counts']=={'labeled':1000,'unlabeled':0}
initialize(engine,settings)
assert service.status()['counts']['labeled']==1000
service.start()
def wait(job_id):
    for _ in range(600):
        job=service.job(job_id)
        if job['status'] in ('completed','failed'):
            assert job['status']=='completed',job
            return job
        time.sleep(.1)
    raise AssertionError('Timed out')
try:
    with engine.connect() as conn:job=str(conn.scalar(text("SELECT id FROM zsk_jobs WHERE kind='train'")))
    training=wait(job)
    assert training['result']['metrics']['labeled_rows']==1000
    assert service.status()['counts']=={'labeled':0,'unlabeled':1000}
    initialize(engine,settings)
    assert service.status()['counts']['labeled']==0
    metrics=service.metrics()['metrics'];assert metrics['test_rows']==200 and metrics['training_rows_for_evaluation']==780
    assert len(metrics['confusion_matrix_label_order_0_1'])==2
    rows=service.records(Filters(page_size=100))['items']
    assert 'health_label' not in rows[0] and 'fault_type_simulated' not in rows[0]
    batch=BatchInput(idempotency_key='test-batch-v1',page_size=37)
    queued=service.queue(batch,'batch');assert queued==service.queue(batch,'batch')
    wait(queued['job_id'])
    outputs=service.predictions(Filters(page_size=100),queued['job_id'])
    assert outputs['total']==1000
    # Last reading and boundary predictions must use exactly the same causal features as a full batch.
    last=service.records(Filters(page=10,page_size=100))['items'][-1]
    single=service.predict(PredictInput(measurement_id=last['id']))
    with engine.connect() as conn:
        probability=conn.scalar(text('SELECT fault_probability FROM zsk_predictions WHERE measurement_id=:id'),{'id':last['id']})
        all_rows=[dict(r)|{'timestamp':r['timestamp'].isoformat()} for r in conn.execute(text('SELECT * FROM zsk_unlabeled_measurements ORDER BY timestamp,machine_id')).mappings()]
    expected=service.predict_rows(all_rows,single['model_version'])
    with engine.connect() as conn:
        probabilities=list(conn.execute(text('SELECT p.fault_probability FROM zsk_predictions p JOIN zsk_unlabeled_measurements m ON m.id=p.measurement_id ORDER BY m.timestamp,m.machine_id')).scalars())
    assert [p['fault_probability'] for p in expected]==probabilities
    assert probability==single['fault_probability'] and single['history_count']==2
    try:service.queue(TrainInput(idempotency_key='no-labels-v1'),'train');raise AssertionError()
    except ServiceError as error:assert error.code=='NO_TRAINING_LABELS'
    new={k:v for k,v in last.items() if k not in ('id','provenance')}
    new.update(timestamp='2026-09-10T00:00:00Z',units=UNITS,provenance='unknown')
    request=AddInput(readings=[Reading(**new)],idempotency_key='test-append-v1')
    added=service.add(request);assert added['accepted_count']==1 and added==service.add(request)
    duplicate=service.add(request.model_copy(update={'idempotency_key':'test-duplicate-v1'}));assert duplicate['rejected_count']==1
    assert service.predict(PredictInput(measurement_id=added['accepted'][0]['id']))['history_count']==2
    try:service.queue(batch.model_copy(update={'page_size':20}),'batch');raise AssertionError()
    except ServiceError as error:assert error.code=='IDEMPOTENCY_CONFLICT'
    try:service.predict(PredictInput(measurement={k:v for k,v in new.items() if k not in ('units','provenance')}|{'machine_id':'NEW'}));raise AssertionError()
    except ServiceError as error:assert error.code=='MISSING_HISTORY'
    try:zsk_model.feature_matrix([all_rows[1],all_rows[0]]);raise AssertionError()
    except ValueError:pass
    assert len(zsk_model.FEATURES)==20 and all(key not in zsk_model.FEATURES for key in ('alarm_active','health_label','fault_type_simulated','timestamp'))
    print(json.dumps({'result':'passed','checks':18,'training_metrics':metrics,'stored_predictions':1000,'single_matches_batch':True,'labels_remaining':0},default=str))
finally:service.stop();engine.dispose()
