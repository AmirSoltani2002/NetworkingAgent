const {withTokenCount}=require('./openai-fixture.cjs');
require('reflect-metadata');
const {test}=require('node:test');const assert=require('node:assert/strict');const {Pool}=require('pg');const {readFile}=require('node:fs/promises');const {randomUUID}=require('node:crypto');
const {McpService}=require('../dist/mcp/mcp.service');const {ChatsService}=require('../dist/chats/chats.service');
test('real PostgreSQL registry upgrades/updates and chat persistence/retry/trace regression',{skip:!process.env.CORE_TEST_DATABASE_URL},async()=>{
 const url=new URL(process.env.CORE_TEST_DATABASE_URL);assert(/_tests?$/.test(url.pathname),'Refuse tests against non-test database');const pool=new Pool({connectionString:url.href});
 const db={pool,transaction:async(fn)=>{const client=await pool.connect();await client.query('BEGIN');try{const value=await fn(client);await client.query('COMMIT');return value;}catch(error){await client.query('ROLLBACK');throw error;}finally{client.release();}}};
 let profile,chat;try{
  const schema=await readFile(require('node:path').resolve(__dirname,'../../database/schema.sql'),'utf8');await pool.query(schema);await pool.query(schema);
  const mcp=new McpService(db,{read:async()=>({})});profile=await mcp.save({name:'SQL fixture',url:'http://rag-api:8090/mcp',authEnvVar:'TEST_TOKEN'});
  profile=await mcp.save({name:'Updated fixture',url:'http://rag-api:8090/mcp',authEnvVar:'TEST_TOKEN'},profile.id);assert.equal(profile.name,'Updated fixture');
  let generations=0;const service=new ChatsService(db,{respond:async(input,record)=>{generations++;assert(input.at(-1).content.includes('contents are not included'));await record({serverId:profile.id,tool:'search_knowledge',success:true,durationMs:1,sources:[{chunk_id:'chunk',document_id:'doc'}]});return 'Evidence reply';}});
  chat=await service.create();const userId=randomUUID();const file={size:5,originalname:'../notes.txt',buffer:Buffer.from('hello')};const user=await service.addMessage(chat.id,'Clicking startup',userId,[file]);assert.equal(user.chat.title,'Clicking startup');assert.equal(user.message.attachments[0].name,'.._notes.txt');
  await service.addMessage(chat.id,'Ignored retry',userId,[]);const reply=await service.respond(chat.id,userId);assert.equal(reply.message.text,'Evidence reply');assert.equal(reply.message.toolCalls[0].tool,'search_knowledge');
  assert.equal((await service.respond(chat.id,userId)).message.id,reply.message.id);assert.equal(generations,1);const history=await service.get(chat.id);assert.equal(history.messages.length,2);assert.equal(history.messages[0].text,'Clicking startup');assert.equal((await service.download(chat.id,user.message.attachments[0].id)).content.toString(),'hello');
 }finally{if(chat)await pool.query('DELETE FROM chats WHERE id=$1',[chat.id]);if(profile)await pool.query('DELETE FROM mcp_servers WHERE id=$1',[profile.id]);await pool.end();}
});

