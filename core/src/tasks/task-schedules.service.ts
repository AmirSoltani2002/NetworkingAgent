import { BadRequestException, Injectable, Logger, NotFoundException, type OnApplicationBootstrap, type OnModuleDestroy } from '@nestjs/common';
import { CronExpressionParser } from 'cron-parser';
import { randomUUID } from 'node:crypto';
import { TasksService } from './tasks.service';
import { object, text, uuid } from './task-contract';
export function nextCron(cron:string,timezone:string,currentDate:Date){try{return CronExpressionParser.parse(cron,{tz:timezone,currentDate}).next().toDate();}catch{throw new BadRequestException('Invalid cron expression or time zone.');}}
@Injectable()
export class TaskSchedulesService implements OnApplicationBootstrap,OnModuleDestroy{
 private timer?:NodeJS.Timeout;private polling=false;private readonly logger=new Logger('TaskSchedules');
 constructor(private readonly tasks:TasksService){}
 onApplicationBootstrap(){if(process.env.TASK_WORKER_ENABLED==='false')return;this.timer=setInterval(()=>void this.tick(),1000);}
 onModuleDestroy(){if(this.timer)clearInterval(this.timer);}
 async list(kind:'schedules'){void kind;return(await this.tasks.db.pool.query('SELECT * FROM task_schedules ORDER BY created_at DESC')).rows;}
 async save(kind:'schedules',body:unknown,id?:string){const b=object(body);const name=text(b.name,200);if(typeof b.enabled!=='boolean')throw new BadRequestException('Choose enabled state.');
  const allowed=['name','enabled','kind','cron','timezone','runAt','template'];if(Object.keys(b).some(k=>!allowed.includes(k)))throw new BadRequestException('Unknown schedule field.');
  const template=await this.tasks.validateCreate(b.template);delete template.dedupeKey;delete template.messageId;
  const key=id??randomUUID();
  if(kind==='schedules'){
   if(!['once','cron'].includes(String(b.kind)))throw new BadRequestException('Choose one-time or cron scheduling.');const timezone=text(b.timezone??'UTC',100);try{new Intl.DateTimeFormat('en',{timeZone:timezone});}catch{throw new BadRequestException('Use a valid IANA time zone.');}
   const next=b.kind==='cron'?nextCron(text(b.cron,200),timezone,new Date()):new Date(text(b.runAt,100));if(!Number.isFinite(next.getTime())||next.getTime()<=Date.now())throw new BadRequestException('One-time execution must be in the future.');
   const row=id?await this.tasks.db.pool.query('UPDATE task_schedules SET name=$2,enabled=$3,kind=$4,cron=$5,timezone=$6,next_run_at=$7,template=$8::jsonb,updated_at=now() WHERE id=$1 RETURNING *',[key,name,b.enabled,b.kind,b.kind==='cron'?b.cron:null,timezone,next,JSON.stringify(template)]):await this.tasks.db.pool.query('INSERT INTO task_schedules(id,name,enabled,kind,cron,timezone,next_run_at,template) VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb) RETURNING *',[key,name,b.enabled,b.kind,b.kind==='cron'?b.cron:null,timezone,next,JSON.stringify(template)]);if(!row.rowCount)throw new NotFoundException('Schedule not found.');return row.rows[0];
  }
  throw new BadRequestException('Unsupported schedule configuration.');
 }
 async enable(kind:'schedules',id:string,enabled:boolean){void kind;const table='task_schedules';const rows=await this.tasks.db.pool.query(`UPDATE ${table} SET enabled=$2,updated_at=now() WHERE id=$1 RETURNING *`,[id,enabled]);if(!rows.rowCount)throw new NotFoundException('Configuration not found.');return rows.rows[0];}
 async remove(kind:'schedules',id:string){void kind;const table='task_schedules';const row=await this.tasks.db.pool.query(`DELETE FROM ${table} WHERE id=$1 RETURNING id`,[id]);if(!row.rowCount)throw new NotFoundException('Configuration not found.');return{deleted:true};}
 async history(kind:'schedules',id:string){uuid(id);return(await this.tasks.db.pool.query('SELECT id,status,goal,source,created_at,finished_at FROM agent_tasks WHERE source->>$1=$2 ORDER BY created_at DESC LIMIT 100',['scheduleId',id])).rows;}
 async tick(){if(this.polling)return;this.polling=true;let failedScheduleId:string|undefined;try{
  await this.tasks.db.transaction(async client=>{
   const schedule=(await client.query('SELECT * FROM task_schedules WHERE enabled AND next_run_at<=now() ORDER BY next_run_at FOR UPDATE SKIP LOCKED LIMIT 1')).rows[0];if(!schedule)return;
   failedScheduleId=schedule.id;const scheduledFor=new Date(schedule.next_run_at).toISOString();await this.tasks.insert(client,{...schedule.template,dedupeKey:'schedule:'+schedule.id+':'+scheduledFor},{scheduleId:schedule.id,scheduledFor});
   // Coalesce missed occurrences to one catch-up execution, then schedule from current time.
   await client.query('UPDATE task_schedules SET enabled=$2,next_run_at=$3,updated_at=now() WHERE id=$1',[schedule.id,schedule.kind==='cron',schedule.kind==='cron'?nextCron(schedule.cron,schedule.timezone,new Date()):schedule.next_run_at]);
  });
  failedScheduleId=undefined;
 }catch(error){if(failedScheduleId&&(error instanceof BadRequestException||error instanceof NotFoundException))await this.tasks.db.pool.query("UPDATE task_schedules SET enabled=false,template=template||$2::jsonb,updated_at=now() WHERE id=$1",[failedScheduleId,JSON.stringify({_lastError:'Configured task template is no longer valid. Edit the schedule.'})]).catch(()=>undefined);this.logger.warn(JSON.stringify({event:'task_schedule_poll_failed'}));}finally{this.polling=false;}}
}
