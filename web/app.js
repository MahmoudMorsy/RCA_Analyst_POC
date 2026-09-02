const $ = (id) => document.getElementById(id);
const qsa = (s) => [...document.querySelectorAll(s)];
const pretty = (x) => JSON.stringify(x ?? null, null, 2);
const terminal = new Set(['COMPLETED','FAILED','CANCELLED']);

const defaultProfiles = [
  {id:'local-dell', name:'Local Dell', backend_url:'http://localhost:8000', description:'Fully local Dell backend', auth_method:'none', model_endpoint_override:'', tls_policy:'allow_http', auto_connect:true},
  {id:'runpod', name:'RunPod Development', backend_url:'', description:'Remote RunPod GPU backend', auth_method:'bearer', model_endpoint_override:'', tls_policy:'require_https', auto_connect:false},
  {id:'home-ai-server', name:'Home AI Server', backend_url:'', description:'Future home AI workstation', auth_method:'bearer', model_endpoint_override:'', tls_policy:'require_https', auto_connect:false},
  {id:'custom', name:'Custom endpoint', backend_url:'', description:'User-defined RCA backend', auth_method:'bearer', model_endpoint_override:'', tls_policy:'auto', auto_connect:false},
];

const state = {
  profiles: loadProfiles(),
  profile: null,
  config: null,
  capabilities: null,
  system: null,
  activeRunId: null,
  pollTimer: null,
  selectedStageId: null,
};

function loadProfiles(){
  try {
    const saved = JSON.parse(localStorage.getItem('rca.backendProfiles') || 'null');
    if (Array.isArray(saved) && saved.length) return saved;
  } catch {}
  const profiles = structuredClone(defaultProfiles);
  if (!['localhost','127.0.0.1',''].includes(location.hostname) && location.origin.startsWith('http')) {
    profiles.find(p=>p.id==='runpod').backend_url = location.origin;
  }
  return profiles;
}
function saveProfiles(){ localStorage.setItem('rca.backendProfiles', JSON.stringify(state.profiles)); }
function tokenKey(){ return `rca.backendToken.${state.profile?.id || 'default'}`; }
function toast(msg, bad=false){ const t=$('toast'); t.textContent=msg; t.style.borderColor=bad?'var(--bad)':'var(--border)'; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),3200); }
function normalizeBase(url){ return (url || '').trim().replace(/\/+$/,''); }
function apiBase(){ return normalizeBase(state.profile?.backend_url || $('backendUrl').value); }
function authHeaders(extra={}){ const h={...extra}; const token=$('backendToken').value.trim(); if(token) h.Authorization=`Bearer ${token}`; return h; }
async function api(path, opts={}){
  const base=apiBase(); if(!base) throw new Error('Backend URL is empty');
  const headers=authHeaders(opts.headers || {});
  if(opts.body && !(opts.body instanceof FormData) && !headers['Content-Type']) headers['Content-Type']='application/json';
  const res=await fetch(`${base}/api/v1${path}`, {...opts,headers});
  if(!res.ok){ let detail=''; try{detail=JSON.stringify((await res.json()).detail)}catch{detail=await res.text()} throw new Error(`${res.status} ${res.statusText}: ${detail}`); }
  const ct=res.headers.get('content-type')||''; return ct.includes('application/json')?res.json():res;
}

