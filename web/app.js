const $ = (id) => document.getElementById(id);
const qsa = (s) => [...document.querySelectorAll(s)];
const pretty = (x) => JSON.stringify(x ?? null, null, 2);
const terminal = new Set(['COMPLETED', 'FAILED', 'CANCELLED']);

const defaultProfiles = [
  {id:'local-dell', name:'Local Dell', backend_url:'http://localhost:8000', description:'Fully local Dell backend', auth_method:'none', model_endpoint_override:'', tls_policy:'allow_http', auto_connect:true},
  {id:'runpod', name:'RunPod Development', backend_url:'', description:'Remote RunPod GPU backend', auth_method:'bearer', model_endpoint_override:'', tls_policy:'require_https', auto_connect:false},
  {id:'home-ai-server', name:'Home AI Server', backend_url:'', description:'Future home AI workstation', auth_method:'bearer', model_endpoint_override:'', tls_policy:'require_https', auto_connect:false},
  {id:'custom', name:'Custom endpoint', backend_url:'', description:'User-defined RCA backend', auth_method:'bearer', model_endpoint_override:'', tls_policy:'auto', auto_connect:false},
];

const state = {
  profiles: loadProfiles(), profile: null, config: null, capabilities: null, system: null,
  activeRunId: null, pollTimer: null, selectedStageId: null, selectedCaseId: null,
  expandedPaths: new Set(), scrollPositions: {},
  modelCatalogs: {primary: [], small: []}, lastRun: null,
};

function loadProfiles(){
  try { const x=JSON.parse(localStorage.getItem('rca.backendProfiles')||'null'); if(Array.isArray(x)&&x.length)return x; } catch {}
  const p=structuredClone(defaultProfiles);
  if(!['localhost','127.0.0.1',''].includes(location.hostname) && location.origin.startsWith('http')) p.find(x=>x.id==='runpod').backend_url=location.origin;
  return p;
}
function saveProfiles(){ localStorage.setItem('rca.backendProfiles', JSON.stringify(state.profiles)); }
function tokenKey(){ return `rca.backendToken.${state.profile?.id||'default'}`; }
function toast(msg,bad=false){const t=$('toast');t.textContent=msg;t.style.borderColor=bad?'var(--bad)':'var(--border)';t.classList.add('show');setTimeout(()=>t.classList.remove('show'),3200);}
function normalizeBase(url){return (url||'').trim().replace(/\/+$/,'');}
function apiBase(){return normalizeBase(state.profile?.backend_url||$('backendUrl').value);}
function authHeaders(extra={}){const h={...extra};const token=$('backendToken').value.trim();if(token)h.Authorization=`Bearer ${token}`;return h;}
async function api(path,opts={}){
  const base=apiBase(); if(!base) throw new Error('Backend URL is empty');
  const headers=authHeaders(opts.headers||{}); if(opts.body&&!(opts.body instanceof FormData)&&!headers['Content-Type'])headers['Content-Type']='application/json';
  const res=await fetch(`${base}/api/v1${path}`,{...opts,headers});
  if(!res.ok){let detail='';try{detail=JSON.stringify((await res.json()).detail)}catch{detail=await res.text()}throw new Error(`${res.status} ${res.statusText}: ${detail}`);}
  const ct=res.headers.get('content-type')||'';return ct.includes('application/json')?res.json():res;
}
function escapeHtml(x){return String(x).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function labelize(x){return String(x).replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());}
function safeJson(text){if(typeof text!=='string'||!text.trim())return null;try{return JSON.parse(text)}catch{return null;}}
function viewKey(suffix=''){return `${state.profile?.id||'default'}|${state.activeRunId||''}|${state.selectedCaseId||''}|${state.selectedStageId||''}${suffix?`|${suffix}`:''}`;}
function persistRunView(){if(!state.activeRunId)return;localStorage.setItem(`rca.runView.${state.profile?.id||'default'}.${state.activeRunId}`,JSON.stringify({case_id:state.selectedCaseId,stage_id:state.selectedStageId}));}
function restoreRunView(id){try{const x=JSON.parse(localStorage.getItem(`rca.runView.${state.profile?.id||'default'}.${id}`)||'null');if(x){state.selectedCaseId=x.case_id||null;state.selectedStageId=x.stage_id||null;}}catch{}}
function captureStructuredState(container){const scope=viewKey(container.id);container.querySelectorAll('details[data-tree-path]').forEach(d=>{const k=`${scope}|${d.dataset.treePath}`;if(d.open)state.expandedPaths.add(k);else state.expandedPaths.delete(k)});state.scrollPositions[scope]=container.scrollTop||0;}
function bindDetailState(det,container,path,defaultOpen=false){det.dataset.treePath=path;const k=`${viewKey(container.id)}|${path}`;det.open=state.expandedPaths.has(k)||(!state.expandedPaths.has(k)&&defaultOpen);det.addEventListener('toggle',()=>{if(det.open)state.expandedPaths.add(k);else state.expandedPaths.delete(k);});}

