const {withTokenCount}=require('./openai-fixture.cjs');
require('reflect-metadata');
const {test}=require('node:test');const assert=require('node:assert/strict');
const {createServer}=require('node:http');
const {approvedUrl,safeAddress}=require('../dist/mcp/network-policy');
const {validateOperation}=require('../dist/rag/rag.controller');
const {ragRequest}=require('../dist/rag/rag-client');
const {LlmService}=require('../dist/llm/llm.service');
const {RagService}=require('../dist/rag/rag.service');
test('approved origins, unsafe addresses and REST operation restrictions',()=>{
 assert.equal(approvedUrl('http://rag-api:8090/mcp').hostname,'rag-api');
 for(const url of ['http://169.254.169.254/','http://example.com/mcp','file:///tmp/x','http://user:pass@rag-api:8090/mcp','http://rag-api:8090/mcp?token=x'])assert.throws(()=>approvedUrl(url));
 for(const address of ['169.254.169.254','0.0.0.1','fe80::1','::ffff:169.254.169.254','fd00:ec2::254'])assert.equal(safeAddress(address),false);
 assert.equal(safeAddress('127.0.0.1'),true);assert.equal(safeAddress('172.18.0.3'),true);
 assert.equal(validateOperation({path:'api/devices?limit=20'}).method,'GET');
 for(const path of ['http://example.com','api/../../health','api/devices%2f..','api/admin','api/devices?url=http://metadata'])assert.throws(()=>validateOperation({path}));
});
test('REST client forwards auth, multipart, deletion; blocks redirects and masks upstream errors',async()=>{
 const seen=[];const server=createServer(async(req,res)=>{
   let body='';for await(const chunk of req)body+=chunk;
   seen.push({url:req.url,auth:req.headers.authorization,body});
   if(req.url==='/redirect'){res.writeHead(302,{location:'http://169.254.169.254/'});res.end();return;}
   if(req.url==='/denied'){res.writeHead(401);res.end('TOP_SECRET stack trace');return;}
   if(req.method==='DELETE'){res.writeHead(204);res.end();return;}
   res.setHeader('Content-Type','application/json');res.end(JSON.stringify({echo:'fixture-secret',items:[]}));
 });await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const origin=`http://127.0.0.1:${server.address().port}`;const target={restUrl:origin,origins:origin,secret:'fixture-secret'};
 try{
  assert.deepEqual(await ragRequest(target,'api/devices'),{echo:'[redacted]',items:[]});
  const body=new FormData();body.set('file',new Blob(['manual']),'manual.txt');await ragRequest(target,'api/documents/upload','POST',body);
  assert(seen.at(-1).body.includes('manual.txt'));assert.equal(seen.at(-1).auth,'Bearer fixture-secret');
  assert.deepEqual(await ragRequest(target,'api/devices/id','DELETE'),{deleted:true});
  await assert.rejects(ragRequest(target,'redirect'),/unavailable/);
  await assert.rejects(ragRequest(target,'denied'),/authentication failed/);
 }finally{await new Promise(resolve=>server.close(resolve));}
});
test('connection tests keep independent MCP/REST failure states and tokens out of results',async()=>{
 const row={id:'profile',url:'http://rag-api:8090/mcp',rest_url:'http://rag-api:8090/',auth_env_var:'TOKEN',tools:[],allowed_tools:[]};
 const statements=[];const service=new RagService({pool:{query:async(...args)=>{statements.push(args);return {rows:[row]};}}},{read:async()=>({TOKEN:'fixture-secret'})},{get:async()=>row,inspect:async()=>{throw new Error('fixture-secret');}});
 // Both unreachable is actionable; MCP exceptions never leak upstream text.
 const result=await service.test({name:'RAG',url:row.url,restUrl:row.rest_url,authentication:'bearer'},'profile');
 assert.equal(result.mcpStatus,'failed');assert.equal(result.restStatus,'failed');assert(!JSON.stringify(result).includes('fixture-secret'));assert.equal(statements.length,1);
});
test('existing Responses path selects permitted MCP tools, preserves reasoning, records sources, and does not force calls',async()=>{
 const old=global.fetch;let requests=[];let calls=0;const trace=[];
 const tools=[{type:'function',name:'rag_fixture',description:'Search',parameters:{type:'object',properties:{query:{type:'string'}}},strict:false,serverId:'server',toolName:'search_knowledge'}];
 const service=new LlmService({read:async()=>({OPENAI_API_KEY:'key-secret',LLM_MODEL:'existing-model',LLM_THINKING:'instant'})},{agentTools:async()=>tools,execute:async(id,name,args)=>{calls++;assert.equal(args.query,'clicking');return {structuredContent:{results:[{chunk_id:'chunk',document_id:'doc',document_title:'Manual',page_number:15}]}};}});
 global.fetch=withTokenCount(async(url,init)=>{const body=JSON.parse(init.body);requests.push(body);return new Response(JSON.stringify(requests.length===1?{status:'completed',output:[{type:'reasoning',id:'reason',encrypted_content:'opaque'},{type:'function_call',name:'rag_fixture',call_id:'call1',arguments:'{"query":"clicking"}'}]}:{status:'completed',output:[{type:'message',content:[{type:'output_text',text:'Manual, p.15: possible relay cause.'}]}]}));});
 try{
  const reply=await service.respond([{role:'user',content:'Clicking?'}],async item=>trace.push(item));
  assert.equal(reply,'Manual, p.15: possible relay cause.');assert.equal(calls,1);assert.equal(requests[0].model,'existing-model');assert.equal(requests[0].tool_choice,'auto');
  assert(requests[1].input.some(item=>item.type==='reasoning'));assert(requests[1].input.some(item=>item.type==='function_call_output'));
  assert.equal(trace[0].sources[0].chunk_id,'chunk');assert(!('arguments' in trace[0]));
  requests=[];global.fetch=withTokenCount(async()=>new Response(JSON.stringify({status:'completed',output:[{type:'message',content:[{type:'output_text',text:'Hello'}]}]})));
  assert.equal(await service.respond([{role:'user',content:'Hi'}]),'Hello');assert.equal(calls,1);
 }finally{global.fetch=old;}
});
test('unregistered functions never reach MCP and provider/auth failures preserve safe errors',async()=>{
 const old=global.fetch;let n=0,calls=0;
 const service=new LlmService({read:async()=>({OPENAI_API_KEY:'key-secret',LLM_MODEL:'saved-model'})},{agentTools:async()=>[],execute:async()=>{calls++;}});
 global.fetch=withTokenCount(async()=>new Response(JSON.stringify(++n===1?{status:'completed',output:[{type:'function_call',name:'shell',arguments:'{}',call_id:'x'}]}:{status:'completed',output:[{type:'message',content:[{type:'output_text',text:'No permitted tool.'}]}]})));
 try{assert.equal(await service.respond([{role:'user',content:'Hi'}]),'No permitted tool.');assert.equal(calls,0);
 global.fetch=withTokenCount(async()=>new Response('key-secret',{status:401}));await assert.rejects(service.respond([]),/rejected the API key/);
 }finally{global.fetch=old;}
});
test('draft authentication changes cannot overwrite saved connection health; MCP and REST remain independent',async()=>{
 const server=createServer((_req,res)=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify({items:[],total:0}));});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin=`http://127.0.0.1:${server.address().port}`;
 let writes=0;const row={url:origin+'/mcp',rest_url:origin+'/',auth_env_var:'TOKEN',allowed_tools:[]};const service=new RagService({pool:{query:async()=>{writes++;return{rows:[row]};}}},{read:async()=>({TOKEN:'secret-fixture',RAG_ALLOWED_ORIGINS:origin})},{get:async()=>row,inspect:async()=>{throw new Error('Unreachable MCP');}});
 try{const result=await service.test({name:'RAG',url:row.url,restUrl:row.rest_url,authentication:'none'},'id');assert.equal(result.restStatus,'connected');assert.equal(result.mcpStatus,'failed');assert.equal(writes,0);}finally{await new Promise(resolve=>server.close(resolve));}
});

test('global error handling never logs stacks containing submitted secrets',()=>{
 const {HttpExceptionFilter}=require('../dist/http-exception.filter');const {Logger,BadRequestException}=require('@nestjs/common');const old=Logger.error;const logged=[];Logger.error=(...items)=>logged.push(items);let response;const host={switchToHttp:()=>({getResponse:()=>({status:()=>({json:body=>{response=body;}})})})};
 try{new HttpExceptionFilter().catch(new Error('submitted-private-token'),host);assert(!JSON.stringify(logged).includes('submitted-private-token'));assert(!JSON.stringify(response).includes('submitted-private-token'));
 new HttpExceptionFilter().catch(new BadRequestException('Unexpected token submitted-private-token in JSON'),host);assert.equal(response.message,'Invalid JSON request body.');}finally{Logger.error=old;}
});
