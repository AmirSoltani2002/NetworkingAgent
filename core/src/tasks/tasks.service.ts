import { BadRequestException, ConflictException, Injectable, NotFoundException } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { PoolClient } from 'pg';
import { DatabaseService } from '../database/database.service';
import { EnvironmentStore } from '../config/environment-store.service';
import { redactContext } from '../llm/context-window';
import { ExecutionPolicy } from './execution-policy';
import { checkCriterion, digest, integer, object, text, uuid, type Grant, type Operation, type Task } from './task-contract';

@Injectable()
export class TasksService{
 constructor(readonly db:DatabaseService,private readonly environment:EnvironmentStore,readonly policy:ExecutionPolicy){}
 async redact<T>(value:T):Promise<T>{const values=await this.environment.read();const secrets=Object.entries(values).filter(([k,v])=>/(KEY|TOKEN|PASSWORD)/.test(k)&&v&&v.length>=4).map(([,v])=>v!);return redactContext(value,secrets) as T;}
 async event(client:PoolClient,id:string,type:string,data:unknown={}){await client.query('INSERT INTO task_events(task_id,type,data) VALUES($1,$2,$3::jsonb)',[id,type,JSON.stringify(data)]);}
 async get(id:string){const row=(await this.db.pool.query<Task>('SELECT * FROM agent_tasks WHERE id=$1',[id])).rows[0];if(!row)throw new NotFoundException('Task not found.');return row;}
 async publicGet(id:string){const task=await this.get(id);const {context_window:_context,context_state:_state,lease_owner:_owner,lease_until:_lease,grants:_grants,...publicTask}=task;void _context;void _state;void _owner;void _lease;void _grants;
  return this.redact({...publicTask,last_error:['FAILED','PAUSED','RETRYING','WAITING_APPROVAL'].includes(task.status)?task.last_error:null,operations:(await this.db.pool.query('SELECT * FROM task_operations WHERE task_id=$1 ORDER BY created_at,id',[id])).rows,approvals:(await this.db.pool.query('SELECT * FROM task_approvals WHERE task_id=$1 ORDER BY created_at',[id])).rows,steps:(await this.db.pool.query('SELECT * FROM task_steps WHERE task_id=$1 ORDER BY step_index',[id])).rows,events:(await this.db.pool.query('SELECT * FROM task_events WHERE task_id=$1 ORDER BY sequence DESC LIMIT 100',[id])).rows,verifications:(await this.db.pool.query('SELECT * FROM task_verifications WHERE task_id=$1 ORDER BY checked_at',[id])).rows});}
 async list(query:Record<string,unknown>={}){const history=query.history==='true';const values:unknown[]=[integer(query.limit,1,100,25),integer(query.offset,0,100000,0)];const where=history?"status IN ('COMPLETED','FAILED','CANCELLED')":"status NOT IN ('COMPLETED','FAILED','CANCELLED')";return (await this.db.pool.query(`SELECT id,conversation_id,goal,status,progress,current_step,last_error,created_at,updated_at FROM agent_tasks WHERE ${where} ORDER BY created_at DESC LIMIT $1 OFFSET $2`,values)).rows;}
 async validateCreate(input:unknown){const b=object(input);if(Object.keys(b).some(k=>!['conversationId','messageId','request','grants','dedupeKey'].includes(k)))throw new BadRequestException('Unknown task field.');const request=await this.redact(text(b.request,100000));const grants:Grant[]=[];
  if(b.grants!==undefined){if(!Array.isArray(b.grants)||b.grants.length>64)throw new BadRequestException('Invalid task grants.');for(const raw of b.grants){const g=object(raw);grants.push(await this.policy.grant(uuid(g.serverId),text(g.tool,200)));}}
  return{request,conversationId:b.conversationId?uuid(b.conversationId):undefined,messageId:b.messageId?uuid(b.messageId):undefined,grants,dedupeKey:b.dedupeKey?text(b.dedupeKey,200):undefined};
 }
 async create(input:unknown){const value=await this.validateCreate(input);return this.db.transaction(client=>this.insert(client,value));}
 async insert(client:PoolClient,value:{request:string;conversationId?:string;messageId?:string;grants?:Grant[];dedupeKey?:string},source:Record<string,unknown>={}){
  const chatId=value.conversationId??randomUUID(),id=randomUUID();
  const acquired=(await client.query('SELECT pg_try_advisory_xact_lock(hashtextextended($1,0)) AS acquired',[chatId])).rows[0].acquired;if(!acquired)throw new ConflictException('This conversation is executing another response.');
  if(value.dedupeKey){const old=(await client.query('SELECT * FROM agent_tasks WHERE dedupe_key=$1',[value.dedupeKey])).rows[0];if(old)return old;}
  if(!value.conversationId)await client.query('INSERT INTO chats(id,title) VALUES($1,$2)',[chatId,value.request.slice(0,60)]);
  else if(!(await client.query('SELECT id FROM chats WHERE id=$1 FOR KEY SHARE',[chatId])).rowCount)throw new NotFoundException('Conversation not found.');
  let messageId=value.messageId;
  if(messageId){const message=(await client.query('SELECT role,text FROM messages WHERE id=$1 AND chat_id=$2',[messageId,chatId])).rows[0];if(!message||message.role!=='user'||message.text!==value.request)throw new BadRequestException('Task must reference a user message in this conversation.');
   if((await client.query('SELECT id FROM messages WHERE reply_to_message_id=$1',[messageId])).rowCount)throw new ConflictException('This message already has a reply.');
   const existing=(await client.query('SELECT * FROM agent_tasks WHERE message_id=$1',[messageId])).rows[0];if(existing)return existing;
  }else{messageId=randomUUID();await client.query("INSERT INTO messages(id,chat_id,role,text) VALUES($1,$2,'user',$3)",[messageId,chatId,value.request]);}
  const task=(await client.query<Task>(`INSERT INTO agent_tasks(id,conversation_id,message_id,user_request,goal,grants,dedupe_key,source) VALUES($1,$2,$3,$4,$4,$5::jsonb,$6,$7::jsonb) RETURNING *`,[id,chatId,messageId,value.request,JSON.stringify(value.grants??[]),value.dedupeKey??null,JSON.stringify(source)])).rows[0];await this.event(client,id,'created');return task;
 }
 async control(id:string,action:'pause'|'resume'|'cancel'|'retry'){
  return this.db.transaction(async client=>{const task=(await client.query<Task>('SELECT * FROM agent_tasks WHERE id=$1 FOR UPDATE',[id])).rows[0];if(!task)throw new NotFoundException('Task not found.');
   if(['COMPLETED','CANCELLED'].includes(task.status))throw new ConflictException('This task is terminal.');
   if(action==='resume'&&!['PAUSED'].includes(task.status)||action==='retry'&&task.status!=='FAILED')throw new ConflictException('This action is not available in the current task state.');
   if((action==='resume'||action==='retry')&&(await client.query("SELECT id FROM task_operations WHERE task_id=$1 AND status IN ('UNKNOWN','DISPATCHING') AND NOT read_only",[id])).rowCount)throw new ConflictException('Reconcile uncertain operations before resuming.');
   if((action==='resume'||action==='retry')&&(await client.query('SELECT id FROM task_approvals WHERE task_id=$1 AND decision IS NULL',[id])).rowCount)throw new ConflictException('Resolve the pending approval first.');
   if(action==='retry'){
    const saved=(await client.query("SELECT id,decision FROM task_steps WHERE task_id=$1 AND kind='complete' ORDER BY step_index DESC LIMIT 1",[id])).rows[0];
    if(saved&&await this.complete(client,task,await this.redact(text(saved.decision.summary,20000)))){
     await client.query("UPDATE task_steps SET status='COMPLETED',updated_at=now() WHERE id=$1",[saved.id]);
     return{status:'COMPLETED'};
    }
   }
   if(action==='retry'&&task.next_action?.kind==='execute'){
    const failed=(await client.query<Operation>("SELECT * FROM task_operations WHERE task_id=$1 AND read_only AND status='FAILED'",[id])).rows;
    if(failed.some(op=>(op.result as {isError?:boolean})?.isError&&digest(op.action)===digest(task.next_action!.action))){
     await client.query("UPDATE task_steps SET status='FAILED',updated_at=now() WHERE task_id=$1 AND step_index=$2",[id,task.current_step]);
     await client.query('UPDATE agent_tasks SET next_action=NULL,current_step=current_step+1 WHERE id=$1',[id]);
    }
   }
   const status=action==='pause'?'PAUSED':action==='cancel'?'CANCELLED':'PENDING';await client.query("UPDATE agent_tasks SET status=$2::text,last_error=CASE WHEN $2::text='PENDING' THEN NULL ELSE last_error END,lease_owner=NULL,lease_until=NULL,next_run_at=now(),updated_at=now(),retry_count=CASE WHEN $3 THEN 0 ELSE retry_count END WHERE id=$1",[id,status,action==='retry']);await this.event(client,id,status.toLowerCase());return{status};
  });
 }
 async decide(id:string,approvalId:string,approved:boolean){return this.db.transaction(async client=>{
  const task=(await client.query<Task>('SELECT * FROM agent_tasks WHERE id=$1 FOR UPDATE',[id])).rows[0];if(!task||!['WAITING_APPROVAL','PAUSED'].includes(task.status))throw new ConflictException('Task has no actionable approval.');
  const approval=(await client.query('SELECT * FROM task_approvals WHERE id=$1 AND task_id=$2 FOR UPDATE',[approvalId,id])).rows[0];if(!approval||approval.decision!==null)throw new ConflictException('Approval is missing or already decided.');
  await client.query('UPDATE task_approvals SET decision=$2,decided_at=now() WHERE id=$1',[approvalId,approved]);
  if(!approved){await client.query("UPDATE task_operations SET status='REJECTED',updated_at=now() WHERE id=$1",[approval.operation_id]);await client.query("UPDATE agent_tasks SET status='PAUSED',last_error='Action rejected by user.',next_action=NULL,current_step=current_step+1,updated_at=now() WHERE id=$1",[id]);}
  else await client.query("UPDATE agent_tasks SET status='PENDING',next_run_at=now(),updated_at=now() WHERE id=$1",[id]);await this.event(client,id,approved?'approved':'rejected',{approvalId});return{approved};
 });}
 async reconcile(id:string,operationId:string,input:unknown){const b=object(input);if(!['succeeded','not_executed'].includes(String(b.outcome)))throw new BadRequestException('Confirm the actual external outcome.');const reason=text(b.reason,4000);const result=await this.redact(b.result??{});if(JSON.stringify(result).length>262144)throw new BadRequestException('Reconciliation result is too large.');
  return this.db.transaction(async client=>{await client.query('SELECT id FROM agent_tasks WHERE id=$1 FOR UPDATE',[id]);const op=(await client.query<Operation>('SELECT * FROM task_operations WHERE id=$1 AND task_id=$2 FOR UPDATE',[operationId,id])).rows[0];if(!op||op.status!=='UNKNOWN')throw new ConflictException('Only uncertain operations can be reconciled.');
   // Operator attestation resolves ambiguity, but does not supply completion evidence. A fresh verification read is required.
   await client.query('UPDATE task_operations SET status=$2,result=$3::jsonb,last_error=$4,updated_at=now() WHERE id=$1',[operationId,b.outcome==='succeeded'?'SUCCEEDED':'FAILED',JSON.stringify({operatorReconciled:true,outcome:b.outcome}),reason]);
   if(b.outcome==='succeeded')await client.query('UPDATE agent_tasks SET current_step=current_step+1,next_action=NULL WHERE id=$1',[id]);
   await this.event(client,id,'reconciled',{operationId,outcome:b.outcome,reason});return{reconciled:true};
  });
 }
 async verify(client:PoolClient,task:Task){const ops=(await client.query<Operation>('SELECT * FROM task_operations WHERE task_id=$1',[task.id])).rows;const checks=task.criteria.map(c=>({id:c.id,...checkCriterion(c,ops)}));for(const c of checks)await client.query('INSERT INTO task_verifications(id,task_id,criterion_id,passed,evidence) VALUES($1,$2,$3,$4,$5::jsonb)',[randomUUID(),task.id,c.id,c.passed,JSON.stringify(c.observations)]);return{passed:checks.length>0&&checks.every(c=>c.passed),checks};}
 async complete(client:PoolClient,task:Task,result:string){const verification=await this.verify(client,task);if(!verification.passed)return false;
  const traces=(await client.query<Operation>("SELECT * FROM task_operations WHERE task_id=$1 AND kind='mcp' ORDER BY created_at",[task.id])).rows.map(op=>({serverId:op.action.serverId,tool:op.action.tool,success:op.status==='SUCCEEDED',operationId:op.id,sources:[],result:op.result}));
  await client.query("INSERT INTO messages(id,chat_id,role,text,reply_to_message_id,tool_calls) VALUES($1,$2,'assistant',$3,$4,$5::jsonb) ON CONFLICT(reply_to_message_id) WHERE reply_to_message_id IS NOT NULL DO NOTHING",[randomUUID(),task.conversation_id,result,task.message_id,JSON.stringify(traces)]);
  await client.query("UPDATE agent_tasks SET status='COMPLETED',last_error=NULL,result=$2,progress=100,lease_owner=NULL,lease_until=NULL,finished_at=now(),updated_at=now() WHERE id=$1",[task.id,result]);await client.query('UPDATE chats SET context_window=NULL,updated_at=now() WHERE id=$1',[task.conversation_id]);await this.event(client,task.id,'completed');
  return true;
 }
 async history(id:string,type:'steps'|'events'){await this.get(id);return(await this.db.pool.query(type==='steps'?'SELECT * FROM task_steps WHERE task_id=$1 ORDER BY step_index':'SELECT * FROM task_events WHERE task_id=$1 ORDER BY sequence DESC LIMIT 200',[id])).rows;}
}
