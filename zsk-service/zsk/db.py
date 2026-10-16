import hashlib, json
from pathlib import Path
from sqlalchemy import create_engine, text
from .errors import ServiceError
from .schemas import Measurement
from .zsk_model import load_csv, MEASURED

TABLES={'labeled':'zsk_labeled_measurements','unlabeled':'zsk_unlabeled_measurements'}
COLUMNS=['timestamp','machine_id','recipe',*MEASURED,'alarm_active']

def database(settings):
    return create_engine(settings.database_url,pool_pre_ping=True,pool_size=8,max_overflow=4,connect_args={'connect_timeout':5,'options':'-c statement_timeout=15000'})
def audit(conn,action,details):
    conn.execute(text('INSERT INTO zsk_audit(action,details) VALUES(:action,CAST(:details AS jsonb))'),{'action':action,'details':json.dumps(details)})
def seed(conn,table,path,labeled):
    rows=load_csv(path)
    fields=COLUMNS+(['fault_type_simulated','health_label'] if labeled else [])
    sql=f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join(':'+k for k in fields)}) ON CONFLICT(machine_id,timestamp) DO NOTHING"
    clean=[]
    for row in rows:
        measurement=Measurement.model_validate({k:row[k] for k in COLUMNS if k!='alarm_active'}|{'alarm_active':int(row['alarm_active'])}).row()
        if labeled:
            measurement.update(health_label=int(row['health_label']),fault_type_simulated=row['fault_type_simulated'])
        clean.append(measurement)
    conn.execute(text(sql),clean)
    return len(clean)
def initialize(engine,settings):
    settings.artifact_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(91320261009)'))
        conn.execute(text('CREATE TABLE IF NOT EXISTS zsk_migrations(name TEXT PRIMARY KEY,checksum TEXT NOT NULL)'))
        for path in sorted(settings.migration_dir.glob('*.sql')):
            sql=path.read_text(); digest=hashlib.sha256(sql.encode()).hexdigest()
            old=conn.scalar(text('SELECT checksum FROM zsk_migrations WHERE name=:n'),{'n':path.name})
            if old and old!=digest:
                raise ServiceError('MIGRATION_CHANGED','An applied ZSK migration was modified',500)
            if not old:
                conn.connection.driver_connection.execute(sql,prepare=False)
                conn.execute(text('INSERT INTO zsk_migrations VALUES(:n,:c)'),{'n':path.name,'c':digest})
        if not conn.scalar(text('SELECT count(*) FROM zsk_state')):
            seed(conn,TABLES['labeled'],settings.data_dir/'zsk_labeled_1000.csv',True)
            conn.execute(text("INSERT INTO zsk_state(id,phase) VALUES(1,'training')"))
            audit(conn,'initial_labeled_import',{'count':1000,'timezone':'UTC','synthetic':True})
        # Never seed labeled rows again after the user's requested training/purge transition.
