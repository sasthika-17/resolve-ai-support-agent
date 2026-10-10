'use strict';
const $ = selector => document.querySelector(selector);
const state = {tickets: [], customers: [], selected: null, ticket: null, run: null, health: null, loadToken: 0, poll: null};
const labels = {open:'Open', resolved:'Resolved', escalated:'Escalated', running:'Working', waiting_review:'Needs review', resuming:'Saving', approved:'Approved', rejected:'Rejected', failed:'Failed'};

function node(tag, attributes = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key,value] of Object.entries(attributes)) {
    if (key === 'class') element.className = value;
    else if (key.startsWith('on')) element.addEventListener(key.slice(2), value);
    else element.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return element;
}
function badge(text, color='') { return node('span', {class:`badge ${color}`}, text); }
function colorFor(status) { return ['approved','resolved'].includes(status) ? 'green' : ['waiting_review','escalated'].includes(status) ? 'amber' : status === 'failed' ? 'red' : 'violet'; }
function button(text, handler, style='') { return node('button', {class:`button ${style}`, type:'button', onclick:handler}, text); }
let noticeTimer;
function notify(text) { $('#notice').textContent = text; $('#notice').hidden = false; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { $('#notice').hidden = true; }, 9000); }
async function api(path, options={}) {
  const headers = {'X-Resolve-Request':'1', ...(options.body instanceof FormData ? {} : {'Content-Type':'application/json'}), ...options.headers};
  const response = await fetch('/api'+path, {...options, headers});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || `Request failed (${response.status})`);
  return data;
}
function post(path, body={}) { return api(path, {method:'POST', body:JSON.stringify(body)}); }
function busy(target, text) { const previous=target.textContent; target.disabled=true; target.textContent=text; return () => {target.disabled=false; target.textContent=previous;}; }
function showSource(source, quote=null) {
  $('#source-title').textContent=source.title;
  $('#source-content').replaceChildren(quote ? node('div', {}, node('strong', {}, 'Quoted in the draft'), node('p', {}, quote), node('hr')) : nullNode(), node('strong', {}, source.source_id ? 'Full retrieved passage' : 'Source document'), node('p', {}, source.text), node('p', {class:'muted small'}, `${source.method || 'Source document'} · ${source.source_id || source.id || ''}`));
  $('#source-dialog').showModal();
}
function nullNode() {return document.createTextNode('');}

