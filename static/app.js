const $ = (id) => document.getElementById(id);
let csrf = null;
let installPrompt = null;

const api = async (url, options = {}) => {
  const headers = {"Content-Type":"application/json", ...(options.headers || {})};
  if (csrf && ["POST","DELETE","PATCH","PUT"].includes((options.method || "GET").toUpperCase())) headers["X-Arjuna-CSRF"] = csrf;
  const res = await fetch(url, {...options, headers, credentials:"same-origin"});
  let data = {};
  try { data = await res.json(); } catch {}
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
};
const fmtNum = (n) => new Intl.NumberFormat().format(n ?? 0);
const fmtDate = (v) => v ? new Date(v).toLocaleString() : "—";
const esc = (s) => String(s ?? "").replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

async function boot(){
  applyTheme(localStorage.getItem("arjuna-theme") || "dark");
  checkHealth();
  try{
    const status = await api("/api/auth/status");
    if(status.authenticated){ csrf=status.csrf; showApp(status.email); await loadAll(); }
    else showLogin();
  }catch{ showLogin(); }
  if("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch(()=>{});
}
function showLogin(){ $("loginView").classList.remove("hidden"); $("appView").classList.add("hidden"); }
function showApp(email){ $("loginView").classList.add("hidden"); $("appView").classList.remove("hidden"); $("userEmail").textContent=email; }

$("loginForm").addEventListener("submit", async e=>{
  e.preventDefault(); $("loginError").textContent="";
  try{ const data=await api("/api/auth/login",{method:"POST",body:JSON.stringify({email:$("loginEmail").value,password:$("loginPassword").value})}); csrf=data.csrf; showApp(data.email); $("loginPassword").value=""; await loadAll(); }
  catch(err){ $("loginError").textContent=err.message; }
});
$("logoutBtn").addEventListener("click", async()=>{ try{await api("/api/auth/logout",{method:"POST"});}catch{} csrf=null; showLogin(); });

function goto(page){
  document.querySelectorAll(".page").forEach(el=>el.classList.toggle("active",el.id===`page-${page}`));
  document.querySelectorAll(".nav-item").forEach(el=>el.classList.toggle("active",el.dataset.page===page));
  const titles={dashboard:["COMMAND CENTRE","Dashboard"],playground:["PROMPT LAB","Playground"],providers:["MODEL ROUTER","Providers"],keys:["ACCESS CONTROL","API Keys"],usage:["OBSERVABILITY","Usage"],settings:["PLATFORM","Settings"]};
  $("pageKicker").textContent=titles[page][0]; $("pageTitle").textContent=titles[page][1]; $("nav").closest(".sidebar").classList.remove("open");
  if(page==="dashboard") loadDashboard(); if(page==="providers") loadProviders(); if(page==="keys") loadKeys(); if(page==="usage") loadUsage();
}
document.querySelectorAll(".nav-item").forEach(b=>b.addEventListener("click",()=>goto(b.dataset.page)));
document.querySelectorAll("[data-goto]").forEach(b=>b.addEventListener("click",()=>goto(b.dataset.goto)));
$("menuBtn").addEventListener("click",()=>document.querySelector(".sidebar").classList.toggle("open"));

async function checkHealth(){ try{const d=await api("/api/health"); $("health").textContent=d.ok?"Online":"Issue"; $("health").className=`status-pill ${d.ok?"ok":"bad"}`;}catch{$("health").textContent="Offline";$("health").className="status-pill bad";} }
async function loadAll(){ await Promise.allSettled([loadDashboard(),loadProviders(),loadKeys(),loadUsage()]); $("apiBase").textContent=location.origin; }
async function loadDashboard(){ try{const d=await api("/api/dashboard"); $("statProviders").textContent=`${d.providersReady}/${d.providersTotal}`; $("statKeys").textContent=fmtNum(d.activeKeys); $("statRequests").textContent=fmtNum(d.requests24h); $("statTokens").textContent=fmtNum(d.tokens24h);}catch{} }
async function loadProviders(){ const box=$("providersList"); box.innerHTML='<div class="muted">Loading…</div>'; try{const d=await api("/api/providers"); const select=$("provider"); const prev=select.value; select.innerHTML='<option value="">Auto route</option>'; box.innerHTML=""; d.providers.forEach(p=>{const opt=document.createElement("option");opt.value=p.name;opt.textContent=p.name;select.appendChild(opt); const state=!p.configured?"Not configured":p.cooldown?"Cooling down":"Ready"; const cls=!p.configured?"":p.cooldown?"warn":"ready"; const card=document.createElement("article");card.className="provider-card";card.innerHTML=`<div class="provider-top"><h3>${esc(p.name)}</h3><span class="pill ${cls}">${state}</span></div><div class="provider-meta"><span>Model · <strong>${esc(p.defaultModel||"—")}</strong></span><span>Priority · ${p.priority}</span><span>Free eligible · ${p.freeEligible?"Yes":"No"}</span>${p.lastError?`<span class="error-text">${esc(p.lastError)}</span>`:""}</div>`; box.appendChild(card);}); select.value=prev;}catch(err){box.innerHTML=`<div class="error-text">${esc(err.message)}</div>`;} }
$("refreshProviders").addEventListener("click",loadProviders);

$("runBtn").addEventListener("click",async()=>{const b=$("runBtn"); b.disabled=true;b.textContent="Running…";$("output").textContent="Waiting for provider…"; try{const d=await api("/api/playground",{method:"POST",body:JSON.stringify({prompt:$("prompt").value,system_prompt:$("systemPrompt").value||null,provider:$("provider").value||null,model:$("model").value||"auto",free_only:$("freeOnly").checked,temperature:Number($("temperature").value),max_tokens:Number($("maxTokens").value)})}); $("output").textContent=typeof d.content==="string"?d.content:JSON.stringify(d.content,null,2); const tokens=d.usage?.total_tokens??d.usage?.totalTokens??"—"; $("runMeta").textContent=`${d.provider} · ${d.model} · ${d.totalLatencyMs} ms · ${tokens} tokens`; await Promise.allSettled([loadDashboard(),loadUsage(),loadProviders()]);}catch(err){$("output").textContent=`Error: ${err.message}`;}finally{b.disabled=false;b.textContent="Run prompt";}});
$("copyOutput").addEventListener("click",()=>navigator.clipboard.writeText($("output").textContent||""));

async function loadKeys(){ try{const d=await api("/api/keys"); $("keysBody").innerHTML=d.keys.map(k=>`<tr><td><strong>${esc(k.name)}</strong></td><td><code>${esc(k.prefix)}…</code></td><td>${fmtDate(k.created_at)}</td><td>${fmtDate(k.last_used_at)}</td><td><span class="pill ${k.revoked_at?'':'ready'}">${k.revoked_at?'Revoked':'Active'}</span></td><td>${k.revoked_at?'':`<button class="danger-btn" data-revoke="${k.id}">Revoke</button>`}</td></tr>`).join("")||'<tr><td colspan="6" class="muted">No generated API keys yet.</td></tr>'; document.querySelectorAll("[data-revoke]").forEach(b=>b.addEventListener("click",()=>revokeKey(b.dataset.revoke)));}catch(err){$("keysBody").innerHTML=`<tr><td colspan="6" class="error-text">${esc(err.message)}</td></tr>`;} }
$("createKeyBtn").addEventListener("click",()=>$("keyDialog").showModal());
$("keyForm").addEventListener("submit",async e=>{e.preventDefault();const name=$("keyName").value.trim();if(name.length<2)return;try{const d=await api("/api/keys",{method:"POST",body:JSON.stringify({name})}); $("newKeySecret").textContent=d.secret;$("keySecretBox").classList.remove("hidden");$("keyName").value="";$("keyDialog").close();await Promise.all([loadKeys(),loadDashboard()]);}catch(err){alert(err.message);}});
async function revokeKey(id){if(!confirm("Revoke this API key? Existing clients using it will stop working."))return;try{await api(`/api/keys/${id}`,{method:"DELETE"});await Promise.all([loadKeys(),loadDashboard()]);}catch(err){alert(err.message);}}
$("copyKeySecret").addEventListener("click",()=>navigator.clipboard.writeText($("newKeySecret").textContent||""));

async function loadUsage(){try{const d=await api("/api/usage?limit=150");$("usageBody").innerHTML=d.events.map(e=>`<tr><td>${fmtDate(e.created_at)}</td><td>${esc(e.provider)}</td><td>${esc(e.model)}</td><td>${e.tokens??"—"}</td><td>${e.latency_ms} ms</td><td><span class="pill ${e.status==='ok'?'ready':''}">${esc(e.status)}</span></td></tr>`).join("")||'<tr><td colspan="6" class="muted">No usage yet.</td></tr>';}catch(err){$("usageBody").innerHTML=`<tr><td colspan="6" class="error-text">${esc(err.message)}</td></tr>`;}}
$("refreshUsage").addEventListener("click",loadUsage);

function applyTheme(theme){document.body.classList.toggle("light",theme==="light");localStorage.setItem("arjuna-theme",theme)}
$("themeBtn").addEventListener("click",()=>applyTheme(document.body.classList.contains("light")?"dark":"light"));
window.addEventListener("beforeinstallprompt",e=>{e.preventDefault();installPrompt=e;$("installBtn").disabled=false;});
$("installBtn").addEventListener("click",async()=>{if(!installPrompt)return;installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;$("installBtn").disabled=true;});
boot();