function initProfiles(){
  const sel=$('profileSelect'); sel.innerHTML=''; state.profiles.forEach(p=>{const o=document.createElement('option');o.value=p.id;o.textContent=p.name;sel.append(o)});
  const savedId=localStorage.getItem('rca.selectedProfile') || state.profiles.find(p=>p.auto_connect)?.id || 'local-dell';
  sel.value=state.profiles.some(p=>p.id===savedId)?savedId:state.profiles[0].id;
  selectProfile(sel.value,false);
}
function selectProfile(id, connect=true){
  state.profile=state.profiles.find(p=>p.id===id) || state.profiles[0];
  localStorage.setItem('rca.selectedProfile',state.profile.id);
  $('backendUrl').value=state.profile.backend_url||'';
  $('backendToken').value=sessionStorage.getItem(tokenKey())||'';
  $('profileDescription').value=state.profile.description||'';
  $('profileAuth').value=state.profile.auth_method||'none';
  $('profileModelOverride').value=state.profile.model_endpoint_override||'';
  $('profileTls').value=state.profile.tls_policy||'auto';
  $('profileAutoConnect').checked=!!state.profile.auto_connect;
  $('profileName').textContent=state.profile.name;
  state.activeRunId=localStorage.getItem(`rca.activeRun.${state.profile.id}`)||null;
  if(connect && state.profile.backend_url) connectBackend().catch(()=>{});
}
function saveCurrentProfile(){
  const p=state.profile; p.backend_url=normalizeBase($('backendUrl').value); p.description=$('profileDescription').value.trim(); p.auth_method=$('profileAuth').value; p.model_endpoint_override=$('profileModelOverride').value.trim(); p.tls_policy=$('profileTls').value; p.auto_connect=$('profileAutoConnect').checked;
  if(p.tls_policy==='require_https' && p.backend_url && !p.backend_url.startsWith('https://')) return toast('This profile requires HTTPS.',true);
  sessionStorage.setItem(tokenKey(), $('backendToken').value.trim()); saveProfiles(); toast('Backend profile saved.');
}

async function connectBackend(){
  saveCurrentProfile();
  setConnection(false,'CONNECTING');
  const [health, system, caps, cfg] = await Promise.all([api('/health'), api('/system'), api('/capabilities'), api('/config')]);
  state.system=system; state.capabilities=caps; state.config=cfg;
  setConnection(true,'CONNECTED');
  $('backendVersion').textContent=`RCA v${health.backend_version} · ${health.profile_name}`;
  $('hardwareSummary').textContent=hardwareLabel(system);
  $('primarySummary').textContent=cfg.primary_model?.model || 'not configured';
  $('smallSummary').textContent=cfg.small_model?.model || 'not configured';
  $('systemView').textContent=pretty({health,system}); $('capabilitiesRaw').textContent=pretty(caps);
  renderCapabilities(); fillConfig(); await refreshHistory();
  if(state.activeRunId){ try{await loadRun(state.activeRunId,true)}catch{state.activeRunId=null} }
  toast('Backend connected.');
}
function setConnection(ok,label){ const b=$('connectionBadge');b.textContent=label;b.className=`badge ${ok?'online':'offline'}`; }
function hardwareLabel(s){ const g=s?.gpus?.map(x=>x.name).join(' + '); return g || `${s?.cpu_count_logical||'?'} CPU threads · ${s?.ram_total_gb||'?'} GB RAM`; }
function renderCapabilities(){
  const caps=state.capabilities||{}; const cards=$('capabilityCards'); cards.innerHTML='';
  Object.entries(caps.features||{}).forEach(([k,v])=>{const d=document.createElement('div');d.className=`cap-card ${v?'available':'unavailable'}`;d.innerHTML=`<span>${escapeHtml(k.replaceAll('_',' '))}</span><strong>${v?'SUPPORTED':'NOT SUPPORTED'}</strong>`;cards.append(d)});
  Object.entries(caps.models||{}).forEach(([k,v])=>{const d=document.createElement('div');d.className=`cap-card ${v?'available':'unavailable'}`;d.innerHTML=`<span>${escapeHtml(k)} model</span><strong>${v?'AVAILABLE':'UNAVAILABLE'}</strong>`;cards.append(d)});
  qsa('[data-cap]').forEach(el=>{const cap=el.dataset.cap;const supported=!!caps.features?.[cap];el.dataset.unsupported=String(!supported); el.querySelectorAll('input,select').forEach(i=>i.disabled=!supported)});
  $('capabilityHint').textContent=`${caps.deployment||''} · ${caps.gpu_count||0} GPU(s)`;
}
function escapeHtml(x){return String(x).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}

