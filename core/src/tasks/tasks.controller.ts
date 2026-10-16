import { BadRequestException, Body, Controller, Delete, Get, Headers, Param, ParseUUIDPipe, Post, Put, Query, Sse } from '@nestjs/common';
import { Observable } from 'rxjs';
import { requireLocalOrigin } from '../config/local-origin';
import { TasksService } from './tasks.service';
import { TaskSchedulesService } from './task-schedules.service';
import { object, text, uuid } from './task-contract';

@Controller()
export class TasksController{
 constructor(private readonly tasks:TasksService,private readonly scheduler:TaskSchedulesService){}
 @Get('tasks')list(@Query() query:Record<string,unknown>){return this.tasks.list(query);}
 @Post('tasks')async create(@Body() body:unknown,@Headers('origin') origin?:string){requireLocalOrigin(origin);const task=await this.tasks.create(body);return this.tasks.publicGet(task.id);}
 @Sse('tasks/stream')stream(@Headers('last-event-id') previous?:string){let cursor=previous&&/^\d+$/.test(previous)?previous:'0';return new Observable<{id:string;type:string;data:unknown}>(subscriber=>{let running=false;const tick=async()=>{if(running)return;running=true;try{const events=(await this.tasks.db.pool.query('SELECT sequence::text,task_id,type FROM task_events WHERE sequence>$1 ORDER BY sequence LIMIT 100',[cursor])).rows;for(const event of events){cursor=event.sequence;subscriber.next({id:cursor,type:'task',data:{id:event.task_id,type:event.type}});}}catch{subscriber.next({type:'connection',id:cursor,data:{error:'Task updates temporarily unavailable.'}});}finally{running=false;}};const timer=setInterval(()=>void tick(),1000);void tick();return()=>clearInterval(timer);});}
 @Get('tasks/:id')get(@Param('id',new ParseUUIDPipe()) id:string){return this.tasks.publicGet(id);}
 @Get('tasks/:id/steps')steps(@Param('id',new ParseUUIDPipe()) id:string){return this.tasks.history(id,'steps');}
 @Get('tasks/:id/events')events(@Param('id',new ParseUUIDPipe()) id:string){return this.tasks.history(id,'events');}
 @Post('tasks/:id/:action')control(@Param('id',new ParseUUIDPipe()) id:string,@Param('action') action:string,@Body() body:unknown,@Headers('origin') origin?:string){requireLocalOrigin(origin);if(['pause','resume','cancel','retry'].includes(action))return this.tasks.control(id,action as 'pause'|'resume'|'cancel'|'retry');if(action==='approve'){const b=object(body);if(typeof b.approved!=='boolean')throw new BadRequestException('Approve or reject the pending action.');return this.tasks.decide(id,uuid(b.approvalId),b.approved);}if(action==='reconcile'){const b=object(body);return this.tasks.reconcile(id,uuid(b.operationId),b);}throw new BadRequestException('Unknown task operation.');}
 @Get('schedules')schedules(){return this.scheduler.list('schedules');}
 @Post('schedules')schedule(@Body() body:unknown,@Headers('origin') origin?:string){requireLocalOrigin(origin);return this.scheduler.save('schedules',body);}
 @Put('schedules/:id')editSchedule(@Param('id',new ParseUUIDPipe()) id:string,@Body() body:unknown,@Headers('origin') origin?:string){requireLocalOrigin(origin);return this.scheduler.save('schedules',body,id);}
 @Post('schedules/:id/enabled')enableSchedule(@Param('id',new ParseUUIDPipe()) id:string,@Body() body:unknown,@Headers('origin') origin?:string){requireLocalOrigin(origin);const b=object(body);if(typeof b.enabled!=='boolean')throw new BadRequestException('Choose enabled state.');return this.scheduler.enable('schedules',id,b.enabled);}
 @Delete('schedules/:id')removeSchedule(@Param('id',new ParseUUIDPipe()) id:string,@Headers('origin') origin?:string){requireLocalOrigin(origin);return this.scheduler.remove('schedules',id);}
 @Get('schedules/:id/history')scheduleHistory(@Param('id',new ParseUUIDPipe()) id:string){return this.scheduler.history('schedules',id);}
 @Get('task-policy')policy(){return{workspaceAvailable:!!process.env.TASK_WORKSPACE_ROOT,controlledTools:(process.env.TASK_CONTROLLED_MCP_TOOLS??'').split(',').filter(Boolean),supportedCommands:['pwd','ls','cat','grep','find','git status --short','git diff --stat'],controlledOperations:['workspace.write','allowlisted MCP writes'],dangerousOperations:['workspace.delete','operator-designated MCP tools'],limits:{maxTurns:process.env.TASK_MAX_TURNS??100,maxTokens:process.env.TASK_MAX_TOKENS??200000,maxActiveMs:process.env.TASK_MAX_ACTIVE_MS??1200000}};}
 @Post('task-policy/check')async check(@Body() body:unknown,@Headers('origin') origin?:string){requireLocalOrigin(origin);const b=object(body);text(b.kind,20);return this.tasks.policy.prepare(b as never);}
}
