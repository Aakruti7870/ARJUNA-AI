const state = {
  token: sessionStorage.getItem('arjuna_session') || '',
  providers: [],
  currentProvider: null,
  recommendation: null,
  lastBuild: null,
};

const $ = (id) => document.getElementById(id);
const authView = $('authView');
const workspaceView = $('workspaceView');
const healthDot = $('healthDot');
const healthText = $('healthText');
const logoutButton = $('logoutButton');
const displayName = $('displayName');
const startFreeButton = $('startFreeButton');
const welcomeText = $('welcomeText');
const connectedCount = $('connectedCount');
const providerList = $('providerList');
const providerDialog = $('providerDialog');
const providerForm = $('providerForm');
const providerDialogTitle = $('providerDialogTitle');
const providerName = $('providerName');
const providerKey = $('providerKey');
const providerModel = $('providerModel');
const providerFree = $('providerFree');
const providerFormStatus = $('providerFormStatus');
const closeProviderDialog = $('closeProviderDialog');
const saveProviderButton = $('saveProviderButton');
const promptInput = $('promptInput');
const freeOnly = $('freeOnly');
const recommendButton = $('recommendButton');
const recommendedTitle = $('recommendedTitle');
const recommendedMeta = $('recommendedMeta');
const routeScore = $('routeScore');
const routeAlternatives = $('routeAlternatives');
const taskTypeBadge = $('taskTypeBadge');
const buildButton = $('buildButton');
const buildStatus = $('buildStatus');
const previewFrame = $('previewFrame');
const previewEmpty = $('previewEmpty');
const previewTitle = $('previewTitle');
const routeMeta = $('routeMeta');
const codeOutput = $('codeOutput');
const resultTitle = $('resultTitle');
const resultSummary = $('resultSummary');
const resultNotes = $('resultNotes');

function setStatus(element, text, type = '') {
  element.textContent = text;
  element.classList.remove('error', 'success');
  if (type) element.classList.add(type);
}

