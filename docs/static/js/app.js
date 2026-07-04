/* Datalyze — app.js (Day 1) */

const API_BASE = 'https://datalyze-api.onrender.com';

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
  colStats:    null,   // populated Day 5 — deep per-column stats
  llmContext:  null,   // populated Day 5 — pre-built text for LLM (Day 9)
  outlierData: null,   // populated Day 6 — outlier detection results
  modelData:   null,   // populated Day 7
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

  document.querySelectorAll('.sample-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.sample;
      showUploadLoading(true);
      try {
        const fileRes = await fetch(`static/samples/${name}.csv`);
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
}

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
  /* Show suggestions bar */
  const sugBar = document.getElementById('suggestions-bar');
  if (sugBar) sugBar.style.display = 'flex';

  /* ── Day 3: run cleaning pipeline automatically ── */
  await runCleaningPipeline(data);

  fileInput.value = '';
}

async function runCleaningPipeline(uploadData) {
  try {
    setLoadingBar(20);
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

    
    showCleaningReportInChat(data.summary, uploadData.insights);
    setLoadingBar(60);
    await fetchAndCacheStats();
    setLoadingBar(100);

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
  showToast('Dataset cleared', 'amber');
  questionCount = 0;
  const sugBar = document.getElementById('suggestions-bar');
  if (sugBar) sugBar.style.display = 'none';
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
async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || !state.fileLoaded) return;

  chatInput.value    = '';
  chatInput.disabled = true;
  chatSend.disabled  = true;

  chatThread.querySelector('.chat-welcome')?.remove();
  appendUserBubble(text);
  appendBotThinkingAnimated();
  setLoadingBar(30);

  try {
    const res = await fetch(`${API_BASE}/chat/${state.sessionId}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ question: text }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Chat failed');
    }

    const data = await res.json();
    setLoadingBar(100);
    replaceBotThinking(data);
    updateSuggestions(data.question_type || 'general');
    incrementQuestionBadge();

  } catch (err) {
    setLoadingBar(100);
    replaceBotThinking({
      answer: `Error: ${err.message}. Is the server running?`,
    });
  } finally {
    chatInput.disabled = false;
    chatSend.disabled  = false;
    chatInput.focus();
  }
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

  console.log('%cDatalyze v1.0 ready ✓', 'color:#7c6ef5;font-weight:600;font-size:14px');
})();

async function fetchAndCacheStats() {
  if (!state.sessionId) return;
  try {
    const res = await fetch(`${API_BASE}/stats/${state.sessionId}`);
    if (!res.ok) return;
    const data = await res.json();

    /* Store in state for use by chat (Day 9+) */
    state.colStats   = data.col_stats;
    state.llmContext = data.llm_context;

    /* Count total outliers across all numeric columns */
    const totalOutliers = Object.values(data.col_stats)
      .filter(s => s.kind === 'numeric')
      .reduce((sum, s) => sum + (s.outlier_count || 0), 0);

    /* Update outlier metric card with real number */
    updateMetricCards({
      rows:         data.profile.rows,
      cols:         data.profile.cols,
      qualityGrade: data.profile.quality_grade,
      outlierCount: totalOutliers,
    });

    if (totalOutliers > 0) {
      addActivity(`${totalOutliers} outlier(s) detected across numeric columns`, 'red');
    }

    await fetchOutlierReport();


  } catch (err) {
    console.warn('Stats fetch failed:', err.message);
  }
}

async function fetchOutlierReport() {
  if (!state.sessionId) return;
  try {
    const res = await fetch(`${API_BASE}/outliers/${state.sessionId}`);
    if (!res.ok) return;
    const data = await res.json();

    /* Cache for LLM context Day 9 */
    state.outlierData = data;

    /* Show outlier summary as insight card in chat */
    if (data.summary && data.summary.length > 0) {
      showOutlierCardInChat(data);
    }

     await trainModel();

  } catch (err) {
    console.warn('Outlier fetch failed:', err.message);
  }
}

function showOutlierCardInChat(data) {
  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  /* Build per-column breakdown for top 3 columns */
  const topCols = Object.entries(data.iqr_results)
    .sort((a, b) => b[1].outlier_count - a[1].outlier_count)
    .slice(0, 3);

  const colRows = topCols.map(([col, info]) => `
    <div style="display:flex;justify-content:space-between;
                padding:4px 0;border-bottom:0.5px solid rgba(245,101,101,.15);
                font-size:11px">
      <span style="color:#e8eaf0;font-weight:500">${escHtml(col)}</span>
      <span style="color:#f56565">${info.outlier_count} outliers</span>
      <span style="color:#5a6378">${info.high_count}↑ ${info.low_count}↓</span>
      <span style="color:#5a6378">fence: ${info.lower_fence} – ${info.upper_fence}</span>
    </div>`).join('');

  /* Method comparison pills */
  const compPills = data.comparison
    .filter(c => c.iqr_count > 0 || c.zscore_count > 0)
    .slice(0, 4)
    .map(c => `
      <div style="font-size:10px;padding:3px 8px;
                  background:var(--surface-3);border:0.5px solid var(--border);
                  border-radius:10px;color:var(--text-2)">
        ${escHtml(c.column)}: IQR=${c.iqr_count} · Z=${c.zscore_count}
        <span style="color:${c.agreement === 'high' ? 'var(--teal)' : 'var(--amber)'}">
          (${c.agreement} agreement)
        </span>
      </div>`).join('');

  bubble.innerHTML = `
    <div class="bubble-avatar bubble-avatar--bot">DZ</div>
    <div class="bubble-body" style="gap:6px">
      <div class="insight-card insight-card--warn">
        <div class="insight-row">
          <div class="insight-label">Outlier Detection Report</div>
          ${data.summary.map(l =>
            `<div class="insight-text" style="margin-bottom:3px">${escHtml(l)}</div>`
          ).join('')}
        </div>
        <div class="insight-row">
          <div class="insight-label">Top columns by outlier count</div>
          <div style="margin-top:4px">${colRows}</div>
        </div>
        <div class="insight-row">
          <div class="insight-label">IQR vs Z-score comparison</div>
          <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:5px">
            ${compPills}
          </div>
        </div>
      </div>
    </div>`;

  chatThread.appendChild(bubble);
  scrollChat();
}

/* ════════════════════════════════════════════
   ML MODEL — Day 7
════════════════════════════════════════════ */
async function trainModel() {
  if (!state.sessionId) return;
  try {
    const res = await fetch(`${API_BASE}/train/${state.sessionId}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json();
      console.warn('Training failed:', err.detail);
      addActivity('Model training skipped — target column not found', 'amber');
      return;
    }
    const data = await res.json();
    state.modelData = data;

    /* Activity feed */
    addActivity(
      `Model trained — accuracy: ${data.metrics.accuracy}%`,
      'teal'
    );
    showToast(`Model trained — ${data.metrics.accuracy}% accuracy`, 'teal');
    pulseButton(predictBtn);

    /* Show model card in chat */
    showModelCardInChat(data);

    /* Show prediction panel in right sidebar */
    showPredictionPanel(data);

  } catch (err) {
    console.warn('Model training error:', err.message);
  }
}

