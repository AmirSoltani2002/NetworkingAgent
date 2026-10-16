import { BadRequestException } from '@nestjs/common';
import { createHash } from 'node:crypto';
import type { TaskContextState } from './task-context';

export const taskStates=['PENDING','RUNNING','WAITING_APPROVAL','RETRYING','PAUSED','COMPLETED','FAILED','CANCELLED'] as const;
export type TaskState=typeof taskStates[number];
export type Action={kind:'mcp'|'command'|'workspace'|'evidence';serverId?:string;tool?:string;arguments?:Record<string,unknown>;executable?:string;args?:string[];path?:string;operation?:'read'|'list'|'exists'|'write'|'delete';content?:string};
export type Criterion={id:string;description:string;kind:Exclude<Action['kind'],'evidence'>|'response';serverId:string|null;tool:string|null;match:Record<string,unknown>;pointer:string;operator:'exists'|'equals'|'nonempty'|'gte'|'contains';expected:unknown};
export type Decision={goal:string;plan:string[];criteria:Criterion[];kind:'execute'|'wait'|'complete'|'blocked'|'respond';step:string;planStep?:number;action:Action|null;waitSeconds:number;summary:string};
export type Grant={serverId:string;tool:string;policyDigest:string};
export interface Task {
 id:string;conversation_id:string;message_id:string|null;user_request:string;goal:string;plan:string[];criteria:Criterion[];status:TaskState;
 current_step:number;completed_steps:string[];progress:number;next_action:Decision|null;result:string|null;last_error:string|null;retry_count:number;
 grants:Grant[];context_window:unknown[]|null;context_state:TaskContextState;prompt_tokens_start:string;prompt_turns_start:number;prompt_active_start:string;continuation_count:number;tokens_used:string;active_ms:string;estimated_cost_usd:string;turn_count:number;source:Record<string,unknown>;
 lease_owner:string|null;lease_until:Date|null;created_at:Date;updated_at:Date;
}
export interface Operation {id:string;task_id:string;step_id:string;operation_key:string;kind:string;action:Action;read_only:boolean;policy_digest:string;status:string;result:unknown;attempts:number;last_error:string|null;}
export function digest(value:unknown){const stable=(v:unknown):unknown=>Array.isArray(v)?v.map(stable):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b)).map(([k,item])=>[k,stable(item)])):v;return createHash('sha256').update(JSON.stringify(stable(value))).digest('hex');}
export function object(value:unknown):Record<string,unknown>{if(!value||typeof value!=='object'||Array.isArray(value))throw new BadRequestException('Expected an object.');return value as Record<string,unknown>;}
export function text(value:unknown,max=4000){if(typeof value!=='string'||!value.trim()||value.length>max)throw new BadRequestException('Provide a nonempty text value within the allowed length.');return value.trim();}
export function uuid(value:unknown){if(typeof value!=='string'||!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value))throw new BadRequestException('Provide a valid UUID.');return value;}
export function integer(value:unknown,min:number,max:number,fallback:number){if(value===undefined)return fallback;const n=Number(value);if(!Number.isInteger(n)||n<min||n>max)throw new BadRequestException('Number is outside the permitted range.');return n;}
export function pointer(value:unknown,path:string):unknown{
 if(path==='')return value;if(!path.startsWith('/'))return undefined;
 for(const key of path.slice(1).split('/').map(k=>k.replaceAll('~1','/').replaceAll('~0','~'))){if(!value||typeof value!=='object'||!Object.hasOwn(value,key))return undefined;value=(value as Record<string,unknown>)[key];}return value;
}
export function matches(value:unknown,filters:Record<string,unknown>){return Object.entries(filters).every(([path,expected])=>JSON.stringify(pointer(value,path===''||path.startsWith('/')?path:'/'+path.replaceAll('~','~0').replaceAll('/','~1')))===JSON.stringify(expected));}
export function checkCriterion(criterion:Criterion,operations:Operation[]){
 const evidence=operations.filter(op=>op.status==='SUCCEEDED'&&!(op.result as {operatorReconciled?:boolean})?.operatorReconciled&&op.kind===criterion.kind&&(!criterion.serverId||op.action.serverId===criterion.serverId)&&(!criterion.tool||op.action.tool===criterion.tool)&&matches(op.action.arguments??op.action,criterion.match));
 const observations=evidence.map(op=>({operationId:op.id,value:pointer(op.result,criterion.pointer)}));
 const passed=observations.some(({value})=>{
  switch(criterion.operator){case'exists':return value!==undefined&&value!==null;case'equals':return JSON.stringify(value)===JSON.stringify(criterion.expected);case'nonempty':return typeof value==='string'?value.trim().length>0:Array.isArray(value)?value.length>0:!!value&&typeof value==='object'&&Object.keys(value).length>0;case'gte':return typeof value==='number'&&typeof criterion.expected==='number'&&value>=criterion.expected;case'contains':return typeof value==='string'&&typeof criterion.expected==='string'?value.includes(criterion.expected):Array.isArray(value)&&value.some(item=>JSON.stringify(item)===JSON.stringify(criterion.expected));}
 });return{passed,observations};
}
export function validateDecision(value:unknown):Decision{
 const d=object(value);if(!['execute','wait','complete','blocked','respond'].includes(String(d.kind)))throw new BadRequestException('Invalid agent decision.');
 if(!Array.isArray(d.plan)||d.plan.length>100||d.plan.some(x=>typeof x!=='string'||x.length>2000)||!Array.isArray(d.criteria)||d.criteria.length>30)throw new BadRequestException('Invalid task plan.');
 const ids=new Set<string>();for(const raw of d.criteria){const c=object(raw);if(typeof c.id!=='string'||ids.has(c.id)||!['mcp','command','workspace','response'].includes(String(c.kind))||!['exists','equals','nonempty','gte','contains'].includes(String(c.operator))||typeof c.pointer!=='string'||c.pointer.length>500||!(c.pointer===''||c.pointer.startsWith('/')))throw new BadRequestException('Invalid measurable completion criterion.');text(c.description,2000);object(c.match);ids.add(c.id);}
 if(d.kind==='execute'){const a=object(d.action);if(!['mcp','command','workspace','evidence'].includes(String(a.kind)))throw new BadRequestException('Invalid action kind.');}
 if(d.kind==='execute'){const a=object(d.action);d.action=a.kind==='evidence'?{kind:'evidence',arguments:object(a.arguments)}:a.kind==='mcp'?{kind:'mcp',serverId:uuid(a.serverId),tool:text(a.tool,200),arguments:object(a.arguments)}:a.kind==='command'?{kind:'command',executable:text(a.executable,100),args:a.args}:{kind:'workspace',operation:a.operation,path:text(a.path,1000),...(a.operation==='write'?{content:a.content}:{})};}
 if(d.kind==='respond')text(d.summary,20000);
 text(d.goal,4000);text(d.step,2000);if(typeof d.summary!=='string'||d.summary.length>20000)throw new BadRequestException('Invalid task summary.');
 integer(d.waitSeconds,0,300,5);if(d.planStep!==undefined)integer(d.planStep,0,99,0);return d as unknown as Decision;
}
export class TransientTaskError extends Error{constructor(message:string,readonly retryAfterMs=0){super(message);}}
export class RecoverableToolError extends Error{}
export class UnknownTaskOutcome extends Error{}
export class LeaseLost extends Error{}
export function retryDelay(attempt:number,retryAfter=0,random=Math.random){return Math.max(retryAfter,Math.min(300000,1000*2**Math.min(attempt,8))*(0.75+random()*0.5));}
