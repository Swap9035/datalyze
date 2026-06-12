/* Datalyze — app.js (Day 1) */

const API_BASE = '';

/* ── DOM refs ── */
const healthDot    = document.getElementById('health-dot');
const uploadZone   = document.getElementById('upload-zone');
const fileInput    = document.getElementById('file-input');
const filePill     = document.getElementById('file-pill');
const filePillName = document.getElementById('file-pill-name');
const clearFileBtn = document.getElementById('clear-file');
const exportBtn    = document.getElementById('export-btn');
const predictBtn   = document.getElementById('predict-btn');
const chatInput    = document.getElementById('chat-input');
const chatSend     = document.getElementById('chat-send');
const chatThread   = document.getElementById('chat-thread');
const activityFeed = document.getElementById('activity-feed');
const navItems     = document.querySelectorAll('.nav-item[data-view]');

/* ── State ── */
const state = {
  sessionId:   null,
  fileName:    null,
  fileLoaded:  false,
  currentView: 'upload',
};

/* ════════════════════════════════════════════
   1. HEALTH CHECK
════════════════════════════════════════════ */
async function checkHealth() {
  try {
    const res  = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    if (data.status === 'ok') {
      healthDot.className = 'health-dot health-ok';
      healthDot.title     = 'API connected';
    } else { throw new Error(); }
  } catch {
    healthDot.className = 'health-dot health-error';
    healthDot.title     = 'API unreachable — is uvicorn running?';
  }
}

/* ════════════════════════════════════════════
   2. NAVIGATION
════════════════════════════════════════════ */
function showView(name) {
  document.querySelectorAll('.view').forEach(v => {
    v.classList.remove('view--active');
    v.style.display = 'none';
  });
  navItems.forEach(n => n.classList.remove('active'));

  const target = document.getElementById(`view-${name}`);
  if (target) { target.style.display = 'flex'; target.classList.add('view--active'); }

  const nav = document.querySelector(`.nav-item[data-view="${name}"]`);
  if (nav) nav.classList.add('active');

  state.currentView = name;
}

navItems.forEach(item => {
  item.addEventListener('click', () => {
    const view = item.dataset.view;
    if (!state.fileLoaded && !['settings','notebooks'].includes(view)) {
      showView('upload');
      flashZone();
      return;
    }
    showView(view);
  });
});

/* ════════════════════════════════════════════
   3. UPLOAD ZONE
════════════════════════════════════════════ */
function setupUploadZone() {
  ['dragenter','dragover','dragleave','drop'].forEach(evt => {
    uploadZone.addEventListener(evt, e => { e.preventDefault(); e.stopPropagation(); });
    document.body.addEventListener(evt, e => e.preventDefault());
  });

  uploadZone.addEventListener('dragenter', () => uploadZone.classList.add('drag-over'));
  uploadZone.addEventListener('dragover',  () => uploadZone.classList.add('drag-over'));
  uploadZone.addEventListener('dragleave', e => {
    if (!uploadZone.contains(e.relatedTarget)) uploadZone.classList.remove('drag-over');
  });
  uploadZone.addEventListener('drop', e => {
    uploadZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) handleFile(fileInput.files[0]);
  });

  
}
document.querySelectorAll('.sample-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.sample;
      showUploadLoading(true);
      try {
        const fileRes = await fetch(`/static/samples/${name}.csv`);
        if (!fileRes.ok) throw new Error('Sample file not found. Add it to frontend/static/samples/');
        const blob = await fileRes.blob();
        const file = new File([blob], `${name}.csv`, { type: 'text/csv' });
        await handleFile(file);
      } catch (err) {
        showUploadError(err.message);
        showUploadLoading(false);
      }
    });
  });

async function handleFile(file) {
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!['.csv','.xlsx','.xls','.json'].includes(ext)) {
    showUploadError(`Unsupported type: ${ext}. Use CSV, Excel, or JSON.`);
    return;
  }

  showUploadLoading(true);

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }

    const data = await res.json();
    onUploadSuccess(data);

  } catch (err) {
    showUploadError(err.message || 'Upload failed. Is the server running?');
  } finally {
    showUploadLoading(false);
  }
}

