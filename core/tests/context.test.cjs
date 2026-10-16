require('reflect-metadata');
const {test}=require('node:test');const assert=require('node:assert/strict');
const {LlmService,ToolContinuationRequired}=require('../dist/llm/llm.service');
const {contextBudget}=require('../dist/llm/context-window');
const {withTokenCount}=require('./openai-fixture.cjs');
const answer={status:'completed',output:[{type:'message',role:'assistant',content:[{type:'output_text',text:'Finished'}]}]};
const settings={OPENAI_API_KEY:'fixture-key-never-sent',LLM_MODEL:'saved-model',LLM_THINKING:'instant'};
const json=value=>new Response(JSON.stringify(value));
const copy=value=>JSON.parse(JSON.stringify(value));
function service(mcp,values={}){return new LlmService({read:async()=>({...settings,...values})},mcp);}

test('context budget uses verified capacities, a conservative fallback, and an explicit override',()=>{
 assert.equal(contextBudget('gpt-6-luna').threshold,945000);
 assert.equal(contextBudget('unknown').window,128000);
 assert.equal(contextBudget('gpt-6-luna','32000').threshold,28800);
 for(const value of ['0','NaN','9000.5','2000001'])assert.throws(()=>contextBudget('model',value));
 for(const window of ['8192','128000','1050000']){const b=contextBudget('model',window);assert(b.threshold+b.output<b.window);}
});

test('at exactly 90%, the same selected model compacts; its entire window is saved before inference and reused',async t=>{
 const input=[{role:'user',content:'Prior preferences'},{role:'assistant',content:'Prior facts'},{role:'user',content:'Continue task'}];
 const compacted=[{role:'user',content:'Retained requirement'},{type:'compaction',encrypted_content:'opaque-memory'}];
 const requests=[],saved=[];let count=0,completed;
 t.mock.method(global,'fetch',async(url,options)=>{
  const body=JSON.parse(options.body);requests.push({url,body});assert.equal(options.headers.Authorization,`Bearer ${settings.OPENAI_API_KEY}`);
  if(url.endsWith('/input_tokens'))return json({input_tokens:count++===0?115200:200});
  if(url.endsWith('/compact')){assert.equal(body.model,settings.LLM_MODEL);assert.deepEqual(body.input,input);assert(body.instructions.includes('declined'));return json({output:compacted});}
  assert.deepEqual(body.input,compacted);assert.equal(body.store,false);return json(answer);
 });
 assert.equal(await service().respond(input,undefined,{saveState:async state=>saved.push(copy(state)),completeContext:async(model,items)=>{completed={model,items:copy(items)};}}),'Finished');
 assert.equal(requests.length,4);assert.deepEqual(saved[0].conversation,compacted);assert.deepEqual(completed.items,[...compacted,...answer.output]);
 assert(!JSON.stringify(completed).includes(settings.OPENAI_API_KEY));
 const tail={role:'user',content:'New question'};
 t.mock.method(global,'fetch',withTokenCount(async(_url,options)=>{assert.deepEqual(JSON.parse(options.body).input,[...completed.items,tail]);return json(answer);}));
 await service().respond([...input,tail],undefined,{context:{...completed,throughPosition:'7'},newInput:[tail]});
});

test('below 90% no summary is requested; switching models rebuilds input from saved transcript',async t=>{
 const full=[{role:'user',content:'Full transcript'}];let requests=0;
 t.mock.method(global,'fetch',async(url,options)=>{
  requests++;if(url.endsWith('/input_tokens'))return json({input_tokens:115199});
  assert.deepEqual(JSON.parse(options.body).input,full);return json(answer);
 });
 await service().respond(full,undefined,{context:{model:'old-model',items:[{type:'compaction',encrypted_content:'old'}],throughPosition:'1'},newInput:[]});
 assert.equal(requests,2);
});

