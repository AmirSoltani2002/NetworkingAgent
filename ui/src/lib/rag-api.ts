import {request} from './api';
import type {ConnectionInput,ConnectionTest,RagConnection,Page,DocumentRecord} from '@/types/rag';
const base='/api/rag/connections';
const json=(body:unknown,method='POST'):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});
export const ragApi={
  list:(signal?:AbortSignal)=>request<RagConnection[]>(base,{signal,cache:'no-store'}),
  save:(body:ConnectionInput,id?:string)=>request<RagConnection>(base+(id?`/${id}`:''),json(body,id?'PUT':'POST')),
  test:(body:ConnectionInput,id?:string)=>request<ConnectionTest>(base+(id?`/${id}/test`:'/test'),json(body)),
  disconnect:(id:string)=>request<RagConnection>(`${base}/${id}/disconnect`,json({})),
  permissions:(id:string,allowedTools:string[],agentEnabled:boolean)=>request<RagConnection>(`${base}/${id}/permissions`,json({allowedTools,agentEnabled},'PUT')),
  operation:<T>(id:string,path:string,method='GET',data?:unknown,signal?:AbortSignal)=>request<T>(`${base}/${id}/request`,{...json({path,method,...(data!==undefined?{data}:{})}),signal}),
  upload:(id:string,body:FormData)=>request<DocumentRecord>(`${base}/${id}/upload`,{method:'POST',body}),
  catalog:async <T>(id:string,path:string,signal?:AbortSignal)=>{
    const items:T[]=[]; let offset=0;
    for (;;) {
      const page=await ragApi.operation<Page<T>>(id,`${path}${path.includes('?')?'&':'?'}offset=${offset}&limit=100`,'GET',undefined,signal);
      if (!Array.isArray(page.items)||typeof page.total!=='number') throw new Error('RAG returned an incompatible list response.');
      items.push(...page.items); offset+=page.items.length;
      if(offset>=page.total) return items;
      if(!page.items.length || offset>=5000) throw new Error('Catalog exceeds the 5,000 record view limit or changed while loading. Narrow the RAG dataset and reload.');
    }
  },
};
