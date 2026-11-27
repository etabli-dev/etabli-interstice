/* Copyright 2026 R. Heller; SPDX-License-Identifier: AGPL-3.0-only */
const $ = id => document.getElementById(id);
let zone = 'Europe/Berlin', outbox, currentTasks=[], currentRole='read';
const categories={discussion:'Discussion',writing:'Writing & review',research:'Research & analysis',software:'Software & systems',administration:'Administration & planning',security:'Security & accounts',learning:'Learning & teaching',practical:'Errands & practical work',other:'Other'};
const modes={'':'Not specified',meeting:'Meeting',phone:'Phone call',email:'Email',video:'Video call',message:'Message'};
function classificationForm(parent, task={}) {
  const inputs={};
  for(const [key,label,choices] of [['category','Category',categories],['person','Person (optional)',null],['communication_mode','Communication mode (optional)',modes],['tags','Topic tags · comma separated',null]]) {
    const wrapper=node('label',label), input=node(choices?'select':'input');
    if(choices)for(const [value,text] of Object.entries(choices)){const option=node('option',text);option.value=value;input.append(option);}
    else input.maxLength=key==='person'?200:1619;
    input.value=key==='tags'?(task.tags||[]).join(', '):(task[key]||(key==='category'?'other':''));
    wrapper.append(input);parent.append(wrapper);inputs[key]=input;
  }
  return ()=>({category:inputs.category.value,person:inputs.person.value,communication_mode:inputs.communication_mode.value,tags:inputs.tags.value.split(',').map(t=>t.trim()).filter(Boolean)});
}
const newClassification=classificationForm($('new-classification'));
for(const [value,label] of Object.entries(categories)){const option=node('option',label);option.value=value;$('category-filter').append(option);}
$('task-filter').oninput=()=>renderTasks();$('category-filter').onchange=()=>renderTasks();
async function api(path, method='GET', body, headers={}) {
  const response = await fetch(path, {method, headers:{'Content-Type':'application/json', ...headers}, body:body === undefined ? undefined : JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) {const error=new Error(typeof result.detail === 'string' ? result.detail : 'Please check the supplied values.'); error.status=response.status; throw error;}
  return result;
}
function node(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
function message(text) { $('message').textContent=text; }
async function run(button, fn) { button.disabled=true; try{await fn();}catch(e){message(e.message);}finally{button.disabled=false;if(outbox)$('pending-panel').hidden=!outbox.read();} }
const clock = date => new Date(date).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', timeZone:zone});
const daykey = date => new Intl.DateTimeFormat('en-CA',{timeZone:zone, year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(date));
async function load() {
  const status = await api('api/v1/status'); zone=status.time_zone;
  $('mode-badge').textContent=status.mode==='shadow'?'READ-ONLY SHADOW':'TEST WORKSPACE';
  outbox=new MutationOutbox(localStorage,`interstice-outbox:${location.pathname}:${status.client_id}`,api,()=>crypto.randomUUID());
  $('pending-panel').hidden=!outbox.read();
  $('zone').textContent=`Planning in ${zone} · external calendar writes disabled`;
  if(status.migration)$('zone').textContent+=` · Task copy from ${new Date(status.migration.captured_at).toLocaleString()}; source changes are not synced`;
  $('model-status').textContent=status.model_configured ? `Configured model (availability unverified): ${status.model}` : 'No model configured';
  $('model-form').hidden=!status.model_configured || status.role!=='admin'; $('task-form').hidden=status.role!=='admin'; $('refresh').hidden=status.role!=='admin';
  $('workspace').hidden=false; $('login-panel').hidden=true; $('logout').hidden=false;
  const tasks=await api('api/v1/tasks');currentTasks=tasks.tasks;currentRole=status.role;renderTasks();
  let plan;
  try {plan=await api('api/v1/schedule');} catch(e) {
    $('schedule').replaceChildren(node('p','Schedule unavailable. Your task list is still available.','shortage'));
    $('shortages').replaceChildren();$('shortage-panel').hidden=true;$('block-count').textContent='';
    $('calendar-warning').hidden=false;$('freshness').textContent='Schedule could not be refreshed.';throw e;
  }
  $('calendar-warning').hidden=plan.calendar_inputs_ready;
  $('freshness').textContent=plan.sources.map(s=>`${s.id}: ${s.error || (s.stale ? 'stale: refresh required' : null) || (s.synced ? 'updated '+new Date(s.synced).toLocaleTimeString() : 'awaiting first refresh')}`).join(' · ') || 'No calendar sources configured';
  $('schedule').replaceChildren();
  const until=Date.now()+7*86400000;
  const items=[...plan.blocks,...plan.events.map(e=>({...e,event:true}))].filter(b=>new Date(b.end)>new Date() && new Date(b.start).getTime()<until).sort((a,b)=>new Date(a.start)-new Date(b.start));
  let last='', section;
  for(const b of items){const d=daykey(b.start);if(d!==last){section=node('section',undefined,'day');section.append(node('h3',new Date(b.start).toLocaleDateString([],{weekday:'long',day:'numeric',month:'short',timeZone:zone})));$('schedule').append(section);last=d;}const row=node('div',undefined,'slot'+(b.event?' busy':''));row.append(node('time',`${clock(b.start)}–${clock(b.end)}`),node('span',b.title));section.append(row);}
  if(!items.length)$('schedule').append(node('p','Add a task to see where it fits.','empty'));
  $('block-count').textContent=`${plan.blocks.length} planned blocks · 8-week horizon`;
  $('shortages').replaceChildren();$('shortage-panel').hidden=!plan.shortages.length&&!(plan.late||[]).length;
  for(const s of plan.shortages)$('shortages').append(node('p',`${s.title}: ${s.minutes} min not scheduled. ${s.reason}`,'shortage'));
  for(const s of plan.late||[])$('shortages').append(node('p',`${s.title}: scheduled after its deadline (${new Date(s.due).toLocaleString()}).`,'shortage'));
}
function renderTasks(){
  const query=$('task-filter').value.trim().toLocaleLowerCase(), selected=$('category-filter').value;
  const tasks=currentTasks.filter(t=>(!selected||(t.category||'other')===selected)&&[t.title,t.list,categories[t.category||'other'],t.person,modes[t.communication_mode],...(t.tags||[])].join(' ').toLocaleLowerCase().includes(query));
  $('tasks').replaceChildren();$('task-count').textContent=`${tasks.length} shown · ${currentTasks.filter(t=>!t.completed).length} open`;
  for(const t of tasks){
    const row=node('article',undefined,'task'+(t.completed?' done':''));
    row.append(node('h3',t.title),node('p',`${t.progress} / ${t.minutes} min · ${t.completed?'completed · ':''}${t.list}`),node('p',[categories[t.category||'other'],t.person,t.communication_mode?modes[t.communication_mode]:'',...(t.tags||[]).map(tag=>'#'+tag)].filter(Boolean).join(' · ')));
    if(currentRole==='admin'){
      const details=node('details'),summary=node('summary','Edit list & details'),form=node('form');details.append(summary,form);
      const label=node('label','List · work area'),list=node('input');list.value=t.list;list.required=true;list.maxLength=100;list.setAttribute('list','work-areas');label.append(list);form.append(label);
      const values=classificationForm(form,t),save=node('button','Save details');save.type='submit';form.append(save);
      form.onsubmit=e=>{e.preventDefault();run(save,async()=>{await outbox.perform(`api/v1/tasks/${encodeURIComponent(t.id)}`,{list:list.value,...values()},{'If-Match':String(t.revision)},'PATCH');await load();});};row.append(details);
    }
    if(!t.completed && currentRole==='admin'){
      const progress=node('button','Credit 25 focused minutes');progress.onclick=()=>run(progress,async()=>{await outbox.perform(`api/v1/tasks/${encodeURIComponent(t.id)}/progress`,{session_id:crypto.randomUUID(),minutes:25});await load();});
      const complete=node('button','Mark complete');complete.onclick=()=>run(complete,async()=>{if(!confirm(`Mark “${t.title}” complete?`))return;await outbox.perform(`api/v1/tasks/${encodeURIComponent(t.id)}/complete`,{}, {'If-Match':String(t.revision)});await load();});row.append(progress,complete);
    }$('tasks').append(row);
  }
  if(!tasks.length)$('tasks').append(node('p','No tasks match these filters.','empty'));
}
$('login-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{await api('login','POST',{token:$('token').value});$('token').value='';message('');await load();});};
$('task-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{await outbox.perform('api/v1/tasks',{title:$('title').value,minutes:Number($('minutes').value),priority:Number($('priority').value),due:$('due').value?new Date($('due').value).toISOString():null,notes:$('notes').value,list:$('task-list').value,...newClassification()});e.target.reset();await load();message('Task added. This plan stays inside the test workspace.');});};
$('retry-pending').onclick=e=>run(e.target,async()=>{await outbox.retry();await load();message('Pending action confirmed.');});
$('reload-plan').onclick=e=>run(e.target,load);
$('refresh').onclick=e=>run(e.target,async()=>{await api('api/v1/calendars/refresh','POST',{});await load();message('Calendar refresh finished. Check source status for any failures.');});
$('model-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{message('Preparing a draft…');const r=await api('api/v1/model/propose','POST',{text:$('prompt').value});$('title').value=r.proposal.title;$('minutes').value=r.proposal.minutes;$('priority').value=r.proposal.priority;$('notes').value=r.proposal.notes;$('due').value='';if(r.proposal.due){const d=new Date(r.proposal.due);const local=new Date(d.getTime()-d.getTimezoneOffset()*60000);$('due').value=local.toISOString().slice(0,16);}message('Draft ready. Review the details, then choose “Add to the plan”.');$('title').focus();});};
$('logout').onclick=e=>run(e.target,async()=>{await api('api/v1/logout','POST',{});location.reload();});
load().catch(e=>{if(e.status===401){$('login-panel').hidden=false;$('workspace').hidden=true;}else message(e.message);});
