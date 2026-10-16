require('reflect-metadata');
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs/promises');const os=require('node:os');const path=require('node:path');const {randomUUID}=require('node:crypto');
const location=require('../dist/config/environment');const {EnvironmentStore}=require('../dist/config/environment-store.service');
test('shared credential store serializes LLM/RAG writes, retains unrelated data and remains private',async()=>{
 const temp=await fs.mkdtemp(path.join(os.tmpdir(),'meta-harness-env-test-'));const originalPath=location.environmentFilePath;location.environmentFilePath=()=>path.join(temp,'.env');const id=randomUUID();const tokenName=`MCP_TOKEN_${id.replaceAll('-','').toUpperCase()}`;
 const before={OPENAI_API_KEY:process.env.OPENAI_API_KEY,LLM_MODEL:process.env.LLM_MODEL,[tokenName]:process.env[tokenName]};
 try{
  await fs.writeFile(location.environmentFilePath(),'DB_PASSWORD="private-test-password"\nOPENAI_API_KEY="original-test-key"\nOTHER_SETTING_2="retained"\n',{mode:0o600});const store=new EnvironmentStore();
  const [name]=await Promise.all([store.saveMcpToken(id,'private-test-token'),store.update({LLM_MODEL:'unchanged-provider-model'},'original-test-key')]);assert.equal(name,tokenName);
  let values=await store.read();assert.equal(values.DB_PASSWORD,'private-test-password');assert.equal(values.OTHER_SETTING_2,'retained');assert.equal(values[tokenName],'private-test-token');assert.equal(values.LLM_MODEL,'unchanged-provider-model');
  await store.saveMcpToken(id,'replacement-test-token');values=await store.read();assert.equal(values[tokenName],'replacement-test-token');assert.equal((await fs.stat(location.environmentFilePath())).mode&0o777,0o600);
  await assert.rejects(store.update({OPENAI_API_KEY:'new-test-key'},'stale-test-key'),/key changed/);
  assert.throws(()=>store.saveMcpToken(id,'unsafe\nvalue'));
 }finally{location.environmentFilePath=originalPath;for(const[key,value]of Object.entries(before)){if(value===undefined)delete process.env[key];else process.env[key]=value;}await fs.rm(temp,{recursive:true});}
});