const configMap = {
  cfgPrimaryTemperature:['primary_model','temperature'], cfgPrimaryReasoning:['primary_model','reasoning_effort'], cfgPrimaryTokens:['primary_model','max_tokens'], cfgTimeout:['primary_model','timeout_seconds'],
  cfgFastIntake:['rca','fast_intake_enabled'], cfgFastIntakeMode:['rca','fast_intake_mode'], cfgSemanticPrep:['rca','semantic_preparation_enabled'], cfgSemanticArb:['rca','semantic_arbitration_enabled'], cfgRcaSynthesis:['rca','rca_synthesis_enabled'], cfgHypReview:['rca','fast_hypothesis_review_enabled'], cfgFinalReview:['rca','fast_final_review_enabled'],
  cfgAvailabilityTokens:['rca','fast_source_availability_max_tokens'], cfgContentTokens:['rca','fast_content_classification_max_tokens'], cfgSemanticTokens:['rca','semantic_preparation_max_tokens'], cfgHypTokens:['rca','fast_hypothesis_review_max_tokens'], cfgReviewTokens:['rca','fast_final_review_max_tokens'], cfgReviewReasoning:['rca','fast_final_review_reasoning_effort'], cfgReviewThinking:['rca','fast_final_review_thinking_mode'], cfgReviewTransport:['rca','fast_final_review_transport'],
  primaryProvider:['primary_model','provider'], primaryEndpoint:['primary_model','endpoint'], primaryModel:['primary_model','model'], primaryContext:['primary_model','context_size'], primaryThinking:['primary_model','thinking_mode'], primaryTransport:['primary_model','transport'], primaryTokenEnv:['primary_model','api_token_env'],
  smallProvider:['small_model','provider'], smallEndpoint:['small_model','endpoint'], smallModel:['small_model','model'], smallTemperature:['small_model','temperature'], smallReasoning:['small_model','reasoning_effort'], smallThinking:['small_model','thinking_mode'], smallTransport:['small_model','transport'], smallContext:['small_model','context_size'], smallTokenEnv:['small_model','api_token_env'],
  infCpuThreads:['inference','cpu_threads'], infGpuLayers:['inference','gpu_layers'], infGpuOffload:['inference','gpu_offload'], infTensorSplit:['inference','tensor_split'], infFlash:['inference','flash_attention'], infBatch:['inference','batch_size'], infEvalBatch:['inference','eval_batch_size'], infParallel:['inference','parallel_slots'], infContext:['inference','context_size_override'],
};
const legacyFields=['primary_large_case_max_tokens','primary_large_case_requirement_threshold','primary_phase_a_chunk_size','max_repair_passes','deterministic_repair_enabled','fast_intake_max_tokens','fast_atomic_claim_enabled','fast_atomic_claim_max_tokens','fast_requirement_language_enabled','fast_requirement_language_max_tokens','fast_repair_enabled','fast_repair_max_tokens','fallback_to_primary_repair','fast_repair_temperature'];
function deepGet(obj,path){return path.reduce((a,k)=>a?.[k],obj)} function deepSet(obj,path,val){let a=obj;path.slice(0,-1).forEach(k=>a=a[k]??=( {} ));a[path.at(-1)]=val}
function setControl(el,val){ if(!el)return; if(el.type==='checkbox')el.checked=!!val; else el.value=val ?? ''; }
function controlValue(el){ if(el.type==='checkbox')return el.checked; if(el.type==='number')return el.value===''?null:Number(el.value); return el.value; }
function buildLegacyFields(){const root=$('legacyConfigFields');root.innerHTML=''; legacyFields.forEach(name=>{const l=document.createElement('label');l.textContent=name; const value=state.config?.rca?.[name]; let i=document.createElement('input'); if(typeof value==='boolean'){i.type='checkbox'}else if(typeof value==='number'){i.type='number'}else{i.type='text'} i.id=`legacy_${name}`;l.append(i);root.append(l)});}
function fillConfig(){ if(!state.config)return; Object.entries(configMap).forEach(([id,path])=>setControl($(id),deepGet(state.config,path))); if(state.profile?.model_endpoint_override){$('primaryEndpoint').value=state.profile.model_endpoint_override;$('smallEndpoint').value=state.profile.model_endpoint_override;} buildLegacyFields(); legacyFields.forEach(k=>setControl($(`legacy_${k}`),state.config.rca?.[k])); }
function collectConfig(){ const cfg=structuredClone(state.config); Object.entries(configMap).forEach(([id,path])=>deepSet(cfg,path,controlValue($(id)))); legacyFields.forEach(k=>{cfg.rca[k]=controlValue($(`legacy_${k}`))}); return cfg; }
async function saveConfig(silent=false){ try{const cfg=collectConfig(); const saved=await api('/config',{method:'PUT',body:JSON.stringify({config:cfg})}); state.config=saved; fillConfig(); if(!silent)toast('Configuration saved.'); $('configStatus').textContent=`Saved ${new Date().toLocaleTimeString()}`; return saved}catch(e){toast(e.message,true); throw e} }
async function reloadConfig(){state.config=await api('/config');fillConfig();toast('Configuration reloaded.');}
async function refreshModels(){const data=await api('/models?refresh=true'); for(const role of ['primary','small']){const dl=$(`${role}ModelList`);dl.innerHTML='';(data[role]?.models||[]).forEach(m=>{const o=document.createElement('option');o.value=m;dl.append(o)})} toast('Model list refreshed.');}
async function testModel(role){const r=await api('/models/test',{method:'POST',body:JSON.stringify({role})});toast(`${role}: ${r.message}`,!r.ok);}