function showModelCardInChat(data) {
  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  const fi = data.feature_importance;

  /* Metric pills */
  const metricPills = Object.entries(data.metrics)
    .map(([key, val]) => `
      <div style="display:flex;flex-direction:column;align-items:center;
                  background:var(--surface-3);border:0.5px solid var(--border);
                  border-radius:8px;padding:8px 12px;min-width:70px">
        <span style="font-size:16px;font-weight:600;color:var(--accent)">${val}%</span>
        <span style="font-size:9px;color:var(--text-3);text-transform:uppercase;
                     letter-spacing:.05em;margin-top:2px">${key}</span>
      </div>`).join('');

  /* Feature importance bars */
  const maxAbs = Math.max(...fi.map(f => f.abs_impact));
  const fiBars = fi.slice(0, 5).map(f => {
    const pct   = maxAbs > 0 ? (f.abs_impact / maxAbs * 100).toFixed(1) : 0;
    const color = f.direction === 'positive' ? 'var(--teal)' : 'var(--red)';
    const sign  = f.coefficient > 0 ? '+' : '';
    return `
      <div style="margin-bottom:6px">
        <div style="display:flex;justify-content:space-between;
                    font-size:11px;margin-bottom:3px">
          <span style="color:var(--text)">${escHtml(f.feature)}</span>
          <span style="color:${color};font-family:var(--mono)">
            ${sign}${f.coefficient}
          </span>
        </div>
        <div style="height:4px;background:var(--surface-3);border-radius:2px">
          <div style="height:100%;width:${pct}%;background:${color};
                      border-radius:2px;transition:width .4s"></div>
        </div>
      </div>`;
  }).join('');

  /* Confusion matrix */
  const cm = data.confusion_matrix;
  const cmHtml = cm ? `
    <div style="margin-top:8px">
      <div style="font-size:10px;color:var(--text-3);text-transform:uppercase;
                  letter-spacing:.05em;margin-bottom:6px">Confusion matrix</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;max-width:160px">
        <div style="background:rgba(45,212,160,.1);border:0.5px solid rgba(45,212,160,.2);
                    border-radius:6px;padding:6px;text-align:center">
          <div style="font-size:14px;font-weight:600;color:var(--teal)">${cm[0][0]}</div>
          <div style="font-size:9px;color:var(--text-3)">True Neg</div>
        </div>
        <div style="background:rgba(245,101,101,.1);border:0.5px solid rgba(245,101,101,.2);
                    border-radius:6px;padding:6px;text-align:center">
          <div style="font-size:14px;font-weight:600;color:var(--red)">${cm[0][1]}</div>
          <div style="font-size:9px;color:var(--text-3)">False Pos</div>
        </div>
        <div style="background:rgba(245,101,101,.1);border:0.5px solid rgba(245,101,101,.2);
                    border-radius:6px;padding:6px;text-align:center">
          <div style="font-size:14px;font-weight:600;color:var(--red)">${cm[1][0]}</div>
          <div style="font-size:9px;color:var(--text-3)">False Neg</div>
        </div>
        <div style="background:rgba(45,212,160,.1);border:0.5px solid rgba(45,212,160,.2);
                    border-radius:6px;padding:6px;text-align:center">
          <div style="font-size:14px;font-weight:600;color:var(--teal)">${cm[1][1]}</div>
          <div style="font-size:9px;color:var(--text-3)">True Pos</div>
        </div>
      </div>
    </div>` : '';

  bubble.innerHTML = `
    <div class="bubble-avatar bubble-avatar--bot">DZ</div>
    <div class="bubble-body" style="gap:6px">
      <div class="insight-card">
        <div class="insight-row">
          <div class="insight-label">ML Model — Logistic Regression</div>
          <div style="font-size:11px;color:var(--text-2);margin-bottom:8px">
            Trained on ${data.train_size} rows · Tested on ${data.test_size} rows
            (80/20 split, random_state=42)
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            ${metricPills}
          </div>
          ${cmHtml}
        </div>
        <div class="insight-row">
          <div class="insight-label">Feature importance (coefficients)</div>
          <div style="margin-top:6px">${fiBars}</div>
          <div style="font-size:10px;color:var(--text-3);margin-top:6px">
            Positive coefficient = increases survival probability.
            Negative = decreases it.
          </div>
        </div>
        <div class="insight-row">
          <div class="insight-label">Next step</div>
          <div class="insight-text">
            Click "Run prediction" in the topbar to predict survival
            for a custom passenger.
          </div>
        </div>
      </div>
    </div>`;

  chatThread.appendChild(bubble);
  scrollChat();
}

