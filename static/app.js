const healthDot = document.getElementById('healthDot');
const healthText = document.getElementById('healthText');
const platformKey = document.getElementById('platformKey');
const model = document.getElementById('model');
const freeOnly = document.getElementById('freeOnly');
const promptInput = document.getElementById('prompt');
const sendButton = document.getElementById('sendButton');
const output = document.getElementById('output');
const routeMeta = document.getElementById('routeMeta');

async function checkHealth() {
  try {
    const response = await fetch('/healthz', { cache: 'no-store' });
    if (!response.ok) throw new Error('Service unavailable');
    healthDot.classList.add('ok');
    healthDot.classList.remove('bad');
    healthText.textContent = 'Gateway online';
  } catch (_) {
    healthDot.classList.add('bad');
    healthDot.classList.remove('ok');
    healthText.textContent = 'Gateway unavailable';
  }
}

function extractText(data) {
  const content = data?.choices?.[0]?.message?.content;
  if (typeof content === 'string') return content;
  if (content !== undefined) return JSON.stringify(content, null, 2);
  return JSON.stringify(data, null, 2);
}

async function sendPrompt() {
  const token = platformKey.value.trim();
  const prompt = promptInput.value.trim();
  if (!token) {
    output.textContent = 'Enter your ARJUNA platform API key.';
    platformKey.focus();
    return;
  }
  if (!prompt) {
    output.textContent = 'Enter a prompt first.';
    promptInput.focus();
    return;
  }

  sendButton.disabled = true;
  sendButton.textContent = 'ROUTING…';
  routeMeta.textContent = 'Request in progress';
  output.textContent = 'ARJUNA is selecting an eligible route…';

  try {
    const response = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: model.value.trim() || 'auto',
        free_only: freeOnly.checked,
        messages: [{ role: 'user', content: prompt }]
      })
    });

    let data;
    try {
      data = await response.json();
    } catch (_) {
      data = { detail: `HTTP ${response.status}` };
    }

    if (!response.ok) {
      const detail = data?.detail || `Request failed with HTTP ${response.status}`;
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }

    const provider = response.headers.get('X-Arjuna-Provider') || 'unknown';
    const selectedModel = response.headers.get('X-Arjuna-Model') || 'unknown';
    const latency = response.headers.get('X-Arjuna-Latency-Ms');
    routeMeta.textContent = `${provider} · ${selectedModel}${latency ? ` · ${latency} ms` : ''}`;
    output.textContent = extractText(data);
  } catch (error) {
    routeMeta.textContent = 'Request failed';
    output.textContent = error instanceof Error ? error.message : 'Unknown request error';
  } finally {
    sendButton.disabled = false;
    sendButton.textContent = 'SEND TO ARJUNA';
  }
}

sendButton.addEventListener('click', sendPrompt);
promptInput.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') sendPrompt();
});

checkHealth();