async function upload(file){const fd=new FormData();fd.append('file',file);return api('/files',{method:'POST',body:fd});}
async function startRun(req){ await saveConfig(true); const r=await api('/runs',{method:'POST',body:JSON.stringify(req)}); state.activeRunId=r.run_id; localStorage.setItem(`rca.activeRun.${state.profile.id}`,r.run_id); $('runSummary').textContent=r.run_id; switchTab('results'); startPolling(); await refreshRun(); }
function startPolling(){ if(state.pollTimer)clearInterval(state.pollTimer); state.pollTimer=setInterval(()=>refreshRun().catch(e=>console.warn(e)),1800); }
function stopPolling(){ if(state.pollTimer){clearInterval(state.pollTimer);state.pollTimer=null} }
async function refreshRun(){ if(!state.activeRunId)return; const [summary,pipeline,logs,metrics,result] = await Promise.all([api(`/runs/${state.activeRunId}/status`),api(`/runs/${state.activeRunId}/pipeline`),api(`/runs/${state.activeRunId}/logs`),api(`/runs/${state.activeRunId}/metrics`).catch(()=>({})),api(`/runs/${state.activeRunId}/result`).catch(()=>({}))]); renderRun(summary,pipeline,logs,metrics,result); if(terminal.has(summary.status)){stopPolling();await refreshHistory();} }
async function loadRun(id, resume=false){state.activeRunId=id;localStorage.setItem(`rca.activeRun.${state.profile.id}`,id);$('runSummary').textContent=id;await refreshRun();if(!terminal.has(($('runStateBadge').textContent||'')))startPolling();if(!resume)switchTab('results');}
function renderRun(s,pipeline,logs,metrics,resultWrap){
  $('runSummary').textContent=s.run_id; $('currentStage').textContent=s.current_stage||s.status; $('progressDetail').textContent=s.progress_detail||s.error||'';
  const badge=$('runStateBadge');badge.textContent=s.status;badge.className=`badge ${s.status.toLowerCase()}`; $('stopBtn').disabled=!['QUEUED','INITIALIZING','RUNNING','CANCELLING'].includes(s.status);
  $('downloadReportBtn').disabled=s.status!=='COMPLETED'||s.run_type!=='single'; $('downloadSessionBtn').disabled=!s.session_id;
  renderPipeline(pipeline||[]); $('logsView').textContent=(logs||[]).map(x=>`[${x.time}] [${x.stage}] ${x.message}`).join('\n'); $('statsView').textContent=pretty(metrics);
  const result=resultWrap?.result, failure=resultWrap?.failure;
  if(result){
    if(s.run_type==='single'){
      $('reportView').textContent=result.final_report||''; $('validationView').textContent=pretty(result.validated?.issues||[]); $('canonicalView').textContent=pretty(result.canonical_case); $('jsonView').textContent=pretty(result.validated?.semantic||result); $('attemptsView').textContent=pretty(result.attempts||[]); $('repairView').textContent=pretty(result.repair_log||[]); $('batchView').textContent='';
    } else { $('batchView').textContent=pretty(result); $('reportView').textContent=`${s.run_type} completed. See Sequential Batch tab.`; $('jsonView').textContent=pretty(result); }
  } else if(failure){ $('reportView').textContent=`FAILED\n\n${failure.message||''}`; $('validationView').textContent=pretty(failure.validated?.issues||failure); $('canonicalView').textContent=pretty(failure.canonical_case); $('attemptsView').textContent=pretty(failure.attempts||[]); $('repairView').textContent=pretty(failure.repair_log||[]); $('jsonView').textContent=pretty(failure); }
}
function renderPipeline(stages){const root=$('stageList');root.innerHTML='';stages.forEach(st=>{const d=document.createElement('div');d.className=`stage-item ${state.selectedStageId===st.stage_id?'active':''}`;d.innerHTML=`<strong><span class="stage-dot ${escapeHtml(st.status)}"></span>${escapeHtml(st.name)}</strong><small>${escapeHtml(st.status)}${st.elapsed_ms!=null?` · ${(st.elapsed_ms/1000).toFixed(1)}s`:''}</small>`;d.onclick=()=>{state.selectedStageId=st.stage_id;showStage(st);renderPipeline(stages)};root.append(d)});if(stages.length&&!state.selectedStageId){state.selectedStageId=stages.at(-1).stage_id;showStage(stages.at(-1))}else{const st=stages.find(x=>x.stage_id===state.selectedStageId);if(st)showStage(st)}}
function showStage(st){$('stageSummary').innerHTML=`<h3>${escapeHtml(st.name)}</h3><p><span class="badge neutral">${escapeHtml(st.status)}</span> ${escapeHtml(st.summary||'')}</p><small>${escapeHtml(st.start_time||'')} ${st.elapsed_ms!=null?` · ${st.elapsed_ms} ms`:''}</small>`;$('stageInput').textContent=st.input_text||'';$('stageOutput').textContent=st.output_text||'';}
async function cancelRun(){if(!state.activeRunId)return;await api(`/runs/${state.activeRunId}/cancel`,{method:'POST'});toast('Cancellation requested.');await refreshRun();}
async function download(path,filename){const res=await fetch(`${apiBase()}/api/v1${path}`,{headers:authHeaders()});if(!res.ok)throw new Error(await res.text());const blob=await res.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);}