function showPredictionPanel(data) {
  updatePredictionsPage(data);
  const panel = document.getElementById('rp-prediction');
  const card  = document.getElementById('prediction-card');
  panel.style.display = 'block';

  const fi = data.feature_importance.slice(0, 3);
  card.innerHTML = `
    <div class="pred-label">Model ready</div>
    <div class="pred-value" style="font-size:13px">
      Accuracy: ${data.metrics.accuracy}%
    </div>
    <div class="pred-conf">F1: ${data.metrics.f1}%</div>
    <div class="pred-features">
      ${fi.map(f => `
        <div class="pred-feat-row">
          <span>${escHtml(f.feature)}</span>
          <span>${f.coefficient > 0 ? '+' : ''}${f.coefficient}</span>
        </div>`).join('')}
    </div>`;
}

/* ── Run prediction button ── */
predictBtn.addEventListener('click', () => {
  if (!state.modelData) {
    alert('Please upload a dataset first — model trains automatically.');
    return;
  }
  showPredictModal();
});

function showPredictModal() {
  /* Remove existing modal if any */
  document.getElementById('predict-modal')?.remove();

  const modal = document.createElement('div');
  modal.id = 'predict-modal';
  modal.style.cssText = `
    position:fixed;inset:0;background:rgba(0,0,0,.7);
    display:flex;align-items:center;justify-content:center;z-index:200`;

  modal.innerHTML = `
    <div style="background:var(--surface);border:0.5px solid var(--border-2);
                border-radius:12px;padding:24px;width:380px;max-width:90vw">
      <div style="display:flex;justify-content:space-between;align-items:center;
                  margin-bottom:16px">
        <span style="font-size:14px;font-weight:500;color:var(--text)">
          Predict Survival
        </span>
        <button onclick="document.getElementById('predict-modal').remove()"
                style="background:none;border:none;color:var(--text-3);
                       font-size:18px;cursor:pointer">×</button>
      </div>
      ${buildInputField('Pclass',  'Passenger Class (1, 2, or 3)', '1')}
      ${buildInputField('Sex',     'Sex (male / female)', 'female')}
      ${buildInputField('Age',     'Age (years)', '29')}
      ${buildInputField('Fare',    'Fare paid (£)', '100')}
      ${buildInputField('SibSp',   'Siblings / Spouses aboard', '0')}
      ${buildInputField('Parch',   'Parents / Children aboard', '0')}
      <button onclick="submitPrediction()"
              style="width:100%;margin-top:16px;padding:9px;
                     background:var(--accent-dim);
                     border:0.5px solid rgba(124,110,245,.35);
                     border-radius:8px;color:var(--accent);
                     font-size:13px;font-weight:500;cursor:pointer">
        Run prediction →
      </button>
      <div id="predict-result" style="margin-top:12px"></div>
    </div>`;

  document.body.appendChild(modal);

  /* Close on backdrop click */
  modal.addEventListener('click', e => {
    if (e.target === modal) modal.remove();
  });
}

