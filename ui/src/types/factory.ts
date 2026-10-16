export type FactoryPage='Factory Simulation'|'Machine Monitoring'|'Alarms'|'Simulation Settings';
export type Component={id:string;name:string;x:number;y:number};
export type Measurement=Record<string,number|string>;
export interface FactoryAction{id:string;kind:string;status:string;result:{action_id:string;status:string;timestamp:string;execution_evidence:unknown};simulation_timestamp:string;}
export interface FactoryAlarm{id:string;alarm_type:string;component:string;severity:string;status:string;agent_task_id:string|null;agent_status:string|null;agent_activity:{latestTool?:string;latestToolStatus?:string;progress?:number;result?:string;lastError?:string}|null;details:{prediction:{risk_score?:number;fault_probability?:number;prediction_horizon_minutes?:number;model_version?:string}};}
export interface FactoryState{
 epoch:string;version:number;sequence:number;machine_id:string;clock:{timestamp:string;elapsed_seconds:number;paused:boolean;speed:number};mode:string;condition:string;
 technician:{id:string;name:string;x:number;y:number;mode:string;destination:string|null};components:Component[];faults:{fault_id:string;start_minute:number;duration_minutes:number}[];
 last_inspections:Record<string,{observation:string;timestamp:string}>;latest_measurement:Measurement|null;alarms:FactoryAlarm[];actions:FactoryAction[];
 monitoring:{status:string;last_error?:string;last_measurement_id:number;next_due_minute:number;attempts:number};
 prediction:{measurement_id:number;current_condition:{predicted_status:string;fault_probability:number;model_version:string};forecast:{risk_score?:number;prediction_horizon_minutes?:number;model_version?:string;status?:string}}|null;
 policy:{auto_stop_allowed:boolean;auto_restart_allowed:boolean;auto_maintenance_allowed:boolean};scenarios:{fault_id:string;name:string;component:string}[];automatic_faults?:boolean;notice:string;
}
