import { BadRequestException, Injectable, Logger, type OnApplicationBootstrap, type OnModuleDestroy } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type { PoolClient } from 'pg';
import { LlmService } from '../llm/llm.service';
import { McpService } from '../mcp/mcp.service';
import { TasksService } from './tasks.service';
import { taskContextDelta, readTaskEvidence } from './task-context';
import { digest, integer, LeaseLost, RecoverableToolError, retryDelay, TransientTaskError, UnknownTaskOutcome, type Operation, type Task } from './task-contract';

@Injectable()
export class TaskWorker implements OnApplicationBootstrap,OnModuleDestroy{
 private timer?:NodeJS.Timeout;private stopping=false;private active=new Map<string,AbortController>();private readonly logger=new Logger('Tasks');private polling=false;
 constructor(private readonly tasks:TasksService,private readonly llm:LlmService,private readonly mcp:McpService){}
 onApplicationBootstrap(){
  if(process.env.TASK_MAX_COST_USD&&(!(Number(process.env.TASK_MAX_COST_USD)>0)||!(Number(process.env.TASK_TOKEN_COST_USD_PER_MILLION)>0)))throw new Error('Task cost limits require positive TASK_MAX_COST_USD and a conservative TASK_TOKEN_COST_USD_PER_MILLION.');
  if(process.env.TASK_WORKER_ENABLED==='false')return;this.timer=setInterval(()=>void this.tick(),1000);void this.tick();}
 async onModuleDestroy(){this.stopping=true;if(this.timer)clearInterval(this.timer);for(const controller of this.active.values())controller.abort();for(let i=0;i<50&&this.active.size;i++)await new Promise(resolve=>setTimeout(resolve,100));}
 async claim(){const client=await this.tasks.db.pool.connect();let lockedId:string|undefined;
  try{await client.query('BEGIN');const task=(await client.query<Task>(`SELECT * FROM agent_tasks WHERE ((status IN ('PENDING','RETRYING') AND next_run_at<=now()) OR (status='RUNNING' AND lease_until<now())) ORDER BY next_run_at,created_at FOR UPDATE SKIP LOCKED LIMIT 1`)).rows[0];if(!task){await client.query('COMMIT');client.release();return;}
   const acquired=(await client.query('SELECT pg_try_advisory_lock(hashtextextended($1,1)) AS acquired',[task.id])).rows[0].acquired;if(!acquired){await client.query('ROLLBACK');client.release();return;}lockedId=task.id;
   const uncertain=(await client.query<Operation>("UPDATE task_operations SET status='UNKNOWN',last_error='Worker stopped after dispatch; external outcome needs reconciliation.',updated_at=now() WHERE task_id=$1 AND status='DISPATCHING' AND NOT read_only RETURNING *",[task.id])).rows;
   if(uncertain.length){await client.query("UPDATE agent_tasks SET status='PAUSED',last_error='External write outcome is unknown. Reconcile before resuming.',lease_owner=NULL,lease_until=NULL,updated_at=now() WHERE id=$1",[task.id]);await this.tasks.event(client,task.id,'uncertain',{operationIds:uncertain.map(o=>o.id)});await client.query('COMMIT');await client.query('SELECT pg_advisory_unlock(hashtextextended($1,1))',[task.id]);client.release();return;}
   await client.query("UPDATE task_operations SET status='FAILED',last_error='Read interrupted; safe to retry.' WHERE task_id=$1 AND status='DISPATCHING' AND read_only",[task.id]);
   const owner=randomUUID();const claimed=(await client.query<Task>("UPDATE agent_tasks SET status='RUNNING',lease_owner=$2,lease_until=now()+interval '30 seconds',updated_at=now() WHERE id=$1 RETURNING *",[task.id,owner])).rows[0];await this.tasks.event(client,task.id,'running');await client.query('COMMIT');return{task:claimed,client,owner};
  }catch(e){await client.query('ROLLBACK').catch(()=>undefined);if(lockedId)await client.query('SELECT pg_advisory_unlock(hashtextextended($1,1))',[lockedId]).catch(()=>undefined);client.release();throw e;}
 }
 async fenced<T>(id:string,owner:string,fn:(client:PoolClient,task:Task)=>Promise<T>){return this.tasks.db.transaction(async client=>{const task=(await client.query<Task>('SELECT * FROM agent_tasks WHERE id=$1 FOR UPDATE',[id])).rows[0];if(!task||task.status!=='RUNNING'||task.lease_owner!==owner)throw new LeaseLost();return fn(client,task);});}
 async tick(){if(this.polling||this.stopping||this.active.size>=integer(process.env.TASK_CONCURRENCY,1,4,2))return;this.polling=true;
  try{const claimed=await this.claim();if(claimed){const abort=new AbortController();this.active.set(claimed.task.id,abort);void this.run(claimed.task,claimed.owner,abort).finally(async()=>{this.active.delete(claimed.task.id);await claimed.client.query('SELECT pg_advisory_unlock(hashtextextended($1,1))',[claimed.task.id]).catch(()=>undefined);claimed.client.release();});}}
  catch{this.logger.warn(JSON.stringify({event:'task_poll_failed'}));}finally{this.polling=false;}
 }
 async run(initial:Task,owner:string,controller:AbortController){const id=initial.id,started=Date.now();let operation:Operation|undefined;
  const heartbeat=setInterval(()=>{void this.tasks.db.pool.query("UPDATE agent_tasks SET lease_until=now()+interval '30 seconds' WHERE id=$1 AND lease_owner=$2 AND status='RUNNING' RETURNING id",[id,owner]).then(r=>{if(!r.rowCount)controller.abort(new LeaseLost());}).catch(()=>controller.abort(new LeaseLost()));},5000);
  const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(120000)]);
  try{
   let task=await this.tasks.get(id);
   if(process.env.TASK_MAX_COST_USD&&Number(task.estimated_cost_usd)>=Number(process.env.TASK_MAX_COST_USD)){await this.pauseBudget(id,owner,'Task cost budget reached. Completed work is saved.');return;}
   const promptLimit=task.turn_count-task.prompt_turns_start>=integer(process.env.TASK_MAX_TURNS,1,1000,8)||Number(task.active_ms)-Number(task.prompt_active_start)>=integer(process.env.TASK_MAX_ACTIVE_MS,1000,86400000,120000)||Number(task.tokens_used)-Number(task.prompt_tokens_start)>=integer(process.env.TASK_MAX_TOKENS,1000,10000000,200000);
   const legacyContext=!!task.context_window?.length&&!Object.hasOwn(task.context_state??{},'initialized');
   if(promptLimit||legacyContext){await this.continuePrompt(task,owner,signal,legacyContext?'legacy_context':'prompt_budget');return;}
   if(!task.next_action){
    const tools=await this.mcp.agentTools();const operations=(await this.tasks.db.pool.query<Operation>('SELECT * FROM task_operations WHERE task_id=$1 ORDER BY created_at,id',[id])).rows;
    const conversation=task.context_state?.initialized?[]:(await this.tasks.db.pool.query('SELECT role,left(text,4000) AS content FROM messages WHERE chat_id=$1 AND position<=(SELECT position FROM messages WHERE id=$2) ORDER BY position DESC LIMIT 20',[task.conversation_id,task.message_id])).rows.reverse();
    const delta=taskContextDelta(task,operations,tools,conversation);
    await this.fenced(id,owner,async client=>{await client.query('UPDATE agent_tasks SET turn_count=turn_count+1 WHERE id=$1',[id]);});
    const decision=await this.llm.taskDecision(delta.snapshot,task.context_window,signal,async output=>this.fenced(id,owner,async client=>this.tasks.event(client,id,'model_output',await this.tasks.redact(output))),tokens=>this.recordUsage(id,owner,tokens));
    if(decision.decision.kind==='blocked'&&!task.criteria.length){decision.decision.kind='respond';decision.decision.action=null;}
    if(decision.decision.kind==='respond'&&!task.criteria.length){decision.decision.goal='Respond to: '+task.user_request.slice(0,1000);decision.decision.plan=['Deliver a useful response with assumptions and limitations'];decision.decision.criteria=[{id:'response-delivered',description:'A nonempty response was saved; external execution is not verified',kind:'response',serverId:null,tool:null,match:{},pointer:'/text',operator:'nonempty',expected:null}];}
    if(decision.decision.kind!=='blocked'&&!task.criteria.length&&!decision.decision.criteria.length)throw new TransientTaskError('The model omitted completion checks. I’ll request a usable plan before executing tools.');
    await this.fenced(id,owner,async client=>{await client.query(`UPDATE agent_tasks SET goal=CASE WHEN jsonb_array_length(criteria)=0 THEN $3 ELSE goal END,plan=CASE WHEN jsonb_array_length(criteria)=0 THEN $4::jsonb ELSE plan END,criteria=CASE WHEN jsonb_array_length(criteria)=0 THEN $5::jsonb ELSE criteria END,next_action=$6::jsonb,context_window=$7::jsonb,context_state=$8::jsonb,updated_at=now() WHERE id=$1 AND lease_owner=$2`,[id,owner,decision.decision.goal,JSON.stringify(decision.decision.plan),JSON.stringify(decision.decision.criteria),JSON.stringify(decision.decision),JSON.stringify(decision.context),JSON.stringify(delta.state)]);await this.tasks.event(client,id,'planned',{step:decision.decision.step,summary:decision.decision.summary});});task=await this.tasks.get(id);
   }
   const decision=task.next_action!;const stepId=(await this.fenced(id,owner,async client=>(await client.query(`INSERT INTO task_steps(id,task_id,step_index,kind,status,decision) VALUES($1,$2,$3,$4,'RUNNING',$5::jsonb) ON CONFLICT(task_id,step_index) DO UPDATE SET updated_at=now() RETURNING id`,[randomUUID(),id,task.current_step,decision.kind,JSON.stringify(decision)])).rows[0].id)) as string;
   if(decision.kind==='respond'){
    await this.fenced(id,owner,async(client,current)=>{
     const response=await this.tasks.redact(decision.summary);
     await client.query(`INSERT INTO task_operations(id,task_id,step_id,operation_key,kind,action,read_only,policy_digest,status,result,attempts) VALUES($1,$2,$3,$4,'response',$5::jsonb,true,'internal-response-v1','SUCCEEDED',$6::jsonb,1) ON CONFLICT(task_id,operation_key) DO NOTHING`,[randomUUID(),id,stepId,'response:'+task.current_step,JSON.stringify({kind:'response'}),JSON.stringify({text:response,externalExecutionVerified:false})]);
     await client.query("UPDATE task_steps SET status='COMPLETED',updated_at=now() WHERE id=$1",[stepId]);
     await this.tasks.event(client,id,'response',{text:response,externalExecutionVerified:false});
     if(!(await this.tasks.complete(client,current,response))){await client.query("UPDATE agent_tasks SET status='PAUSED',result=$2,last_error='A partial response is available. External completion checks remain unmet.',next_action=NULL,lease_owner=NULL,lease_until=NULL,updated_at=now() WHERE id=$1",[id,response]);await this.tasks.event(client,id,'partial_response');}
    });return;
   }
   if(decision.kind==='blocked'){await this.fenced(id,owner,async client=>{await client.query("UPDATE agent_tasks SET status='PAUSED',last_error=$2,next_action=NULL,lease_owner=NULL,lease_until=NULL,updated_at=now() WHERE id=$1",[id,decision.summary||'A required capability is unavailable.']);await this.tasks.event(client,id,'blocked');});return;}
   if(decision.kind==='complete'){
    const done=await this.fenced(id,owner,async(client,current)=>this.tasks.complete(client,current,decision.summary));if(done)return;
    await this.advance(id,owner,stepId,'Verification failed; additional evidence required.',Math.max(1000,retryDelay(task.retry_count)),false);return;
   }
   if(decision.kind==='wait'){await this.advance(id,owner,stepId,decision.step,integer(decision.waitSeconds,1,300,5)*1000);return;}
   const action=decision.action!;
   if(action.kind==='evidence'){
    const operations=(await this.tasks.db.pool.query<Operation>('SELECT * FROM task_operations WHERE task_id=$1',[id])).rows;
    let result:unknown,success=true;
    try{result=readTaskEvidence(operations,action.arguments);}catch(error){if(!(error instanceof BadRequestException))throw error;success=false;result={isError:true,message:error.message};}
    result=await this.tasks.redact(result);
    await this.fenced(id,owner,async client=>{await client.query(`INSERT INTO task_operations(id,task_id,step_id,operation_key,kind,action,read_only,policy_digest,status,result,attempts) VALUES($1,$2,$3,$4,'evidence',$5::jsonb,true,'internal-evidence-v1',$6,$7::jsonb,1) ON CONFLICT(task_id,operation_key) DO NOTHING`,[randomUUID(),id,stepId,'evidence:'+task.current_step,JSON.stringify(action),success?'SUCCEEDED':'FAILED',JSON.stringify(result)]);await this.tasks.event(client,id,'evidence_read',{success,arguments:action.arguments});});
    await this.advance(id,owner,stepId,decision.step,0,success);return;
   }
   if(action.kind==='mcp'){const row=await this.mcp.get(action.serverId!);if(row.status==='failed'&&row.enabled&&row.agent_enabled&&!row.disconnected)await this.mcp.discover(row.id);}
   const prepared=await this.tasks.policy.prepare(action);const actionKey=digest(action);const key=prepared.readOnly?`${task.current_step}:${actionKey}`:decision.planStep===undefined?actionKey:`write:${decision.planStep}`;
   if(!prepared.readOnly){const completed=(await this.tasks.db.pool.query<Operation>("SELECT * FROM task_operations WHERE task_id=$1 AND NOT read_only AND status='SUCCEEDED'",[id])).rows.find(op=>digest(op.action)===actionKey);if(completed){await this.advance(id,owner,stepId,'Reused completed operation: '+decision.step);return;}}
   operation=await this.fenced(id,owner,async client=>(await client.query<Operation>(`INSERT INTO task_operations(id,task_id,step_id,operation_key,kind,action,read_only,policy_digest,status) VALUES($1,$2,$3,$4,$5,$6::jsonb,$7,$8,'PREPARED') ON CONFLICT(task_id,operation_key) DO UPDATE SET updated_at=now() RETURNING *`,[randomUUID(),id,stepId,key,action.kind,JSON.stringify(action),prepared.readOnly,prepared.policyDigest])).rows[0]);
   if(operation.status==='SUCCEEDED'){await this.advance(id,owner,stepId,decision.step);return;}
   if(['UNKNOWN','DISPATCHING'].includes(operation.status)&&!operation.read_only)throw new UnknownTaskOutcome('External write outcome is uncertain.');
   if(operation.status==='REJECTED')throw new BadRequestException('This action was rejected. Revise the request instead of repeating it.');
   let approval=(await this.tasks.db.pool.query('SELECT * FROM task_approvals WHERE operation_id=$1',[operation.id])).rows[0];
   const grant=prepared.level==='controlled'&&task.grants.some(g=>g.serverId===action.serverId&&g.tool===action.tool&&g.policyDigest===prepared.policyDigest);
   if(prepared.level!=='safe'&&!grant&&(!approval||approval.decision!==true||approval.policy_digest!==prepared.policyDigest)){
    await this.fenced(id,owner,async client=>{await client.query(`INSERT INTO task_approvals(id,task_id,operation_id,action,policy_digest) VALUES($1,$2,$3,$4::jsonb,$5) ON CONFLICT(operation_id) DO UPDATE SET id=$1,action=$4::jsonb,policy_digest=$5,decision=NULL,created_at=now(),decided_at=NULL`,[randomUUID(),id,operation!.id,JSON.stringify(action),prepared.policyDigest]);await client.query("UPDATE agent_tasks SET status='WAITING_APPROVAL',lease_owner=NULL,lease_until=NULL,updated_at=now() WHERE id=$1",[id]);await this.tasks.event(client,id,'approval_required',{operationId:operation!.id});});return;
   }
   approval=approval??null;
   const dispatch=async()=>{if(signal.aborted)throw signal.reason;await this.fenced(id,owner,async client=>{await client.query("UPDATE task_operations SET status='DISPATCHING',attempts=attempts+1,policy_digest=$2,updated_at=now() WHERE id=$1",[operation!.id,prepared.policyDigest]);await this.tasks.event(client,id,'tool_dispatch',{operationId:operation!.id});});operation!.status='DISPATCHING';};
   let output:unknown;const executionStarted=Date.now();
   if(action.kind==='mcp')output=await this.mcp.execute(action.serverId!,action.tool!,action.arguments,signal,prepared.confirmation,{operationId:operation.id,beforeDispatch:dispatch});
   else{await dispatch();output=await this.tasks.policy.execute(action,signal);}
   output=await this.tasks.redact(output);
   if((output as {isError?:boolean})?.isError||action.kind==='command'&&(output as {exitCode:number}).exitCode!==0){await this.tasks.db.transaction(async client=>{await client.query('UPDATE task_operations SET result=$2::jsonb WHERE id=$1',[operation!.id,JSON.stringify(output)]);await this.tasks.event(client,id,'tool_result',{operationId:operation!.id,success:false});});}
   if((output as {isError?:boolean})?.isError){if(!prepared.readOnly)throw new UnknownTaskOutcome('Tool reported an error after write dispatch. Check its actual outcome.');throw new RecoverableToolError('The read-only tool rejected this request. Reviewing its response to correct the next action.');}
   if(action.kind==='command'&&(output as {exitCode:number}).exitCode!==0)throw new BadRequestException('Command did not exit successfully.');
   await this.tasks.db.transaction(async client=>{await client.query("UPDATE task_operations SET status='SUCCEEDED',result=$2::jsonb,duration_ms=$3,updated_at=now() WHERE id=$1 AND status='DISPATCHING'",[operation!.id,JSON.stringify(output),Date.now()-executionStarted]);await this.tasks.event(client,id,'tool_result',{operationId:operation!.id,success:true});});operation.status='SUCCEEDED';
   await this.advance(id,owner,stepId,decision.step);
  }catch(error){
   if(error instanceof LeaseLost||controller.signal.reason instanceof LeaseLost){if(operation?.status==='DISPATCHING'&&!operation.read_only)await this.tasks.db.pool.query("UPDATE task_operations SET status='UNKNOWN',last_error='Execution interrupted after dispatch; reconcile outcome.' WHERE id=$1 AND status='DISPATCHING'",[operation.id]).catch(()=>undefined);return;}
   const unknown=error instanceof UnknownTaskOutcome||(operation?.status==='DISPATCHING'&&!operation.read_only);
   const recoverable=error instanceof RecoverableToolError;
   const permanent=(error instanceof BadRequestException||(error as {permanent?:boolean})?.permanent===true)&&!unknown;
   const message=await this.tasks.redact(unknown?'State-changing operation has an unknown outcome. Reconcile it before resuming.':permanent||recoverable||error instanceof TransientTaskError?(error as Error).message:'A service is temporarily unavailable. I’ll retry automatically; saved work is preserved.');
   try{await this.fenced(id,owner,async(client,task)=>{
    if(operation&&operation.status!=='SUCCEEDED')await client.query('UPDATE task_operations SET status=$2,last_error=$3,updated_at=now() WHERE id=$1',[operation.id,unknown?'UNKNOWN':'FAILED',message]);
    if(recoverable&&operation){await client.query("UPDATE task_steps SET status='FAILED',updated_at=now() WHERE id=$1",[operation.step_id]);await client.query('UPDATE agent_tasks SET next_action=NULL,current_step=current_step+1 WHERE id=$1',[id]);}
    const retries=task.retry_count+1;const exhausted=retries>integer(process.env.TASK_MAX_RETRIES,0,20,5);const status=unknown?'PAUSED':permanent||exhausted?'FAILED':'RETRYING';const outcomeMessage=exhausted&&!unknown&&!permanent?'I couldn’t complete this task after repeated service or model-response failures. Saved work is preserved. Open task details to review or retry it.':message;const delay=retryDelay(retries,(error as {retryAfterMs?:number})?.retryAfterMs??0);
    await client.query("UPDATE agent_tasks SET status=$2,last_error=$3,retry_count=$4,next_run_at=now()+($5*interval '1 millisecond'),lease_owner=NULL,lease_until=NULL,updated_at=now() WHERE id=$1",[id,status,outcomeMessage,retries,Math.min(delay,86400000)]);await this.tasks.event(client,id,'error',{status,message,attempt:retries,retryAfterMs:delay,operationId:operation?.id});
   });}catch{this.logger.warn(JSON.stringify({event:'task_checkpoint_failed',taskId:id}));}
  }finally{
   clearInterval(heartbeat);controller.abort();await this.tasks.db.pool.query('UPDATE agent_tasks SET active_ms=active_ms+$2 WHERE id=$1',[id,Date.now()-started]).catch(()=>undefined);this.logger.log(JSON.stringify({event:'task_slice',taskId:id,durationMs:Date.now()-started}));
  }
 }
 async recordUsage(id:string,owner:string,tokens:number){
  if(!Number.isSafeInteger(tokens)||tokens<0)throw new BadRequestException('Invalid provider usage.');
  await this.fenced(id,owner,async client=>{await client.query('UPDATE agent_tasks SET tokens_used=tokens_used+$2,estimated_cost_usd=estimated_cost_usd+$3 WHERE id=$1',[id,tokens,tokens*Number(process.env.TASK_TOKEN_COST_USD_PER_MILLION??0)/1000000]);});
 }
 async pauseBudget(id:string,owner:string,message:string){await this.fenced(id,owner,async client=>{await client.query("UPDATE agent_tasks SET status='PAUSED',last_error=$2,lease_owner=NULL,lease_until=NULL,updated_at=now() WHERE id=$1",[id,message]);await this.tasks.event(client,id,'budget_paused',{message});});}
 async continuePrompt(task:Task,owner:string,signal:AbortSignal,reason:string){
  if(task.continuation_count>=integer(process.env.TASK_MAX_CONTINUATIONS,0,100,20)){await this.pauseBudget(task.id,owner,'Automatic continuation limit reached. Saved progress and evidence are preserved.');return;}
  // Only the model window changes; pending actions, immutable criteria, grants and operation ledger survive.
  const context=task.context_window?.length?await this.llm.summarizeTaskContext(task.context_window,signal,tokens=>this.recordUsage(task.id,owner,tokens)):[];
  await this.fenced(task.id,owner,async client=>{await client.query(`UPDATE agent_tasks SET context_window=$2::jsonb,context_state=$3::jsonb,prompt_tokens_start=tokens_used,prompt_turns_start=turn_count,prompt_active_start=active_ms,continuation_count=continuation_count+1,status='PENDING',last_error=NULL,next_run_at=now(),lease_owner=NULL,lease_until=NULL,updated_at=now() WHERE id=$1`,[task.id,JSON.stringify(context),JSON.stringify({...task.context_state,initialized:false,toolsDigest:undefined})]);await this.tasks.event(client,task.id,'prompt_continuation',{reason,continuation:task.continuation_count+1});});
 }
 async advance(id:string,owner:string,stepId:string,label:string,delay=0,success=true){await this.fenced(id,owner,async(client,task)=>{
  await client.query('UPDATE task_steps SET status=$2,updated_at=now() WHERE id=$1',[stepId,success?'COMPLETED':'FAILED']);const verification=await this.tasks.verify(client,task);const progress=task.criteria.length?Math.floor(verification.checks.filter(c=>c.passed).length/task.criteria.length*99):0;
  await client.query("UPDATE agent_tasks SET status='PENDING',last_error=NULL,current_step=current_step+1,completed_steps=completed_steps||$2::jsonb,progress=$3,next_action=NULL,retry_count=0,next_run_at=now()+($4*interval '1 millisecond'),lease_owner=NULL,lease_until=NULL,updated_at=now() WHERE id=$1",[id,JSON.stringify(success?[label]:[]),progress,delay]);await this.tasks.event(client,id,'checkpoint',{step:label,progress});
 });}
}
