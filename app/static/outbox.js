/* Copyright 2026 R. Heller; SPDX-License-Identifier: AGPL-3.0-only */
class MutationOutbox {
  constructor(storage, key, send, uuid) {
    this.storage=storage; this.key=key; this.send=send; this.uuid=uuid;
    this.pending=this.read();
  }
  read() {
    const raw=this.storage.getItem(this.key);
    if(raw===null)return null;
    const item=JSON.parse(raw);
    if(!item || item.version!==1 || typeof item.path!=='string' || !item.path.startsWith('api/v1/tasks') || typeof item.id!=='string')
      throw new Error('Pending work cannot be read. Keep browser storage and contact the administrator.');
    return item;
  }
  lock(fn) {
    if(typeof window==='undefined')return fn();
    if(!navigator.locks)throw new Error('This browser cannot safely coordinate writes. Use a current browser.');
    return navigator.locks.request(this.key,fn);
  }
  async perform(path, body, headers={}) {
    return this.lock(async()=>{
    if(this.read())throw new Error('Resolve the pending action before recording more work.');
    const item={version:1,path,body,headers,id:this.uuid()};
    // Persistence must succeed before the first network request.
    this.storage.setItem(this.key,JSON.stringify(item)); this.pending=item;
    return this.deliver();
    });
  }
  async retry() {return this.lock(()=>this.deliver());}
  async deliver() {
    const item=this.read();
    if(!item)throw new Error('No pending action.');
    try {
      const result=await this.send(item.path,'POST',item.body,{...item.headers,'Idempotency-Key':item.id});
      this.storage.removeItem(this.key); this.pending=null;
      return result;
    } catch(error) {
      // Definitive rejection means no write was accepted. Lost responses retain the exact intent.
      if(error.status>=400 && error.status<500 && ![401,403,408,409,429].includes(error.status)) {
        this.storage.removeItem(this.key); this.pending=null;
      }
      throw error;
    }
  }
}
if(typeof module!=='undefined')module.exports=MutationOutbox;
