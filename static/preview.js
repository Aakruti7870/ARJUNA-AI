let previewAnalysis = null;
let previewBaseline = null;
const PREVIEW_SNAPSHOTS_KEY = "arjuna-preview-snapshots-v1";

function previewEscape(value){return String(value ?? "").replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));}
function previewMarkdown(raw){
  const lines=String(raw||"").split("\n");
  let out=""; let inList=false;
  for(const line of lines){
    const safe=previewEscape(line);
    if(/^#{1,6}\s+/.test(line)){ if(inList){out+="</ul>";inList=false;} const n=Math.min(6,(line.match(/^#+/)||[""])[0].length); out+=`<h${n}>${previewEscape(line.replace(/^#{1,6}\s+/,""))}</h${n}>`; continue; }
    if(/^[-*+]\s+/.test(line)){ if(!inList){out+="<ul>";inList=true;} out+=`<li>${previewEscape(line.replace(/^[-*+]\s+/,""))}</li>`; continue; }
    if(inList){out+="</ul>";inList=false;}
    const formatted=safe.replace(/\*\*([^*]+)\*\*/g,"<strong>$1</strong>").replace(/`([^`]+)`/g,"<code>$1</code>");
    out+=line.trim()?`<p>${formatted}</p>`:"<br>";
  }
  if(inList)out+="</ul>"; return out;
}
function safeHtml(raw){
  const doc=new DOMParser().parseFromString(String(raw||""),"text/html");
  doc.querySelectorAll("script,iframe,object,embed,base,link,meta[http-equiv]").forEach(n=>n.remove());
  doc.querySelectorAll("*").forEach(el=>{
    [...el.attributes].forEach(attr=>{
      const name=attr.name.toLowerCase(), value=attr.value.trim();
      if(name.startsWith("on") || (name==="srcdoc") || (/^(href|src|action|formaction)$/i.test(name)&&/^(?:javascript:|https?:|\/\/)/i.test(value))) el.removeAttribute(attr.name);
      if(name==="target") el.removeAttribute(attr.name);
    });
    if(el.tagName==="FORM"){el.removeAttribute("action");el.setAttribute("onsubmit","return false");}
  });
  return doc.body.innerHTML;
}
function previewDocument(analysis){
  const kind=analysis.kind, raw=analysis.content||"";
  let body="";
  if(kind==="html") body=safeHtml(raw);
  else if(kind==="markdown") body=previewMarkdown(raw);
  else if(kind==="json") { try{body=`<pre>${previewEscape(JSON.stringify(JSON.parse(raw),null,2))}</pre>`;}catch{body=`<pre>${previewEscape(raw)}</pre>`;} }
  else body=`<pre>${previewEscape(raw)}</pre>`;
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:;"><style>html{background:#fff;color:#111;font-family:Inter,system-ui,sans-serif}body{margin:0;padding:24px;line-height:1.55}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f6f8;border-radius:12px;padding:16px}code{background:#f1f2f4;padding:2px 5px;border-radius:5px}button,input,select,textarea{font:inherit}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px}a{color:#555;text-decoration:underline;pointer-events:none}</style></head><body>${body}</body></html>`;
}
function renderPreview(analysis){
  previewAnalysis=analysis;
  $("previewKind").textContent=analysis.kind.toUpperCase();
  $("previewRisk").textContent=`${analysis.riskLevel.toUpperCase()} · ${analysis.riskScore}`;
  $("previewCompleteness").textContent=`${analysis.completenessScore}%`;
  $("previewFingerprint").textContent=analysis.fingerprint;
  $("previewSource").textContent=analysis.content||"";
  $("previewFrame").srcdoc=$("previewPolicy").value==="source"?previewDocument({...analysis,kind:"text"}):previewDocument(analysis);
  $("previewInsights").innerHTML=(analysis.insights||[]).map(i=>`<div class="insight-item">${previewEscape(i)}</div>`).join("")||'<span class="muted">No additional findings.</span>';
  $("previewRisks").innerHTML=(analysis.risks||[]).map(r=>`<div class="risk-item"><span>${previewEscape(r.label)}</span><strong>${r.count}</strong></div>`).join("")||'<div class="risk-item safe"><span>No active-content risk patterns detected</span><strong>✓</strong></div>';
  renderPreviewCompare();
}
async function analyzePreview(){
  const content=$("previewInput").value;
  if(!content.trim()){alert("Add preview content first.");return;}
  const b=$("previewAnalyze"); b.disabled=true;b.textContent="Analyzing…";
  try{const d=await api("/api/preview/analyze",{method:"POST",body:JSON.stringify({content,hint:$("previewHint").value})});renderPreview(d);}
  catch(err){alert(err.message);}finally{b.disabled=false;b.textContent="Analyze & render";}
}
function setPreviewTab(tab){
  document.querySelectorAll(".preview-tab").forEach(b=>b.classList.toggle("active",b.dataset.previewTab===tab));
  $("previewFrame").classList.toggle("hidden",tab!=="render"); $("previewSource").classList.toggle("hidden",tab!=="source"); $("previewCompare").classList.toggle("hidden",tab!=="compare");
}
function simpleLineDiff(a,b){
  const A=String(a||"").split("\n"),B=String(b||"").split("\n"),max=Math.max(A.length,B.length);let html="",added=0,removed=0,changed=0;
  for(let i=0;i<max;i++){const x=A[i],y=B[i];if(x===y){if(x!==undefined)html+=`<div class="diff-line same">  ${previewEscape(x)}</div>`;continue;} if(x!==undefined){removed++;html+=`<div class="diff-line removed">- ${previewEscape(x)}</div>`;} if(y!==undefined){added++;html+=`<div class="diff-line added">+ ${previewEscape(y)}</div>`;} changed++;}
  return {html,added,removed,changed};
}
function renderPreviewCompare(){
  if(!previewBaseline||!previewAnalysis){$("previewCompare").innerHTML='<div class="empty-state">Set a baseline, then analyze a changed version to compare.</div>';return;}
  const diff=simpleLineDiff(previewBaseline.content,previewAnalysis.content); $("previewCompare").innerHTML=`<div class="diff-summary"><span>Changed lines <strong>${diff.changed}</strong></span><span>Added <strong>${diff.added}</strong></span><span>Removed <strong>${diff.removed}</strong></span></div><div class="diff-body">${diff.html||'<div class="empty-state">No content difference.</div>'}</div>`;
}
function getSnapshots(){try{return JSON.parse(localStorage.getItem(PREVIEW_SNAPSHOTS_KEY)||"[]")}catch{return []}}
function renderSnapshots(){const items=getSnapshots();$("previewSnapshots").innerHTML=items.length?items.map(s=>`<button class="snapshot-item" data-preview-snapshot="${s.id}"><span>${previewEscape(s.kind)} · ${previewEscape(s.fingerprint)}</span><small>${new Date(s.createdAt).toLocaleString()}</small></button>`).join(""):'<span class="muted">No snapshots saved.</span>';document.querySelectorAll("[data-preview-snapshot]").forEach(b=>b.addEventListener("click",()=>{const s=getSnapshots().find(x=>x.id===b.dataset.previewSnapshot);if(!s)return;$("previewInput").value=s.content;$("previewHint").value=s.kind||"auto";goto("preview");analyzePreview();}));}
function saveSnapshot(){if(!previewAnalysis){alert("Analyze a preview first.");return;}const items=getSnapshots();items.unshift({id:crypto.randomUUID?crypto.randomUUID():String(Date.now()),createdAt:new Date().toISOString(),kind:previewAnalysis.kind,fingerprint:previewAnalysis.fingerprint,content:previewAnalysis.content});localStorage.setItem(PREVIEW_SNAPSHOTS_KEY,JSON.stringify(items.slice(0,20)));renderSnapshots();}

$("previewAnalyze").addEventListener("click",analyzePreview);
$("previewClear").addEventListener("click",()=>{$("previewInput").value="";$("previewFrame").srcdoc="";$("previewSource").textContent="No preview yet.";previewAnalysis=null;});
$("previewSetBaseline").addEventListener("click",()=>{if(!previewAnalysis){alert("Analyze content before setting a baseline.");return;}previewBaseline={...previewAnalysis};renderPreviewCompare();setPreviewTab("compare");});
$("previewSaveSnapshot").addEventListener("click",saveSnapshot);
$("previewClearSnapshots").addEventListener("click",()=>{if(confirm("Clear local preview snapshots from this browser?")){localStorage.removeItem(PREVIEW_SNAPSHOTS_KEY);renderSnapshots();}});
$("previewUseOutput").addEventListener("click",()=>{$("previewInput").value=$("output").textContent||"";analyzePreview();});
$("previewOutputBtn").addEventListener("click",()=>{goto("preview");$("previewInput").value=$("output").textContent||"";analyzePreview();});
$("previewPolicy").addEventListener("change",()=>{if(previewAnalysis)renderPreview(previewAnalysis);});
document.querySelectorAll(".preview-tab").forEach(b=>b.addEventListener("click",()=>setPreviewTab(b.dataset.previewTab)));
document.querySelectorAll(".device-btn").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".device-btn").forEach(x=>x.classList.toggle("active",x===b));$("previewViewport").className=`preview-viewport ${b.dataset.device}`;}));
renderSnapshots();