function renderTickets() {
  const filter = $('#ticket-search').value.trim().toLowerCase();
  const visible=state.tickets.filter(t => `${t.subject} ${t.body}`.toLowerCase().includes(filter));
  $('#tickets').replaceChildren(...visible.map(ticket => {
    const customer=state.customers.find(c=>c.id===ticket.customer_id);
    return node('button', {class:`ticket-card ${state.selected===ticket.id?'active':''}`, 'aria-pressed':String(state.selected===ticket.id), onclick:()=>loadTicket(ticket.id)},
      node('div', {class:'ticket-meta'}, node('span', {}, customer?.name || 'Customer'), node('span', {}, 'OrbitDesk')),
      node('strong', {}, ticket.subject), node('p', {}, ticket.body), badge(labels[ticket.status], colorFor(ticket.status)));
  }));
  if (!visible.length) $('#tickets').append(node('p', {class:'loading-placeholder'}, 'No matching conversations.'));
  $('#ticket-count').textContent=String(state.tickets.length);
  $('#open-count').textContent=String(state.tickets.filter(t=>t.status==='open').length);
}
async function refreshHealth() {
  state.health=await api('/health');
  $('#connection').textContent=state.health.configured ? 'OpenAI configured' : 'Key setup needed';
  $('#connection').classList.toggle('muted-warning', !state.health.configured);
}
async function refreshTickets() {state.tickets=await api('/tickets');renderTickets();}
async function loadTicket(id, runId=null) {
  clearTimeout(state.poll); const token=++state.loadToken; state.selected=id; localStorage.setItem('resolve-ticket', id); renderTickets();
  try {
    const ticket=await api('/tickets/'+encodeURIComponent(id));
    const currentRun=runId || ticket.runs[0];
    const run=currentRun ? await api('/runs/'+encodeURIComponent(currentRun)) : null;
    if (token!==state.loadToken) return;
    state.ticket=ticket;state.run=run;renderConversation();renderEvidence();
    if (run && ['running','resuming'].includes(run.status)) pollRun(run.id, token);
  } catch(error) { notify(error.message); }
}
function pollRun(id, token) {
  state.poll=setTimeout(async()=> {
    try {
      const run=await api('/runs/'+encodeURIComponent(id));
      if (token!==state.loadToken) return;
      const changed=run.status!==state.run?.status || run.events.length!==state.run?.events.length;
      state.run=run;
      if(changed){renderConversation();renderEvidence();}
      if(['running','resuming'].includes(run.status)) pollRun(id, token);
      else {await refreshHealth();await refreshTickets();}
    } catch(error) { notify(error.message); }
  },1500);
}
async function generate(event) {
  const target=event.currentTarget, restore=busy(target,'Starting…');
  try {
    const feedback=$('#draft-feedback')?.value || '';
    const run=await post(`/tickets/${encodeURIComponent(state.ticket.id)}/runs`, {feedback,retrieval_mode:'hybrid'});
    await loadTicket(state.ticket.id,run.id);
  } catch(error) { notify(error.message); } finally {restore();}
}
async function review(approve, event) {
  const restore=busy(event.currentTarget, approve?'Recording…':'Rejecting…');
  const runId=state.run.id, ticketId=state.ticket.id;
  try {
    await post(`/runs/${encodeURIComponent(runId)}/review`, {approve,note:$('#review-note')?.value || ''});
    notify(approve?'Resolution approved and saved locally.':'Draft rejected. You can generate a new draft with feedback.');
    await refreshTickets();await loadTicket(ticketId,runId);
  } catch(error) {notify(error.message);await loadTicket(ticketId,runId);} finally {restore();}
}
function renderConversation() {
  const ticket=state.ticket,run=state.run;
  if(!ticket) return;
  const customer=ticket.customer;
  const container=$('#conversation');
  container.replaceChildren(node('div', {class:'conversation-top'}, node('span', {class:'case-id'}, `CONVERSATION / ${ticket.id.slice(-8).toUpperCase()}`),badge(labels[run?.status||ticket.status],colorFor(run?.status||ticket.status))),
    node('h2',{class:'conversation-title'},ticket.subject),node('div',{class:'person-line'},node('span',{class:'person-avatar'},customer.name.split(' ').map(n=>n[0]).join('')),node('div',{},node('strong',{},customer.name),node('small',{},customer.company+' · '+customer.plan))),
    node('div',{class:'ticket-message'},ticket.body),node('div',{class:'agent-divider'},'RESOLVE ASSISTANT'));
  if(run && ['running','resuming'].includes(run.status)) {
    container.append(node('div',{class:'run-progress'},node('span',{class:'spinner'}),run.status==='resuming'?'Recording your approved resolution…':'Finding evidence and preparing a draft…'),node('p',{class:'muted small'},'You can leave this conversation open while the agent works. Its steps appear in the trace.'));
  } else {
    if(run?.error) container.append(node('div',{class:'error-card',role:'alert'},run.error));
    if(run?.draft) {
      const draft=run.draft;
      const chips=draft.citations.map((citation,index)=>{
        const source=run.sources.find(s=>s.source_id===citation.source_id);
        return source ? node('button',{class:'citation-chip',onclick:()=>showSource(source,citation.quote)},`${index+1} · ${source.title} ↗`) : nullNode();
      });
      container.append(node('div',{class:'draft-card'},node('div',{class:'draft-title'},node('strong',{},'✳  Suggested reply'),badge(draft.disposition==='escalated'?'Specialist review':'Documented guidance',draft.disposition==='escalated'?'amber':'violet')),node('div',{class:'draft-body'},draft.reply),node('div',{class:'citation-chips'},chips)));
      if(run.status==='waiting_review') {
        container.append(node('div',{class:'review-area'},node('label',{},'Review note (optional)',node('textarea',{id:'review-note',maxlength:'1000',placeholder:'What should change, or why are you approving this?'})),node('div',{class:'review-actions'},button('✓ Approve & save',event=>review(true,event),'success'),button('Reject draft',event=>review(false,event)))),node('p',{class:'muted small'},'Review the wording and sources. Approval records this exact draft locally.'));
      } else if(run.status==='approved') {
        container.append(node('p',{class:'result-note'},'✓ Human-approved resolution saved. No customer message was sent.'));
      } else if(run.status==='rejected') {
        container.append(node('p',{class:'muted small'},'This draft was rejected. '+(run.review_note || '')));
      }
    }
    if(ticket.status==='open' && (!run || ['failed','rejected'].includes(run.status))) {
      const feedback=run ? node('label',{},'Guide the next draft',node('textarea',{id:'draft-feedback',maxlength:'1500',rows:'3',placeholder:'For example: be more concise and explain the escalation.'},run.review_note || '')) : nullNode();
      container.append(feedback,node('div',{class:'draft-empty'},node('div',{class:'spark'},'✳'),node('h3',{},run?'Take another pass':'A useful answer starts with evidence.'),node('p',{},'The agent checks the customer, searches your knowledge, and brings you a draft to review.'),button(run?'Generate a new draft ↗':'Generate resolution ↗',generate,'primary'),node('small',{},'Uses OpenAI for generation and embeddings. Ticket text, account context, and relevant policies are sent to the API.')));
    }
  }
  if(ticket.runs.length>1){
    const select=node('select',{'aria-label':'View previous run',onchange:event=>loadTicket(ticket.id,event.target.value)},ticket.runs.map((id,index)=>node('option',{value:id},`${index===0?'Latest run':'Previous run'} · ${id.slice(0,8)}`)));
    select.value=run?.id||ticket.runs[0];container.append(node('div',{class:'prior-runs'},node('p',{class:'muted'},'RUN HISTORY'),select));
  }
}
function kv(label,value){return node('div',{class:'kv'},node('span',{},label),node('span',{},value));}
function renderEvidence(){
  const ticket=state.ticket,run=state.run;if(!ticket)return;
  const customer=ticket.customer;
  const customerSection=node('section',{class:'evidence-section'},node('h3',{},'CUSTOMER CONTEXT'),kv('Organization',customer.company),kv('Plan',customer.plan),kv('Role',customer.role),kv('Identity','Not verified'));
  const sourcesSection=node('section',{class:'evidence-section'},node('h3',{},'SUPPORTING EVIDENCE'));
  if(run?.draft) sourcesSection.append(node('p',{class:'evidence-summary'},run.draft.summary));
  if(run?.draft?.escalation_reason) sourcesSection.append(node('p',{class:'evidence-summary'},'Escalation: '+run.draft.escalation_reason));
  const citedIds=run?.draft?.citations.map(c=>c.source_id)||[];
  const passages=run?.sources?.filter(s=>!run.draft||citedIds.includes(s.source_id))||[];
  for(const source of passages)sourcesSection.append(node('button',{class:'source-card',onclick:()=>showSource(source)},node('strong',{},'▤ '+source.title),node('small',{},`${source.method.toUpperCase()} · passage ${source.source_id.slice(0,6)} ↗`)));
  if(!passages.length)sourcesSection.append(node('p',{class:'evidence-summary'},run?.draft?'No supporting policy was cited. Review the escalation carefully.':'Retrieved passages and exact quotes will appear here.'));
  const trace=node('section',{class:'evidence-section'},node('div',{class:'trace-title'},node('h3',{},'EXECUTION TRACE'),badge(run ? String(run.events.length)+' steps':'Ready')));
  const names={started:'Run started',index:'Knowledge index',customer_lookup:'Customer lookup',search:'Knowledge search',review_required:'Human review',approved:'Resolution recorded',rejected:'Draft rejected',error:'Run stopped'};
  trace.append(node('ol',{class:'timeline'},run ? run.events.map(event=>node('li',{},node('strong',{},names[event.kind]||event.kind),event.detail)) : [node('li',{},node('strong',{},'Read the conversation'),'Understand the request.'),node('li',{},node('strong',{},'Find supporting context'),'Retrieve policies and account facts.'),node('li',{},node('strong',{},'Pause for your approval'),'Record only the draft you approve.') ]));
  if(run?.usage?.input_tokens) trace.append(kv('Generation tokens',(run.usage.input_tokens+run.usage.output_tokens).toLocaleString()),kv('Elapsed',`${(run.elapsed_ms/1000).toFixed(1)}s`));
  if(run)trace.append(node('a',{class:'download-link',href:`/api/runs/${encodeURIComponent(run.id)}/export`,download:''},'↓ Download run evidence'));
  $('#evidence').replaceChildren(customerSection,sourcesSection,trace);
}
async function loadDocuments(){
  try{
    const docs=await api('/documents');
    $('#documents').replaceChildren(...docs.map(doc=>node('article',{class:'document-card'},node('span',{class:'document-icon'},'▤'),node('h2',{},doc.title),node('p',{},doc.text.replace(/^#.*\n/,'')),node('div',{class:'document-foot'},badge(doc.indexed_model===state.health?.embedding_model?`${doc.chunks} indexed passages`:'Pending index',doc.indexed_model===state.health?.embedding_model?'green':'amber'),button('Read ↗',()=>showSource(doc))))));
  }catch(error){notify(error.message);}
}
async function loadEvaluations(){
  const container=$('#evaluation-summary');container.replaceChildren(node('div',{class:'panel-heading'},node('h2',{},'Behavior evaluation'),badge('Measured, not assumed','violet')),node('p',{},'Checks source validity, expected escalation, tool use, and the human-review boundary.'));
  try{
    const data=await api('/evaluations');
    if(!data.available){container.append(node('div',{class:'empty-eval'},node('h3',{},'No live report yet'),node('p',{},'The repository includes an opt-in evaluation suite. Its results will appear here after a run, including provider errors. A configured key alone does not verify the model.')));return;}
    const report=data.report;
    container.append(node('p',{class:'small muted'},`Last run: ${new Date(report.created_at).toLocaleString()} · ${report.model}`));
    for(const result of report.cases)container.append(node('div',{class:'evaluation-row'},node('span',{},result.name),badge((result.status || (result.passed?'pass':result.error?'error':'fail')).toUpperCase(),result.passed?'green':result.status==='skipped'?'amber':'red')));
    container.append(node('p',{class:'muted small'},`${report.passed}/${report.graded ?? report.cases.length} graded cases passed · ${report.errors ?? 0} provider/run errors · ${report.skipped ?? 0} skipped. This is a small synthetic test set, not a production accuracy estimate.`));
  }catch(error){notify(error.message);}
}
function switchView(name){
  for(const view of document.querySelectorAll('.view'))view.hidden=view.id!==`view-${name}`;
  for(const item of document.querySelectorAll('.nav-item'))item.classList.toggle('active',item.dataset.view===name);
  $('#page-label').textContent={inbox:'Support inbox',knowledge:'Knowledge base',quality:'Quality lab'}[name];
  if(name==='knowledge')loadDocuments();if(name==='quality')loadEvaluations();
}
for(const item of document.querySelectorAll('[data-view]'))item.addEventListener('click',()=>switchView(item.dataset.view));
for(const item of document.querySelectorAll('[data-close]'))item.addEventListener('click',()=>document.getElementById(item.dataset.close).close());
$('#ticket-search').addEventListener('input',renderTickets);
$('#new-ticket').addEventListener('click',()=>$('#ticket-dialog').showModal());
$('#add-document').addEventListener('click',()=>$('#document-dialog').showModal());
$('#ticket-form').addEventListener('submit',async event=>{event.preventDefault();const restore=busy(event.submitter,'Saving…');try{const ticket=await post('/tickets',Object.fromEntries(new FormData(event.target)));$('#ticket-dialog').close();event.target.reset();await refreshTickets();await loadTicket(ticket.id);}catch(error){notify(error.message);}finally{restore();}});
$('#document-form').addEventListener('submit',async event=>{event.preventDefault();const restore=busy(event.submitter,'Saving…');try{await post('/documents',Object.fromEntries(new FormData(event.target)));$('#document-dialog').close();event.target.reset();notify('Document saved. Index it to make it available to the agent.');await loadDocuments();await refreshHealth();}catch(error){notify(error.message);}finally{restore();}});
$('#document-file').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{const form=new FormData();form.append('file',file);await api('/documents/upload',{method:'POST',body:form});$('#document-dialog').close();notify('Document imported. Index it before retrieval.');await loadDocuments();}catch(error){notify(error.message);}finally{event.target.value='';}});
$('#index-documents').addEventListener('click',async event=>{const restore=busy(event.currentTarget,'Embedding documents…');try{const result=await post('/knowledge/index');notify(`Knowledge ready · ${result.chunks_added} new passages embedded.`);await refreshHealth();await loadDocuments();}catch(error){notify(error.message);}finally{restore();}});
$('#search-form').addEventListener('submit',async event=>{event.preventDefault();const restore=busy(event.submitter,'Retrieving…');try{const result=await post('/knowledge/search',Object.fromEntries(new FormData(event.target)));$('#search-results').replaceChildren(...result.sources.map(source=>node('article',{class:'search-result'},node('h3',{},`${source.rank}. ${source.title}`),badge(source.method,'violet'),node('p',{},source.text),node('span',{class:'muted small'},source.similarity===null?'Keyword match':`Cosine similarity ${source.similarity} · not a confidence score`))));if(!result.sources.length)$('#search-results').append(node('p',{},'No passages matched.'));}catch(error){notify(error.message);}finally{restore();}});
async function init(){try{await refreshHealth();state.customers=await api('/customers');$('#customer-select').replaceChildren(...state.customers.map(c=>node('option',{value:c.id},`${c.name} · ${c.company} (${c.plan})`)));await refreshTickets();const saved=localStorage.getItem('resolve-ticket');const first=state.tickets.find(t=>t.id===saved)||state.tickets.find(t=>t.id==='ticket_export')||state.tickets[0];if(first)await loadTicket(first.id);}catch(error){$('#connection').textContent='Connection unavailable';notify(error.message);}}
init();