test('failed or ineffective compaction preserves the original state and never sends a truncated generation request',async t=>{
 const input=[{role:'user',content:'Original requirement'}];let generations=0;
 t.mock.method(global,'fetch',async(url)=>{
  if(url.endsWith('/input_tokens'))return json({input_tokens:115200});
  if(url.endsWith('/compact'))return json({output:[]});
  generations++;return json(answer);
 });
 await assert.rejects(service().respond(input),/no valid compacted context/);assert.deepEqual(input,[{role:'user',content:'Original requirement'}]);assert.equal(generations,0);
 t.mock.method(global,'fetch',async(url)=>url.endsWith('/input_tokens')?json({input_tokens:115200}):json({output:[{type:'compaction',encrypted_content:'not-smaller'}]}));
 await assert.rejects(service().respond(input),/still at 90%/);
});

function toolsFixture(){
 const executed=[];const tool={serverId:'server',toolName:'lookup',readOnly:true,type:'function',name:'lookup',description:'Read only',parameters:{type:'object',properties:{}},strict:false};
 return{executed,tool,mcp:{agentTools:async()=>[tool],execute:async(_id,_name,args)=>{executed.push(args.index);return{structuredContent:{index:args.index}};}}};
}
const call=(index)=>({type:'function_call',name:'lookup',call_id:`call-${index}`,arguments:JSON.stringify({index})});
async function checkpoint(promise,reason){let state;await assert.rejects(promise,error=>{assert(error instanceof ToolContinuationRequired);assert.equal(error.reason,reason);state=copy(error.state);return true;});return state;}

test('eight model turns checkpoint before queued tools; the next prompt completes without replaying completed calls',async t=>{
 const f=toolsFixture();let rounds=0;const saved=[];
 t.mock.method(global,'fetch',withTokenCount(async()=>json(++rounds<=8?{status:'completed',output:[call(rounds)]}:answer)));
 const llm=service(f.mcp);const state=await checkpoint(llm.respond([{role:'user',content:'Look up details'}],undefined,{saveState:async s=>saved.push(copy(s))}),'model_turns');
 assert.equal(rounds,8);assert.deepEqual(f.executed,[1,2,3,4,5,6,7]);assert.equal(state.remaining.length,1);
 assert.equal(await llm.respond([],undefined,{state}),'Finished');assert.deepEqual(f.executed,[1,2,3,4,5,6,7,8]);assert.equal(rounds,9);assert(saved.length>=8);
});

test('twelve tool calls checkpoint a partially consumed batch with every completed result retained',async t=>{
 const f=toolsFixture();let rounds=0;
 t.mock.method(global,'fetch',withTokenCount(async()=>json(++rounds===1?{status:'completed',output:Array.from({length:13},(_v,i)=>call(i))}:answer)));
 const llm=service(f.mcp);const state=await checkpoint(llm.respond([{role:'user',content:'Read dataset'}]),'tool_calls');
 assert.equal(f.executed.length,12);assert.equal(state.remaining[0].call_id,'call-12');assert.equal(state.conversation.filter(item=>item.type==='function_call_output').length,12);
 assert.equal(await llm.respond([],undefined,{state}),'Finished');assert.deepEqual(f.executed,Array.from({length:13},(_v,i)=>i));
});

test('a two-minute deadline checkpoints completed work; a fresh prompt uses a fresh deadline and never replays a tool',async t=>{
 const f=toolsFixture();let rounds=0,current;const durations=[];
 t.mock.method(AbortSignal,'timeout',ms=>{durations.push(ms);current=new AbortController();return current.signal;});
 t.mock.method(global,'fetch',withTokenCount(async()=>{
  if(++rounds===1)return json({status:'completed',output:[call(1)]});
  if(rounds===2){current.abort();throw new DOMException('Timed out','TimeoutError');}
  return json(answer);
 }));
 const llm=service(f.mcp);const state=await checkpoint(llm.respond([{role:'user',content:'Lookup'}]),'deadline');
 assert.deepEqual(f.executed,[1]);assert.equal(state.remaining.length,0);assert.equal(await llm.respond([],undefined,{state}),'Finished');assert.deepEqual(f.executed,[1]);assert.deepEqual(durations,[120000,120000]);
});

test('token-count authentication errors and invalid counts are visible and never trigger generation',async t=>{
 t.mock.method(global,'fetch',async()=>json({input_tokens:'invalid'}));await assert.rejects(service().respond([]),/invalid context token count/);
 t.mock.method(global,'fetch',async()=>new Response('credential and stack trace',{status:401}));await assert.rejects(service().respond([]),/rejected the API key/);
});