async function onUploadSuccess(data) {
  state.sessionId  = data.session_id;
  state.fileName   = data.filename;
  state.fileLoaded = true;

  filePillName.textContent = data.filename;
  filePill.style.display   = 'flex';

  exportBtn.disabled  = false;
  predictBtn.disabled = false;
  chatInput.disabled  = false;
  chatSend.disabled   = false;

  showView('analysis');

  /* Initial metric cards from raw upload */
  updateMetricCards({
    rows: data.profile.rows,
    cols: data.profile.cols,
    qualityGrade: data.profile.quality_grade,
    outlierCount: '—',   // Day 6 will populate this
  });

  addActivity(`${data.filename} uploaded — ${data.profile.rows.toLocaleString()} rows, ${data.profile.cols} cols`, 'purple');

  chatThread.querySelector('.chat-welcome')?.remove();

  /* ── Day 3: run cleaning pipeline automatically ── */
  await runCleaningPipeline(data);

  fileInput.value = '';
}

async function runCleaningPipeline(uploadData) {
  try {
    const res = await fetch(`${API_BASE}/clean/${state.sessionId}`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Cleaning failed');
    }
    const data = await res.json();

    /* Update metric cards with POST-CLEANING data */
    updateMetricCards({
      rows: data.profile_after.rows,
      cols: data.profile_after.cols,
      qualityGrade: data.profile_after.quality_grade,
      outlierCount: '—',
    });

    /* Activity feed entries for each cleaning action */
    const r = data.report;

    if (r.cols_stripped.length > 0) {
      addActivity(`Trimmed whitespace in ${r.cols_stripped.length} column(s)`, 'purple');
    }
    if (r.cols_coerced.length > 0) {
      addActivity(`Converted ${r.cols_coerced.length} column(s) to numeric`, 'purple');
    }
    if (Object.keys(r.nulls_filled).length > 0) {
      const totalFilled = Object.values(r.nulls_filled).reduce((a, b) => a + b, 0);
      addActivity(`Filled ${totalFilled} missing value(s)`, 'teal');
    } else {
      addActivity('No missing values to fill', 'teal');
    }
    if (r.duplicates_removed > 0) {
      addActivity(`Removed ${r.duplicates_removed} duplicate row(s)`, 'amber');
    } else {
      addActivity('No duplicate rows found', 'teal');
    }

    /* Show cleaning report as a bot message + insights from upload */
    showCleaningReportInChat(data.summary, uploadData.insights);

  } catch (err) {
    addActivity(`Cleaning failed: ${err.message}`, 'red');
    /* Still show original insights even if cleaning fails */
    showInsightsInChat(uploadData.insights);
  }
}

function showCleaningReportInChat(summaryLines, insightLines) {
  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  const cleaningCard = `
    <div class="insight-card">
      <div class="insight-row">
        <div class="insight-label">Data cleaning report</div>
        ${summaryLines.map(l => `<div class="insight-text" style="margin-bottom:3px">${escHtml(l)}</div>`).join('')}
      </div>
    </div>`;

  const insightLinesHtml = insightLines
    .map(i => `<div class="bubble-msg" style="margin-bottom:4px">${escHtml(i)}</div>`)
    .join('');

  bubble.innerHTML = `
    <div class="bubble-avatar bubble-avatar--bot">DZ</div>
    <div class="bubble-body" style="gap:6px">
      ${insightLinesHtml}
      ${cleaningCard}
    </div>`;

  chatThread.appendChild(bubble);
  scrollChat();
}

  
function showInsightsInChat(insights) {
  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  const insightLines = insights.map(i => `<div class="bubble-msg" style="margin-bottom:4px">${escHtml(i)}</div>`).join('');

  bubble.innerHTML = `
    <div class="bubble-avatar bubble-avatar--bot">DZ</div>
    <div class="bubble-body" style="gap:4px">
      ${insightLines}
    </div>`;
  chatThread.appendChild(bubble);
  scrollChat();
}

