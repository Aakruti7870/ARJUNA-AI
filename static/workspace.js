goto = function(page){
  document.querySelectorAll('.page').forEach(el=>el.classList.toggle('active',el.id===`page-${page}`));
  document.querySelectorAll('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.page===page));
  const titles={
    dashboard:['COMMAND CENTRE','Dashboard'],
    playground:['PROMPT LAB','Playground'],
    preview:['ISOLATED RENDERING','Preview Lab'],
    growth:['GROWTH OPERATING SYSTEM','Growth OS'],
    providers:['MODEL ROUTER','Providers'],
    keys:['ACCESS CONTROL','API Keys'],
    usage:['OBSERVABILITY','Usage'],
    settings:['PLATFORM','Settings']
  };
  const selected=titles[page]||['ARJUNA AI',page];
  $('pageKicker').textContent=selected[0];$('pageTitle').textContent=selected[1];$('nav').closest('.sidebar').classList.remove('open');
  if(page==='dashboard')loadDashboard();if(page==='providers')loadProviders();if(page==='keys')loadKeys();if(page==='usage')loadUsage();
  if(page==='growth'&&typeof loadGrowth==='function')loadGrowth();
};