function buildInputField(name, label, placeholder) {
  return `
    <div style="margin-bottom:10px">
      <label style="display:block;font-size:11px;color:var(--text-3);
                    text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">
        ${label}
      </label>
      <input id="input-${name}" value="${placeholder}"
             style="width:100%;background:var(--surface-2);
                    border:0.5px solid var(--border);border-radius:6px;
                    color:var(--text);padding:7px 10px;font-size:12px;
                    outline:none" />
    </div>`;
}

async function submitPrediction() {
  const inputData = {
    Pclass: parseFloat(document.getElementById('input-Pclass').value),
    Sex:    document.getElementById('input-Sex').value.trim(),
    Age:    parseFloat(document.getElementById('input-Age').value),
    Fare:   parseFloat(document.getElementById('input-Fare').value),
    SibSp:  parseFloat(document.getElementById('input-SibSp').value),
    Parch:  parseFloat(document.getElementById('input-Parch').value),
  };

  const resultDiv = document.getElementById('predict-result');
  resultDiv.innerHTML = `<p style="color:var(--text-3);font-size:12px">Predicting…</p>`;

  try {
    const res = await fetch(`${API_BASE}/predict/${state.sessionId}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(inputData),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail);
    }

    const data = await res.json();
    const survived = data.prediction === 1;
    const color    = survived ? 'var(--teal)' : 'var(--red)';

    resultDiv.innerHTML = `
      <div style="background:var(--surface-2);border:0.5px solid ${color};
                  border-radius:8px;padding:12px;margin-top:4px">
        <div style="font-size:16px;font-weight:600;color:${color};margin-bottom:4px">
          ${escHtml(data.label)}
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:8px">
          ${data.confidence}% confidence ·
          Survived: ${data.prob_survived}% ·
          Not: ${data.prob_not}%
        </div>
        <div style="font-size:10px;color:var(--text-3);
                    text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px">
          Top influencing features
        </div>
        ${data.top_features.map(f => `
          <div style="display:flex;justify-content:space-between;
                      font-size:11px;padding:2px 0;color:var(--text-2)">
            <span>${escHtml(f.feature)}</span>
            <span style="color:${f.direction === 'positive' ?
              'var(--teal)' : 'var(--red)'};font-family:var(--mono)">
              ${f.coefficient > 0 ? '+' : ''}${f.coefficient}
            </span>
          </div>`).join('')}
      </div>`;

    /* Also show in activity feed */
    addActivity(
      `Prediction: ${data.label} (${data.confidence}% confidence)`,
      survived ? 'teal' : 'red'
    );

    /* Update right panel */
    const card = document.getElementById('prediction-card');
    if (card) {
      card.innerHTML = `
        <div class="pred-label">Latest prediction</div>
        <div class="pred-value" style="color:${color}">${escHtml(data.label)}</div>
        <div class="pred-conf">${data.confidence}% confidence</div>
        <div class="pred-features">
          ${data.top_features.map(f => `
            <div class="pred-feat-row">
              <span>${escHtml(f.feature)}</span>
              <span>${f.coefficient > 0 ? '+' : ''}${f.coefficient}</span>
            </div>`).join('')}
        </div>`;
    }

  } catch (err) {
    resultDiv.innerHTML = `
      <p style="color:var(--red);font-size:12px">Error: ${escHtml(err.message)}</p>`;
  }
}

/* ════════════════════════════════════════════
   EXPORT — Day 12
════════════════════════════════════════════ */
exportBtn.addEventListener('click', () => {
  if (!state.sessionId) return;
  showExportMenu();
});

function showExportMenu() {
  document.getElementById('export-menu')?.remove();

  const menu = document.createElement('div');
  menu.id = 'export-menu';
  menu.style.cssText = `
    position:fixed;top:52px;right:16px;
    background:var(--surface);border:0.5px solid var(--border-2);
    border-radius:8px;padding:6px;z-index:150;
    box-shadow:0 8px 24px rgba(0,0,0,.4);min-width:180px`;

  menu.innerHTML = `
    <div style="font-size:10px;color:var(--text-3);
                text-transform:uppercase;letter-spacing:.05em;
                padding:4px 8px;margin-bottom:4px">Export as</div>
    <button onclick="downloadReport()"
            style="display:block;width:100%;text-align:left;
                   padding:7px 10px;background:none;border:none;
                   color:var(--text-2);font-size:12px;border-radius:6px;
                   cursor:pointer"
            onmouseover="this.style.background='var(--surface-2)'"
            onmouseout="this.style.background='none'">
      📄 Markdown report (.md)
    </button>
    <button onclick="downloadCSV()"
            style="display:block;width:100%;text-align:left;
                   padding:7px 10px;background:none;border:none;
                   color:var(--text-2);font-size:12px;border-radius:6px;
                   cursor:pointer"
            onmouseover="this.style.background='var(--surface-2)'"
            onmouseout="this.style.background='none'">
      📊 Column summary (.csv)
    </button>`;

  document.body.appendChild(menu);

  setTimeout(() => {
    document.addEventListener('click', function handler(e) {
      if (!menu.contains(e.target) && e.target !== exportBtn) {
        menu.remove();
        document.removeEventListener('click', handler);
      }
    });
  }, 100);
}

async function downloadReport() {
  document.getElementById('export-menu')?.remove();
  if (!state.sessionId) return;

  try { await fetch(`${API_BASE}/trends/${state.sessionId}`); } catch {}

  const a   = document.createElement('a');
  a.href    = `${API_BASE}/export/report/${state.sessionId}`;
  a.download = 'datalyze_report.md';
  a.click();

  addActivity('Markdown report downloaded', 'teal');
  showToast('Report downloaded successfully', 'teal');

}

async function downloadCSV() {
  document.getElementById('export-menu')?.remove();
  if (!state.sessionId) return;

  const a   = document.createElement('a');
  a.href    = `${API_BASE}/export/csv/${state.sessionId}`;
  a.download = 'datalyze_summary.csv';
  a.click();

  addActivity('CSV summary downloaded', 'teal');
  showToast('CSV summary downloaded', 'teal');
}

/* ════════════════════════════════════════════
   UI POLISH — Day 14
════════════════════════════════════════════ */

/* ── Toast notifications ── */
function showToast(message, type = 'teal', duration = 3000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;

  const icons = {
    teal:   '✓',
    red:    '✕',
    amber:  '⚠',
    purple: '◆',
  };

  toast.innerHTML = `
    <span style="font-size:14px">${icons[type] || '•'}</span>
    <span>${escHtml(message)}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'toast-out .2s ease forwards';
    setTimeout(() => toast.remove(), 200);
  }, duration);
}

