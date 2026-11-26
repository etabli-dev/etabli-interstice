/* Copyright 2026 R. Heller; SPDX-License-Identifier: AGPL-3.0-only */
const $ = id => document.getElementById(id);
let zone = 'Europe/Berlin', outbox;
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
  outbox=new MutationOutbox(localStorage,`interstice-outbox:${location.pathname}:${status.client_id}`,api,()=>crypto.randomUUID());
  $('pending-panel').hidden=!outbox.read();
  $('zone').textContent=`Planning in ${zone} · external calendar writes disabled`;
  $('model-status').textContent=status.model_configured ? `Configured model (availability unverified): ${status.model}` : 'No model configured';
  $('model-form').hidden=!status.model_configured || status.role!=='admin'; $('task-form').hidden=status.role!=='admin'; $('refresh').hidden=status.role!=='admin';
  $('workspace').hidden=false; $('login-panel').hidden=true; $('logout').hidden=false;
  const [tasks,plan]=await Promise.all([api('api/v1/tasks'),api('api/v1/schedule')]);
  $('calendar-warning').hidden=plan.calendar_inputs_ready;
  $('freshness').textContent=plan.sources.map(s=>`${s.id}: ${s.error || (s.stale ? 'stale: refresh required' : null) || (s.synced ? 'updated '+new Date(s.synced).toLocaleTimeString() : 'awaiting first refresh')}`).join(' · ') || 'No calendar sources configured';
  $('schedule').replaceChildren();
  const until=Date.now()+7*86400000;
  const items=[...plan.blocks,...plan.events.map(e=>({...e,event:true}))].filter(b=>new Date(b.end)>new Date() && new Date(b.start).getTime()<until).sort((a,b)=>new Date(a.start)-new Date(b.start));
  let last='', section;
  for(const b of items){const d=daykey(b.start);if(d!==last){section=node('section',undefined,'day');section.append(node('h3',new Date(b.start).toLocaleDateString([],{weekday:'long',day:'numeric',month:'short',timeZone:zone})));$('schedule').append(section);last=d;}const row=node('div',undefined,'slot'+(b.event?' busy':''));row.append(node('time',`${clock(b.start)}–${clock(b.end)}`),node('span',b.title));section.append(row);}
  if(!items.length)$('schedule').append(node('p','Add a task to see where it fits.','empty'));
  $('block-count').textContent=`${plan.blocks.length} planned blocks · 8-week horizon`;
  $('shortages').replaceChildren();$('shortage-panel').hidden=!plan.shortages.length;
  for(const s of plan.shortages)$('shortages').append(node('p',`${s.title}: ${s.minutes} min not scheduled. ${s.reason}`,'shortage'));
  $('tasks').replaceChildren();$('task-count').textContent=`${tasks.tasks.filter(t=>!t.completed).length} open`;
  for(const t of tasks.tasks){const row=node('article',undefined,'task'+(t.completed?' done':''));row.append(node('h3',t.title),node('p',`${t.progress} / ${t.minutes} min · ${t.completed?'completed':t.list}`));
    if(!t.completed && status.role==='admin'){
      const progress=node('button','Credit 25 focused minutes');progress.onclick=()=>run(progress,async()=>{await outbox.perform(`api/v1/tasks/${t.id}/progress`,{session_id:crypto.randomUUID(),minutes:25});await load();message('25 minutes recorded in the test workspace.');});
      const complete=node('button','Mark complete');complete.onclick=()=>run(complete,async()=>{if(!confirm(`Mark “${t.title}” complete?`))return;await outbox.perform(`api/v1/tasks/${t.id}/complete`,{}, {'If-Match':String(t.revision)});await load();});row.append(progress,complete);
    }$('tasks').append(row);
  }
}
$('login-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{await api('login','POST',{token:$('token').value});$('token').value='';message('');await load();});};
$('task-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{await outbox.perform('api/v1/tasks',{title:$('title').value,minutes:Number($('minutes').value),priority:Number($('priority').value),due:$('due').value?new Date($('due').value).toISOString():null,notes:$('notes').value,list:'Test work'});e.target.reset();await load();message('Task added. This plan stays inside the test workspace.');});};
$('retry-pending').onclick=e=>run(e.target,async()=>{await outbox.retry();await load();message('Pending action confirmed.');});
$('refresh').onclick=e=>run(e.target,async()=>{await api('api/v1/calendars/refresh','POST',{});await load();message('Calendar refresh finished. Check source status for any failures.');});
$('model-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{message('Preparing a draft…');const r=await api('api/v1/model/propose','POST',{text:$('prompt').value});$('title').value=r.proposal.title;$('minutes').value=r.proposal.minutes;$('priority').value=r.proposal.priority;$('notes').value=r.proposal.notes;$('due').value='';if(r.proposal.due){const d=new Date(r.proposal.due);const local=new Date(d.getTime()-d.getTimezoneOffset()*60000);$('due').value=local.toISOString().slice(0,16);}message('Draft ready. Review the details, then choose “Add to the plan”.');$('title').focus();});};
$('logout').onclick=e=>run(e.target,async()=>{await api('api/v1/logout','POST',{});location.reload();});
load().catch(()=>{$('login-panel').hidden=false;});