function initProfiles(){
  const sel=$('profileSelect');sel.innerHTML='';state.profiles.forEach(p=>{const o=document.createElement('option');o.value=p.id;o.textContent=p.name;sel.append(o)});
  const saved=localStorage.getItem('rca.selectedProfile')||state.profiles.find(p=>p.auto_connect)?.id||'local-dell';sel.value=state.profiles.some(p=>p.id===saved)?saved:state.profiles[0].id;selectProfile(sel.value,false);
}
function selectProfile(id,connect=true){
  state.profile=state.profiles.find(p=>p.id===id)||state.profiles[0];localStorage.setItem('rca.selectedProfile',state.profile.id);
  $('backendUrl').value=state.profile.backend_url||'';$('backendToken').value=sessionStorage.getItem(tokenKey())||'';$('profileDescription').value=state.profile.description||'';$('profileAuth').value=state.profile.auth_method||'none';$('profileModelOverride').value=state.profile.model_endpoint_override||'';$('profileTls').value=state.profile.tls_policy||'auto';$('profileAutoConnect').checked=!!state.profile.auto_connect;$('profileName').textContent=state.profile.name;
  state.activeRunId=localStorage.getItem(`rca.activeRun.${state.profile.id}`)||null;if(connect&&state.profile.backend_url)connectBackend().catch(()=>{});
}
function saveCurrentProfile(){
  const p=state.profile;p.backend_url=normalizeBase($('backendUrl').value);p.description=$('profileDescription').value.trim();p.auth_method=$('profileAuth').value;p.model_endpoint_override=$('profileModelOverride').value.trim();p.tls_policy=$('profileTls').value;p.auto_connect=$('profileAutoConnect').checked;
  if(p.tls_policy==='require_https'&&p.backend_url&&!p.backend_url.startsWith('https://'))return toast('This profile requires HTTPS.',true);
  sessionStorage.setItem(tokenKey(),$('backendToken').value.trim());saveProfiles();toast('Backend profile saved.');
}
async function connectBackend(preserveEdits=false){
  const draft=(preserveEdits&&state.config)?collectConfig():null;saveCurrentProfile();setConnection(false,'CONNECTING');
  const [health,system,caps,cfg]=await Promise.all([api('/health'),api('/system'),api('/capabilities'),api('/config')]);state.system=system;state.capabilities=caps;state.config=draft||cfg;setConnection(true,'CONNECTED');
  $('backendVersion').textContent=`App v${health.backend_version} · Core v${health.core_version||'?'} · ${health.profile_name}`;$('hardwareSummary').textContent=hardwareLabel(system);$('primarySummary').textContent=cfg.primary_model?.model||'not configured';$('smallSummary').textContent=cfg.small_model?.model||'not configured';$('systemView').textContent=pretty({health,system});$('capabilitiesRaw').textContent=pretty(caps);
  renderCapabilities();if(!draft)fillConfig();renderEnvironmentOverrides();const runs=await refreshHistory();await reconcileActiveRuns(runs);toast('Backend connected.');
}
async function reconcileActiveRuns(runs){
  const active=(runs||[]).filter(r=>['QUEUED','INITIALIZING','RUNNING','CANCELLING'].includes(r.status));
  const bar=$('activeRunBar'),sel=$('activeRunSelect');sel.innerHTML='';
  active.forEach(r=>{const o=document.createElement('option');o.value=r.run_id;o.textContent=`${r.run_id} · ${r.status}${r.current_stage?` · ${r.current_stage}`:''}`;sel.append(o)});bar.hidden=active.length<2;
  const remembered=state.activeRunId&&active.find(r=>r.run_id===state.activeRunId);
  const target=remembered||(active.length===1?active[0]:null);
  if(target){await loadRun(target.run_id,true);if(sel.options.length)sel.value=target.run_id;}
  else if(active.length>1){toast(`${active.length} active runs found. Select one to reconnect.`);}
  else if(state.activeRunId){try{await loadRun(state.activeRunId,true)}catch{state.activeRunId=null;}}
}
function setConnection(ok,label){const b=$('connectionBadge');b.textContent=label;b.className=`badge ${ok?'online':'offline'}`;}
function hardwareLabel(s){const g=s?.gpus?.map(x=>x.name).join(' + ');return g||`${s?.cpu_count_logical||'?'} CPU threads · ${s?.ram_total_gb||'?'} GB RAM`;}
function renderCapabilities(){
  const caps=state.capabilities||{},cards=$('capabilityCards');cards.innerHTML='';
  Object.entries(caps.features||{}).forEach(([k,v])=>{const d=document.createElement('div');d.className=`cap-card ${v?'available':'unavailable'}`;d.innerHTML=`<span>${escapeHtml(k.replaceAll('_',' '))}</span><strong>${v?'SUPPORTED':'NOT SUPPORTED'}</strong>`;cards.append(d)});
  Object.entries(caps.models||{}).forEach(([k,v])=>{const d=document.createElement('div');d.className=`cap-card ${v?'available':'unavailable'}`;d.innerHTML=`<span>${escapeHtml(k)} model</span><strong>${v?'AVAILABLE':'UNAVAILABLE'}</strong>`;cards.append(d)});
  qsa('[data-cap]').forEach(el=>{const cap=el.dataset.cap,supported=!!caps.features?.[cap];el.dataset.unsupported=String(!supported);el.querySelectorAll('input,select').forEach(i=>i.disabled=!supported)});$('capabilityHint').textContent=`${caps.deployment||''} · ${caps.gpu_count||0} GPU(s)`;
}
function renderEnvironmentOverrides(){
  const overrides=state.capabilities?.environment_overrides||{},box=$('modelOverrideWarning');const rows=Object.entries(overrides);
  if(!rows.length){box.textContent='';box.hidden=true;box.classList.remove('show');return;}box.hidden=false;box.classList.add('show');
  box.innerHTML=`<strong>Active deployment environment overrides</strong><br>${rows.map(([field,x])=>`${escapeHtml(field)} ← ${escapeHtml(x.env)} = ${escapeHtml(x.value)}`).join('<br>')}<br><span>Saved values may differ from effective backend defaults. v1.8.9 run-specific configuration overrides remain authoritative for the run you start.</span>`;
}