/* ── Loading bar ── */
function setLoadingBar(pct) {
  const bar = document.getElementById('loading-bar');
  if (!bar) return;
  bar.style.width = `${pct}%`;
  if (pct >= 100) {
    setTimeout(() => { bar.style.width = '0'; }, 400);
  }
}

/* ── Typing indicator (replaces plain "Analysing…") ── */
function appendBotThinkingAnimated() {
  thinkingEl = document.createElement('div');
  thinkingEl.className = 'bubble';
  thinkingEl.innerHTML = `
    <div class="bubble-avatar bubble-avatar--bot">DZ</div>
    <div class="bubble-body">
      <div class="bubble-msg" style="color:var(--text-3)">
        <span class="typing-dots">
          <span></span><span></span><span></span>
        </span>
      </div>
    </div>`;
  chatThread.appendChild(thinkingEl);
  scrollChat();
}

/* ── Suggested questions ── */
function useSuggestion(el) {
  chatInput.value = el.textContent;
  chatInput.focus();
  sendMessage();
}

function updateSuggestions(questionType) {
  const bar  = document.getElementById('suggestions-bar');
  if (!bar) return;

  const sets = {
    stats: [
      'What is the average fare?',
      'Show distribution of age',
      'Which column has most nulls?',
      'Show top 10 by fare',
    ],
    chart: [
      'Show survival by class',
      'Show correlation matrix',
      'Distribution of age',
      'Value counts for sex',
    ],
    outliers: [
      'Which columns have outliers?',
      'Show fare outliers',
      'Compare IQR vs z-score',
    ],
    model: [
      'What is the model accuracy?',
      'Which features matter most?',
      'Show feature importance',
    ],
    general: [
      'What are the outliers?',
      'Show correlation matrix',
      'Which columns have nulls?',
      'Show survival by class',
    ],
  };

  const chips = sets[questionType] || sets.general;
  bar.innerHTML = chips.map(q =>
    `<span class="suggestion-chip" onclick="useSuggestion(this)">${escHtml(q)}</span>`
  ).join('');
}

