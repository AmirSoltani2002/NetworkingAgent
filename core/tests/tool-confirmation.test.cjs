const {withTokenCount}=require('./openai-fixture.cjs');
require('reflect-metadata');
const {test}=require('node:test');const assert=require('node:assert/strict');const {randomBytes}=require('node:crypto');
const {LlmService,ToolConfirmationRequired,publicConfirmation}=require('../dist/llm/llm.service');
const {McpService}=require('../dist/mcp/mcp.service');

function fixture(){
 let calls=0,revision='revision-1';const traces=[],states=[];
 const tool={serverId:'server',serverName:'Generic classifier',toolName:'retrain',readOnly:false,type:'function',name:'mcp_function',description:'Retrain model',parameters:{type:'object',properties:{approved:{type:'boolean'}},required:['approved'],additionalProperties:false},strict:false};
 const mcp={agentTools:async()=>[tool],prepareCall:async(_id,_name,args)=>{assert.deepEqual(args,{approved:true});return{serverId:'server',serverName:'Generic classifier',toolName:'retrain',readOnly:false,configurationDigest:revision,argumentsDigest:'arguments'};},execute:async(_id,_name,_args,_signal,confirmation)=>{assert.equal(states.at(-1).phase,'executing');assert.equal(confirmation.configurationDigest,revision);calls++;return{structuredContent:{job_id:'job-1',status:'queued'},content:[]};}};
 const key=randomBytes(32).toString('hex');const llm=new LlmService({read:async()=>({OPENAI_API_KEY:key,LLM_MODEL:'saved-model',LLM_THINKING:'instant'})},mcp);
 const first={status:'completed',output:[{type:'reasoning',encrypted_content:'opaque-reasoning'}, {type:'function_call',name:tool.name,arguments:'{"approved":true}',call_id:'call-1'}]};
 const final={status:'completed',output:[{type:'message',content:[{type:'output_text',text:'Job queued.'}]}]};
 const record=async trace=>traces.push(trace);const saveState=async state=>states.push(JSON.parse(JSON.stringify(state)));
 return{llm,mcp,tool,key,first,final,traces,states,record,saveState,get calls(){return calls;},changeRevision(){revision='revision-2';}};
}
async function propose(f){let pending;await assert.rejects(f.llm.respond([{role:'user',content:'Train the model'}],f.record,{saveState:f.saveState}),error=>{assert(error instanceof ToolConfirmationRequired);pending=JSON.parse(JSON.stringify(error.state));return true;});assert.equal(f.calls,0);return pending;}

test('state-changing tools pause, expose exact invocation and run once only after explicit confirmation',async t=>{
 const f=fixture();let requests=0;t.mock.method(global,'fetch',withTokenCount(async()=>new Response(JSON.stringify(requests++===0?f.first:f.final))));
 const state=await propose(f);assert.equal(publicConfirmation(state).tool,'retrain');assert.deepEqual(publicConfirmation(state).arguments,{approved:true});assert(!JSON.stringify(state).includes(f.key));
 const answer=await f.llm.respond([],f.record,{state,decision:{id:state.pending.id,approved:true},saveState:f.saveState});
 assert.equal(answer,'Job queued.');assert.equal(f.calls,1);assert.equal(f.traces[0].result.job_id,'job-1');assert.equal(f.states.at(-1).phase,'continuing');
});

test('declined operations never execute and return denial to the same saved-model loop',async t=>{
 const f=fixture();let requests=0;t.mock.method(global,'fetch',withTokenCount(async(_url,options)=>{const payload=JSON.parse(options.body);if(requests++===0)return new Response(JSON.stringify(f.first));assert(payload.input.some(item=>item.type==='function_call_output'&&item.output.includes('declined')));return new Response(JSON.stringify(f.final));}));
 const state=await propose(f);await f.llm.respond([],f.record,{state,decision:{id:state.pending.id,approved:false},saveState:f.saveState});assert.equal(f.calls,0);assert.equal(f.traces[0].success,false);
});

test('schema/connection/permission changes invalidate the proposed authorization',async t=>{
 const f=fixture();let requests=0;t.mock.method(global,'fetch',withTokenCount(async()=>new Response(JSON.stringify(requests++===0?f.first:f.final))));
 const state=await propose(f);f.changeRevision();await f.llm.respond([],f.record,{state,decision:{id:state.pending.id,approved:true},saveState:f.saveState});assert.equal(f.calls,0);assert.equal(f.traces[0].success,false);
});

test('mismatched, expired and interrupted confirmations cannot execute',async t=>{
 const f=fixture();t.mock.method(global,'fetch',withTokenCount(async()=>new Response(JSON.stringify(f.first))));const state=await propose(f);
 await assert.rejects(f.llm.respond([],f.record,{state,decision:{id:'wrong-id',approved:true}}),/does not match/);
 const expired={...state,expiresAt:new Date(0).toISOString()};await assert.rejects(f.llm.respond([],f.record,{state:expired,decision:{id:state.pending.id,approved:true}}),/expired/);
 await assert.rejects(f.llm.respond([],f.record,{state:{...state,phase:'executing'},decision:{id:state.pending.id,approved:true}}),/already have executed/);
 assert.equal(f.calls,0);
});

test('provider failures after confirmed execution resume from persisted output without retraining',async t=>{
 const f=fixture();let requests=0;t.mock.method(global,'fetch',withTokenCount(async(_url,options)=>{requests++;if(requests===1)return new Response(JSON.stringify(f.first));if(requests===2)throw new Error('network');const input=JSON.parse(options.body).input;assert(input.some(item=>item.type==='reasoning'&&item.encrypted_content==='opaque-reasoning'));assert(input.some(item=>item.type==='function_call_output'&&item.output.includes('job-1')));return new Response(JSON.stringify(f.final));}));
 const state=await propose(f);await assert.rejects(f.llm.respond([],f.record,{state,decision:{id:state.pending.id,approved:true},saveState:f.saveState}),/connection failed/);assert.equal(f.calls,1);
 assert.equal(await f.llm.respond([],f.record,{state:f.states.at(-1),saveState:f.saveState}),'Job queued.');assert.equal(f.calls,1);
});

test('generic tool identities do not collide and include operator description plus actual schema',async()=>{
 const tool={name:'predict',description:'Actual discovered prediction',readOnly:true,inputSchema:{type:'object',properties:{value:{type:'number'}}}};
 const rows=['server-a','server-b'].map(id=>({id,name:'Same name',description:'Operator purpose',tools:[tool],allowed_tools:['predict'],enabled:true,agent_enabled:true,status:'connected'}));
 const service=new McpService({pool:{query:async()=>({rows})}},{read:async()=>({})});const available=await service.agentTools();assert.equal(available.length,2);assert.notEqual(available[0].name,available[1].name);assert(available[0].description.includes('Operator purpose'));assert.deepEqual(available[0].parameters,tool.inputSchema);
});
