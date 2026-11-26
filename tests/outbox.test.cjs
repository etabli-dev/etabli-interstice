const {test}=require('node:test');
const assert=require('node:assert/strict');
const Outbox=require('../app/static/outbox.js');
function storage(){const map=new Map();return {getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)};}
test('lost response then reload reuses exact intent and receipt',async()=>{
 const db=storage(), received=new Map(); let count=0, first=true;
 const send=async(path,method,body,headers)=>{const key=headers['Idempotency-Key'];if(!received.has(key)){count+=body.minutes;received.set(key,{progress:count});}if(first){first=false;throw new Error('connection lost');}return received.get(key);};
 const a=new Outbox(db,'client',send,()=> 'stable-receipt');
 await assert.rejects(a.perform('api/v1/tasks/task/progress',{session_id:'session',minutes:25}));
 const b=new Outbox(db,'client',send,()=> 'must-not-be-used');
 await assert.rejects(b.perform('api/v1/tasks/task/progress',{session_id:'another',minutes:25}));
 assert.equal((await b.retry()).progress,25);assert.equal(count,25);assert.equal(db.getItem('client'),null);
});
test('storage failure prevents network writes',async()=>{
 let writes=0;const db=storage();db.setItem=()=>{throw new Error('quota');};
 const a=new Outbox(db,'client',async()=>{writes++;},()=> 'id');
 await assert.rejects(a.perform('api/v1/tasks',{title:'x'}));assert.equal(writes,0);
});
test('expired authorization preserves ambiguous action',async()=>{
 const db=storage();const a=new Outbox(db,'client',async()=>{throw Object.assign(new Error('sign in'),{status:401});},()=> 'id');
 await assert.rejects(a.perform('api/v1/tasks',{title:'x'}));assert.ok(db.getItem('client'));
});
test('malformed persisted action stops writes',()=>{
 const db=storage();db.setItem('client','{"version":2}');assert.throws(()=>new Outbox(db,'client',()=>{},()=> 'id'));
});
