"""Versioned future-onset baseline, entirely separate from current health labels."""
import hashlib,json,os,threading
from datetime import datetime
from uuid import uuid4
import joblib,numpy as np
from sqlalchemy import text
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report,confusion_matrix,balanced_accuracy_score
from .zsk_model import feature_matrix,FEATURES
from .synthetic import forecast_episodes
from .errors import ServiceError


def supervised(rows,horizon):
    """Only observed features; targets look forward. Censor incomplete horizons
    and current faults. Episode boundaries never share a rolling window."""
    X=feature_matrix(rows);indices=[];labels=[]
    for i,r in enumerate(rows):
        if r['truth_fault']:continue
        now=datetime.fromisoformat(r['timestamp']);future=[]
        for j in range(i+1,len(rows)):
            if rows[j]['machine_id']!=r['machine_id']:break
            dt=(datetime.fromisoformat(rows[j]['timestamp'])-now).total_seconds()/60
            if dt>horizon:break
            future.append(j)
        if not future or (datetime.fromisoformat(rows[future[-1]]['timestamp'])-now).total_seconds()/60<horizon:continue
        indices.append(i);labels.append(int(any(rows[j]['truth_fault'] for j in future)))
    return X[indices],np.asarray(labels),indices


def fit_baseline(rows,horizon=30):
    X,y,indices=supervised(rows,horizon)
    cutoff=int(len(rows)*.8);embargo=int(horizon/5)+3
    train=np.array([j for j,i in enumerate(indices) if i<cutoff-embargo]);test=np.array([j for j,i in enumerate(indices) if i>=cutoff])
    if len(train)<100 or len(test)<20 or len(set(y[train]))!=2 or len(set(y[test]))!=2:raise ValueError('Both onset classes required in chronological partitions')
    # Synthetic episode ID/order and truth are NEVER input features.
    model=RandomForestClassifier(n_estimators=120,max_depth=8,min_samples_leaf=3,class_weight='balanced',random_state=20261009,n_jobs=1)
    model.fit(X[train],y[train]);pred=model.predict(X[test]);report=classification_report(y[test],pred,output_dict=True,zero_division=0)
    metrics={'synthetic_only':True,'source':'reproducible simulator episodes, separate from historical condition data','horizon_minutes':horizon,'cadence_minutes':5,'feature_names':FEATURES,'train_rows':len(train),'test_rows':len(test),'embargo_raw_rows':embargo,'cutoff_timestamp':rows[cutoff]['timestamp'],'train_last_timestamp':rows[indices[train[-1]]]['timestamp'],'test_first_timestamp':rows[indices[test[0]]]['timestamp'],'training_label_counts':np.bincount(y[train],minlength=2).tolist(),'test_label_counts':np.bincount(y[test],minlength=2).tolist(),'balanced_accuracy':float(balanced_accuracy_score(y[test],pred)),'classification_report':report,'confusion_matrix_0_1':confusion_matrix(y[test],pred,labels=[0,1]).tolist(),'limitation':'Evaluation candidate is deployed without fitting holdout rows. Synthetic-only probabilities are uncalibrated; no industrial prognosis. Unseen scenarios and simulator distribution shift can fail.'}
    return {'model':model,'feature_names':FEATURES,'horizon_minutes':horizon,'metrics':metrics},metrics

class Forecast:
    def __init__(self,engine,settings):self.engine,self.settings=engine,settings;self.lock=threading.Lock();self.cache=None
    def bootstrap(self):
        with self.lock,self.engine.begin() as conn:
            conn.execute(text('SELECT pg_advisory_xact_lock(91320261021)'))
            active=conn.execute(text('SELECT horizon_minutes FROM zsk_forecast_models WHERE active')).first()
            if active and active[0]==self.settings.forecast_horizon_minutes:return
            if not self.settings.forecast_bootstrap: return
            artifact,metrics=fit_baseline(forecast_episodes(),self.settings.forecast_horizon_minutes)
            version=str(uuid4());path=self.settings.artifact_dir/f'forecast-{version}.joblib';temp=path.with_suffix('.tmp')
            joblib.dump(artifact,temp)
            with temp.open('rb') as f:os.fsync(f.fileno())
            os.replace(temp,path)
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            conn.execute(text('UPDATE zsk_forecast_models SET active=false WHERE active'))
            conn.execute(text('INSERT INTO zsk_forecast_models(version,horizon_minutes,artifact_sha256,metrics,active) VALUES(CAST(:v AS uuid),:h,:s,CAST(:m AS jsonb),true)'),{'v':version,'h':artifact['horizon_minutes'],'s':sha,'m':json.dumps(metrics)})
    def load(self):
        with self.engine.connect() as conn:row=conn.execute(text('SELECT * FROM zsk_forecast_models WHERE active')).mappings().first()
        if not row:raise ServiceError('FORECAST_NOT_READY','Forecast model is unavailable',503)
        path=self.settings.artifact_dir/f"forecast-{row['version']}.joblib"
        if not path.is_file() or path.is_symlink() or path.stat().st_uid!=os.getuid() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['artifact_sha256']:raise ServiceError('UNTRUSTED_FORECAST','Forecast artifact failed integrity checks',503)
        with self.lock:
            if not self.cache or self.cache[0]!=str(row['version']):
                artifact=joblib.load(path)
                if artifact['feature_names']!=FEATURES:raise ServiceError('FEATURE_MISMATCH','Forecast features changed',503)
                self.cache=(str(row['version']),artifact)
        return self.cache
    def metrics(self):
        version,artifact=self.load();return {'model_version':version,'metrics':artifact['metrics'],'prediction_kind':'future_fault_onset','synthetic_only':True}
    def predict(self,rows):
        if len(rows)!=3 or len({r['machine_id'] for r in rows})!=1:raise ServiceError('MISSING_HISTORY','Forecast needs target and two same-machine preceding readings')
        times=[datetime.fromisoformat(r['timestamp']) for r in rows]
        if any(abs((b-a).total_seconds()-300)>1 for a,b in zip(times,times[1:])):raise ServiceError('INVALID_CADENCE','Forecast requires five-minute continuous readings')
        version,artifact=self.load();X=feature_matrix(rows)
        probability=artifact['model'].predict_proba(X)[-1,list(artifact['model'].classes_).index(1)]
        return {'prediction_kind':'future_fault_onset','risk_score':float(probability),'prediction_horizon_minutes':artifact['horizon_minutes'],'model_version':version,'simulation_timestamp':rows[-1]['timestamp'],'synthetic_only':True,'notice':'Synthetic future-onset baseline; uncalibrated risk, not industrial failure prognosis.'}