function showUploadLoading(isLoading) {
  const inner = document.getElementById('upload-zone-inner');
  if (isLoading) {
    inner.style.opacity = '0.5';
    inner.style.pointerEvents = 'none';
  } else {
    inner.style.opacity = '1';
    inner.style.pointerEvents = 'auto';
  }
}
  

function flashZone() {
  uploadZone.classList.add('drag-over');
  setTimeout(() => uploadZone.classList.remove('drag-over'), 600);
}

function showUploadError(msg) {
  document.querySelector('.upload-error')?.remove();
  const el = document.createElement('p');
  el.className = 'upload-error';
  el.style.cssText = 'color:var(--red);font-size:11px;margin-top:8px;text-align:center';
  el.textContent = msg;
  document.getElementById('upload-zone-inner').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

clearFileBtn.addEventListener('click', () => {
  state.sessionId  = null;
  state.fileName   = null;
  state.fileLoaded = false;

  filePill.style.display = 'none';
  exportBtn.disabled     = true;
  predictBtn.disabled    = true;
  chatInput.disabled     = true;
  chatSend.disabled      = true;

  chatThread.innerHTML = `
    <div class="chat-welcome">
      <div class="welcome-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </div>
      <p class="welcome-title">Ask anything about your data</p>
      <p class="welcome-sub">Try: "What are the outliers?" · "Show survival by class" · "Which columns have nulls?"</p>
    </div>`;

  activityFeed.innerHTML = '<div class="activity-empty">No activity yet</div>';

  ['rows','cols','quality','outliers'].forEach(id => {
    document.getElementById(`mc-${id}`).classList.add('skeleton');
    document.getElementById(`mc-${id}-val`).textContent = '—';
  });

  showView('upload');
});

/* ════════════════════════════════════════════
   4. METRIC CARDS
   Called Day 2+ with real profile data.
════════════════════════════════════════════ */
function updateMetricCards({ rows, cols, qualityGrade, outlierCount }) {
  [
    { id:'rows',     val:rows?.toLocaleString() ?? '—', cls:'color-purple' },
    { id:'cols',     val:cols ?? '—',                   cls:'color-teal'   },
    { id:'quality',  val:qualityGrade ?? '—',           cls:'color-amber'  },
    { id:'outliers', val:outlierCount ?? '—',           cls:'color-red'    },
  ].forEach(({ id, val, cls }) => {
    const card  = document.getElementById(`mc-${id}`);
    const valEl = document.getElementById(`mc-${id}-val`);
    card.classList.remove('skeleton');
    valEl.textContent = val;
    valEl.className   = `metric-val ${cls}`;
  });
}

/* ════════════════════════════════════════════
   5. CHAT
════════════════════════════════════════════ */
function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || !state.fileLoaded) return;
  chatInput.value = '';
  chatThread.querySelector('.chat-welcome')?.remove();

  appendUserBubble(text);

  /* Day 9: replace with real POST /chat */
  appendBotThinking();
  setTimeout(() => {
    replaceBotThinking({ answer: `Chat live on Day 9. You asked: "${text}"` });
  }, 800);
}

chatSend.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

function appendUserBubble(text) {
  const el = document.createElement('div');
  el.className = 'bubble bubble--user';
  el.innerHTML = `
    <div class="bubble-avatar bubble-avatar--user">U</div>
    <div class="bubble-body">
      <div class="bubble-msg">${escHtml(text)}</div>
    </div>`;
  chatThread.appendChild(el);
  scrollChat();
}

let thinkingEl = null;

function appendBotThinking() {
  thinkingEl = document.createElement('div');
  thinkingEl.className = 'bubble';
  thinkingEl.innerHTML = `
    <div class="bubble-avatar bubble-avatar--bot">DZ</div>
    <div class="bubble-body">
      <div class="bubble-msg" style="color:var(--text-3)">Analysing…</div>
    </div>`;
  chatThread.appendChild(thinkingEl);
  scrollChat();
}