const configMap={
  cfgPrimaryTemperature:['primary_model','temperature'],cfgPrimaryReasoning:['primary_model','reasoning_effort'],cfgPrimaryTokens:['primary_model','max_tokens'],cfgTimeout:['primary_model','timeout_seconds'],
  cfgFastIntake:['rca','fast_intake_enabled'],cfgFastIntakeMode:['rca','fast_intake_mode'],cfgSemanticPrep:['rca','semantic_preparation_enabled'],cfgSemanticArb:['rca','semantic_arbitration_enabled'],cfgRcaSynthesis:['rca','rca_synthesis_enabled'],cfgHypReview:['rca','fast_hypothesis_review_enabled'],cfgFinalReview:['rca','fast_final_review_enabled'],
  cfgAvailabilityTokens:['rca','fast_source_availability_max_tokens'],cfgContentTokens:['rca','fast_content_classification_max_tokens'],cfgSemanticTokens:['rca','semantic_preparation_max_tokens'],cfgHypTokens:['rca','fast_hypothesis_review_max_tokens'],cfgReviewTokens:['rca','fast_final_review_max_tokens'],cfgReviewReasoning:['rca','fast_final_review_reasoning_effort'],cfgReviewThinking:['rca','fast_final_review_thinking_mode'],cfgReviewTransport:['rca','fast_final_review_transport'],
  semanticPrepRole:['model_routing','semantic_preparation_role'],semanticVerifyRole:['model_routing','semantic_verification_role'],semanticPrepReasoning:['model_routing','semantic_preparation_reasoning_effort'],semanticPrepThinking:['model_routing','semantic_preparation_thinking_mode'],semanticVerifyReasoning:['model_routing','semantic_verification_reasoning_effort'],semanticVerifyThinking:['model_routing','semantic_verification_thinking_mode'],
  primaryProvider:['primary_model','provider'],primaryEndpoint:['primary_model','endpoint'],primaryModel:['primary_model','model'],primaryContext:['primary_model','context_size'],primaryThinking:['primary_model','thinking_mode'],primaryTransport:['primary_model','transport'],primaryTokenEnv:['primary_model','api_token_env'],
  smallProvider:['small_model','provider'],smallEndpoint:['small_model','endpoint'],smallModel:['small_model','model'],smallTemperature:['small_model','temperature'],smallReasoning:['small_model','reasoning_effort'],smallThinking:['small_model','thinking_mode'],smallTransport:['small_model','transport'],smallContext:['small_model','context_size'],smallTokenEnv:['small_model','api_token_env'],
  infCpuThreads:['inference','cpu_threads'],infGpuLayers:['inference','gpu_layers'],infGpuOffload:['inference','gpu_offload'],infTensorSplit:['inference','tensor_split'],infFlash:['inference','flash_attention'],infBatch:['inference','batch_size'],infEvalBatch:['inference','eval_batch_size'],infParallel:['inference','parallel_slots'],infContext:['inference','context_size_override'],
};
const legacyFields=['primary_large_case_max_tokens','primary_large_case_requirement_threshold','primary_phase_a_chunk_size','max_repair_passes','deterministic_repair_enabled','fast_intake_max_tokens','fast_atomic_claim_enabled','fast_atomic_claim_max_tokens','fast_requirement_language_enabled','fast_requirement_language_max_tokens','fast_repair_enabled','fast_repair_max_tokens','fallback_to_primary_repair','fast_repair_temperature'];
function deepGet(obj,path){return path.reduce((a,k)=>a?.[k],obj)}
function deepSet(obj,path,val){let a=obj;path.slice(0,-1).forEach(k=>{if(a[k]==null)a[k]={};a=a[k]});a[path.at(-1)]=val;}
function controlValue(el){if(el.type==='checkbox')return el.checked;if(el.type==='number')return el.value===''?null:Number(el.value);return el.value;}
function setControl(el,val){if(!el)return;if(el.type==='checkbox')el.checked=!!val;else el.value=val??'';}
function buildLegacyFields(){const root=$('legacyConfigFields');root.innerHTML='';legacyFields.forEach(k=>{const val=state.config?.rca?.[k],lab=document.createElement('label');lab.textContent=labelize(k);let input;if(typeof val==='boolean'){input=document.createElement('input');input.type='checkbox';lab.prepend(input)}else{input=document.createElement('input');input.type=typeof val==='number'?'number':'text';}input.id=`legacy_${k}`;lab.append(input);root.append(lab)});}
function fillConfig(){
  if(!state.config)return;Object.entries(configMap).forEach(([id,path])=>setControl($(id),deepGet(state.config,path)));buildLegacyFields();legacyFields.forEach(k=>setControl($(`legacy_${k}`),state.config.rca?.[k]));$('configStatus').textContent=`schema ${state.config.schema_version||1}`;
}
function collectConfig(){const cfg=structuredClone(state.config||{});Object.entries(configMap).forEach(([id,path])=>deepSet(cfg,path,controlValue($(id))));legacyFields.forEach(k=>{cfg.rca[k]=controlValue($(`legacy_${k}`))});return cfg;}
async function saveConfig(silent=false){const cfg=collectConfig();const saved=await api('/config',{method:'PUT',body:JSON.stringify({config:cfg})});state.config=saved;if(!silent)toast('Configuration saved.');if(Object.keys(state.capabilities?.environment_overrides||{}).length&&!silent)toast('Saved. Active environment overrides still affect backend defaults; run-specific form values remain available.',false);return cfg;}
async function reloadConfig(){state.config=await api('/config');fillConfig();toast('Configuration reloaded from backend defaults.');}
function roleFormConfig(role){const cfg=collectConfig();return structuredClone(role==='primary'?cfg.primary_model:cfg.small_model);}
function catalogContext(catalog){for(const x of catalog||[]){const meta=x.meta||x.details||{};for(const k of ['n_ctx','context_length','context_size','max_context_length'])if(meta[k]!=null)return Number(meta[k]);}return null;}
function fillDatalist(role,models){const dl=$(role==='primary'?'primaryModelList':'smallModelList');dl.innerHTML='';(models||[]).forEach(m=>{const o=document.createElement('option');o.value=m;dl.append(o)});}
function renderModelHint(role,catalog){const el=$(role==='primary'?'primaryModelHint':'smallModelHint'),ctx=catalogContext(catalog),form=roleFormConfig(role),advertised=(catalog||[]).map(x=>x.id).filter(Boolean);const pieces=[];if(ctx)pieces.push(`Server advertises context ${ctx.toLocaleString()}`);if(form.context_size)pieces.push(`configured metadata ${Number(form.context_size).toLocaleString()}`);if(form.model&&advertised.length&&!advertised.includes(form.model))pieces.push('current model ID is not advertised by this endpoint');el.textContent=pieces.join(' · ')||'Endpoint catalog loaded.';}
async function discoverModel(role){const config=roleFormConfig(role);const data=await api('/models/discover',{method:'POST',body:JSON.stringify({role,config})});if(data.status!=='AVAILABLE')throw new Error(data.error||`${role} endpoint unavailable`);state.modelCatalogs[role]=data.catalog||[];fillDatalist(role,data.models||[]);const field=$(role==='primary'?'primaryModel':'smallModel');if((data.models||[]).length===1&&!(data.models||[]).includes(field.value))field.value=data.models[0];renderModelHint(role,data.catalog||[]);toast(`${role}: discovered ${(data.models||[]).length} model(s) at ${data.endpoint}.`);return data;}
async function refreshModels(){await Promise.allSettled([discoverModel('primary'),discoverModel('small')]);}
async function testModel(role){const config=roleFormConfig(role);const r=await api('/models/test',{method:'POST',body:JSON.stringify({role,config})});if(r.catalog){state.modelCatalogs[role]=r.catalog;renderModelHint(role,r.catalog)}toast(`${role}: ${r.message}`,!r.ok);return r;}

