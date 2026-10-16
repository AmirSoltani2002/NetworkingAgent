import { BadRequestException, Body, Controller, Get, Headers, NotFoundException, Param, Post } from '@nestjs/common';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { EnvironmentStore } from '../config/environment-store.service';
import { TasksService } from '../tasks/tasks.service';
import { digest,object,text,uuid,validateDecision,type Criterion } from '../tasks/task-contract';
import { authenticate,eventInput,expand } from './integration-contract';
@Controller('internal/task-events')
export class IntegrationsController {
 constructor(private readonly tasks:TasksService,private readonly environment:EnvironmentStore){}
 @Post() async receive(@Body() raw:unknown,@Headers('authorization') auth?:string){
  const env=await this.environment.read();authenticate(auth,env.TASK_INTEGRATION_TOKEN);
  const input=eventInput(raw),config=object(JSON.parse(await readFile(resolve(__dirname,'../../config/task-integrations.json'),'utf8')));
  const templates=object(config.templates),template=object(templates[input.template]);
  const source=text(template.source,100);const fingerprint=digest(input);
  // A service credential can select ONLY preconfigured templates; request text,
  // grants, criteria and filesystem/command capabilities never come from callers.
  return this.tasks.db.transaction(async client=>{
   await client.query('SELECT pg_advisory_xact_lock(hashtextextended($1,3))',[source+input.eventId]);
   const old=(await client.query('SELECT * FROM task_integration_receipts WHERE source=$1 AND event_id=$2',[source,input.eventId])).rows[0];
   if(old){if(old.fingerprint!==fingerprint)throw new BadRequestException('Event ID conflicts with previous payload.');return{taskId:old.task_id,duplicate:true};}
   const grants=expand(template.grants??[],env,{},false);
   const variables={...input.variables,event_id:input.eventId,alarm_details:JSON.stringify(input.variables)};
   const request=expand(template.request,env,variables);
   const value=await this.tasks.validateCreate({request,grants,dedupeKey:source+':'+input.eventId});
   const plan=expand(template.plan,env,variables),criteria=expand(template.criteria,env,variables);
   validateDecision({kind:'wait',goal:value.request.slice(0,4000),plan,criteria,step:'Receive integration event',action:null,summary:'Awaiting investigation',waitSeconds:1});
   for(const criterion of criteria as Criterion[]){if(criterion.kind!=='mcp')throw new BadRequestException('Integration criteria must verify external MCP evidence.');uuid(criterion.serverId);text(criterion.tool,200);}
   const task=await this.tasks.insert(client,value,{integration:source,eventId:input.eventId,template:input.template});
   await client.query('UPDATE agent_tasks SET plan=$2::jsonb,criteria=$3::jsonb WHERE id=$1',[task.id,JSON.stringify(plan),JSON.stringify(criteria)]);
   await client.query('INSERT INTO task_integration_receipts(source,event_id,fingerprint,task_id) VALUES($1,$2,$3,$4)',[source,input.eventId,fingerprint,task.id]);
   return{taskId:task.id,duplicate:false};
  });
 }
 @Get(':eventId') async status(@Param('eventId') id:string,@Headers('authorization') auth?:string){
  const env=await this.environment.read();authenticate(auth,env.TASK_INTEGRATION_TOKEN);uuid(id);
  const receipt=(await this.tasks.db.pool.query('SELECT task_id FROM task_integration_receipts WHERE event_id=$1',[id])).rows[0];if(!receipt)throw new NotFoundException('Integration event not found.');
  const task=await this.tasks.get(receipt.task_id);
  const latest=(await this.tasks.db.pool.query('SELECT action,status FROM task_operations WHERE task_id=$1 ORDER BY created_at DESC LIMIT 1',[task.id])).rows[0];
  return this.tasks.redact({taskId:task.id,status:task.status,progress:task.progress,result:task.result,lastError:task.last_error,latestTool:latest?.action?.tool??null,latestToolStatus:latest?.status??null});
 }
}