/*
  replaceBotThinking(response)
  Full shape used from Day 11:
  {
    answer:     string,
    chart:      plotlyJsonString | null,
    chart_type: string | null,
    insight:    { what_happened, why_it_matters, next_question } | null,
    method:     string | null
  }
*/
function replaceBotThinking(response) {
  if (!thinkingEl) return;
  const body = thinkingEl.querySelector('.bubble-body');
  body.innerHTML = '';

  /* 1. Text */
  const msg = document.createElement('div');
  msg.className   = 'bubble-msg';
  msg.textContent = response.answer;
  body.appendChild(msg);

  /* 2. Chart (Day 11+) */
  if (response.chart) {
    const wrap = document.createElement('div');
    wrap.className = 'chart-bubble';
    if (response.chart_type || response.method) {
      wrap.innerHTML = `<div class="chart-meta">${response.chart_type ?? ''}${response.method ? ` · <span>${escHtml(response.method)}</span>` : ''}</div>`;
    }
    const plotDiv = document.createElement('div');
    wrap.appendChild(plotDiv);
    body.appendChild(wrap);
    try {
      const fig = JSON.parse(response.chart);
      fig.layout = Object.assign({
        paper_bgcolor:'#161b27', plot_bgcolor:'#161b27',
        font:{ color:'#8892a4', family:'Inter,sans-serif', size:11 },
        margin:{ t:10, r:10, b:36, l:40 },
        xaxis:{ gridcolor:'#2a3147', linecolor:'#2a3147' },
        yaxis:{ gridcolor:'#2a3147', linecolor:'#2a3147' },
      }, fig.layout ?? {});
      Plotly.newPlot(plotDiv, fig.data, fig.layout, { responsive:true, displayModeBar:false });
    } catch(e) {
      plotDiv.textContent = 'Chart render error.';
      plotDiv.style.color = 'var(--text-3)';
    }
  }

  /* 3. Insight card (Day 11+) */
  if (response.insight) {
    const card = document.createElement('div');
    card.className = `insight-card${response.insight.trend === 'down' ? ' insight-card--warn' : ''}`;
    card.innerHTML = `
      <div class="insight-row"><div class="insight-label">What happened</div><div class="insight-text">${escHtml(response.insight.what_happened)}</div></div>
      <div class="insight-row"><div class="insight-label">Why it matters</div><div class="insight-text">${escHtml(response.insight.why_it_matters)}</div></div>
      <div class="insight-row"><div class="insight-label">Next question</div><div class="insight-text">${escHtml(response.insight.next_question)}</div></div>`;
    body.appendChild(card);
  }

  /* 4. Meta pills (Day 11+) */
  if (response.method || response.chart_type) {
    const pills = document.createElement('div');
    pills.className = 'meta-pills';
    if (response.method)     pills.innerHTML += `<span class="meta-pill">Method: <span>${escHtml(response.method)}</span></span>`;
    if (response.chart_type) pills.innerHTML += `<span class="meta-pill">Chart: <span>${escHtml(response.chart_type)}</span></span>`;
    body.appendChild(pills);
  }

  thinkingEl = null;
  scrollChat();
}

/* ════════════════════════════════════════════
   6. ACTIVITY FEED
════════════════════════════════════════════ */
function addActivity(text, colour = 'teal') {
  activityFeed.querySelector('.activity-empty')?.remove();
  const item = document.createElement('div');
  item.className = 'activity-item';
  item.innerHTML = `
    <div class="activity-dot activity-dot--${colour}"></div>
    <div>
      <div class="activity-text">${escHtml(text)}</div>
      <div class="activity-time">just now</div>
    </div>`;
  activityFeed.insertBefore(item, activityFeed.firstChild);
  while (activityFeed.children.length > 20) activityFeed.removeChild(activityFeed.lastChild);
}

/* ════════════════════════════════════════════
   7. UTILS
════════════════════════════════════════════ */
function scrollChat() { chatThread.scrollTop = chatThread.scrollHeight; }
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ════════════════════════════════════════════
   8. BOOT
════════════════════════════════════════════ */
(function init() {
  showView('upload');
  const uv = document.getElementById('view-upload');
  uv.style.display = 'flex';
  uv.classList.add('view--active');

  setupUploadZone();
  checkHealth();
  setInterval(checkHealth, 30_000);

  console.log('%cDatalyze Day 1 ready ✓', 'color:#7c6ef5;font-weight:600');
})();