function renderStructured(container,data,{raw=true,empty='No data available.'}={}){
  captureStructuredState(container);
  const scope=viewKey(container.id),savedScroll=state.scrollPositions[scope]||0;
  container.replaceChildren();if(data===undefined||data===null||(Array.isArray(data)&&!data.length)||(typeof data==='object'&&!Array.isArray(data)&&!Object.keys(data).length)){const e=document.createElement('div');e.className='structured-empty';e.textContent=empty;container.append(e);container.scrollTop=savedScroll;return;}
  container.append(buildStructuredNode(data,'',0,'root',container));
  if(raw){const d=document.createElement('details');d.className='raw-json';const s=document.createElement('summary');s.textContent='Raw JSON';const p=document.createElement('pre');p.textContent=pretty(data);bindDetailState(d,container,'raw-json',false);d.append(s,p);container.append(d);}
  container.scrollTop=savedScroll;
}
function buildStructuredNode(value,key,depth,path='root',container=null){
  if(value===null||typeof value!=='object'){const row=document.createElement('div');row.className='kv-row';if(key){const k=document.createElement('span');k.className='kv-key';k.textContent=labelize(key);row.append(k)}const v=document.createElement('span');v.className='kv-value';v.textContent=value===null?'—':String(value);row.append(v);return row;}
  if(Array.isArray(value)){
    const box=document.createElement('div');box.className='structured-array';if(key){const h=document.createElement('div');h.className='structured-heading';h.textContent=`${labelize(key)} (${value.length})`;box.append(h)}
    if(!value.length){box.append(buildStructuredNode('None','',depth+1,`${path}/empty`,container));return box;}
    value.forEach((item,i)=>{if(item&&typeof item==='object'){const det=document.createElement('details');det.className='structured-card';const sum=document.createElement('summary');const identity=item.requirement_id||item.evidence_id||item.fact_id||item.case_id||item.stage_id||item.stage||item.issue_id||`Item ${i+1}`;sum.textContent=String(identity);const itemPath=`${path}/${key||'array'}/${identity}`;if(container)bindDetailState(det,container,itemPath,depth<1);det.append(sum,buildStructuredNode(item,'',depth+1,itemPath,container));box.append(det)}else box.append(buildStructuredNode(item,`${i+1}`,depth+1,`${path}/${i}`,container));});return box;
  }
  const box=document.createElement('div');box.className='structured-object';if(key){const h=document.createElement('div');h.className='structured-heading';h.textContent=labelize(key);box.append(h)}
  const entries=Object.entries(value);const scalars=entries.filter(([,v])=>v===null||typeof v!=='object'),nested=entries.filter(([,v])=>v!==null&&typeof v==='object');if(scalars.length){const grid=document.createElement('div');grid.className='kv-grid';scalars.forEach(([k,v])=>grid.append(buildStructuredNode(v,k,depth+1,`${path}/${k}`,container)));box.append(grid)}nested.forEach(([k,v])=>box.append(buildStructuredNode(v,k,depth+1,`${path}/${k}`,container)));return box;
}
function renderTable(container,headers,items,rowFn,onClick){const t=document.createElement('table');t.innerHTML=`<thead><tr>${headers.map(h=>`<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>`;const b=document.createElement('tbody');items.forEach(item=>{const tr=document.createElement('tr');if(onClick){tr.className='clickable';tr.onclick=()=>onClick(item)};tr.innerHTML=rowFn(item).map(x=>`<td>${escapeHtml(x??'')}</td>`).join('');b.append(tr)});t.append(b);container.replaceChildren(t);}

async function upload(file){const fd=new FormData();fd.append('file',file);return api('/files',{method:'POST',body:fd});}
async function startRun(req){
  const configOverride=collectConfig();try{await saveConfig(true)}catch(e){console.warn('Config persistence failed; run override will still be used',e)}req={...req,config_override:configOverride};
  const r=await api('/runs',{method:'POST',body:JSON.stringify(req)});state.activeRunId=r.run_id;state.selectedCaseId=null;localStorage.setItem(`rca.activeRun.${state.profile.id}`,r.run_id);$('runSummary').textContent=r.run_id;switchTab('results');startPolling();await refreshRun();
}
function startPolling(){if(state.pollTimer)clearInterval(state.pollTimer);state.pollTimer=setInterval(()=>refreshRun().catch(e=>console.warn(e)),1800);}
function stopPolling(){if(state.pollTimer){clearInterval(state.pollTimer);state.pollTimer=null;}}
async function refreshRun(){if(!state.activeRunId)return;const [summary,pipeline,logs,metrics,result]=await Promise.all([api(`/runs/${state.activeRunId}/status`),api(`/runs/${state.activeRunId}/pipeline`),api(`/runs/${state.activeRunId}/logs`),api(`/runs/${state.activeRunId}/metrics`).catch(()=>({})),api(`/runs/${state.activeRunId}/result`).catch(()=>({}))]);state.lastRun={summary,pipeline,logs,metrics,result};renderRun(summary,pipeline,logs,metrics,result);if(terminal.has(summary.status)){stopPolling();await refreshHistory();}}
async function loadRun(id,resume=false){state.activeRunId=id;state.selectedCaseId=null;state.selectedStageId=null;restoreRunView(id);localStorage.setItem(`rca.activeRun.${state.profile.id}`,id);$('runSummary').textContent=id;await refreshRun();if(!terminal.has($('runStateBadge').textContent||''))startPolling();if(!resume)switchTab('results');}
function caseRows(resultWrap,summary){
  const lifecycle=resultWrap?.case_lifecycle||[];
  if(summary?.run_type==='single')return lifecycle;
  return resultWrap?.result?.cases||lifecycle;
}
function selectedCaseRecord(resultWrap,summary){
  const rows=caseRows(resultWrap,summary),row=rows.find(x=>x.case_id===state.selectedCaseId)||null;if(!row)return null;
  if(summary?.run_type==='single'){
    if(resultWrap?.result)return {...row,result:resultWrap.result,result_available:true};
    if(resultWrap?.failure)return {...row,failure:resultWrap.failure,result_available:true};
  }
  return row;
}
function updateCaseSelector(rows,resultMeta){
  const bar=$('batchCaseBar'),sel=$('batchCaseSelect');if(!rows.length){bar.hidden=true;state.selectedCaseId=null;return;}bar.hidden=false;
  const ids=rows.map(x=>x.case_id);if(!state.selectedCaseId||!ids.includes(state.selectedCaseId)){const running=rows.find(x=>x.execution_status==='RUNNING');state.selectedCaseId=(running||rows.at(-1)).case_id;}
  const old=sel.value;sel.innerHTML='';rows.forEach(c=>{const o=document.createElement('option');o.value=c.case_id;const sa=typeof c.semantic_acceptance==='string'?c.semantic_acceptance:(c.semantic_acceptance?.status||'');o.textContent=`${c.case_id} · ${c.execution_status||''}${sa&&sa!=='NOT_EVALUATED'?` · ${sa}`:''}`;sel.append(o)});sel.value=state.selectedCaseId||old;
  const current=rows.find(x=>x.case_id===sel.value);const done=resultMeta?.count??rows.filter(x=>!['RUNNING','QUEUED'].includes(x.execution_status)).length,total=resultMeta?.total_cases??rows.length;$('batchCaseStatus').textContent=`${current?.execution_status||''} · ${done}/${total}`;
}
function renderBatchSummary(result){
  const cases=result?.cases||[],root=$('batchView');if(!cases.length){renderStructured(root,result,{empty:'No completed testcase results yet.'});return;}
  const wrap=document.createElement('div');const h=document.createElement('h3');h.textContent=`Batch progress: ${result.count||cases.length}/${result.total_cases||cases.length}`;wrap.append(h);const table=document.createElement('div');wrap.append(table);renderTable(table,['Case','Execution','Semantic acceptance','Elapsed','Model time','Calls','Tokens','Tok/s'],cases,c=>{const st=c.statistics||{},sa=c.semantic_acceptance;let accept=typeof sa==='string'?sa:(sa?.accepted===true?'PASS':sa?.accepted===false?'FAIL':sa?.status||'—');return[c.case_id,c.execution_status,accept,fmtSec(st.elapsed_seconds),fmtSec(st.model_seconds),st.model_calls??0,st.total_tokens??0,st.weighted_generation_tokens_per_second??'—'];},c=>{captureStructuredState($('stageInput'));captureStructuredState($('stageOutput'));state.selectedCaseId=c.case_id;persistRunView();renderRun(state.lastRun.summary,state.lastRun.pipeline,state.lastRun.logs,state.lastRun.metrics,state.lastRun.result)});root.replaceChildren(wrap);
}
function fmtSec(v){if(v==null||Number.isNaN(Number(v)))return '—';const n=Number(v);if(n<60)return `${n.toFixed(2)} s`;return `${Math.floor(n/60)}m ${(n%60).toFixed(1)}s`;}
function selectedCasePayload(record){return record?.result||record?.failure||null;}
function renderRun(s,pipeline,logs,metrics,resultWrap){
  $('runSummary').textContent=s.run_id;$('currentStage').textContent=s.current_stage||s.status;$('progressDetail').textContent=s.progress_detail||s.error||'';const badge=$('runStateBadge');badge.textContent=s.status;badge.className=`badge ${s.status.toLowerCase()}`;$('stopBtn').disabled=!['QUEUED','INITIALIZING','RUNNING','CANCELLING'].includes(s.status);$('downloadReportBtn').disabled=s.status!=='COMPLETED'||s.run_type!=='single';$('downloadSessionBtn').disabled=!s.session_id;
  const result=resultWrap?.result,failure=resultWrap?.failure,isBatch=s.run_type!=='single',rows=caseRows(resultWrap,s);updateCaseSelector(rows,isBatch?result:null);
  const selected=selectedCaseRecord(resultWrap,s);
  const filteredPipeline=isBatch&&state.selectedCaseId?(pipeline||[]).filter(x=>x.stage_id?.startsWith(`${state.selectedCaseId}:`)):(pipeline||[]);renderPipeline(filteredPipeline);
  const filteredLogs=isBatch&&state.selectedCaseId?(logs||[]).filter(x=>String(x.stage||'').startsWith(`${state.selectedCaseId} /`)||String(x.message||'').includes(state.selectedCaseId)):(logs||[]);$('logsView').textContent=filteredLogs.map(x=>`[${x.time}] [${x.stage}] ${x.message}`).join('\n');
  if(isBatch&&result){renderBatchSummary(result);renderCaseResultViews(selected,selectedCasePayload(selected),metrics,filteredPipeline);}
  else if(rows.length){$('batchView').replaceChildren();renderCaseResultViews(selected,selectedCasePayload(selected),metrics,filteredPipeline);}
  else if(result){$('batchView').replaceChildren();renderSingleResultViews(result,metrics,filteredPipeline);}
  else if(failure){$('reportView').textContent=`FAILED\n\n${failure.message||''}`;renderStructured($('validationView'),failure.validated?.issues||failure);renderStructured($('canonicalView'),failure.canonical_case);renderStructured($('jsonView'),failure);renderStructured($('attemptsView'),failure.attempts||[]);renderStructured($('repairView'),failure.repair_log||[]);renderStats(metrics,null,filteredPipeline);}
  else {if(isBatch)renderBatchSummary(result||{cases:[]});renderStats(metrics,null,filteredPipeline);}
}
function renderSingleResultViews(result,metrics,pipeline){$('reportView').textContent=result.final_report||'No final report.';renderStructured($('validationView'),result.validated?.issues||[]);renderStructured($('canonicalView'),result.canonical_case);renderStructured($('jsonView'),result);renderStructured($('attemptsView'),result.attempts||[]);renderStructured($('repairView'),result.repair_log||[]);renderStats(metrics,null,pipeline);}
function renderCaseResultViews(c,payload,metrics,pipeline){
  if(!c){$('reportView').textContent='No testcase selected.';for(const id of ['validationView','canonicalView','jsonView','attemptsView','repairView'])renderStructured($(id),null);renderStats(metrics,null,pipeline);return;}
  if(c.result){$('reportView').textContent=c.result.final_report||'No final report.';renderStructured($('validationView'),c.result.validated?.issues||[]);renderStructured($('canonicalView'),c.result.canonical_case);renderStructured($('jsonView'),c.result);renderStructured($('attemptsView'),c.result.attempts||[]);renderStructured($('repairView'),c.result.repair_log||[]);}
  else if(c.failure){$('reportView').textContent=`FAILED\n\n${c.failure?.message||''}`;renderStructured($('validationView'),c.failure?.validated?.issues||c.failure);renderStructured($('canonicalView'),c.failure?.canonical_case);renderStructured($('jsonView'),c.failure);renderStructured($('attemptsView'),c.failure?.attempts||[]);renderStructured($('repairView'),c.failure?.repair_log||[]);}
  else {
    $('reportView').textContent=`${c.case_id} is ${c.execution_status||'RUNNING'}. Final report is not available until testcase completion.`;
    for(const id of ['validationView','canonicalView','jsonView','attemptsView','repairView'])renderStructured($(id),null,{empty:'Live testcase data is available in Pipeline, Logs and Stats until the result is finalized.'});
  }
  renderStats(metrics,c.statistics||null,pipeline);
}
function renderStats(metrics,caseStats,pipeline){
  const root=$('statsView'),wrap=document.createElement('div');if(caseStats){const h=document.createElement('h3');h.textContent=`Testcase statistics · ${state.selectedCaseId}`;wrap.append(h,buildStructuredNode(caseStats,'',0));}
  const stageRows=(pipeline||[]).map(st=>({stage:st.name,status:st.status,elapsed_seconds:(st.elapsed_ms??0)/1000,...(st.metadata?.statistics||{})}));if(stageRows.length){const h=document.createElement('h3');h.textContent='Stage statistics';wrap.append(h);const t=document.createElement('div');wrap.append(t);renderTable(t,['Stage','Status','Elapsed','Model time','Calls','Prompt','Completion','Reasoning','Tok/s'],stageRows,x=>[x.stage,x.status,fmtSec(x.elapsed_seconds),fmtSec(x.model_seconds),x.model_call_count??0,x.prompt_tokens??0,x.completion_tokens??0,x.reasoning_tokens??0,x.weighted_generation_tokens_per_second??'—']);}
  const calls=(metrics?.model_calls||[]).filter(x=>!state.selectedCaseId||x.case_id===state.selectedCaseId);if(calls.length){const h=document.createElement('h3');h.textContent='Model calls';wrap.append(h);const t=document.createElement('div');wrap.append(t);renderTable(t,['#','Role','Stage','Model','Endpoint','Time','Prompt','Completion','Reasoning tokens','Reasoning chars','Thinking','Finish','Retries'],calls,x=>[x.call_index,x.model_role,x.stage,x.model,x.endpoint,fmtSec(x.request_duration_seconds),x.prompt_tokens,x.completion_tokens,x.reasoning_tokens,x.reasoning_content_chars??0,x.thinking_requested??'provider_default',x.finish_reason,x.retries]);}
  const raw=document.createElement('details');raw.className='raw-json';raw.innerHTML='<summary>Raw run metrics</summary>';const pre=document.createElement('pre');pre.textContent=pretty(metrics);raw.append(pre);wrap.append(raw);root.replaceChildren(wrap);
}
function renderPipeline(stages){
  const root=$('stageList');root.innerHTML='';if(!stages.length){$('stageSummary').textContent='No pipeline stage available for this selection.';renderStructured($('stageInput'),null);renderStructured($('stageOutput'),null);state.selectedStageId=null;return;}
  if(!stages.some(x=>x.stage_id===state.selectedStageId))state.selectedStageId=stages.at(-1).stage_id;
  stages.forEach(st=>{const d=document.createElement('div');d.className=`stage-item ${state.selectedStageId===st.stage_id?'active':''}`;d.innerHTML=`<strong><span class="stage-dot ${escapeHtml(st.status)}"></span>${escapeHtml(st.name)}</strong><small>${escapeHtml(st.status)}${st.elapsed_ms!=null?` · ${(st.elapsed_ms/1000).toFixed(1)}s`:''}</small>`;d.onclick=()=>{captureStructuredState($('stageInput'));captureStructuredState($('stageOutput'));state.selectedStageId=st.stage_id;persistRunView();showStage(st);renderPipeline(stages)};root.append(d)});showStage(stages.find(x=>x.stage_id===state.selectedStageId)||stages.at(-1));
}
function showStage(st){
  const stats=st.metadata?.statistics||{};$('stageSummary').innerHTML=`<h3>${escapeHtml(st.name)}</h3><p><span class="badge neutral">${escapeHtml(st.status)}</span> ${escapeHtml(st.summary||'')}</p><small>${escapeHtml(st.start_time||'')}${st.elapsed_ms!=null?` · ${st.elapsed_ms} ms`:''}${stats.model_call_count?` · ${stats.model_call_count} model call(s) · ${stats.total_tokens||0} tokens`:''}</small>`;
  const input=st.input_data??safeJson(st.input_text)??st.input_text,output=st.output_data??safeJson(st.output_text)??st.output_text;renderStructured($('stageInput'),input,{raw:typeof input==='object'});renderStructured($('stageOutput'),output,{raw:typeof output==='object'});
}
async function cancelRun(){if(!state.activeRunId)return;await api(`/runs/${state.activeRunId}/cancel`,{method:'POST'});toast('Cancellation requested.');await refreshRun();}
async function download(path,filename){const res=await fetch(`${apiBase()}/api/v1${path}`,{headers:authHeaders()});if(!res.ok)throw new Error(await res.text());const blob=await res.blob(),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);}
async function refreshHistory(){const [runs,sessions]=await Promise.all([api('/runs'),api('/sessions')]);renderTable($('runHistory'),['Run','Type','Status','Created','Stage'],runs,r=>[r.run_id,r.run_type,r.status,new Date(r.created_at).toLocaleString(),r.current_stage||''],r=>loadRun(r.run_id));renderTable($('sessionHistory'),['Session','Status','Version','Created'],sessions,s=>[s.session_id,s.status,s.app_version||'',s.created_at?new Date(s.created_at).toLocaleString():''],s=>loadSession(s.session_id));return runs;}
async function loadSession(id){const s=await api(`/sessions/${id}`);renderStructured($('sessionView'),s);}
async function importSession(file){const up=await upload(file);const r=await api('/sessions/load',{method:'POST',body:JSON.stringify({file_id:up.file_id})});renderStructured($('sessionView'),r.session);await refreshHistory();toast('Session imported/migrated.');}

function switchTab(name){qsa('#mainTabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));qsa('.tab-page').forEach(p=>p.classList.toggle('active',p.id===`tab-${name}`));}
function wireTabs(){qsa('#mainTabs button').forEach(b=>b.onclick=()=>switchTab(b.dataset.tab));qsa('#resultTabs button').forEach(b=>b.onclick=()=>{qsa('#resultTabs button').forEach(x=>x.classList.toggle('active',x===b));qsa('.result-page').forEach(p=>p.classList.toggle('active',p.id===`result-${b.dataset.result}`))});qsa('.io-tabs button').forEach(b=>b.onclick=()=>{qsa('.io-tabs button').forEach(x=>x.classList.toggle('active',x===b));$('stageInput').classList.toggle('active',b.dataset.io==='input');$('stageOutput').classList.toggle('active',b.dataset.io==='output')});}
function wireActions(){
  $('activeRunSelect').onchange=()=>loadRun($('activeRunSelect').value).catch(e=>toast(e.message,true));$('profileSelect').onchange=()=>selectProfile($('profileSelect').value);$('backendToken').oninput=()=>sessionStorage.setItem(tokenKey(),$('backendToken').value);$('saveProfileBtn').onclick=saveCurrentProfile;$('testBackendBtn').onclick=()=>connectBackend(true).catch(e=>{setConnection(false,'OFFLINE');toast(e.message,true)});$('themeBtn').onclick=()=>{document.documentElement.classList.toggle('light');localStorage.setItem('rca.theme',document.documentElement.classList.contains('light')?'light':'dark')};
  qsa('.exampleBtn').forEach(b=>b.onclick=async()=>{$('caseInput').value=(await api(`/examples/${b.dataset.example}`)).raw_case});$('clearBtn').onclick=()=>{$('caseInput').value='';};$('analyzeBtn').onclick=()=>startRun({run_type:'single',raw_case:$('caseInput').value,label:'Single case'}).catch(e=>toast(e.message,true));$('runBuiltinBtn').onclick=()=>startRun({run_type:'builtin_regression',label:'Built-in TEST-001 → TEST-003'}).catch(e=>toast(e.message,true));$('runBundleBtn').onclick=async()=>{try{const f=$('bundleFile').files[0];if(!f)throw new Error('Select a ZIP bundle first');const up=await upload(f);await startRun({run_type:'bundle',file_id:up.file_id,label:f.name})}catch(e){toast(e.message,true)}};$('stopBtn').onclick=()=>cancelRun().catch(e=>toast(e.message,true));
  $('reloadConfigBtn').onclick=()=>reloadConfig().catch(e=>toast(e.message,true));$('saveConfigBtn').onclick=()=>saveConfig().catch(e=>toast(e.message,true));$('saveModelConfigBtn').onclick=()=>saveConfig().catch(e=>toast(e.message,true));$('refreshModelsBtn').onclick=()=>refreshModels().catch(e=>toast(e.message,true));$('discoverPrimaryBtn').onclick=()=>discoverModel('primary').catch(e=>toast(e.message,true));$('discoverSmallBtn').onclick=()=>discoverModel('small').catch(e=>toast(e.message,true));$('testPrimaryBtn').onclick=()=>testModel('primary').catch(e=>toast(e.message,true));$('testSmallBtn').onclick=()=>testModel('small').catch(e=>toast(e.message,true));
  $('batchCaseSelect').onchange=()=>{captureStructuredState($('stageInput'));captureStructuredState($('stageOutput'));state.selectedCaseId=$('batchCaseSelect').value;state.selectedStageId=null;persistRunView();if(state.lastRun)renderRun(state.lastRun.summary,state.lastRun.pipeline,state.lastRun.logs,state.lastRun.metrics,state.lastRun.result)};
  $('refreshHistoryBtn').onclick=()=>refreshHistory().catch(e=>toast(e.message,true));$('sessionFile').onchange=()=>{const f=$('sessionFile').files[0];if(f)importSession(f).catch(e=>toast(e.message,true))};$('downloadReportBtn').onclick=()=>download(`/runs/${state.activeRunId}/report/download`,`${state.activeRunId}-RCA_Report.md`).catch(e=>toast(e.message,true));$('downloadSessionBtn').onclick=()=>download(`/runs/${state.activeRunId}/session/download`,`${state.activeRunId}-RCA_Session.json`).catch(e=>toast(e.message,true));
}
async function boot(){if(localStorage.getItem('rca.theme')==='light')document.documentElement.classList.add('light');wireTabs();initProfiles();wireActions();if(state.profile?.auto_connect&&state.profile.backend_url){connectBackend().catch(e=>{setConnection(false,'OFFLINE');console.warn(e)})}}
boot();
