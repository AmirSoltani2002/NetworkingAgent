import os,time
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import text
from factory.config import Settings
from factory.store import Store
from factory.worker import Worker
from zsk.config import Settings as MLSettings
from zsk.db import database,initialize
from zsk.service import Service
from zsk.forecast import Forecast

@pytest.fixture(scope='module')
def store():
    name=os.environ.get('FACTORY_DB_NAME','')
    if not name.endswith(('_test','_tests')):pytest.skip('Isolated *_test(s) DB required')
    settings=Settings();s=Store(settings)
    mlsettings=MLSettings(db_host=settings.db_host,db_name=name,db_user=settings.db_user,db_password=settings.db_password,api_key=settings.ml_api_token,admin_api_key=settings.ml_api_token,artifact_dir=Path('/tmp/test-models'),data_dir=Path('/app/data'),migration_dir=Path('/app/migrations'))
    mlengine=database(mlsettings);initialize(mlengine,mlsettings);ml=Service(mlengine,mlsettings);ml.forecast=Forecast(mlengine,mlsettings)
    ml.forecast.bootstrap();ml.start()
    for _ in range(180):
        try:ml.loaded(str(ml.active()['version']));break
        except Exception:time.sleep(.2)
    else:raise AssertionError('Initial ML unavailable')
    s.initialize();s.test_ml=ml
    yield s
    ml.stop();mlengine.dispose();s.engine.dispose()

def test_persistence_idempotency_actions_and_recovery(store):
    worker=Worker(store)
    store.action('clock',{'speed':60,'automatic_faults':False,'paused':False},str(uuid4()),operator=True)
    worker.tick(5);s=store.state();assert s['latest_measurement']
    identifier=s['latest_measurement']['id']
    with store.engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM factory_ground_truth WHERE measurement_id=:id'),{'id':identifier})==1
        assert c.scalar(text('SELECT count(*) FROM zsk_labeled_measurements'))==0
    readings=store.measurements(s['machine_id']);assert len(readings['items'])>=50
    assert all('health_label' not in r for r in readings['items'])
    key=str(uuid4());first=store.action('inspect',{'component_id':'gearbox'},key)
    second=store.action('inspect',{'component_id':'gearbox'},key);assert first==second and not first['completed']
    recovered=Store(store.settings);recovered.initialize();assert recovered.state()['epoch']==s['epoch']
    Worker(recovered).tick(2)
    assert recovered.action_status(first['action_id'])['completed'];recovered.engine.dispose()

def test_monitoring_duplicates_outage_and_outbox(store):
    worker=Worker(store);ml=store.test_ml
    def local(path,payload=None):
        if path=='/api/model/predict':
            from zsk.schemas import PredictInput
            return ml.predict(PredictInput.model_validate(payload))
        if path=='/api/forecast/predict':return ml.forecast.predict(payload['recent_history']+[payload['measurement']])
        raise AssertionError(path)
    store.action('fault',{'fault_id':'gearbox_vibration','mode':'sudden'},str(uuid4()),operator=True)
    worker.tick(10);worker.ml=lambda *a:(_ for _ in ()).throw(RuntimeError('outage'))
    worker.monitor();assert store.state()['monitoring']['status']=='retrying'
    with store.engine.begin() as c:c.execute(text('UPDATE monitoring_checkpoints SET retry_at=NULL'))
    worker.ml=local;worker.monitor()
    with store.engine.connect() as c:
        count=c.scalar(text('SELECT count(*) FROM machine_alarms'));assert count==1
        assert c.scalar(text("SELECT count(*) FROM factory_outbox WHERE status='pending'"))==1
    worker.monitor()
    with store.engine.connect() as c:assert c.scalar(text('SELECT count(*) FROM machine_alarms'))==count
    # Endpoint down: outbox remains durable, no direct provider invocation.
    worker.deliver()
    with store.engine.connect() as c:assert c.scalar(text("SELECT count(*) FROM factory_outbox WHERE status='pending' AND attempts>0"))==1
