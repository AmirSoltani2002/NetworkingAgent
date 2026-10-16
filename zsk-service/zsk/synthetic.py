"""Synthetic engineering scenarios; NEVER manufacturer specifications or real control."""
import math
from datetime import datetime, timedelta, timezone

SCENARIOS = {
 'gearbox_vibration': ('gearbox', 'Gearbox vibration', {'gearbox_vibration_rms_mm_s':5.5,'gearbox_oil_temp_c':22,'screw_torque_pct':12}),
 'bearing_deterioration': ('gearbox', 'Bearing deterioration', {'gearbox_vibration_rms_mm_s':6.5,'gearbox_oil_temp_c':32,'motor_current_a':18}),
 'excessive_torque': ('barrel', 'Excessive screw torque', {'screw_torque_pct':55,'motor_current_a':45,'motor_power_kw':45}),
 'oil_overheating': ('gearbox', 'Oil overheating', {'gearbox_oil_temp_c':48,'gearbox_vibration_rms_mm_s':2.5}),
 'barrel_instability': ('cooling', 'Barrel temperature instability', {'barrel_zone_temp_c':35,'melt_temp_c':25}),
 'high_melt_pressure': ('die', 'High melt pressure', {'melt_pressure_bar':90,'screw_torque_pct':35,'feed_rate_kg_h':-35}),
 'unstable_feeding': ('feeder', 'Unstable feeding', {'feed_rate_kg_h':-50,'screw_torque_pct':18,'melt_pressure_bar':25}),
 'excessive_current': ('motor', 'Excessive motor current', {'motor_current_a':65,'motor_power_kw':50,'screw_torque_pct':30}),
}
BASE = dict(screw_speed_rpm=180,screw_torque_pct=41,motor_current_a=75,motor_power_kw=85,
 gearbox_vibration_rms_mm_s=1.6,gearbox_oil_temp_c=44,barrel_zone_temp_c=190,
 melt_temp_c=195,melt_pressure_bar=80,feed_rate_kg_h=145)


def severity(fault, minutes):
    if not fault: return 0.0
    return max(0.0,min(1.0,(minutes-fault['start_minute'])/fault.get('duration_minutes',60))) if fault.get('mode','gradual')=='gradual' else float(minutes>=fault['start_minute'])


def sensors(minutes, faults=(), running=True, seed=1, residual=0.0):
    # Shared low-frequency load/thermal drivers correlate signals. Deterministic
    # phases make restart/catch-up reproducible without frame-dependent randomness.
    load=math.sin(minutes*.07+seed)*1.4+math.sin(minutes*.013+seed*.3)*.8
    heat=math.sin(minutes*.029+seed*.7)
    row=BASE.copy()
    row.update(screw_torque_pct=41+load,motor_current_a=75+load*1.7,
     motor_power_kw=85+load*1.8,gearbox_vibration_rms_mm_s=1.6+load*.035,
     gearbox_oil_temp_c=44+heat*.7,barrel_zone_temp_c=190+heat,
     melt_temp_c=195+heat*.8,melt_pressure_bar=80+load*.8,
     feed_rate_kg_h=145+math.sin(minutes*.035+seed)*2)
    for fault in faults:
        amount=severity(fault,minutes)
        for name,effect in SCENARIOS[fault['fault_id']][2].items():
            factor=amount
            if fault['fault_id'] in ('barrel_instability','unstable_feeding'):
                factor*=.65+.35*math.sin(minutes*.5+seed)
            row[name]+=effect*factor
        if fault['fault_id'] in ('gearbox_vibration','bearing_deterioration','high_melt_pressure'):
            row['motor_current_a']+=amount*12;row['motor_power_kw']+=amount*15
    # After repairs thermal/mechanical residuals decay gradually.
    row['gearbox_vibration_rms_mm_s']+=residual*2;row['gearbox_oil_temp_c']+=residual*8
    if not running:
        for name in ('screw_speed_rpm','screw_torque_pct','motor_current_a','motor_power_kw','gearbox_vibration_rms_mm_s','melt_pressure_bar','feed_rate_kg_h'):row[name]=0.0
        row['gearbox_oil_temp_c']=35+(row['gearbox_oil_temp_c']-35)*.5
    return {k:round(max(0,v),4) for k,v in row.items()}


def forecast_episodes(count=24, points=100):
    """Separate labeled simulator trajectories; not the purged historical labels.

    Fault onset = severity >= .7. Future labels are built later, outside features.
    Different episodes/phases and fault order are chronological synthetic runs.
    """
    start=datetime(2026,10,1,tzinfo=timezone.utc);rows=[]
    kinds=list(SCENARIOS)
    for episode in range(count):
        for i in range(points):
            minute=i*5;start_fault=120+(episode%5)*10
            fault={'fault_id':kinds[episode%len(kinds)],'start_minute':start_fault,'duration_minutes':100+(episode%3)*10}
            truth=int(severity(fault,minute)>=.7)
            row=sensors(minute,[fault] if minute>=start_fault else [],seed=episode+7)
            row.update(timestamp=(start+timedelta(minutes=episode*points*5+minute)).isoformat(),
             machine_id=f'forecast-episode-{episode}',recipe='A',episode=episode,truth_fault=truth)
            rows.append(row)
    return rows