/* ── Pulse the predict button after model trains ── */
function pulseButton(btn) {
  btn.classList.add('pulse');
  setTimeout(() => btn.classList.remove('pulse'), 5000);
}

/* ── Nav badge (show question count) ── */
let questionCount = 0;
function incrementQuestionBadge() {
  questionCount++;
  const nav = document.querySelector('.nav-item[data-view="analysis"]');
  if (!nav) return;
  let badge = nav.querySelector('.nav-badge');
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'nav-badge';
    nav.appendChild(badge);
  }
  badge.textContent = questionCount;
}

/* ════════════════════════════════════════════
   PREDICTIONS PAGE — Full implementation
════════════════════════════════════════════ */
function updatePredictionsPage(modelData) {
  const statusEl = document.getElementById('pred-status-content');
  const fiCard   = document.getElementById('pred-fi-card');
  const fiEl     = document.getElementById('pred-fi-content');

  if (!statusEl) return;

  if (
    !modelData ||
    modelData.skipped ||
    !modelData.metrics ||
    Object.keys(modelData.metrics).length === 0
  ) {
    statusEl.innerHTML = `
      <div style="
        background:rgba(245,158,11,.08);
        border:1px solid rgba(245,158,11,.25);
        border-radius:8px;
        padding:12px;
        color:var(--amber);
        font-size:12px;
      ">
        <strong>Prediction unavailable</strong><br>
        ${modelData?.reason || 'No suitable target column found in this dataset.'}
      </div>
    `;

    if (fiCard) fiCard.style.display = 'none';
    return;
  }

  statusEl.innerHTML = `
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
      ${Object.entries(modelData.metrics).map(([k,v]) => `
        <div style="background:var(--surface-2);
                    border:0.5px solid var(--border);
                    border-radius:8px;
                    padding:8px 12px;
                    text-align:center;
                    min-width:70px">
          <div style="font-size:16px;font-weight:600;color:var(--accent)">
            ${v}%
          </div>
          <div style="font-size:9px;color:var(--text-3);
                      text-transform:uppercase;
                      letter-spacing:.05em;
                      margin-top:2px">
            ${k}
          </div>
        </div>
      `).join('')}
    </div>

    <div style="font-size:11px;color:var(--text-3)">
      Trained on ${modelData.train_size} rows ·
      Tested on ${modelData.test_size} rows
      (80/20 split)
    </div>
  `;

  if (fiCard && fiEl && modelData.feature_importance?.length) {
    fiCard.style.display = 'block';

    const maxAbs = Math.max(
      ...modelData.feature_importance.map(f => f.abs_impact)
    );

    fiEl.innerHTML = modelData.feature_importance
      .slice(0, 6)
      .map(f => {
        const pct = maxAbs > 0
          ? (f.abs_impact / maxAbs * 100).toFixed(1)
          : 0;

        const color =
          f.direction === 'positive'
            ? 'var(--teal)'
            : 'var(--red)';

        const sign = f.coefficient > 0 ? '+' : '';

        return `
          <div style="margin-bottom:8px">
            <div style="
              display:flex;
              justify-content:space-between;
              font-size:12px;
              margin-bottom:3px">
              <span>${escHtml(f.feature)}</span>
              <span style="color:${color};font-family:monospace">
                ${sign}${f.coefficient}
              </span>
            </div>

            <div style="
              height:4px;
              background:var(--surface-3);
              border-radius:2px">
              <div style="
                height:100%;
                width:${pct}%;
                background:${color};
                border-radius:2px">
              </div>
            </div>
          </div>
        `;
      })
      .join('');
  }
}

