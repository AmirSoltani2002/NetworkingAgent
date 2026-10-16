from datetime import datetime
import pytest
from factory.domain import initial,advance,measurement,transition,Denied,InvalidAction,SCENARIOS
from zsk.synthetic import forecast_episodes,sensors
from zsk.forecast import supervised,fit_baseline

START='2026-10-01T00:00:00+00:00'
POLICY=dict(auto_stop_allowed=True,auto_restart_allowed=False,auto_maintenance_allowed=False)

def test_clock_independent_of_frames_and_pause():
    s=initial('ZSK-SIM-01',START);s['clock']['speed']=10
    once,_=advance(s,60,False)
    repeated=s
    for _ in range(60):repeated,_=advance(repeated,1,False)
    assert once['clock']==repeated['clock'];assert once['clock']['elapsed_seconds']==600
    once['clock']['paused']=True;paused,_=advance(once,300,False);assert paused['clock']==once['clock']

def test_correlated_signals_and_all_scenarios():
    baseline=sensors(60,seed=13)
    for key in SCENARIOS:
        altered=sensors(60,[dict(fault_id=key,start_minute=0,duration_minutes=60)],seed=13)
        assert any(altered[k]!=baseline[k] for k in SCENARIOS[key][2])
    load=sensors(60,[dict(fault_id='excessive_torque',start_minute=0,duration_minutes=60)],seed=13)
    assert load['screw_torque_pct']>baseline['screw_torque_pct'] and load['motor_current_a']>baseline['motor_current_a'] and load['motor_power_kw']>baseline['motor_power_kw']

def test_action_preconditions_and_actual_completed_inspection():
    s=initial('ZSK-SIM-01',START)
    with pytest.raises(Denied):transition(s,'stop',{},dict(POLICY,auto_stop_allowed=False),'a')
    s,r=transition(s,'stop',{},POLICY,'stop');assert s['mode']=='STOPPING' and r['status']=='accepted'
    s,events=advance(s,5,False);assert s['mode']=='STOPPED' and events[0][0]=='machine.action.completed'
    s,r=transition(s,'inspect',{'component_id':'gearbox'},POLICY,'inspect');assert s['technician']['mode']=='WALKING'
    s,_=advance(s,80,False);assert s['technician']['x']==320 and s['last_inspections']['gearbox']['action_id']=='inspect'
    with pytest.raises(Denied):transition(s,'maintenance',{'component_id':'gearbox','maintenance_action':'repair'},POLICY,'repair')
    s,_=transition(s,'maintenance',{'component_id':'gearbox','maintenance_action':'repair'},dict(POLICY,auto_maintenance_allowed=True),'repair');assert s['mode']=='MAINTENANCE'
    s,_=advance(s,120,False);assert s['mode']=='STOPPED' and s['residual']==1
    with pytest.raises(Denied):transition(s,'start',{},POLICY,'start')

def test_fault_and_measurement_labels_never_enter_feature_payload():
    s=initial('ZSK-SIM-01',START);s,_=transition(s,'fault',{'fault_id':'gearbox_vibration','mode':'sudden'},POLICY,'fault')
    s,_=advance(s,300,False);assert s['condition']=='FAULT'
    row=measurement(s,5);assert 'health_label' not in row and 'fault_id' not in row and row['timestamp']=='2026-10-01T00:05:00'

def test_future_labels_causal_features_censoring_and_embargo():
    rows=forecast_episodes();X,y,indices=supervised(rows,30)
    assert X.shape[1]==20 and set(y)=={0,1}
    for j,i in enumerate(indices):
        assert not rows[i]['truth_fault']
        future=rows[i+1:i+7]
        assert all(r['machine_id']==rows[i]['machine_id'] for r in future)
        assert y[j]==int(any(r['truth_fault'] for r in future))
    changed=[dict(r,truth_fault=1-r['truth_fault']) for r in rows]
    from zsk.zsk_model import feature_matrix
    import numpy as np
    assert np.array_equal(feature_matrix(rows),feature_matrix(changed))
    artifact,metrics=fit_baseline(rows)
    assert datetime.fromisoformat(metrics['train_last_timestamp'])<datetime.fromisoformat(metrics['test_first_timestamp'])
    assert metrics['embargo_raw_rows']==9 and artifact['horizon_minutes']==30

@pytest.mark.parametrize('speed',[1,5,10,60])
def test_speeds(speed):
    s=initial('ZSK-SIM-01',START);s,_=transition(s,'clock',{'speed':speed},POLICY,'clock')
    s,_=advance(s,10,False);assert s['clock']['elapsed_seconds']==speed*10
