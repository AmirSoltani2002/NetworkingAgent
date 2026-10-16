require('reflect-metadata');const test=require('node:test'),assert=require('node:assert/strict');const {Pool}=require('pg');const {randomUUID}=require('node:crypto');const fs=require('node:fs/promises');
const {TasksService}=require('../dist/tasks/tasks.service');const {IntegrationsController}=require('../dist/integrations/integrations.controller');
test('PostgreSQL integration receipt atomically creates one template-bound task under concurrent duplicate delivery',{skip:!process.env.CORE_TEST_DATABASE_URL},async()=>{
 const url=new URL(process.env.CORE_TEST_DATABASE_URL);assert(/_tests?$/.test(url.pathname));const pool=new Pool({connectionString:url.href});
 const db={pool,transaction:async fn=>{const c=await pool.connect();await c.query('BEGIN');try{const r=await fn(c);await c.query('COMMIT');return r;}catch(e){await c.query('ROLLBACK');throw e;}finally{c.release();}}};
 await pool.query(await fs.readFile(require('node:path').resolve(__dirname,'../../database/schema.sql'),'utf8'));
 const env={TASK_INTEGRATION_TOKEN:'test-token-for-isolated-integration-only',FACTORY_SERVER_ID:randomUUID(),FACTORY_RAG_SERVER_ID:randomUUID()};
 const tasks=new TasksService(db,{read:async()=>env},{grant:async(s,t)=>({serverId:s,tool:t,policyDigest:'operator-grant'})});const endpoint=new IntegrationsController(tasks,{read:async()=>env});
 const event={template:'factory-stop-demo',eventId:randomUUID(),variables:{machine_id:'ZSK-SIM-01',component:'gearbox',rag_device_id:randomUUID(),epoch:randomUUID()}};
 let taskId;
 try{
  await assert.rejects(endpoint.receive(event,'Bearer wrong'));
  const results=await Promise.all([endpoint.receive(event,'Bearer '+env.TASK_INTEGRATION_TOKEN),endpoint.receive(event,'Bearer '+env.TASK_INTEGRATION_TOKEN)]);taskId=results[0].taskId;
  assert.equal(taskId,results[1].taskId);assert.equal(results.filter(r=>r.duplicate).length,1);
  const t=await tasks.get(taskId);assert.equal(t.criteria.length,6);assert.equal(t.grants.length,3);assert.equal(t.source.integration,'factory-simulation');
  await assert.rejects(endpoint.receive({...event,variables:{...event.variables,machine_id:'different'}},'Bearer '+env.TASK_INTEGRATION_TOKEN));
  await assert.rejects(endpoint.receive({...event,grants:[]},'Bearer '+env.TASK_INTEGRATION_TOKEN));
 }finally{if(taskId){await pool.query('DELETE FROM task_integration_receipts WHERE task_id=$1',[taskId]);const t=await tasks.get(taskId);await pool.query('DELETE FROM chats WHERE id=$1',[t.conversation_id]);}await pool.end();}
});