test('real PostgreSQL confirms an exact invocation, hides continuation, and retries provider without tool replay',{skip:!process.env.CORE_TEST_DATABASE_URL},async t=>{
 const {LlmService}=require('../dist/llm/llm.service');const url=new URL(process.env.CORE_TEST_DATABASE_URL);assert(/_tests?$/.test(url.pathname));const pool=new Pool({connectionString:url.href});
 const db={pool,transaction:async fn=>{const c=await pool.connect();await c.query('BEGIN');try{const result=await fn(c);await c.query('COMMIT');return result;}catch(error){await c.query('ROLLBACK');throw error;}finally{c.release();}}};
 const serverId=randomUUID();let executions=0,providerCalls=0;const tool={serverId,serverName:'Fixture service',toolName:'train',readOnly:false,type:'function',name:'mcp_train',description:'Train',parameters:{type:'object',properties:{},additionalProperties:false},strict:false};
 const mcp={agentTools:async()=>[tool],prepareCall:async()=>({serverId,serverName:'Fixture service',toolName:'train',readOnly:false,configurationDigest:'saved-configuration',argumentsDigest:'args'}),execute:async()=>{executions++;return{structuredContent:{job_id:'persisted-job'},content:[]};}};
 t.mock.method(global,'fetch',withTokenCount(async()=>{providerCalls++;if(providerCalls===1)return new Response(JSON.stringify({status:'completed',output:[{type:'function_call',name:tool.name,arguments:'{}',call_id:'call'}]}));if(providerCalls===2)throw new Error('provider unavailable');return new Response(JSON.stringify({status:'completed',output:[{type:'message',content:[{type:'output_text',text:'Job persisted'}]}]}));}));
 const service=new ChatsService(db,new LlmService({read:async()=>({OPENAI_API_KEY:'fixture-key-never-sent',LLM_MODEL:'fixture',LLM_THINKING:'instant'})},mcp));let chat;
 try{
  await pool.query(await readFile(require('node:path').resolve(__dirname,'../../database/schema.sql'),'utf8'));chat=await service.create();const messageId=randomUUID();await service.addMessage(chat.id,'Train the fixture',messageId,[]);
  const proposed=await service.respond(chat.id,messageId);assert.equal(executions,0);assert.equal(proposed.pendingConfirmation.tool,'train');const detail=await service.get(chat.id);assert.equal(detail.pendingConfirmation.id,proposed.pendingConfirmation.id);assert(!JSON.stringify(detail).includes('conversation'));assert(!JSON.stringify(detail).includes('configurationDigest'));
  assert.equal((await service.respond(chat.id,messageId)).pendingConfirmation.id,proposed.pendingConfirmation.id);assert.equal(providerCalls,1);
  await assert.rejects(service.respond(chat.id,messageId,{id:randomUUID(),approved:true}),/does not match/);
  await assert.rejects(service.respond(chat.id,messageId,{id:proposed.pendingConfirmation.id,approved:true}),/connection failed/);assert.equal(executions,1);
  const reply=await service.respond(chat.id,messageId);assert.equal(reply.message.text,'Job persisted');assert.equal(reply.message.toolCalls[0].result.job_id,'persisted-job');assert.equal(executions,1);
  assert.equal((await service.respond(chat.id,messageId,{id:proposed.pendingConfirmation.id,approved:true})).message.id,reply.message.id);assert.equal(executions,1);assert.equal((await service.get(chat.id)).pendingConfirmation,null);
 }finally{if(chat)await pool.query('DELETE FROM chats WHERE id=$1',[chat.id]);await pool.end();}
});

test('real PostgreSQL persists a compacted window and watermark across service recreation without leaking it to the UI',{skip:!process.env.CORE_TEST_DATABASE_URL},async t=>{
 const {LlmService}=require('../dist/llm/llm.service');const url=new URL(process.env.CORE_TEST_DATABASE_URL);assert(/_tests?$/.test(url.pathname));const pool=new Pool({connectionString:url.href});
 const db={pool,transaction:async fn=>{const c=await pool.connect();await c.query('BEGIN');try{const result=await fn(c);await c.query('COMMIT');return result;}catch(error){await c.query('ROLLBACK');throw error;}finally{c.release();}}};
 const retained=[{role:'user',content:'Retained requirement'},{type:'compaction',encrypted_content:'fixture-private-summary'}];
 let counts=0,generations=0;const requests=[];const settings={read:async()=>({OPENAI_API_KEY:'fixture-never-sent',LLM_MODEL:'saved-model',LLM_THINKING:'instant'})};
 t.mock.method(global,'fetch',async(url,options)=>{const body=JSON.parse(options.body);
  if(url.endsWith('/input_tokens'))return new Response(JSON.stringify({input_tokens:counts++===0?115200:100}));
  if(url.endsWith('/compact'))return new Response(JSON.stringify({output:retained}));
  requests.push(body.input);generations++;return new Response(JSON.stringify({status:'completed',output:[{type:'message',role:'assistant',content:[{type:'output_text',text:`Reply ${generations}`}]}]}));
 });
 let chat;try{
  const schema=await readFile(require('node:path').resolve(__dirname,'../../database/schema.sql'),'utf8');await pool.query(schema);await pool.query(schema);
  let service=new ChatsService(db,new LlmService(settings));chat=await service.create();const first=randomUUID();await service.addMessage(chat.id,'First question',first,[]);await service.respond(chat.id,first);
  const context=(await pool.query('SELECT context_window FROM chats WHERE id=$1',[chat.id])).rows[0].context_window;
  assert.deepEqual(context.items.slice(0,2),retained);assert(/^[0-9]+$/.test(context.throughPosition));
  assert(!JSON.stringify(await service.get(chat.id)).includes('fixture-private-summary'));assert(!JSON.stringify(await service.list()).includes('context_window'));
  service=new ChatsService(db,new LlmService(settings));const second=randomUUID();await service.addMessage(chat.id,'Second question',second,[]);const reply=await service.respond(chat.id,second);
  assert.equal(reply.message.text,'Reply 2');assert.deepEqual(requests[1],[...context.items,{role:'user',content:'Second question'}]);
  assert.equal((await service.get(chat.id)).messages.length,4);assert.equal((await service.respond(chat.id,second)).message.id,reply.message.id);assert.equal(generations,2);
 }finally{if(chat)await pool.query('DELETE FROM chats WHERE id=$1',[chat.id]);await pool.end();}
});
