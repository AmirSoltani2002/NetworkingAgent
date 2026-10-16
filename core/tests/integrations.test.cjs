const test=require('node:test');const assert=require('node:assert/strict');
const {authenticate,eventInput,expand}=require('../dist/integrations/integration-contract');
test('service auth rejects missing/incorrect token and never accepts a short configuration',()=>{
 const secret='a'.repeat(32);assert.throws(()=>authenticate(undefined,secret));assert.throws(()=>authenticate('Bearer '+'b'.repeat(32),secret));assert.throws(()=>authenticate('Bearer short','short'));authenticate('Bearer '+secret,secret);
});
test('integration receipt accepts only template ID, stable UUID and bounded variables',()=>{
 const value={template:'factory-stop-demo',eventId:'bb8eabde-50bc-4e20-8759-13836de4e248',variables:{machine_id:'ZSK-SIM-01'}};
 assert.deepEqual(eventInput(value),value);assert.throws(()=>eventInput({...value,grants:[]}));assert.throws(()=>eventInput({...value,eventId:'invalid'}));assert.throws(()=>eventInput({...value,variables:{data:'a'.repeat(16001)}}));
});
test('event variables cannot change operator-configured grants or environment references',()=>{
 const env={SERVER_ID:'fixed-operator-profile'};const variables={machine_id:'sim-machine',SERVER_ID:'attacker'};
 assert.deepEqual(expand([{serverId:'${SERVER_ID}',tool:'inspect_component'}],env,variables,false),[{serverId:'fixed-operator-profile',tool:'inspect_component'}]);
 assert.equal(expand('Investigate {{machine_id}}',env,variables),'Investigate sim-machine');assert.throws(()=>expand('${MISSING}',env,variables));
});
