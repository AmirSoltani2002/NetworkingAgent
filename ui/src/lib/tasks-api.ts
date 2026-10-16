import {request} from './api';
import type {TaskConfig,TaskDetail,TaskSummary} from '@/types/tasks';
const json=(method:string,body:unknown)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const tasksApi={
 policy:()=>request<{controlledTools:string[]}>('/api/task-policy'),
 list:(history=false,offset=0)=>request<TaskSummary[]>(`/api/tasks?history=${history}&offset=${offset}&limit=25`),
 get:(id:string)=>request<TaskDetail>(`/api/tasks/${id}`),
 create:(body:unknown)=>request<TaskDetail>('/api/tasks',json('POST',body)),
 control:(id:string,action:string,body:unknown={})=>request(`/api/tasks/${id}/${action}`,json('POST',body)),
 configs:(kind:'schedules')=>request<TaskConfig[]>(`/api/${kind}`),
 save:(kind:'schedules',body:unknown,id?:string)=>request<TaskConfig>(`/api/${kind}${id?'/'+id:''}`,json(id?'PUT':'POST',body)),
 enable:(kind:'schedules',id:string,enabled:boolean)=>request(`/api/${kind}/${id}/enabled`,json('POST',{enabled})),
 remove:(kind:'schedules',id:string)=>request(`/api/${kind}/${id}`,{method:'DELETE'}),
 history:(kind:'schedules',id:string)=>request<TaskSummary[]>(`/api/${kind}/${id}/history`),
};