async function runPagePrediction() {
  if (!state.sessionId || !state.modelData) {
    showToast('Please upload a dataset first', 'amber');
    return;
  }

  const inputData = {
    Pclass: parseFloat(document.getElementById('pred-pclass').value),
    Sex:    document.getElementById('pred-sex').value,
    Age:    parseFloat(document.getElementById('pred-age').value),
    Fare:   parseFloat(document.getElementById('pred-fare').value),
    SibSp:  parseFloat(document.getElementById('pred-sibsp').value),
    Parch:  parseFloat(document.getElementById('pred-parch').value),
  };

  const resultCard = document.getElementById('pred-page-result');
  const resultEl   = document.getElementById('pred-page-result-content');
  resultCard.style.display = 'block';
  resultEl.innerHTML = `<div style="color:var(--text-3);font-size:12px">Predicting…</div>`;

  try {
    const res = await fetch(`${API_BASE}/predict/${state.sessionId}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(inputData),
    });

    if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }

    const data    = await res.json();
    const survived = data.prediction === 1;
    const color    = survived ? 'var(--teal)' : 'var(--red)';
    const bg       = survived ? 'rgba(45,212,160,.08)' : 'rgba(245,101,101,.08)';

    resultEl.innerHTML = `
      <div style="background:${bg};border:0.5px solid ${color};
                  border-radius:8px;padding:14px">
        <div style="font-size:20px;font-weight:600;color:${color};margin-bottom:6px">
          ${escHtml(data.label)}
        </div>
        <div style="font-size:12px;color:var(--text-2);margin-bottom:12px">
          ${data.confidence}% confidence ·
          Survived: ${data.prob_survived}% ·
          Did not: ${data.prob_not}%
        </div>
        <div style="font-size:10px;color:var(--text-3);text-transform:uppercase;
                    letter-spacing:.05em;margin-bottom:6px">Top influencing features</div>
        ${data.top_features.map(f => `
          <div style="display:flex;justify-content:space-between;
                      font-size:11px;padding:3px 0;color:var(--text-2)">
            <span>${escHtml(f.feature)}</span>
            <span style="color:${f.direction === 'positive' ?
              'var(--teal)' : 'var(--red)'};font-family:monospace">
              ${f.coefficient > 0 ? '+' : ''}${f.coefficient}
            </span>
          </div>`).join('')}
      </div>`;

    addActivity(`Prediction: ${data.label} (${data.confidence}% confidence)`,
                survived ? 'teal' : 'red');
    showToast(`${data.label} — ${data.confidence}% confidence`,
              survived ? 'teal' : 'red');

  } catch (err) {
    resultEl.innerHTML = `<div style="color:var(--red);font-size:12px">Error: ${escHtml(err.message)}</div>`;
  }
}