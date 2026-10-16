import {request} from './api';
import type {McpConnection,McpInput,McpTest} from '@/types/mcp';
const base='/api/mcp/servers';
const json=(method:string,body:unknown):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});
export const mcpApi={
 list:(signal?:AbortSignal)=>request<McpConnection[]>(base+'/managed',{signal,cache:'no-store'}),
 save:(body:McpInput,id?:string)=>request<McpConnection>(id?`${base}/${id}/configuration`:base+'/managed',json(id?'PUT':'POST',body)),
 test:(body:McpInput,id?:string)=>request<McpTest>(id?`${base}/${id}/test`:base+'/test',json('POST',body)),
 discover:(id:string)=>request<McpConnection>(`${base}/${id}/discover`,{method:'POST',cache:'no-store'}),
 permissions:(id:string,allowedTools:string[],enabled:boolean)=>request<McpConnection>(`${base}/${id}/permissions`,json('PUT',{allowedTools,enabled})),
 disconnect:(id:string)=>request<McpConnection>(`${base}/${id}/disconnect`,{method:'POST'}),
 remove:(id:string)=>request<{deleted:boolean}>(`${base}/${id}`,{method:'DELETE'}),
};