async function checkHealth() {
  try {
    const response = await fetch('/healthz', { cache: 'no-store' });
    if (!response.ok) throw new Error('offline');
    healthDot.classList.add('ok');
    healthDot.classList.remove('bad');
    healthText.textContent = 'Gateway online';
  } catch (_) {
    healthDot.classList.add('bad');
    healthDot.classList.remove('ok');
    healthText.textContent = 'Gateway unavailable';
  }
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');

  const response = await fetch(path, { ...options, headers, cache: 'no-store' });
  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    payload = null;
  }

  if (response.status === 401 && path !== '/api/auth/guest') {
    clearSession();
    throw new Error('Your free session expired. Start a new session.');
  }
  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`);
  }
  return payload;
}

function clearSession() {
  state.token = '';
  state.providers = [];
  state.recommendation = null;
  state.lastBuild = null;
  sessionStorage.removeItem('arjuna_session');
  authView.classList.remove('hidden');
  workspaceView.classList.add('hidden');
  logoutButton.classList.add('hidden');
  previewFrame.removeAttribute('src');
  previewEmpty.classList.remove('hidden');
}

function showWorkspace(session) {
  authView.classList.add('hidden');
  workspaceView.classList.remove('hidden');
  logoutButton.classList.remove('hidden');
  welcomeText.textContent = `Good to see you, ${session.user?.name || 'Creator'}. What should ARJUNA build?`;
}

async function startFreeSession() {
  startFreeButton.disabled = true;
  startFreeButton.textContent = 'STARTING…';
  try {
    const result = await api('/api/auth/guest', {
      method: 'POST',
      body: JSON.stringify({ display_name: displayName.value.trim() || 'Creator' }),
    });
    state.token = result.token;
    sessionStorage.setItem('arjuna_session', result.token);
    showWorkspace(result);
    await loadProviders();
    promptInput.focus();
  } catch (error) {
    alert(error.message || 'Could not start ARJUNA session.');
  } finally {
    startFreeButton.disabled = false;
    startFreeButton.textContent = 'CONTINUE FREE →';
  }
}

async function restoreSession() {
  if (!state.token) return;
  try {
    const session = await api('/api/session');
    showWorkspace(session);
    await loadProviders();
  } catch (_) {
    clearSession();
  }
}

function providerInitial(label) {
  const parts = label.split(/\s+/).filter(Boolean);
  return parts.map((part) => part[0]).join('').slice(0, 2).toUpperCase();
}

function renderProviders() {
  providerList.replaceChildren();
  const connected = state.providers.filter((provider) => provider.connected).length;
  connectedCount.textContent = `${connected} provider${connected === 1 ? '' : 's'}`;

  state.providers.forEach((provider) => {
    const card = document.createElement('div');
    card.className = 'provider-card';

    const logo = document.createElement('div');
    logo.className = 'provider-logo';
    logo.textContent = providerInitial(provider.label);

    const info = document.createElement('div');
    info.className = 'provider-info';
    const title = document.createElement('strong');
    title.textContent = provider.label;
    const meta = document.createElement('small');
    meta.textContent = provider.connected
      ? `${provider.model} · ${provider.free_eligible ? 'free-eligible' : 'standard'}`
      : `${provider.free_eligible ? 'Free route supported' : 'BYOK'} · not connected`;
    info.append(title, meta);

    const action = document.createElement('button');
    action.type = 'button';
    action.className = `provider-action${provider.connected ? ' connected' : ''}`;
    action.textContent = provider.connected ? 'Disconnect' : 'Connect';
    action.addEventListener('click', () => {
      if (provider.connected) disconnectProvider(provider.provider);
      else openProviderDialog(provider);
    });

    card.append(logo, info, action);
    providerList.append(card);
  });

  updateBuildAvailability();
}

async function loadProviders() {
  const result = await api('/api/providers');
  state.providers = result.data || [];
  renderProviders();
}

function openProviderDialog(provider) {
  state.currentProvider = provider;
  providerName.value = provider.provider;
  providerDialogTitle.textContent = provider.label;
  providerKey.value = '';
  providerModel.value = provider.model || '';
  providerFree.checked = Boolean(provider.free_eligible);
  setStatus(providerFormStatus, '');
  providerDialog.showModal();
  setTimeout(() => providerKey.focus(), 30);
}

async function connectProvider(event) {
  event.preventDefault();
  if (!state.currentProvider) return;
  saveProviderButton.disabled = true;
  saveProviderButton.textContent = 'CONNECTING…';
  setStatus(providerFormStatus, 'Saving key to this server session…');

  try {
    await api('/api/providers/connect', {
      method: 'POST',
      body: JSON.stringify({
        provider: providerName.value,
        api_key: providerKey.value.trim(),
        model: providerModel.value.trim(),
        free_eligible: providerFree.checked,
      }),
    });
    providerKey.value = '';
    setStatus(providerFormStatus, 'Provider connected.', 'success');
    await loadProviders();
    setTimeout(() => providerDialog.close(), 350);
    if (promptInput.value.trim().length >= 3) await recommendRoute();
  } catch (error) {
    setStatus(providerFormStatus, error.message || 'Could not connect provider.', 'error');
  } finally {
    saveProviderButton.disabled = false;
    saveProviderButton.textContent = 'CONNECT PROVIDER';
  }
}

async function disconnectProvider(name) {
  try {
    await api(`/api/providers/${encodeURIComponent(name)}`, { method: 'DELETE' });
    await loadProviders();
    state.recommendation = null;
    renderRecommendation({ recommended: null, routes: [], requires_provider: true });
  } catch (error) {
    setStatus(buildStatus, error.message || 'Could not disconnect provider.', 'error');
  }
}

function renderRecommendation(result) {
  state.recommendation = result.recommended || null;
  routeAlternatives.replaceChildren();

  if (!result.recommended) {
    recommendedTitle.textContent = result.requires_provider ? 'Connect an AI provider first' : 'No eligible route found';
    recommendedMeta.textContent = 'Add a provider key or disable Free routes only.';
    routeScore.textContent = '—';
    taskTypeBadge.textContent = 'Waiting';
    updateBuildAvailability();
    return;
  }

  const best = result.recommended;
  recommendedTitle.textContent = `${best.label} · ${best.model}`;
  recommendedMeta.textContent = `Selected for ${best.task} · ${best.free_eligible ? 'free-eligible' : 'standard route'}`;
  routeScore.textContent = `${Math.round(best.score)}`;
  taskTypeBadge.textContent = best.task.toUpperCase();

  (result.routes || []).slice(1, 5).forEach((route) => {
    const pill = document.createElement('span');
    pill.className = 'route-pill';
    pill.textContent = `${route.label} ${Math.round(route.score)}`;
    routeAlternatives.append(pill);
  });

  updateBuildAvailability();
}

async function recommendRoute() {
  const prompt = promptInput.value.trim();
  if (prompt.length < 3) {
    setStatus(buildStatus, 'Enter a prompt first.', 'error');
    return null;
  }

  recommendButton.disabled = true;
  recommendButton.textContent = 'ANALYSING…';
  try {
    const result = await api('/api/router/recommend', {
      method: 'POST',
      body: JSON.stringify({ prompt, free_only: freeOnly.checked }),
    });
    renderRecommendation(result);
    setStatus(
      buildStatus,
      result.recommended ? `ARJUNA recommends ${result.recommended.label}.` : 'No eligible route is available.',
      result.recommended ? 'success' : 'error',
    );
    return result;
  } catch (error) {
    setStatus(buildStatus, error.message || 'Router analysis failed.', 'error');
    return null;
  } finally {
    recommendButton.disabled = false;
    recommendButton.textContent = 'FIND BEST AI';
  }
}

function updateBuildAvailability() {
  const hasProvider = state.providers.some((provider) => provider.connected && (!freeOnly.checked || provider.free_eligible));
  const hasPrompt = promptInput.value.trim().length >= 3;
  buildButton.disabled = !(hasProvider && hasPrompt);
  if (!hasProvider) setStatus(buildStatus, 'Connect at least one eligible AI provider.');
  else if (!hasPrompt) setStatus(buildStatus, 'Enter a prompt to continue.');
}

function setStep(id, mode) {
  const element = $(id);
  if (!element) return;
  element.classList.remove('active', 'done');
  if (mode) element.classList.add(mode);
}

function renderBuild(result) {
  state.lastBuild = result;
  previewTitle.textContent = result.title || 'ARJUNA preview';
  routeMeta.textContent = `${result.provider} · ${result.model} · ${result.latency_ms} ms`;
  codeOutput.textContent = result.html || 'No HTML returned.';
  resultTitle.textContent = result.title || 'ARJUNA Result';
  resultSummary.textContent = result.summary || 'Build completed.';
  resultNotes.replaceChildren();
  (result.notes || []).forEach((note) => {
    const item = document.createElement('li');
    item.textContent = String(note);
    resultNotes.append(item);
  });

  previewFrame.src = `/api/previews/${encodeURIComponent(result.preview_id)}`;
  previewEmpty.classList.add('hidden');
  activateTab('preview');

  taskTypeBadge.textContent = String(result.task || 'BUILD').toUpperCase();
  recommendedTitle.textContent = `${result.provider} · ${result.model}`;
  recommendedMeta.textContent = `Build completed via ARJUNA smart routing · ${result.latency_ms} ms`;
  routeScore.textContent = `${Math.round(result.score || 0)}`;

  setStep('providerStep', 'done');
  setStep('promptStep', 'done');
  setStep('routerStep', 'done');
  setStep('previewStep', 'active');
}

async function buildWithArjuna() {
  const prompt = promptInput.value.trim();
  if (prompt.length < 3) return;

  buildButton.disabled = true;
  buildButton.textContent = 'ARJUNA IS BUILDING…';
  setStatus(buildStatus, 'Analysing task → scoring providers → executing best route → preparing preview…');
  setStep('promptStep', 'done');
  setStep('routerStep', 'active');

  try {
    const recommendation = await recommendRoute();
    if (!recommendation?.recommended) throw new Error('No eligible AI route is available for this prompt.');

    const result = await api('/api/build', {
      method: 'POST',
      body: JSON.stringify({ prompt, free_only: freeOnly.checked }),
    });
    renderBuild(result);
    const fallbackText = result.fallbacks_before_success?.length
      ? ` after ${result.fallbacks_before_success.length} fallback attempt(s)`
      : '';
    setStatus(buildStatus, `Build complete with ${result.provider}${fallbackText}.`, 'success');
  } catch (error) {
    setStep('routerStep', 'active');
    setStatus(buildStatus, error.message || 'Build failed.', 'error');
  } finally {
    buildButton.textContent = 'BUILD WITH ARJUNA →';
    updateBuildAvailability();
  }
}

function activateTab(name) {
  document.querySelectorAll('.tab').forEach((button) => {
    button.classList.toggle('active', button.dataset.tab === name);
  });
  document.querySelectorAll('.tab-pane').forEach((pane) => pane.classList.remove('active'));
  $(`${name}Pane`)?.classList.add('active');
}

startFreeButton.addEventListener('click', startFreeSession);
displayName.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') startFreeSession();
});
logoutButton.addEventListener('click', clearSession);
providerForm.addEventListener('submit', connectProvider);
closeProviderDialog.addEventListener('click', () => {
  providerKey.value = '';
  providerDialog.close();
});
recommendButton.addEventListener('click', recommendRoute);
buildButton.addEventListener('click', buildWithArjuna);
promptInput.addEventListener('input', () => {
  state.recommendation = null;
  setStep('promptStep', promptInput.value.trim().length >= 3 ? 'active' : '');
  setStep('routerStep', '');
  setStep('previewStep', state.lastBuild ? 'done' : '');
  updateBuildAvailability();
});
freeOnly.addEventListener('change', () => {
  state.recommendation = null;
  renderRecommendation({ recommended: null, routes: [], requires_provider: false });
  updateBuildAvailability();
});
document.querySelectorAll('.tab').forEach((button) => {
  button.addEventListener('click', () => activateTab(button.dataset.tab));
});

checkHealth();
restoreSession();
updateBuildAvailability();