// Table helper with item-aware callbacks without inline RCA logic.
function renderTable(container,headers,items,rowFn,onClick){const t=document.createElement('table');t.innerHTML=`<thead><tr>${headers.map(h=>`<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>`;const b=document.createElement('tbody');items.forEach(item=>{const tr=document.createElement('tr');if(onClick){tr.className='clickable';tr.onclick=()=>onClick(item)};tr.innerHTML=rowFn(item).map(x=>`<td>${escapeHtml(x??'')}</td>`).join('');b.append(tr)});t.append(b);container.replaceChildren(t);}
async function refreshHistory(){const [runs,sessions]=await Promise.all([api('/runs'),api('/sessions')]);renderTable($('runHistory'),['Run','Type','Status','Created','Stage'],runs,r=>[r.run_id,r.run_type,r.status,new Date(r.created_at).toLocaleString(),r.current_stage||''],r=>loadRun(r.run_id));renderTable($('sessionHistory'),['Session','Status','Version','Created'],sessions,s=>[s.session_id,s.status,s.app_version||'',s.created_at?new Date(s.created_at).toLocaleString():''],s=>loadSession(s.session_id));}
async function loadSession(id){const s=await api(`/sessions/${id}`);$('sessionView').textContent=pretty(s);}
async function importSession(file){const up=await upload(file);const r=await api('/sessions/load',{method:'POST',body:JSON.stringify({file_id:up.file_id})});$('sessionView').textContent=pretty(r.session);await refreshHistory();toast('Session imported/migrated.');}

function switchTab(name){qsa('#mainTabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));qsa('.tab-page').forEach(p=>p.classList.toggle('active',p.id===`tab-${name}`));}
function wireTabs(){qsa('#mainTabs button').forEach(b=>b.onclick=()=>switchTab(b.dataset.tab));qsa('#resultTabs button').forEach(b=>b.onclick=()=>{qsa('#resultTabs button').forEach(x=>x.classList.toggle('active',x===b));qsa('.result-page').forEach(p=>p.classList.toggle('active',p.id===`result-${b.dataset.result}`))});qsa('.io-tabs button').forEach(b=>b.onclick=()=>{qsa('.io-tabs button').forEach(x=>x.classList.toggle('active',x===b));$('stageInput').classList.toggle('active',b.dataset.io==='input');$('stageOutput').classList.toggle('active',b.dataset.io==='output')});}

function wireActions(){
  $('profileSelect').onchange=()=>selectProfile($('profileSelect').value); $('backendToken').oninput=()=>sessionStorage.setItem(tokenKey(),$('backendToken').value); $('saveProfileBtn').onclick=saveCurrentProfile; $('testBackendBtn').onclick=()=>connectBackend().catch(e=>{setConnection(false,'OFFLINE');toast(e.message,true)});
  $('themeBtn').onclick=()=>{document.documentElement.classList.toggle('light');localStorage.setItem('rca.theme',document.documentElement.classList.contains('light')?'light':'dark')};
  qsa('.exampleBtn').forEach(b=>b.onclick=async()=>{$('caseInput').value=(await api(`/examples/${b.dataset.example}`)).raw_case}); $('clearBtn').onclick=()=>{$('caseInput').value='';};
  $('analyzeBtn').onclick=()=>startRun({run_type:'single',raw_case:$('caseInput').value,label:'Single case'}).catch(e=>toast(e.message,true)); $('runBuiltinBtn').onclick=()=>startRun({run_type:'builtin_regression',label:'Built-in TEST-001 → TEST-003'}).catch(e=>toast(e.message,true)); $('runBundleBtn').onclick=async()=>{try{const f=$('bundleFile').files[0];if(!f)throw new Error('Select a ZIP bundle first');const up=await upload(f);await startRun({run_type:'bundle',file_id:up.file_id,label:f.name})}catch(e){toast(e.message,true)}}; $('stopBtn').onclick=()=>cancelRun().catch(e=>toast(e.message,true));
  $('reloadConfigBtn').onclick=()=>reloadConfig().catch(e=>toast(e.message,true)); $('saveConfigBtn').onclick=()=>saveConfig().catch(()=>{}); $('saveModelConfigBtn').onclick=()=>saveConfig().catch(()=>{}); $('refreshModelsBtn').onclick=()=>refreshModels().catch(e=>toast(e.message,true)); $('testPrimaryBtn').onclick=()=>testModel('primary').catch(e=>toast(e.message,true)); $('testSmallBtn').onclick=()=>testModel('small').catch(e=>toast(e.message,true));
  $('refreshHistoryBtn').onclick=()=>refreshHistory().catch(e=>toast(e.message,true)); $('sessionFile').onchange=()=>{const f=$('sessionFile').files[0];if(f)importSession(f).catch(e=>toast(e.message,true))};
  $('downloadReportBtn').onclick=()=>download(`/runs/${state.activeRunId}/report/download`,`${state.activeRunId}-RCA_Report.md`).catch(e=>toast(e.message,true)); $('downloadSessionBtn').onclick=()=>download(`/runs/${state.activeRunId}/session/download`,`${state.activeRunId}-RCA_Session.json`).catch(e=>toast(e.message,true));
}

async function boot(){if(localStorage.getItem('rca.theme')==='light')document.documentElement.classList.add('light');wireTabs();initProfiles();wireActions();if(state.profile?.auto_connect&&state.profile.backend_url){connectBackend().catch(e=>{setConnection(false,'OFFLINE');console.warn(e)})}}
boot();
