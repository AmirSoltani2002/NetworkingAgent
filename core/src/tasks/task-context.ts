import { BadRequestException } from '@nestjs/common';
import { checkCriterion, digest, integer, object, pointer, uuid, type Operation, type Task } from './task-contract';

export interface TaskContextState { initialized?: boolean; versions?: Record<string,string>; toolsDigest?: string }
const previewCharacters=12000;

export function resultPreview(value:unknown){
 let previewValue=value;
 if(value&&typeof value==='object'&&'structuredContent' in value&&'content' in value&&Array.isArray(value.content)&&value.content.length===1){
  const entry=value.content[0];
  if(entry&&entry.type==='text'&&typeof entry.text==='string'){
   try{if(digest(JSON.parse(entry.text))===digest(value.structuredContent))previewValue={...value,content:[],duplicateTextOmitted:true};}catch{/* Non-JSON or distinct text remains available in the preview. */}
  }
 }
 const json=JSON.stringify(previewValue??null);
 return json.length<=previewCharacters?{value:previewValue,truncated:false}:{preview:json.slice(0,previewCharacters),truncated:true,totalCharacters:json.length,keys:previewValue&&typeof previewValue==='object'?Object.keys(previewValue):[]};
}

/** Cursor and model window must be committed in the same fenced transaction. */
export function taskContextDelta(task:Task,operations:Operation[],tools:unknown,conversation:unknown){
 const previous=task.context_state??{};
 const versions={...previous.versions};
 const changes=[];let characters=0;
 for(const operation of operations){
  const version=digest({status:operation.status,result:operation.result,error:operation.last_error,attempts:operation.attempts});
  if(versions[operation.id]===version)continue;
  const change={id:operation.id,kind:operation.kind,action:operation.action,status:operation.status,read_only:operation.read_only,last_error:operation.last_error,result:resultPreview(operation.result)};
  const length=JSON.stringify(change).length;
  if(changes.length&&characters+length>64000)break;
  changes.push(change);characters+=length;versions[operation.id]=version;
 }
 const toolsDigest=digest(tools);
 const snapshot={
  ...(previous.initialized?{}:{request:task.user_request,goal:task.goal,plan:task.plan,immutableCriteria:task.criteria,conversation}),
  ...(toolsDigest===previous.toolsDigest?{}:{tools}),
  contextMode:'incremental',currentStep:task.current_step,lastPlannerError:task.last_error,plannerRetryCount:task.retry_count,
  executionScope:{grantedControlledTools:(task.grants??[]).map(({serverId,tool})=>({serverId,tool})),dangerousActionsRequireExactApproval:true},
  completedSteps:task.completed_steps.slice(-10),
  checks:task.criteria.map(criterion=>({id:criterion.id,passed:checkCriterion(criterion,operations).passed})),
  operations:operations.slice(-40).map(op=>({id:op.id,kind:op.kind,action:op.action,status:op.status,read_only:op.read_only,attempts:op.attempts})),
  operationChanges:changes,undeliveredChanges:operations.some(op=>versions[op.id]!==digest({status:op.status,result:op.result,error:op.last_error,attempts:op.attempts})),
  workspaceAvailable:!!process.env.TASK_WORKSPACE_ROOT,
 };
 return{snapshot,state:{initialized:true,versions,toolsDigest} satisfies TaskContextState};
}

/** Pure paging of already stored evidence, never external execution or SQL supplied by the model. */
export function readTaskEvidence(operations:Operation[],input:unknown){
 const args=object(input);
 if(Object.keys(args).some(key=>!['operationId','pointer','offset','limit'].includes(key)))throw new BadRequestException('Unknown stored-evidence field.');
 const operation=operations.find(op=>op.id===uuid(args.operationId));
 if(!operation)throw new BadRequestException('Evidence operation does not belong to this task.');
 const path=args.pointer??'';
 if(typeof path!=='string'||path.length>500||!(path===''||path.startsWith('/')))throw new BadRequestException('Provide a valid evidence JSON pointer.');
 const value=pointer(operation.result,path);
 const offset=integer(args.offset,0,10000000,0),limit=integer(args.limit,1,12000,4000);
 const array=Array.isArray(value);
 const source=array?value:typeof value==='string'?value:JSON.stringify(value??null);
 // Array pages are also bounded by characters; reduce the page without discarding entries.
 let page=array?(source as unknown[]).slice(offset,offset+Math.min(limit,50)):(source as string).slice(offset,offset+limit);
 while(Array.isArray(page)&&page.length>1&&JSON.stringify(page).length>previewCharacters)page=page.slice(0,-1);
 const preview=resultPreview(page);
 const consumed=Array.isArray(page)?page.length:(page as string).length;
 return{operationId:operation.id,status:operation.status,pointer:path,found:value!==undefined,unit:array?'items':'characters',offset,nextOffset:offset+consumed,total:source.length,...preview};
}
