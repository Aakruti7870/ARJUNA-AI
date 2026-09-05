let integrationCatalogCache=[];
const integrationEsc=(s)=>String(s??"").replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));

function integrationTemplate(item){
  if(item.id==='mcp_streamable_http') return {transport:'streamable_http',endpoint:'https://example.com/mcp',capabilities:['tools','resources','prompts'],approval:'required'};
  if(item.id==='mcp_sse') return {transport:'sse',endpoint:'https://example.com/sse',capabilities:['tools','resources','prompts'],approval:'required'};
  if(item.id==='mcp_stdio') return {transport:'stdio',command:'node',args:['server.js'],deployment:'local_or_worker_only',approval:'required'};
  if(item.id==='plugin_openapi') return {manifest_type:'openapi',schema_url:'https://example.com/openapi.json',approval:'required'};
  if(item.id==='plugin_custom') return {manifest_type:'arjuna_plugin',manifest_url:'https://example.com/arjuna-plugin.json',approval:'required'};
  if(item.id==='rest_api') return {base_url:'https://api.example.com',auth_type:'bearer',approval:'required'};
  if(item.id==='webhook') return {endpoint:'https://example.com/webhook',direction:'outbound',approval:'required'};
  return {};
}

async function loadIntegrations(){
  const grid=$('integrationGrid');
  if(!grid) return;
  grid.innerHTML='<div class="muted">Loading global integration catalog…</div>';
  try{
    const d=await api('/api/growth/catalog');
    integrationCatalogCache=d.platforms||[];
    renderIntegrationFilters();
    renderIntegrations();
    updateIntegrationStats();
  }catch(err){grid.innerHTML=`<div class="error-text">${integrationEsc(err.message)}</div>`;}
}

function renderIntegrationFilters(){
  const select=$('integrationCategory');
  const categories=[...new Set(integrationCatalogCache.map(x=>x.category||'Other'))].sort();
  const current=select.value;
  select.innerHTML='<option value="">All categories</option>'+categories.map(c=>`<option value="${integrationEsc(c)}">${integrationEsc(c)}</option>`).join('');
  if(categories.includes(current)) select.value=current;
}

function updateIntegrationStats(){
  const connected=integrationCatalogCache.filter(x=>x.connection?.configured&&x.connection?.enabled).length;
  const plugins=integrationCatalogCache.filter(x=>x.kind==='plugin').length;
  const mcp=integrationCatalogCache.filter(x=>x.kind==='mcp').length;
  $('integrationStatTotal').textContent=fmtNum(integrationCatalogCache.length);
  $('integrationStatConnected').textContent=fmtNum(connected);
  $('integrationStatPlugins').textContent=fmtNum(plugins);
  $('integrationStatMcp').textContent=fmtNum(mcp);
}

function renderIntegrations(){
  const grid=$('integrationGrid');
  const q=$('integrationSearch').value.trim().toLowerCase();
  const category=$('integrationCategory').value;
  const kind=$('integrationKind').value;
  const items=integrationCatalogCache.filter(item=>{
    const hay=[item.label,item.category,item.kind,...(item.channels||[]),...(item.capabilities||[])].join(' ').toLowerCase();
    return (!q||hay.includes(q))&&(!category||item.category===category)&&(!kind||item.kind===kind);
  });
  grid.innerHTML=items.map(item=>{
    const c=item.connection;
    const ready=!!(c?.configured&&c?.enabled);
    const state=c?.configured?(c.enabled?'Connected':'Disabled'):'Available';
    const kindLabel=item.kind==='mcp'?'MCP':item.kind==='plugin'?'Plugin':'Integration';
    return `<article class="integration-card ${item.kind==='mcp'?'mcp-card':''}">
      <div class="integration-card-head"><div class="integration-symbol">${item.kind==='mcp'?'M':item.kind==='plugin'?'P':'↗'}</div><div><p class="integration-category">${integrationEsc(item.category||'Other')}</p><h3>${integrationEsc(item.label)}</h3></div><span class="pill ${ready?'ready':''}">${integrationEsc(state)}</span></div>
      <p class="muted small">${integrationEsc((item.channels||[]).join(' · '))}</p>
      <div class="integration-capabilities">${(item.capabilities||[]).slice(0,6).map(x=>`<span>${integrationEsc(x)}</span>`).join('')}</div>
      <div class="integration-card-foot"><div><small class="muted">${integrationEsc(kindLabel)} · ${integrationEsc(item.auth||'Provider-defined auth')}</small></div><button class="secondary" data-integrate="${integrationEsc(item.id)}">${c?'Configure':'Connect'}</button></div>
    </article>`;
  }).join('')||'<div class="empty-state">No matching integrations.</div>';
  document.querySelectorAll('[data-integrate]').forEach(b=>b.addEventListener('click',()=>openIntegration(b.dataset.integrate)));
}

function openIntegration(id){
  const item=integrationCatalogCache.find(x=>x.id===id);
  if(!item||typeof openGrowthConnector!=='function') return;
  openGrowthConnector(id);
  if(!item.connection){
    const template=integrationTemplate(item);
    if(Object.keys(template).length) $('growthConnectorConfig').value=JSON.stringify(template,null,2);
  }
  $('growthConnectorHelp').textContent=`${item.category} · ${item.auth}. Configuration is global to ARJUNA. Credentials are encrypted and external actions remain approval-gated until the official provider integration is verified.`;
}

$('integrationSearch').addEventListener('input',renderIntegrations);
$('integrationCategory').addEventListener('change',renderIntegrations);
$('integrationKind').addEventListener('change',renderIntegrations);
$('refreshIntegrations').addEventListener('click',loadIntegrations);
$('integrationMcpBtn').addEventListener('click',()=>{$('integrationKind').value='mcp';$('integrationCategory').value='';$('integrationSearch').value='';renderIntegrations();});
$('integrationPluginsBtn').addEventListener('click',()=>{$('integrationKind').value='plugin';$('integrationCategory').value='';$('integrationSearch').value='';renderIntegrations();});
const integrationNav=document.querySelector('[data-page="integrations"]');if(integrationNav)integrationNav.addEventListener('click',loadIntegrations);
