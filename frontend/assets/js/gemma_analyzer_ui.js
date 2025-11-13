(function (global) {
  const emotionOptions = [
    { value: 'anger', label: '😠 Anger' },
    { value: 'disgust', label: '🤢 Disgust' },
    { value: 'fear', label: '😨 Fear' },
    { value: 'joy', label: '😊 Joy' },
    { value: 'neutral', label: '😐 Neutral' },
    { value: 'sadness', label: '😢 Sadness' },
    { value: 'surprise', label: '😲 Surprise' },
  ];

  const datePresets = [
    { label: 'Today', days: 0 },
    { label: '1 Day', days: 1 },
    { label: '2 Days', days: 2 },
    { label: '3 Days', days: 3 },
    { label: '5 Days', days: 5 },
    { label: '7 Days', days: 7 },
    { label: 'All Time', days: -1 },
  ];

  const STRATEGY_LABELS = {
    artifact: 'Artifact',
    method: 'Method',
    chat_history: 'Chat History',
    chat_summary: 'Chat Summary',
    summary: 'Summary',
    chat_eight_words: 'Chat Eight Words',
    artifact_rag: 'Artifact RAG',
    artifact_rag_none: 'Artifact RAG (No Context)',
  };

  const DB_SORT_LABELS = {
    created_at: 'Date',
    speaker: 'Speaker',
    emotion: 'Emotion',
    job_id: 'Job',
    start_time: 'Start Time',
  };

  const escapeHTML = typeof global.escapeHTML === 'function'
    ? global.escapeHTML
    : (value) => {
        if (value === null || value === undefined) return '';
        return String(value)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      };

  function formatDateTimeDisplay(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }

  function formatTimecode(value) {
    if (value === null || value === undefined || value === '') return '—';
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    const total = Math.max(0, Math.floor(num));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    return [hours, minutes, seconds].map((n) => String(n).padStart(2, '0')).join(':');
  }

  function formatDuration(start, end) {
    if (start === null || start === undefined || end === null || end === undefined) return '—';
    const s = Number(start);
    const e = Number(end);
    if (!Number.isFinite(s) || !Number.isFinite(e) || e < s) return '—';
    const delta = e - s;
    if (delta >= 1) {
      return `${delta.toFixed(1)}s`;
    }
    return `${Math.round(delta * 1000)}ms`;
  }

  function formatScore(score) {
    if (score === null || score === undefined) return '—';
    const num = Number(score);
    if (!Number.isFinite(num)) return '—';
    return num.toFixed(3);
  }

  function formatSortLabel(code) {
    const key = String(code || '').toLowerCase();
    return DB_SORT_LABELS[key] || key || 'Date';
  }

  function formatMetaValue(value) {
    if (value === null || value === undefined || value === '') return '—';
    return String(value);
  }

  function renderMetaItem(label, value, { monospace = false } = {}) {
    const classes = ['meta-value'];
    if (monospace) classes.push('meta-mono');
    return `
      <div class="db-meta-item">
        <span class="meta-label">${escapeHTML(label)}</span>
        <span class="${classes.join(' ')}">${escapeHTML(formatMetaValue(value))}</span>
      </div>
    `;
  }

  function getBaselineConfidence(defaultValue = 0.7) {
    try {
      if (typeof window !== 'undefined' && typeof window.getEmotionConfidenceBaseline === 'function') {
        return window.getEmotionConfidenceBaseline();
      }
    } catch (_) {
      /* noop */
    }
    return defaultValue;
  }

  function getNormalizedEmotionConfidence(value) {
    try {
      if (typeof window !== 'undefined' && typeof window.normalizeEmotionConfidence === 'function') {
        return window.normalizeEmotionConfidence(value);
      }
    } catch (_) {
      /* noop */
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      return Math.max(0, Math.min(1, value));
    }
    return getBaselineConfidence();
  }

  function getStrategyLabel(code) {
    if (!code) return '';
    const normalized = String(code).toLowerCase();
    return STRATEGY_LABELS[normalized] || normalized.replace(/_/g, ' ');
  }

  function formatDateInput(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function formatWindowTimestamp(value) {
    if (value === null || value === undefined || value === '') return null;
    try {
      const dt = new Date(value);
      if (!Number.isNaN(dt.getTime())) {
        return `${dt.toLocaleDateString()} ${dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
      }
    } catch (_) {
      /* noop */
    }
    const numeric = Number(value);
    if (!Number.isNaN(numeric)) {
      try {
        const dt = new Date(numeric > 1e12 ? numeric : numeric * 1000);
        if (!Number.isNaN(dt.getTime())) {
          return `${dt.toLocaleDateString()} ${dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
        }
      } catch (_) {
        /* noop */
      }
    }
    return String(value);
  }

  function summarizeWindowRange(windowStats) {
    if (!windowStats) return '';
    const start = formatWindowTimestamp(windowStats?.transcript_range?.start);
    const end = formatWindowTimestamp(windowStats?.transcript_range?.end);
    if (start && end) return `${start} → ${end}`;
    if (start || end) return start || end;
    return '';
  }

  function createAnalysisId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'analysis-' + Math.random().toString(36).slice(2, 10);
  }

  function encodePayload(payload) {
    try {
      const jsonStr = JSON.stringify(payload || {});
      let b64 = btoa(unescape(encodeURIComponent(jsonStr)));
      b64 = b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
      return b64;
    } catch (_) {
      return '';
    }
  }

  function createEventElement(message, level = 'info') {
    const item = document.createElement('div');
    item.className = `analyzer-log-item level-${level}`;
    const ts = new Date().toLocaleTimeString();
    item.innerHTML = `<span class="analyzer-log-time">${ts}</span><span class="analyzer-log-message">${message}</span>`;
    return item;
  }

  // Keyword highlight helpers (HTML-safe)
  function escapeRegExp(s) {
    return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function highlightText(text, keywords) {
    if (!text || !Array.isArray(keywords) || !keywords.length) return escapeHTML(text || '');
    let html = escapeHTML(text);
    try {
      const tokens = keywords
        .map((k) => String(k || '').trim())
        .filter(Boolean)
        .sort((a, b) => b.length - a.length); // longest first
      if (!tokens.length) return html;
      const pattern = new RegExp('(' + tokens.map(escapeRegExp).join('|') + ')', 'ig');
      html = html.replace(pattern, '<mark class="kw">$1</mark>');
      return html;
    } catch (_) {
      return html;
    }
  }

  function renderTemplate() {
    const baselinePercent = Math.round(getBaselineConfidence() * 100);
    return `
      <div class="analyzer-card">
        <div class="analyzer-filters">
          <div class="analyzer-section" data-stack="filters">
            <h3>Date Range</h3>
            <div class="analyzer-date-presets">
              ${datePresets
                .map(
                  (preset) => `
                    <button class="chip" data-days="${preset.days}" ${preset.days === -1 ? 'data-active="true"' : ''}>
                      ${preset.label}
                    </button>
                  `
                )
                .join('')}
              <button class="chip" data-custom="true">Custom</button>
            </div>
            <div class="analyzer-date-inputs">
              <div>
                <label>Start Date</label>
                <input type="date" data-role="start-date" class="input" disabled>
              </div>
              <div>
                <label>End Date</label>
                <input type="date" data-role="end-date" class="input" disabled>
              </div>
            </div>
            <p class="text-muted analyzer-transcript-range" data-role="transcript-range">
              Loading transcript stats…
            </p>
          </div>

          <div class="analyzer-section" data-stack="filters">
            <h3>Speakers & Emotions</h3>
            <div class="analyzer-grid-two">
              <div>
                <label>Speaker</label>
                <select data-role="speaker" class="input">
                  <option value="">All Speakers</option>
                </select>
              </div>
              <div>
                <label>Viewer Page Size</label>
                <input type="number" min="1" max="200" value="20" data-role="limit" class="input">
                <p class="text-muted" style="font-size:12px;margin-top:4px;">Controls how many rows load in the transcript browser.</p>
              </div>
            </div>
            <div class="analyzer-emotions">
              <label class="checkbox">
                <input type="checkbox" data-role="emotion-all" checked>
                <span>Select All Emotions</span>
              </label>
              <div class="analyzer-emotion-grid">
                ${emotionOptions
                  .map(
                    (emotion) => `
                      <label class="checkbox emotion-option">
                        <input type="checkbox" value="${emotion.value}" data-role="emotion-option" checked>
                        <span>
                          ${emotion.label}
                          <span class="emotion-confidence-pill" data-role="emotion-pill" data-emotion="${emotion.value}">
                            ${baselinePercent}%
                          </span>
                        </span>
                      </label>
                    `
                  )
                  .join('')}
              </div>
              <div class="emotion-confidence-control">
                <label>Emotion Confidence Baseline</label>
                <div class="confidence-slider">
                  <input type="range" min="50" max="100" step="5" value="${baselinePercent}" data-role="emotion-confidence-range">
                  <span class="confidence-value" data-role="emotion-confidence-label">${baselinePercent}%</span>
                </div>
                <p class="confidence-help">Used whenever transcripts do not include explicit emotion confidence scores.</p>
              </div>
            </div>
          </div>

          <div class="analyzer-section">
            <h3>Keywords & Context</h3>
            <div class="analyzer-grid-two">
              <div>
                <label>Keywords / Phrases (comma separated)</label>
                <input type="text" data-role="keywords" class="input" placeholder="Ex: compliance issue, customer escalation">
              </div>
              <div>
                <label>Context Lines (previous statements)</label>
                <input type="number" min="0" max="10" value="3" data-role="context-lines" class="input">
              </div>
            </div>
            <div class="analyzer-grid-two">
              <div>
                <label>Keyword Match</label>
                <select data-role="match-mode" class="input">
                  <option value="any">Match ANY keyword</option>
                  <option value="all">Match ALL keywords</option>
                </select>
              </div>
              <div>
                <label>Search Type</label>
                <select data-role="search-type" class="input">
                  <option value="keyword">Keyword (fast)</option>
                  <option value="semantic">Semantic (AI)</option>
                </select>
              </div>
            </div>
          </div>

          <div class="analyzer-section">
            <h3>Prompt</h3>
            <textarea data-role="prompt" class="input analyzer-prompt" rows="10"></textarea>
            <div class="analyzer-prompt-actions">
              <button class="btn btn-ghost" data-role="reset-prompt">
                <i data-lucide="rotate-ccw"></i>
                Reset Prompt
              </button>
            </div>
          </div>
        </div>

        <div class="analyzer-summary">
          <div class="analyzer-summary-card">
            <div class="analyzer-summary-header">
              <div>
                <h2>Ready to Analyze</h2>
                <p class="text-muted">Configure filters, adjust prompt, then run streaming or quick summary analysis.</p>
              </div>
              <div class="analyzer-summary-tools">
                <div class="analyzer-count" data-role="count-display">
                  <span class="analyzer-count-value" data-role="count-number">0</span>
                  <span class="analyzer-count-label">matching statements</span>
                </div>
                <button class="chip analyzer-log-toggle" data-role="toggle-log-panel" type="button">
                  Show Live Logs
                </button>
              </div>
            </div>

            <div class="analyzer-summary-body">
              <div class="analyzer-gpu" data-role="gpu-status">GPU status: unknown</div>
              <div class="analyzer-run-config">
                <label for="analyzer-analysis-count">Statements to Analyze</label>
                <div class="analyzer-run-config-input">
                  <input id="analyzer-analysis-count" type="number" min="1" max="200" value="50" data-role="analysis-count" class="input">
                  <p class="text-muted" style="font-size:12px;margin-top:4px;">Gemma stops after this many statements per run (applies to streaming and quick summary).</p>
                </div>
              </div>
              <div class="analyzer-actions">
                <button class="btn btn-primary" data-role="run-stream">
                  <i data-lucide="activity"></i>
                  Run Streaming Analysis
                </button>
                <button class="btn" data-role="run-quick">
                  <i data-lucide="zap"></i>
                  Run Quick Summary
                </button>
                <button class="btn btn-ghost" data-role="cancel" disabled>
                  <i data-lucide="stop-circle"></i>
                  Stop
                </button>
              </div>
            </div>

            <div class="analyzer-progress" data-role="progress" hidden>
              <div class="analyzer-progress-bar">
                <div class="analyzer-progress-fill" data-role="progress-fill"></div>
              </div>
              <div class="analyzer-progress-detail" data-role="progress-detail">Idle</div>
            </div>

            <div class="analyzer-results">
              <div class="analyzer-results-stream" data-role="results-stream"></div>
              <div class="analyzer-summary-output" data-role="quick-summary" hidden>
                <h3>Summary Result</h3>
                <pre data-role="quick-summary-text"></pre>
                <div class="analyzer-summary-meta" data-role="quick-summary-meta"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="gemma-transcript-stack">
        <section class="gemma-transcript-card analyzer-db-panel">
          <div class="analyzer-db-viewer" data-role="db-viewer">
            <div class="analyzer-db-header">
              <h3>Transcript Browser</h3>
              <div class="analyzer-db-controls">
                <input class="input" data-role="db-search" placeholder="Search page…"/>
                <button class="chip" data-role="db-density">Dense View</button>
                <select class="input" data-role="sort-select" aria-label="Sort transcripts by column">
                  <option value="created_at">Sort: Date</option>
                  <option value="speaker">Sort: Speaker</option>
                  <option value="emotion">Sort: Emotion</option>
                  <option value="job_id">Sort: Job</option>
                  <option value="start_time">Sort: Start Time</option>
                </select>
                <button class="chip" data-role="order-toggle" data-order="desc">Order: Desc</button>
                <button class="chip" data-role="db-export">Export CSV</button>
              </div>
            </div>
            <div class="analyzer-db-header">
              <div style="flex:1"></div>
              <div class="analyzer-db-controls" data-role="cols-panel">
                <label class="checkbox-pill"><input type="checkbox" data-col="created_at" checked><span>Created Time</span></label>
                <label class="checkbox-pill"><input type="checkbox" data-col="start_time"><span>Start Time</span></label>
                <label class="checkbox-pill"><input type="checkbox" data-col="end_time"><span>End Time</span></label>
                <label class="checkbox-pill"><input type="checkbox" data-col="duration" checked><span>Duration</span></label>
                <label class="checkbox-pill"><input type="checkbox" data-col="speaker" checked><span>Speaker</span></label>
                <label class="checkbox-pill"><input type="checkbox" data-col="emotion" checked><span>Emotion</span></label>
                <label class="checkbox-pill"><input type="checkbox" data-col="job_id" checked><span>Job ID</span></label>
                <label class="checkbox-pill"><input type="checkbox" data-col="transcript_id"><span>Transcript ID</span></label>
                <label class="checkbox-pill"><input type="checkbox" data-col="segment_id"><span>Segment ID</span></label>
              </div>
            </div>
            <div class="analyzer-db-list" data-role="db-list">
              <div class="db-header" data-role="db-header-cols"></div>
            </div>
            <div class="analyzer-db-meta" data-role="db-meta"></div>
          </div>
        </section>

        <section class="gemma-transcript-card analyzer-archive">
          <div class="analyzer-archive-grid">
            <div class="archive-column archive-column--list">
              <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
                <h3 style="margin:0;">Analysis Archive</h3>
                <button class="chip" data-role="artifacts-refresh">Refresh</button>
              </div>
              <div class="artifact-list" data-role="artifacts-list">
                <div data-role="artifacts-local"></div>
                <div data-role="artifacts-remote"></div>
              </div>
              <button class="btn btn-ghost" data-role="artifacts-more" style="margin-top:8px;">Load More</button>
            </div>
            <div class="archive-column archive-column--preview">
              <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
                <h3 style="margin:0;" data-role="artifact-title">Select an artifact</h3>
                <div style="display:flex; gap:8px;">
                  <button class="btn" data-role="meta-run">Run Meta-Analysis</button>
                  <button class="btn btn-primary" data-role="chat-open">Ask About This</button>
                </div>
              </div>
              <div class="artifact-preview">
                <pre data-role="artifact-body" class="artifact-body">—</pre>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="meta-overlay" data-role="meta-overlay" style="position:fixed; inset:0; background:rgba(0,0,0,0.45); display:none; align-items:center; justify-content:center;">
        <div style="width:720px; max-width:90vw; max-height:80vh; overflow:auto; background:#111827; color:#e5e7eb; border-radius:12px; padding:16px;">
          <div style="display:flex; align-items:center; justify-content:space-between;">
            <h3 style="margin:0;">Running Meta-Analysis…</h3>
            <button class="chip" data-role="meta-close">Close</button>
          </div>
          <div data-role="meta-log" style="margin-top:12px; border:1px solid #374151; border-radius:8px; background:#0b1220; padding:8px; font-family: ui-monospace, SFMono-Regular, Menlo; font-size:12px; min-height:240px; white-space:pre-wrap;"></div>
        </div>
      </div>

      <div class="chat-drawer" data-role="chat-drawer" data-position="bottom">
        <div class="chat-drawer__header">
          <strong>Ask About This</strong>
          <div class="chat-drawer__actions">
            <button class="chip" data-role="chat-summary">Summarize Chat</button>
            <select data-role="chat-mode" class="input">
              <option value="rag">RAG (fast)</option>
              <option value="long">Long Context</option>
            </select>
            <button class="chip" data-role="chat-close">Close</button>
          </div>
        </div>
        <div data-role="chat-messages" class="chat-drawer__body">
          <div style="color:#9ca3af; font-size:0.85rem;">Select an artifact and ask a question.</div>
        </div>
        <div class="chat-drawer__footer">
          <input data-role="chat-input" class="input" placeholder="Ask a question…"/>
          <button class="btn btn-primary" data-role="chat-send">Send</button>
        </div>
      </div>
      <div class="chat-overlay" data-role="chat-overlay"></div>
      <div class="log-overlay" data-role="log-overlay">
        <div class="log-panel">
          <div class="log-panel-header">
            <strong>Live Logs</strong>
            <button class="chip" data-role="log-close">Close</button>
          </div>
          <div class="analyzer-log" data-role="log"></div>
        </div>
      </div>
    `;
  }

  function toUtcIso(dateStr, endOfDay = false) {
    if (!dateStr) return '';
    const local = new Date(`${dateStr}T${endOfDay ? '23:59:59' : '00:00:00'}`);
    const utc = new Date(local.getTime() - local.getTimezoneOffset() * 60000);
    return utc.toISOString().slice(0, 19);
  }

  function initGemmaAnalyzer(options = {}) {
    const { mount, defaults = {} } = options;
    const mountEl = typeof mount === 'string' ? document.querySelector(mount) : mount;
    if (!mountEl) {
      throw new Error('Gemma analyzer mount element not found');
    }

    mountEl.classList.add('gemma-analyzer-root');
    mountEl.innerHTML = renderTemplate();

    const els = {
      dateButtons: Array.from(mountEl.querySelectorAll('.analyzer-date-presets .chip')),
      customButton: mountEl.querySelector('.analyzer-date-presets .chip[data-custom]'),
      startDate: mountEl.querySelector('input[data-role="start-date"]'),
      endDate: mountEl.querySelector('input[data-role="end-date"]'),
      transcriptRange: mountEl.querySelector('[data-role="transcript-range"]'),
      speakerSelect: mountEl.querySelector('select[data-role="speaker"]'),
      limitInput: mountEl.querySelector('input[data-role="limit"]'),
      analysisCountInput: mountEl.querySelector('input[data-role="analysis-count"]'),
      emotionAll: mountEl.querySelector('input[data-role="emotion-all"]'),
      emotionChecks: Array.from(mountEl.querySelectorAll('input[data-role="emotion-option"]')),
      emotionConfidenceRange: mountEl.querySelector('[data-role="emotion-confidence-range"]'),
      emotionConfidenceLabel: mountEl.querySelector('[data-role="emotion-confidence-label"]'),
      emotionConfidencePills: Array.from(mountEl.querySelectorAll('[data-role="emotion-pill"]')),
      keywords: mountEl.querySelector('input[data-role="keywords"]'),
      contextLines: mountEl.querySelector('input[data-role="context-lines"]'),
      matchMode: mountEl.querySelector('select[data-role="match-mode"]'),
      searchType: mountEl.querySelector('select[data-role="search-type"]'),
      prompt: mountEl.querySelector('textarea[data-role="prompt"]'),
      resetPrompt: mountEl.querySelector('button[data-role="reset-prompt"]'),
      runStream: mountEl.querySelector('button[data-role="run-stream"]'),
      runQuick: mountEl.querySelector('button[data-role="run-quick"]'),
      cancel: mountEl.querySelector('button[data-role="cancel"]'),
      countDisplay: mountEl.querySelector('[data-role="count-display"]'),
      countNumber: mountEl.querySelector('[data-role="count-number"]'),
      gpuStatus: mountEl.querySelector('[data-role="gpu-status"]'),
      progress: mountEl.querySelector('[data-role="progress"]'),
      progressFill: mountEl.querySelector('[data-role="progress-fill"]'),
      progressDetail: mountEl.querySelector('[data-role="progress-detail"]'),
      resultsStream: mountEl.querySelector('[data-role="results-stream"]'),
      log: mountEl.querySelector('[data-role="log"]'),
      quickSummary: mountEl.querySelector('[data-role="quick-summary"]'),
      quickSummaryText: mountEl.querySelector('[data-role="quick-summary-text"]'),
      quickSummaryMeta: mountEl.querySelector('[data-role="quick-summary-meta"]'),
      dbViewer: mountEl.querySelector('[data-role="db-viewer"]'),
      dbList: mountEl.querySelector('[data-role="db-list"]'),
      dbMeta: mountEl.querySelector('[data-role="db-meta"]'),
      dbSearch: mountEl.querySelector('[data-role="db-search"]'),
      dbExport: mountEl.querySelector('[data-role="db-export"]'),
      dbDensity: mountEl.querySelector('[data-role="db-density"]'),
      sortSelect: mountEl.querySelector('[data-role="sort-select"]'),
      orderToggle: mountEl.querySelector('[data-role="order-toggle"]'),
      // Column toggles
      colsPanel: null,
      colsToggles: null,
      logToggle: mountEl.querySelector('[data-role="toggle-log-panel"]'),
      logOverlay: mountEl.querySelector('[data-role="log-overlay"]'),
      logClose: mountEl.querySelector('[data-role="log-close"]'),
      // Archive/Meta/Chat selectors
      artifactsList: mountEl.querySelector('[data-role="artifacts-list"]'),
      artifactsLocal: mountEl.querySelector('[data-role="artifacts-local"]'),
      artifactsRemote: mountEl.querySelector('[data-role="artifacts-remote"]'),
      artifactsMore: mountEl.querySelector('[data-role="artifacts-more"]'),
      artifactsRefresh: mountEl.querySelector('[data-role="artifacts-refresh"]'),
      artifactTitle: mountEl.querySelector('[data-role="artifact-title"]'),
      artifactBody: mountEl.querySelector('[data-role="artifact-body"]'),
      metaRun: mountEl.querySelector('[data-role="meta-run"]'),
      metaOverlay: mountEl.querySelector('[data-role="meta-overlay"]'),
      metaLog: mountEl.querySelector('[data-role="meta-log"]'),
      metaClose: mountEl.querySelector('[data-role="meta-close"]'),
      chatOpen: mountEl.querySelector('[data-role="chat-open"]'),
      chatDrawer: mountEl.querySelector('[data-role="chat-drawer"]'),
      chatClose: mountEl.querySelector('[data-role="chat-close"]'),
      chatModeSelect: mountEl.querySelector('[data-role="chat-mode"]'),
      chatMessages: mountEl.querySelector('[data-role="chat-messages"]'),
      chatInput: mountEl.querySelector('[data-role="chat-input"]'),
      chatSend: mountEl.querySelector('[data-role="chat-send"]'),
      chatSummary: mountEl.querySelector('[data-role="chat-summary"]'),
      chatOverlay: mountEl.querySelector('[data-role="chat-overlay"]'),
    };

    const selectPresetButton = (targetBtn) => {
      els.dateButtons.forEach((b) => b.removeAttribute('data-active'));
      if (els.customButton) {
        els.customButton.removeAttribute('data-active');
      }
      if (targetBtn) {
        targetBtn.setAttribute('data-active', 'true');
      }
    };

    const applyDatePreset = (days, { triggerCount = true } = {}) => {
      const daysInt = Number(days);
      if (!Number.isFinite(daysInt)) {
        return;
      }
      const presetBtn = els.dateButtons.find((btn) => parseInt(btn.dataset.days, 10) === daysInt) || null;
      selectPresetButton(presetBtn);
      if (daysInt < 0) {
        // All time: clear date filters
        els.startDate.value = '';
        els.endDate.value = '';
        els.startDate.disabled = true;
        els.endDate.disabled = true;
      } else {
        const end = new Date();
        const start = new Date();
        start.setDate(start.getDate() - daysInt);
        els.startDate.value = formatDateInput(start);
        els.endDate.value = formatDateInput(end);
        els.startDate.disabled = true;
        els.endDate.disabled = true;
      }
      if (triggerCount) {
        updateCount();
        refreshDb(true);
      }
    };

    const defaultPrompt = (defaults.prompt || `Analyze the following conversation transcripts for communication patterns.

Focus on identifying:
1. **Logical Fallacies**: Name any fallacies used (ad hominem, straw man, false dilemma, etc.)
2. **Snippiness**: Identify curt, dismissive, or unnecessarily brief responses
3. **Hyperbolic Language**: Point out exaggerated, extreme, or dramatic phrasing
4. **Emotional Triggers**: Note what causes emotional reactions and why

For each issue found, provide:
- Specific quote from the transcript
- Why it's problematic
- A better alternative approach

Then provide a 2-3 sentence summary of the overall communication style and root emotional causes.

Transcripts:
{transcripts}

Provide your analysis in clear, structured sections.`).trim();

    els.prompt.value = defaultPrompt;

    const state = {
      analysisId: null,
      eventSource: null,
      running: false,
      total: 0,
      completed: 0,
      lastCount: null,
      contextLines: parseInt(els.contextLines.value, 10) || 3,
      latestResultTs: 0,
      debounceTimer: null,
      speakersLoaded: false,
      streamCompleted: false,
      viewer: {
        sort_by: 'created_at',
        order: 'desc',
        limit: Math.max(1, Math.min(200, parseInt(els.limitInput.value, 10) || 20)),
        offset: 0,
        loading: false,
        has_more: true,
        lastFiltersKey: '',
        context_lines: 2,
        dense: false,
        highlight: [],
      },
      // Archive state
      artifacts: [],
      artifactsOffset: 0,
      artifactsHasMore: true,
      selectedArtifacts: new Set(),
      currentArtifactId: null,
      latestStreamResults: [],
      latestStreamSections: [],
      localArtifacts: [],
      localArtifactMap: Object.create(null),
      chatSessionId: null,
      chatMessagesHistory: [],
      transcriptWindow: null,
    };

    const updateTranscriptRangeBanner = (loadingText = null) => {
      if (!els.transcriptRange) return;
      if (loadingText) {
        els.transcriptRange.textContent = loadingText;
        return;
      }
      const stats = state.transcriptWindow;
      if (!stats || !stats.transcript_count) {
        els.transcriptRange.textContent = 'No transcripts have been indexed yet.';
        return;
      }
      const base = summarizeWindowRange(stats);
      let text = `Indexed transcripts: ${stats.transcript_count}`;
      if (base) {
        text += ` (${base})`;
      }
      if (Number.isFinite(state.lastCount)) {
        if (state.lastCount === 0 && stats.transcript_count > 0) {
          text += ' • 0 match current filters – adjust your date range or filters.';
        } else if (state.lastCount >= 0) {
          text += ` • Current filters match ${state.lastCount}`;
        }
      }
      if (stats.segment_count) {
        text += ` • Segments: ${stats.segment_count}`;
      }
      els.transcriptRange.textContent = text;
    };

    const refreshTranscriptWindow = async () => {
      if (!els.transcriptRange) return;
      updateTranscriptRangeBanner('Loading transcript stats…');
      try {
        const stats = await api.transcriptsTimeRange();
        if (stats && typeof stats.transcript_count === 'number') {
          state.transcriptWindow = stats;
          updateTranscriptRangeBanner();
          logEvent(
            `[RAG] Indexed transcripts ${stats.transcript_count} (${summarizeWindowRange(stats) || 'no timestamps'})`,
            'info',
          );
        } else {
          state.transcriptWindow = null;
          updateTranscriptRangeBanner('Transcript stats unavailable.');
        }
      } catch (error) {
        console.warn('[Analyzer] Failed to load transcript stats', error);
        updateTranscriptRangeBanner('Transcript stats unavailable.');
      }
    };

    const updateEmotionConfidenceUI = (value) => {
      const percent = `${Math.round(value * 100)}%`;
      if (els.emotionConfidenceLabel) {
        els.emotionConfidenceLabel.textContent = percent;
      }
      if (els.emotionConfidencePills && els.emotionConfidencePills.length) {
        els.emotionConfidencePills.forEach((pill) => {
          pill.textContent = percent;
        });
      }
    };

    const initEmotionBaseline = () => {
      const baseline = getBaselineConfidence();
      updateEmotionConfidenceUI(baseline);
      if (els.emotionConfidenceRange) {
        els.emotionConfidenceRange.value = Math.round(baseline * 100);
        els.emotionConfidenceRange.addEventListener('input', (event) => {
          const percent = Math.round(Number(event.target.value));
          const normalized = Math.max(0, Math.min(100, percent)) / 100;
          if (typeof window.setEmotionConfidenceBaseline === 'function') {
            window.setEmotionConfidenceBaseline(normalized);
          } else {
            updateEmotionConfidenceUI(normalized);
          }
        });
      }

      document.addEventListener('emotionConfidenceBaselineChanged', (evt) => {
        const updated = typeof evt.detail === 'number' ? evt.detail : baseline;
        if (els.emotionConfidenceRange) {
          els.emotionConfidenceRange.value = Math.round(updated * 100);
        }
        updateEmotionConfidenceUI(updated);
      });
    };

    initEmotionBaseline();

    function describeError(err) {
      if (!err) return 'Unknown error';
      const parts = [];
      if (err.message) parts.push(err.message);
      if (err.detail) {
        if (typeof err.detail === 'string') {
          parts.push(err.detail);
        } else {
          try {
            parts.push(JSON.stringify(err.detail));
          } catch (_) {
            parts.push(String(err.detail));
          }
        }
      }
      return parts.filter(Boolean).join(' • ') || String(err);
    }

    function trimClientChat() {
      if (state.chatMessagesHistory.length > 60) {
        state.chatMessagesHistory = state.chatMessagesHistory.slice(-60);
      }
    }

    function setGPUStatus(text, variant = 'muted') {
      if (!els.gpuStatus) return;
      els.gpuStatus.textContent = text;
      els.gpuStatus.dataset.variant = variant;
    }

    async function loadGPUStats() {
      try {
        const stats = await api.getGemmaStats();
        if (stats && typeof stats === 'object') {
          const mode = stats.model_on_gpu ? 'GPU' : 'CPU';
          const vram = stats.vram_used_mb && stats.vram_total_mb
            ? `${Math.round(stats.vram_used_mb / 1024 * 10) / 10} / ${Math.round(stats.vram_total_mb / 1024 * 10) / 10} GB`
            : 'n/a';
          setGPUStatus(`GPU status: ${mode} • VRAM ${vram}`, stats.model_on_gpu ? 'success' : 'warning');
        }
      } catch (error) {
        console.error('[Analyzer] Failed to load GPU stats', error);
        setGPUStatus('GPU status: unknown (failed to fetch)', 'warning');
      }
    }

    function getSelectedEmotions() {
      const selected = els.emotionChecks.filter((c) => c.checked).map((c) => c.value);
      return selected;
    }

    function gatherFilters() {
      const limit = Math.max(1, Math.min(200, parseInt(els.limitInput.value, 10) || 20));
      if (state && state.viewer) {
        state.viewer.limit = limit;
      }
      const filters = { limit };
      const speaker = els.speakerSelect.value.trim();
      if (speaker) filters.speakers = [speaker];
      const emotions = getSelectedEmotions();
      if (emotions.length && emotions.length !== emotionOptions.length) {
        filters.emotions = emotions;
      }
      const startDate = els.startDate.value;
      const endDate = els.endDate.value;
      if (startDate) {
        filters.start_date = startDate;
        filters.start_date_utc = toUtcIso(startDate, false);
      }
      if (endDate) {
        filters.end_date = endDate;
        filters.end_date_utc = toUtcIso(endDate, true);
      }
      filters.tz_offset_minutes = new Date().getTimezoneOffset();
      const contextLines = Math.max(0, Math.min(10, parseInt(els.contextLines.value, 10) || 0));
      filters.context_lines = contextLines;
      const keywordsRaw = els.keywords.value.trim();
      if (keywordsRaw) {
        filters.keywords = keywordsRaw;
        filters.match = els.matchMode.value;
        filters.search_type = els.searchType.value;
      }
      return filters;
    }

    function getAnalysisLimit() {
      const input = els.analysisCountInput;
      const raw = input ? parseInt(input.value, 10) : NaN;
      const limit = Math.max(1, Math.min(200, Number.isFinite(raw) ? raw : 50));
      if (input && Number(input.value) !== limit) {
        input.value = String(limit);
      }
      return limit;
    }

    function updateCountDisplay(count) {
      let nextCount = Number.isFinite(count) ? count : 0;
      if (nextCount < 0) nextCount = 0;
      state.total = nextCount;
      state.lastCount = nextCount;
      if (els.countNumber) {
        els.countNumber.textContent = nextCount;
        els.countNumber.classList.remove('pulse');
        // eslint-disable-next-line no-unused-expressions
        void els.countNumber.offsetWidth;
        els.countNumber.classList.add('pulse');
      }
      if (els.countDisplay) {
        els.countDisplay.classList.add('active');
      }
      updateTranscriptRangeBanner();
    }

    function logEvent(message, level = 'info') {
      const el = createEventElement(message, level);
      els.log.appendChild(el);
      els.log.scrollTop = els.log.scrollHeight;
    }

    function logFilterSummary(filters, analysisLimit) {
      if (!filters) return;
      const summary = [];
      summary.push(`max=${analysisLimit}`);
      if (Array.isArray(filters.speakers) && filters.speakers.length) {
        summary.push(`speaker=${filters.speakers.join(', ')}`);
      }
      if (Array.isArray(filters.emotions) && filters.emotions.length) {
        summary.push(`emotions=${filters.emotions.join(', ')}`);
      }
      if (filters.start_date || filters.end_date) {
        summary.push(`dates=${filters.start_date || 'any'}→${filters.end_date || 'any'}`);
      }
      if (filters.keywords) {
        summary.push(`keywords="${filters.keywords}"`);
      }
      if (typeof filters.context_lines === 'number') {
        summary.push(`context=${filters.context_lines}`);
      }
      logEvent(`[Filters] ${summary.join(' • ')}`);
    }

    function clearResults() {
      els.resultsStream.innerHTML = '';
      els.quickSummary.hidden = true;
      els.quickSummaryText.textContent = '';
      els.quickSummaryMeta.textContent = '';
    }

    // =====================
    // Database Viewer (Browse Transcripts)
    // =====================
    function serializeFiltersKey(filters) {
      try {
        const clone = { ...filters };
        delete clone.offset; delete clone.limit;
        return JSON.stringify(clone);
      } catch { return '' }
    }

  function renderDbItems(items = []) {
      const frag = document.createDocumentFragment();
      items.forEach((it) => {
        const row = document.createElement('div');
        row.className = state.viewer.dense ? 'db-row db-row-dense' : 'db-row';
        if (it && it.emotion) {
          const ecls = String(it.emotion).toLowerCase();
          row.classList.add(`emotion-${ecls}`);
        }

        const header = document.createElement('div');
        header.className = 'db-row-header';

        const toggle = document.createElement('button');
        toggle.className = 'db-row-toggle';
        toggle.type = 'button';
        toggle.setAttribute('aria-label', 'Toggle details');
        toggle.innerHTML = '<i data-lucide="chevron-right"></i>';

        const createdDisplay = formatDateTimeDisplay(it.created_at);
        const startDisplay = formatTimecode(it.start_time);
        const endDisplay = formatTimecode(it.end_time);
        const durationDisplay = formatDuration(it.start_time, it.end_time);
        const speakerDisplay = formatMetaValue(it.speaker || 'Unknown');
        const normalizedConfidence = getNormalizedEmotionConfidence(it.emotion_confidence);
        const percent = ` ${Math.round(normalizedConfidence * 100)}%`;
        const emotionDisplay = formatMetaValue(it.emotion ? `${it.emotion}${percent}` : percent.trim());
        const jobDisplay = formatMetaValue(it.job_id);
        const segmentDisplay = formatMetaValue(it.segment_id);

        const cols = document.createElement('div');
        cols.className = 'db-row-cols';
        const emotionClass = `emotion-${String(it.emotion || '').toLowerCase()}`;
        const highlighted = highlightText(it.text || '', state.viewer.highlight);
        // Build columns dynamically based on visibility settings
        const colVisible = state.viewer.columns || {};
        const parts = [];
        if (colVisible.created_at !== false) parts.push(`<span class="db-col db-date">${escapeHTML(createdDisplay)}</span>`);
        if (colVisible.start_time !== false) parts.push(`<span class="db-col db-time">${escapeHTML(startDisplay)}</span>`);
        if (colVisible.end_time) parts.push(`<span class="db-col db-time">${escapeHTML(endDisplay)}</span>`);
        if (colVisible.duration) parts.push(`<span class="db-col db-time">${escapeHTML(durationDisplay)}</span>`);
        if (colVisible.speaker !== false) parts.push(`<span class="db-col db-speaker"><span class="speaker-badge">${escapeHTML(speakerDisplay)}</span></span>`);
        if (colVisible.emotion) parts.push(`<span class="db-col db-emotion"><span class="emotion-badge ${emotionClass}">${escapeHTML(emotionDisplay)}</span></span>`);
        if (colVisible.job_id) parts.push(`<span class="db-col db-job">${escapeHTML(jobDisplay)}</span>`);
        if (colVisible.segment_id || colVisible.transcript_id) {
          const seg = colVisible.segment_id ? escapeHTML(segmentDisplay) : '';
          const tr = colVisible.transcript_id ? escapeHTML(it.transcript_id || '') : '';
          parts.push(`<span class="db-col db-segment">${[seg,tr].filter(Boolean).join(' • ')}</span>`);
        }
        parts.push(`<span class="db-col db-text">${highlighted}</span>`);
        cols.innerHTML = parts.join('');

        header.appendChild(toggle);
        header.appendChild(cols);

        const detail = document.createElement('div');
        detail.className = 'db-row-detail';
        detail.hidden = true;

        const metaBlock = document.createElement('div');
        metaBlock.className = 'db-meta-grid';
        const m = [];
        const v = state.viewer.columns || {};
        if (v.created_at !== false) m.push(renderMetaItem('Created', createdDisplay));
        if (v.start_time !== false) m.push(renderMetaItem('Start', startDisplay, { monospace: true }));
        if (v.end_time) m.push(renderMetaItem('End', endDisplay, { monospace: true }));
        if (v.duration) m.push(renderMetaItem('Duration', durationDisplay));
        if (v.speaker !== false) m.push(renderMetaItem('Speaker', speakerDisplay));
        if (v.emotion) m.push(renderMetaItem('Emotion', emotionDisplay));
        if (v.job_id) m.push(renderMetaItem('Job ID', jobDisplay, { monospace: true }));
        if (v.transcript_id) m.push(renderMetaItem('Transcript ID', formatMetaValue(it.transcript_id), { monospace: true }));
        if (v.segment_id) m.push(renderMetaItem('Segment ID', segmentDisplay, { monospace: true }));
        m.push(renderMetaItem('Score', formatScore(it.score)));
        metaBlock.innerHTML = m.join('');

        const snippetBlock = document.createElement('div');
        snippetBlock.className = 'db-snippet';
        const snippetHtml = highlightText(it.text || '', state.viewer.highlight);
        snippetBlock.innerHTML = `<strong>Snippet</strong><pre>${snippetHtml}</pre>`;

        const ctxBlock = document.createElement('div');
        ctxBlock.className = 'db-context';
        if (Array.isArray(it.context_before) && it.context_before.length) {
          ctxBlock.innerHTML = '<strong>Context Before</strong>';
          const ctxList = document.createElement('div');
          ctxList.className = 'db-context-list';
          it.context_before.forEach((ctx) => {
            const ctxLine = document.createElement('p');
            const ctxHtml = highlightText(ctx.text || '', state.viewer.highlight);
            ctxLine.innerHTML = `<span>${escapeHTML(ctx.speaker || 'Speaker')}:</span> ${ctxHtml}`;
            ctxList.appendChild(ctxLine);
          });
          ctxBlock.appendChild(ctxList);
        }

        const actions = document.createElement('div');
        actions.className = 'db-actions';

        const analyzeBtn = document.createElement('button');
        analyzeBtn.type = 'button';
        analyzeBtn.className = 'chip';
        analyzeBtn.textContent = 'Analyze snippet';
        analyzeBtn.addEventListener('click', async () => {
          showInlineAnalyzer(row, it);
        });

        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'chip';
        copyBtn.textContent = 'Copy text';
        copyBtn.addEventListener('click', () => {
          copySnippet(it);
        });

        const openBtn = document.createElement('button');
        openBtn.type = 'button';
        openBtn.className = 'chip';
        openBtn.textContent = 'Open source';
        openBtn.disabled = !it.job_id;
        openBtn.addEventListener('click', () => openSnippetSource(it));

        actions.append(analyzeBtn, copyBtn, openBtn);

        detail.append(metaBlock, snippetBlock, ctxBlock, actions);
        row.__item = it;

        header.addEventListener('click', () => {
          const expanded = !detail.hidden;
          detail.hidden = expanded;
          toggle.classList.toggle('expanded', !expanded);
          if (window.lucide) window.lucide.createIcons();
        });

        row.append(header, detail);
        frag.appendChild(row);
      });
      els.dbList.appendChild(frag);
      if (window.lucide) window.lucide.createIcons();
    }

    async function analyzeSnippet(item) {
      try {
        logEvent(`[DB] Analyzing snippet from ${item.speaker || 'Speaker'}`);
        const prompt = `You are an analyst. Review the following transcript snippet and summarize key fallacies, emotions, and risks.\n\nSnippet:\n${item.text || ''}\n\nProvide bullet points.`;
        const response = await api.gemmaGenerate(prompt, 256);
        const text = typeof response?.text === 'string' ? response.text.trim() : (response?.response || '').trim();
        if (text) {
          logEvent(`[DB] Snippet analysis result: ${text.slice(0, 200)}${text.length > 200 ? '…' : ''}`, 'success');
          showToast('Snippet Analyzed', 'Result logged in analyzer log.', 'success');
        } else {
          throw new Error('Empty response');
        }
      } catch (error) {
        console.error('[Analyzer] analyzeSnippet failed', error);
        showToast('Snippet Analysis Failed', error.message || 'Unable to analyze snippet.', 'error');
      }
    }

    function showInlineAnalyzer(row, item) {
      try {
        const existing = row.querySelector('.inline-analyzer');
        if (existing) { existing.remove(); }
        const box = document.createElement('div');
        box.className = 'inline-analyzer';
        const before = Array.isArray(item.context_before) ? item.context_before : [];
        const after = Array.isArray(item.context_after) ? item.context_after : [];
        const ctxLeft = before.map((c) => `<p><strong>${escapeHTML(c.speaker || 'Speaker')}:</strong> ${escapeHTML(c.text || '')}</p>`).join('') || '<p>—</p>';
        const ctxRight = after.map((c) => `<p><strong>${escapeHTML(c.speaker || 'Speaker')}:</strong> ${escapeHTML(c.text || '')}</p>`).join('') || '<p>—</p>';
        box.innerHTML = `
          <div class="inline-analyzer-body">
            <div class="inline-analyzer-input">
              <input class="input" type="text" data-role="inline-question" placeholder="What should Gemma analyze about this?" />
              <button class="btn btn-primary" data-role="inline-run">Ask</button>
            </div>
            <div class="inline-analyzer-context">
              <div>
                <div class="meta-label">Context Before</div>
                <div class="context-col">${ctxLeft}</div>
              </div>
              <div>
                <div class="meta-label">Context After</div>
                <div class="context-col">${ctxRight}</div>
              </div>
            </div>
          </div>`;
        row.appendChild(box);
        const runBtn = box.querySelector('[data-role="inline-run"]');
        const input = box.querySelector('[data-role="inline-question"]');
        const ask = async () => {
          const userQ = (input.value || 'Analyze this snippet').trim();
          const prompt = `${userQ}\n\nSnippet:\n${item.text || ''}`;
          runBtn.disabled = true;
          try {
            const response = await api.gemmaGenerate(prompt, 256);
            const text = typeof response?.text === 'string' ? response.text.trim() : (response?.response || '').trim();
            if (text) {
              showToast('Gemma', 'Response received.', 'success');
              logEvent(`[Inline] ${text.slice(0, 200)}${text.length > 200 ? '…' : ''}`, 'success');
            }
          } catch (e) {
            showToast('Gemma', 'Analysis failed.', 'error');
          } finally {
            runBtn.disabled = false;
          }
        };
        runBtn.addEventListener('click', ask);
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask(); });
      } catch (e) { console.warn('inline analyzer failed', e); }
    }

    function copySnippet(item) {
      try {
        const text = item.text || '';
        const tryNative = async () => {
          if (navigator && navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
          }
          return false;
        };
        tryNative().then((ok) => {
          if (ok) {
            showToast('Copied', 'Snippet copied to clipboard.', 'success');
            return;
          }
          // Fallback
          const ta = document.createElement('textarea');
          ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
          document.body.appendChild(ta); ta.select();
          try { document.execCommand('copy'); showToast('Copied', 'Snippet copied to clipboard.', 'success'); }
          catch { showToast('Clipboard', 'Copy failed.', 'error'); }
          finally { document.body.removeChild(ta); }
        });
      } catch (error) {
        console.error('[Analyzer] copySnippet failed', error);
        showToast('Clipboard', 'Copy failed.', 'error');
      }
    }

    function openSnippetSource(item) {
      if (!item?.job_id) {
        showToast('Unavailable', 'No source job ID for this snippet.', 'warning');
        return;
      }
      const start = typeof item.start_time === 'number' ? `&t=${Math.max(0, Math.floor(item.start_time))}` : '';
      window.open(`transcripts.html?job=${encodeURIComponent(item.job_id)}${start}`, '_blank');
    }

    async function loadDbBatch() {
      if (state.viewer.loading || !els.dbList) return;
      const filters = gatherFilters();
      filters.context_lines = state.viewer.context_lines;
      filters.limit = state.viewer.limit;
      filters.offset = state.viewer.offset;
      filters.sort_by = state.viewer.sort_by;
      filters.order = state.viewer.order;
      const key = serializeFiltersKey(filters);
      // Capture highlight tokens from current filter keywords
      try {
        const kraw = (filters.keywords || '').trim();
        state.viewer.highlight = kraw
          ? kraw.split(',').map((k) => k.trim()).filter(Boolean)
          : [];
      } catch { state.viewer.highlight = []; }
      try {
        state.viewer.loading = true;
        els.dbMeta.textContent = `Loading… (${state.viewer.offset} loaded)`;
        const analysisId = createAnalysisId();
        const resp = await api.queryTranscripts(filters, { analysisId });
        const items = Array.isArray(resp?.items) ? resp.items : [];
        renderDbItems(items);
        state.viewer.offset += items.length;
        state.viewer.has_more = Boolean(resp?.has_more) || (items.length === state.viewer.limit);
        const total = typeof resp?.total === 'number' ? resp.total : null;
        const sortLabel = formatSortLabel(state.viewer.sort_by);
        els.dbMeta.textContent = total != null
          ? `Showing ${state.viewer.offset} of ${total} (sorted by ${sortLabel}/${state.viewer.order})`
          : `Loaded ${state.viewer.offset} items (sorted by ${sortLabel}/${state.viewer.order})`;
        logEvent(`[DB] Loaded ${items.length} items (offset=${state.viewer.offset})`);
      } catch (e) {
        console.error('[Analyzer] DB load failed', e);
        const msg = e?.message || String(e || 'error');
        logEvent(`[DB] Error: ${msg}`, 'error');
        // Fallback: use recent transcripts and client-side filter/sort/paginate
        try {
          const recentLimit = Math.max(state.viewer.limit * 5, 200);
          const recent = await api.getRecentTranscripts(recentLimit);
          const list = Array.isArray(recent?.transcripts) ? recent.transcripts : [];
          const itemsAll = [];
          const speaker = filters.speakers ? filters.speakers[0] : null;
          const emotionSet = filters.emotions ? new Set(filters.emotions.map((e) => e.toLowerCase())) : null;
          const startDate = filters.start_date ? new Date(filters.start_date + 'T00:00:00') : null;
          const endDate = filters.end_date ? new Date(filters.end_date + 'T23:59:59') : null;
          const keywords = (filters.keywords || '')
            .split(',')
            .map((k) => k.trim().toLowerCase())
            .filter(Boolean);
          const requireAll = filters.match === 'all';
          for (const t of list) {
            const createdAt = t.created_at ? new Date(t.created_at) : null;
            if (startDate && createdAt && createdAt < startDate) continue;
            if (endDate && createdAt && createdAt > endDate) continue;
            const segs = Array.isArray(t.segments) ? t.segments : [];
            for (let idx = 0; idx < segs.length; idx += 1) {
              const seg = segs[idx];
              if (speaker) {
                const s = (seg.speaker || '').trim();
                if (s !== speaker) continue;
              }
              if (emotionSet) {
                const e2 = (seg.emotion || '').toLowerCase();
                if (!emotionSet.has(e2)) continue;
              }
              if (keywords.length) {
                const text = (seg.text || '').toLowerCase();
                if (!text) continue;
                const matches = keywords.filter((kw) => text.includes(kw));
                if (requireAll && matches.length !== keywords.length) continue;
                if (!requireAll && matches.length === 0) continue;
              }
              const context = [];
              if (state.viewer.context_lines > 0) {
                const startIdx = Math.max(0, idx - state.viewer.context_lines);
                for (let i = startIdx; i < idx; i += 1) {
                  const ctxSeg = segs[i];
                  context.push({
                    speaker: ctxSeg?.speaker,
                    text: ctxSeg?.text,
                  });
                }
              }
              itemsAll.push({
                speaker: seg.speaker || 'Speaker',
                emotion: seg.emotion || null,
                text: seg.text || '',
                created_at: t.created_at || null,
                context_before: context,
                job_id: t.job_id || t.transcript_id,
                transcript_id: t.transcript_id,
                start_time: seg.start_time,
              });
            }
          }
          // Sort
          const sortBy = state.viewer.sort_by;
          const ord = state.viewer.order === 'asc' ? 1 : -1;
          itemsAll.sort((a, b) => {
            if (sortBy === 'speaker') {
              const as = (a.speaker || '').toLowerCase();
              const bs = (b.speaker || '').toLowerCase();
              if (as < bs) return -1 * ord;
              if (as > bs) return 1 * ord;
              return 0;
            }
            const ad = a.created_at ? new Date(a.created_at).getTime() : 0;
            const bd = b.created_at ? new Date(b.created_at).getTime() : 0;
            return (bd - ad) * (ord === 1 ? -1 : 1);
          });
          // Paginate
          const slice = itemsAll.slice(state.viewer.offset, state.viewer.offset + state.viewer.limit);
          renderDbItems(slice);
          state.viewer.offset += slice.length;
          state.viewer.has_more = (state.viewer.offset < itemsAll.length);
          const sortLabel = formatSortLabel(state.viewer.sort_by);
          els.dbMeta.textContent = `Showing ${state.viewer.offset} of ${itemsAll.length} (fallback, sorted by ${sortLabel}/${state.viewer.order})`;
          logEvent(`[DB] Fallback loaded ${slice.length} items of ${itemsAll.length}`);
        } catch (fe) {
          console.error('[Analyzer] DB fallback failed', fe);
          els.dbMeta.textContent = 'Error loading data';
        }
      } finally {
        state.viewer.loading = false;
      }
    }

    function resetDbList() {
      if (els.dbList) els.dbList.innerHTML = '';
      state.viewer.offset = 0;
      state.viewer.has_more = true;
    }

    function refreshDb(reset = true) {
      if (!els.dbList) return;
      if (reset) resetDbList();
      loadDbBatch();
    }

    function bindDbScroll() {
      if (!els.dbList) return;
      els.dbList.addEventListener('scroll', () => {
        if (!state.viewer.has_more || state.viewer.loading) return;
        const nearBottom = (els.dbList.scrollTop + els.dbList.clientHeight) >= (els.dbList.scrollHeight - 24);
        if (nearBottom) loadDbBatch();
      });
    }

    function filterDbList(query) {
      if (!els.dbList) return;
      const q = (query || '').toLowerCase().trim();
      const rows = els.dbList.querySelectorAll('.db-row');
      rows.forEach((row) => {
        if (!q) {
          row.style.display = '';
          return;
        }
        const text = row.textContent || '';
        row.style.display = text.toLowerCase().includes(q) ? '' : 'none';
      });
      // Update footer meta to reflect visible count
      try {
        const total = rows.length;
        let visible = 0;
        rows.forEach((r) => { if (r.style.display !== 'none') visible += 1; });
        if (els.dbMeta) {
          const base = els.dbMeta.textContent || '';
          const withoutFilter = base.replace(/\s*\(filtered:.*\)$/i, '');
          els.dbMeta.textContent = `${withoutFilter} (filtered: ${visible}/${total})`;
        }
      } catch {}
    }

    function exportDbCsv() {
      if (!els.dbList) return;
      const rows = Array.from(els.dbList.querySelectorAll('.db-row')).filter((r) => r.style.display !== 'none');
      if (!rows.length) {
        showToast('Export', 'No rows to export on this page.', 'warning');
        return;
      }
      const escape = (s) => '"' + String(s ?? '').replace(/"/g, '""') + '"';
      const header = [
        'Created At',
        'Start Time',
        'End Time',
        'Duration',
        'Speaker',
        'Emotion',
        'Job ID',
        'Segment ID',
        'Transcript ID',
        'Score',
        'Text',
        'Context Before',
      ];
      const lines = [header.join(',')];
      rows.forEach((row) => {
        const item = row.__item || {};
        const contextJoined = Array.isArray(item.context_before)
          ? item.context_before
              .map((ctx) => `${ctx?.speaker || 'Speaker'}: ${ctx?.text || ''}`)
              .join(' | ')
          : '';
        lines.push([
          formatDateTimeDisplay(item.created_at),
          formatTimecode(item.start_time),
          formatTimecode(item.end_time),
          formatDuration(item.start_time, item.end_time),
          item.speaker || 'Unknown',
          item.emotion || '',
          item.job_id || '',
          item.segment_id || '',
          item.transcript_id || '',
          formatScore(item.score),
          item.text || '',
          contextJoined,
        ].map(escape).join(','));
      });
      const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const ts = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
      a.download = `transcripts_page_${ts}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('Export', `Exported ${rows.length} rows to CSV.`, 'success');
    }

    function updateSortControls() {
      if (els.sortSelect) {
        els.sortSelect.value = state.viewer.sort_by;
      }
      els.orderToggle?.setAttribute('data-order', state.viewer.order);
      els.orderToggle && (els.orderToggle.textContent = `Order: ${state.viewer.order === 'asc' ? 'Asc' : 'Desc'}`);
    }

    function applyDbDensity() {
      if (!els.dbViewer) return;
      if (state.viewer.dense) {
        els.dbViewer.classList.add('density-dense');
        els.dbDensity && (els.dbDensity.textContent = 'Comfortable View');
      } else {
        els.dbViewer.classList.remove('density-dense');
        els.dbDensity && (els.dbDensity.textContent = 'Dense View');
      }
    }

    function loadColumnPrefs() {
      try {
        const raw = localStorage.getItem('gemma_viewer_columns');
        if (raw) {
          state.viewer.columns = JSON.parse(raw);
        } else {
          // Default: only these are checked automatically: created_at, duration, speaker, emotion, job_id
          state.viewer.columns = {
            created_at: true,
            start_time: false,
            end_time: false,
            duration: true,
            speaker: true,
            emotion: true,
            job_id: true,
            transcript_id: false,
            segment_id: false,
          };
        }
      } catch {
        state.viewer.columns = { created_at: true, start_time: false, end_time: false, duration: true, speaker: true, emotion: true, job_id: true, transcript_id: false, segment_id: false };
      }
    }

    function saveColumnPrefs() {
      try {
        localStorage.setItem('gemma_viewer_columns', JSON.stringify(state.viewer.columns || {}));
      } catch {}
    }

    function syncColumnToggles() {
      if (!els.colsPanel) els.colsPanel = mountEl.querySelector('[data-role="cols-panel"]');
      if (!els.colsPanel) return;
      const toggles = Array.from(els.colsPanel.querySelectorAll('input[type="checkbox"][data-col]'));
      els.colsToggles = toggles;
      const columns = state.viewer.columns || {};
      toggles.forEach((cb) => {
        const key = cb.getAttribute('data-col');
        const val = columns[key];
        cb.checked = Boolean(val);
        cb.addEventListener('change', () => {
          columns[key] = cb.checked;
          saveColumnPrefs();
          renderDbHeader();
          refreshDb(true);
        });
      });
    }

    function renderDbHeader() {
      const header = mountEl.querySelector('[data-role="db-header-cols"]');
      if (!header) return;
      const c = state.viewer.columns || {};
      const parts = [];
      if (c.created_at !== false) parts.push('<div class="db-date">Date</div>');
      if (c.start_time !== false) parts.push('<div class="db-time">Start</div>');
      if (c.end_time) parts.push('<div class="db-time">End</div>');
      if (c.duration) parts.push('<div class="db-time">Duration</div>');
      if (c.speaker !== false) parts.push('<div class="db-speaker">Speaker</div>');
      if (c.emotion) parts.push('<div class="db-emotion">Emotion</div>');
      if (c.job_id) parts.push('<div class="db-job">Job ID</div>');
      if (c.segment_id || c.transcript_id) parts.push('<div class="db-segment">IDs</div>');
      parts.push('<div class="db-text" style="flex:1;">Text</div>');
      header.innerHTML = parts.join('');
    }

    function openLogOverlay() {
      if (!els.logOverlay) return;
      els.logOverlay.setAttribute('data-open', 'true');
      els.logToggle && (els.logToggle.textContent = 'Hide Live Logs');
    }

    function closeLogOverlay() {
      if (!els.logOverlay) return;
      els.logOverlay.removeAttribute('data-open');
      els.logToggle && (els.logToggle.textContent = 'Show Live Logs');
    }

    function resetProgress() {
      state.total = 0;
      state.completed = 0;
      els.progressFill.style.width = '0%';
      els.progressDetail.textContent = 'Idle';
      els.progress.hidden = true;
    }

    function setRunning(running) {
      state.running = running;
      els.runStream.disabled = running;
      els.runQuick.disabled = running;
      els.cancel.disabled = !running;
    }

    async function fetchSpeakers() {
      if (state.speakersLoaded) return;
      try {
        const response = await api.getSpeakers();
        if (response && response.success && Array.isArray(response.speakers)) {
          const fragment = document.createDocumentFragment();
          response.speakers.sort().forEach((speaker) => {
            const option = document.createElement('option');
            option.value = speaker;
            option.textContent = speaker;
            fragment.appendChild(option);
          });
          els.speakerSelect.appendChild(fragment);
        }
      } catch (error) {
        console.warn('[Analyzer] Failed to load speakers', error);
      } finally {
        state.speakersLoaded = true;
      }
    }

    async function updateCount(debounced = true) {
      const run = async () => {
        const filters = gatherFilters();
        console.debug('[Analyzer] updateCount filters', filters);
        try {
          const analysisId = createAnalysisId();
          const response = await api.countTranscripts(filters, { analysisId });
          if (response && typeof response.count === 'number') {
            updateCountDisplay(response.count);
            if (response.count === 0 && state.transcriptWindow?.transcript_count) {
              const summary = summarizeWindowRange(state.transcriptWindow);
              logEvent(
                `[Analyzer] 0 transcripts match filters. Indexed window ${summary || 'unknown'} (${state.transcriptWindow.transcript_count} total).`,
                'warning',
              );
            }
            return;
          }
        } catch (error) {
          console.warn('[Analyzer] countTranscripts failed, using fallback', error);
          try {
            const recent = await api.getRecentTranscripts(Math.max(filters.limit || 20, 100));
            const transcripts = recent?.transcripts || [];
            const speaker = filters.speakers ? filters.speakers[0] : null;
            const emotionSet = filters.emotions ? new Set(filters.emotions.map((e) => e.toLowerCase())) : null;
            const startDate = filters.start_date ? new Date(filters.start_date + 'T00:00:00') : null;
            const endDate = filters.end_date ? new Date(filters.end_date + 'T23:59:59') : null;
            const keywords = (filters.keywords || '')
              .split(',')
              .map((k) => k.trim().toLowerCase())
              .filter(Boolean);
            const requireAll = filters.match === 'all';
            let count = 0;
            transcripts.forEach((t) => {
              if (speaker) {
                const s = (t.speaker || t.primary_speaker || '').trim();
                if (s !== speaker) return;
              }
              if (emotionSet) {
                const e = (t.dominant_emotion || t.emotion || '').toLowerCase();
                if (!emotionSet.has(e)) return;
              }
              if (startDate || endDate) {
                const ts = t.timestamp || t.created_at;
                if (!ts) return;
                const dt = new Date(ts);
                if (startDate && dt < startDate) return;
                if (endDate && dt > endDate) return;
              }
              if (keywords.length) {
                const text = (t.full_text || t.snippet || '').toLowerCase();
                if (!text) return;
                const matches = keywords.filter((kw) => text.includes(kw));
                if (requireAll && matches.length !== keywords.length) return;
                if (!requireAll && matches.length === 0) return;
              }
              count += 1;
            });
            updateCountDisplay(count);
            if (count === 0 && state.transcriptWindow?.transcript_count) {
              const summary = summarizeWindowRange(state.transcriptWindow);
              logEvent(
                `[Analyzer] 0 transcripts match filters. Indexed window ${summary || 'unknown'} (${state.transcriptWindow.transcript_count} total).`,
                'warning',
              );
            }
          } catch (fallbackError) {
            console.error('[Analyzer] count fallback failed', fallbackError);
            updateCountDisplay(0);
          }
        }
      };

      if (debounced) {
        clearTimeout(state.debounceTimer);
        state.debounceTimer = setTimeout(run, 300);
      } else {
        await run();
      }
    }

    function stopStream(reason = 'stopped') {
      if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
      }
      if (reason === 'complete') {
        state.streamCompleted = true;
        logEvent('Streaming completed.', 'success');
      } else if (state.running) {
        logEvent(`Streaming stopped (${reason})`, reason === 'error' ? 'error' : 'warning');
      }
      setRunning(false);
      els.progress.hidden = false;
      els.progressDetail.textContent = 'Idle';
      els.progressFill.style.width = '0%';
    }

    function addResultCard({ index, total, response, item }) {
      const label = (item && (item.label || item.Label)) || null;
      const titleText = label ? `Statement ${label} (${index} of ${total})` : `Statement ${index} of ${total}`;
      const card = document.createElement('div');
      card.className = 'analyzer-result-card';
      card.dataset.index = String(index);
      card.innerHTML = `
        <div class="analyzer-result-header">
          <div>
            <h4>${titleText}</h4>
            <p class="text-muted">
              ${label ? `<span class="badge badge-label">${label}</span>` : ''}
              Speaker: ${item.speaker || 'Unknown'} • Emotion: ${item.emotion || 'n/a'}
            </p>
          </div>
          <div class="analyzer-result-metadata">
            ${item.created_at ? `<span>${new Date(item.created_at).toLocaleString()}</span>` : ''}
            ${item.job_id ? `<span>Job ${item.job_id}</span>` : ''}
          </div>
        </div>
        <div class="analyzer-result-context">
          ${Array.isArray(item.context_before) && item.context_before.length
            ? `<details><summary>Context (${item.context_before.length})</summary>
                ${item.context_before
                  .map(
                    (ctx) => `<p><strong>${ctx.speaker || 'Speaker'}:</strong> ${ctx.text}</p>`
                  )
                  .join('')}
              </details>`
            : ''}
          <p><strong>Statement:</strong> ${item.text}</p>
        </div>
        <div class="analyzer-result-body">
          <h5>Gemma Response</h5>
          <pre>${response}</pre>
        </div>
      `;
      els.resultsStream.appendChild(card);
      els.resultsStream.scrollTop = els.resultsStream.scrollHeight;
      card.classList.add('highlight');
      setTimeout(() => card.classList.remove('highlight'), 5000);
    }

    async function runStreamingAnalysis() {
      const filters = gatherFilters();
      const analysisLimit = getAnalysisLimit();
      filters.limit = Math.min(analysisLimit, filters.limit || analysisLimit);
      logFilterSummary(filters, analysisLimit);
      if (!els.prompt.value.trim()) {
        showToast('Prompt Required', 'Please enter an analysis prompt before running.', 'error');
        return;
      }
      state.analysisId = createAnalysisId();
      state.streamCompleted = false;
      state.latestStreamResults = [];
      state.latestStreamSections = [];
      clearResults();
      els.log.innerHTML = '';
      resetProgress();
      els.progress.hidden = false;
      els.progressDetail.textContent = 'Preparing analysis...';
      setRunning(true);
      logEvent('Connecting to Gemma stream...');

      try {
        const payload = {
          filters,
          custom_prompt: els.prompt.value.trim(),
          max_tokens: 512,
          temperature: 0.4,
          max_statements: analysisLimit,
          analysis_id: state.analysisId,
        };
        if (state.eventSource) {
          state.eventSource.close();
        }
        const encoded = encodePayload(payload);
        const streamUrl = api.buildURL(`/gemma/analyze/stream/inline/start?payload=${encoded}&analysis_id=${encodeURIComponent(state.analysisId)}`);
        const es = new EventSource(streamUrl, { withCredentials: true });
        state.eventSource = es;

        es.addEventListener('meta', (event) => {
          try {
            const data = JSON.parse(event.data);
            if (typeof data.total === 'number') {
              state.total = data.total;
              state.completed = 0;
              els.progressDetail.textContent = `Found ${state.total} statements`;
              logEvent(`Streaming analysis started (${state.total} statements)`);
            }
            if (typeof data.max_statements === 'number') {
              logEvent(`Server enforcing ${data.max_statements} statement limit`);
            }
            if (data.message) {
              const level = data.message.toLowerCase().includes('fallback') ? 'warning' : 'info';
              logEvent(data.message, level);
            }
            if (data.fallback) {
              logEvent(`Fallback query source in use: ${data.fallback}`, 'warning');
              if (data.fallback_reason) {
                logEvent(`Fallback reason: ${data.fallback_reason}`, 'warning');
              }
            }
          } catch (err) {
            console.warn('meta event parse failed', err);
          }
        });

        es.addEventListener('step', (event) => {
          try {
            const data = JSON.parse(event.data);
            const { i, total, status, prompt_fragment } = data;
            if (total) {
              state.total = total;
              updateCountDisplay(state.total);
            }
            const pct = total ? Math.min(100, Math.max(0, Math.round(((i - 1) / total) * 100))) : 0;
            els.progressFill.style.width = `${pct}%`;
            els.progressDetail.textContent = `Statement ${i} of ${total}: ${status}`;
            if (prompt_fragment) {
              logEvent(`Statement ${i}/${total} → ${status}: ${prompt_fragment.substring(0, 120)}...`);
            } else {
              logEvent(`Statement ${i}/${total} → ${status}`);
            }
          } catch (err) {
            console.warn('step event parse failed', err);
          }
        });

        es.addEventListener('result', (event) => {
          try {
            const data = JSON.parse(event.data);
            state.completed = data.i || state.completed + 1;
            if (state.total) {
              updateCountDisplay(state.total);
            }
            const pct = state.total ? Math.min(100, Math.round((state.completed / state.total) * 100)) : 100;
            els.progressFill.style.width = `${pct}%`;
            els.progressDetail.textContent = `Gemma responded (${state.completed}/${state.total})`;
            addResultCard({ index: data.i, total: state.total, response: data.response, item: data.item });
            if (typeof data.response === 'string') {
              const trimmed = data.response.length > 180 ? `${data.response.slice(0, 180)}…` : data.response;
              logEvent(`Gemma responded: ${trimmed}`, 'success');
            } else {
              logEvent(`Gemma response received for statement ${data.i}`, 'success');
            }
            state.latestStreamResults.push({ item: data.item, response: data.response, index: data.i, total: state.total });
            state.latestStreamSections.push(buildLocalSection(data.item, data.response, data.i, state.total));
          } catch (err) {
            console.warn('result event parse failed', err);
          }
        });

        es.addEventListener('server_error', (event) => {
          try {
            const data = JSON.parse(event.data || '{}');
            const msg = data.detail || 'Server error while preparing analysis.';
            logEvent(msg, 'error');
          } catch (_) {}
          // Mark complete to avoid network 'error' handler showing a misleading toast
          state.streamCompleted = true;
          stopStream('error');
        });

        es.addEventListener('done', (event) => {
          try {
            const data = JSON.parse(event.data);
            const model = data.model || 'unknown';
            els.progressFill.style.width = '100%';
            els.progressDetail.textContent = `Analysis complete (${state.completed}/${state.total})`;
            logEvent(`Analysis complete using ${model}`, 'success');

            let summaryPayload = data.summary;
            if (!summaryPayload && state.latestStreamResults?.length) {
              summaryPayload = buildLocalSummary(state.latestStreamResults);
              if (summaryPayload) {
                logEvent('[Summary] Backend summary unavailable; generated local summary', 'warning');
              }
            }
            if (summaryPayload) {
              els.quickSummary.hidden = false;
              els.quickSummaryText.textContent = summaryPayload;
              const meta = [];
              if (state.total) meta.push(`📊 ${state.total} statements`);
              if (data.completed_at) meta.push(`⏱️ completed at ${new Date(data.completed_at).toLocaleTimeString()}`);
              if (data.artifact_id) meta.push(`💾 archived ${data.artifact_id}`);
              if (!data.summary) meta.push('⚠️ local summary');
              els.quickSummaryMeta.textContent = meta.join(' • ');
            } else {
              els.quickSummary.hidden = false;
              els.quickSummaryText.textContent = 'Summary unavailable. Check backend logs or rerun analysis.';
              els.quickSummaryMeta.textContent = '';
            }

            let nextArtifactId = data.artifact_id;
            if (!nextArtifactId && state.latestStreamSections?.length) {
              const localId = `local-${Date.now()}`;
              const localArtifact = {
                artifact_id: localId,
                title: `Streaming Analysis (${new Date().toLocaleTimeString()})`,
                body: state.latestStreamSections.join('\n\n'),
                created_at: new Date().toISOString(),
              };
              registerLocalArtifact(localArtifact);
              nextArtifactId = localId;
              logEvent(`[Archive] Created local artifact ${localId} (backend archive unavailable)`, 'warning');
            }
            if (nextArtifactId) {
              state.currentArtifactId = nextArtifactId;
              if (data.artifact_id) {
                logEvent(`[Archive] Auto-selecting artifact ${nextArtifactId} from streaming run`);
                previewArtifact(nextArtifactId);
                loadArtifacts(true);
              } else {
                logEvent(`[Archive] Auto-selecting local artifact ${nextArtifactId}`, 'warning');
                previewArtifact(nextArtifactId);
              }
            } else {
              logEvent('[Archive] No artifact was produced for this run', 'warning');
            }
          } catch (err) {
            console.warn('done event parse failed', err);
          }
          stopStream('complete');
        });

        es.addEventListener('error', (err) => {
          if (state.streamCompleted || !state.running) {
            return;
          }
          console.error('SSE error', err);
          logEvent('Streaming connection lost.', 'error');
          stopStream('error');
          showToast('Stream Error', 'Connection lost during streaming analysis.', 'error');
        });
      } catch (error) {
        console.error('[Analyzer] Streaming analysis failed', error);
        showToast('Analysis Failed', error.message || 'Unable to start streaming analysis', 'error');
        logEvent(error.message || 'Streaming analysis failed', 'error');
        stopStream('error');
      }
    }

    async function runQuickSummary() {
      const filters = gatherFilters();
      const analysisLimit = getAnalysisLimit();
      filters.limit = Math.min(analysisLimit, filters.limit || analysisLimit);
      logFilterSummary(filters, analysisLimit);
      if (!els.prompt.value.trim()) {
        showToast('Prompt Required', 'Please enter an analysis prompt before running.', 'error');
        return;
      }
      state.analysisId = createAnalysisId();
      clearResults();
      els.quickSummary.hidden = false;
      els.quickSummaryText.textContent = 'Running analysis...';
      els.quickSummaryMeta.textContent = '';
      setRunning(true);
      logEvent('Running quick Gemma analysis...');
      try {
        const response = await api.gemmaAnalyze({
          filters,
          custom_prompt: els.prompt.value.trim(),
          max_tokens: 1024,
          temperature: 0.3,
          max_statements: analysisLimit,
        }, { analysisId: state.analysisId });
        if (response && response.success) {
          els.quickSummaryText.textContent = response.analysis || 'No analysis returned.';
          const meta = [];
          if (typeof response.transcripts_analyzed === 'number') meta.push(`📊 ${response.transcripts_analyzed} transcripts analyzed`);
          if (typeof response.processing_time_seconds === 'number') meta.push(`⏱️ ${response.processing_time_seconds}s processing`);
          if (response.saved_to) meta.push(`💾 Saved to ${response.saved_to.split('/').pop()}`);
          els.quickSummaryMeta.textContent = meta.join(' • ');
          logEvent('Quick analysis completed', 'success');
        } else {
          throw new Error(response?.error || 'Quick analysis failed');
        }
      } catch (error) {
        console.error('[Analyzer] Quick analysis failed', error);
        els.quickSummaryText.textContent = 'Analysis failed.';
        logEvent(error.message || 'Quick analysis failed', 'error');
        showToast('Analysis Failed', error.message || 'Quick analysis failed.', 'error');
      } finally {
        setRunning(false);
      }
    }

    // =====================
    // Analysis Archive UI
    // =====================
    function buildLocalSection(item = {}, response = '', index = 0, total = 0) {
      const lines = [];
      if (item.created_at) lines.push(`Timestamp: ${new Date(item.created_at).toLocaleString()}`);
      if (item.speaker) lines.push(`Speaker: ${item.speaker}`);
      if (item.emotion) lines.push(`Emotion: ${item.emotion}`);
      if (item.text) lines.push(`Statement: ${item.text}`);
      if (Array.isArray(item.context_before) && item.context_before.length) {
        const ctx = item.context_before.map((ctxItem) => `${ctxItem.speaker || 'Speaker'}: ${ctxItem.text || ''}`).join('\n');
        lines.push(`Context before:\n${ctx}`);
      }
      lines.push(`Gemma Response:\n${response || ''}`);
      lines.push(`(Statement ${index}/${total || 'n/a'})`);
      return lines.join('\n');
    }

    function buildLocalSummary(results = []) {
      if (!results.length) return '';
      const bullets = results.slice(0, 6).map((entry) => {
        const speaker = entry?.item?.speaker || 'Speaker';
        const snippet = (entry?.item?.text || '').trim().slice(0, 160);
        return `- ${speaker}: ${snippet || 'No transcript text provided.'}`;
      }).join('\n');
      return `${bullets}\n\nOverall: Conversations were analyzed locally because the archive service was unavailable. Review backend logs to persist results.`;
    }

    function renderArtifactItem(item, options = {}) {
      const row = document.createElement('div');
      row.className = 'artifact-row';
      if (options.local || item.is_local) {
        row.classList.add('artifact-local-row');
      }
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = state.selectedArtifacts.has(item.artifact_id);
      const syncSelectionClass = () => {
        if (cb.checked) {
          state.selectedArtifacts.add(item.artifact_id);
          row.classList.add('artifact-selected');
        } else {
          state.selectedArtifacts.delete(item.artifact_id);
          row.classList.remove('artifact-selected');
        }
      };
      cb.addEventListener('change', (event) => {
        event.stopPropagation();
        syncSelectionClass();
      });
      syncSelectionClass();

      const info = document.createElement('div');
      info.className = 'artifact-info';
      info.innerHTML = `
        <span class="artifact-title">${escapeHTML(item.title || 'Untitled')}</span>
        <span class="artifact-meta">${escapeHTML(item.created_at || 'Unknown time')} • ${escapeHTML((item.size || 0).toString())} bytes</span>
      `;

      row.appendChild(cb);
      row.appendChild(info);
      row.addEventListener('click', (event) => {
        if (event.target !== cb) {
          previewArtifact(item.artifact_id);
        }
      });
      return row;
    }

    function syncLocalArtifacts() {
      if (!els.artifactsLocal) return;
      els.artifactsLocal.innerHTML = '';
      if (!state.localArtifacts.length) return;
      const label = document.createElement('div');
      label.className = 'archive-local-label';
      label.textContent = 'Local (unsaved) artifacts';
      els.artifactsLocal.appendChild(label);
      state.localArtifacts.forEach((artifact) => {
        const row = renderArtifactItem(artifact, { local: true });
        els.artifactsLocal.appendChild(row);
      });
    }

    function registerLocalArtifact(artifact) {
      if (!artifact || !artifact.artifact_id) return;
      artifact.is_local = true;
      state.localArtifacts = state.localArtifacts.filter((a) => a.artifact_id !== artifact.artifact_id);
      state.localArtifacts.unshift(artifact);
      state.localArtifactMap[artifact.artifact_id] = artifact;
      state.selectedArtifacts.add(artifact.artifact_id);
      if (state.localArtifacts.length > 5) {
        const removed = state.localArtifacts.pop();
        if (removed) {
          delete state.localArtifactMap[removed.artifact_id];
          state.selectedArtifacts.delete(removed.artifact_id);
        }
      }
      syncLocalArtifacts();
    }

    function getArtifactData(artifactId) {
      if (!artifactId) return null;
      if (state.localArtifactMap[artifactId]) return state.localArtifactMap[artifactId];
      return state.artifacts.find((a) => a.artifact_id === artifactId) || null;
    }

    function isLocalArtifact(artifactId) {
      return Boolean(state.localArtifactMap[artifactId]);
    }

    async function loadArtifacts(reset = false) {
      try {
        if (!els.artifactsList) return;
        const remoteContainer = els.artifactsRemote || els.artifactsList;
        if (reset) {
          state.artifacts = [];
          state.artifactsOffset = 0;
          state.artifactsHasMore = true;
          state.selectedArtifacts.clear();
          if (remoteContainer) remoteContainer.innerHTML = '';
          syncLocalArtifacts();
          logEvent('[Archive] Refresh requested (offset reset to 0)');
        } else {
          logEvent(`[Archive] Load more requested (offset=${state.artifactsOffset})`);
        }
        if (!state.artifactsHasMore) {
          logEvent('[Archive] No additional artifacts to load', 'warning');
          return;
        }
        const resp = await api.listArtifacts(25, state.artifactsOffset);
        if (!resp || resp.success === false) {
          throw new Error(resp?.error || 'Archive unavailable');
        }
        const items = Array.isArray(resp?.items) ? resp.items : [];
        state.artifacts.push(...items);
        state.artifactsOffset += items.length;
        state.artifactsHasMore = Boolean(resp?.has_more) || (items.length > 0);
        const frag = document.createDocumentFragment();
        items.forEach((it) => {
          const row = renderArtifactItem(it);
          frag.appendChild(row);
        });
        if (remoteContainer) remoteContainer.appendChild(frag);
        if (items.length === 0 && state.artifactsOffset === 0) {
          if (remoteContainer) {
            remoteContainer.innerHTML = '<div class="archive-empty">No archived analyses yet.</div>';
          }
        }
        logEvent(`[Archive] Loaded ${items.length} artifacts (offset=${state.artifactsOffset})`);
      } catch (e) {
        const msg = describeError(e);
        logEvent(`[Archive] loadArtifacts failed (offset=${state.artifactsOffset}): ${msg}`, 'error');
        const remoteContainer = els.artifactsRemote || els.artifactsList;
        if (remoteContainer && state.artifactsOffset === 0) {
          remoteContainer.innerHTML = `<div class="archive-error">Archive service unavailable (${msg}). Rebuild rag-service or run ./start.sh --build-all.</div>`;
        }
        state.artifactsHasMore = false;
      }
    }

    async function previewArtifact(artifactId) {
      try {
        const previousArtifact = state.currentArtifactId;
        if (!artifactId) return;
        if (state.localArtifactMap[artifactId]) {
          const localArtifact = state.localArtifactMap[artifactId];
          els.artifactTitle && (els.artifactTitle.textContent = localArtifact.title || artifactId);
          els.artifactBody && (els.artifactBody.textContent = localArtifact.body || '—');
          state.currentArtifactId = artifactId;
          logEvent(`[Archive] Previewing local artifact ${artifactId}`);
          if (previousArtifact !== artifactId) {
            state.chatSessionId = null;
            state.chatMessagesHistory = [];
            if (els.chatMessages) {
              els.chatMessages.innerHTML = '<div style="color:#9ca3af; font-size:0.85rem;">Select an artifact and ask a question.</div>';
            }
          }
          return;
        }
        logEvent(`[Archive] Previewing artifact ${artifactId}`);
        const resp = await api.getArtifact(artifactId);
        if (resp && resp.success && resp.artifact) {
          els.artifactTitle && (els.artifactTitle.textContent = resp.artifact.title || artifactId);
          els.artifactBody && (els.artifactBody.textContent = resp.artifact.body || '—');
          state.currentArtifactId = artifactId;
          if (previousArtifact !== artifactId) {
            state.chatSessionId = null;
            state.chatMessagesHistory = [];
            if (els.chatMessages) {
              els.chatMessages.innerHTML = '<div style="color:#9ca3af; font-size:0.85rem;">Select an artifact and ask a question.</div>';
            }
          }
          logEvent(`[Archive] Artifact ${artifactId} loaded into preview`, 'success');
        } else {
          els.artifactTitle && (els.artifactTitle.textContent = 'Artifact unavailable');
          els.artifactBody && (els.artifactBody.textContent = 'Archive returned 404 or empty body.');
          logEvent(`[Archive] Artifact ${artifactId} unavailable`, 'warning');
        }
      } catch (e) {
        logEvent(`[Archive] getArtifact failed: ${e?.message || e}`, 'error');
      }
    }

    function openMetaOverlay() {
      if (!els.metaOverlay) return;
      els.metaLog && (els.metaLog.textContent = '');
      els.metaOverlay.style.display = 'flex';
    }
    function closeMetaOverlay() {
      if (!els.metaOverlay) return;
      els.metaOverlay.style.display = 'none';
    }
    function appendMetaLog(line) {
      if (!els.metaLog) return;
      els.metaLog.textContent += (line.endsWith('\n') ? line : (line + '\n'));
      els.metaLog.scrollTop = els.metaLog.scrollHeight;
    }
    function parseSseChunk(chunk) {
      const parts = chunk.split('\n\n');
      parts.forEach(block => {
        const lines = block.trim().split('\n');
        if (lines.length < 2) return;
        const ev = lines[0].replace('event: ', '').trim();
        const data = lines.slice(1).join('\n').replace(/^data: /, '');
        try {
          const obj = JSON.parse(data);
          if (ev === 'meta') appendMetaLog(`Meta: total=${obj.total}, strategy=${obj.strategy}`);
          if (ev === 'result') appendMetaLog(`Chunk ${obj.i}/${obj.total}: ${String(obj.summary || '').slice(0,120)}…`);
          if (ev === 'error') { appendMetaLog(`Error: ${obj.detail || ''}`); showToast('Meta-analysis error', obj.detail || 'Unexpected error', 'error'); }
          if (ev === 'done') {
            appendMetaLog(`Done. artifact_id=${obj.artifact_id || 'n/a'}`);
            loadArtifacts(true);
            // Auto-close overlay shortly after completion
            setTimeout(() => closeMetaOverlay(), 600);
          }
        } catch {}
      });
    }
    function runMetaAnalysis() {
      const selected = Array.from(state.selectedArtifacts);
      const ids = selected.length ? selected : (state.currentArtifactId ? [state.currentArtifactId] : []);
      if (!ids.length) {
        showToast('Select artifacts', 'Pick at least one artifact (or preview one).', 'warning');
        return;
      }
      openMetaOverlay();
      const stop = api.streamMetaAnalysis({ artifact_ids: ids, strategy: 'map_reduce' }, {
        onEvent: parseSseChunk,
        analysisId: state.analysisId || createAnalysisId(),
      });
      els.metaClose && (els.metaClose.onclick = () => { try { stop(); } catch(_){}; closeMetaOverlay(); });
    }

    function setChatDrawerOpen(open) {
      if (!els.chatDrawer) return;
      if (open) {
        els.chatDrawer.setAttribute('data-open', 'true');
        els.chatOverlay && els.chatOverlay.setAttribute('data-open', 'true');
      } else {
        els.chatDrawer.removeAttribute('data-open');
        els.chatOverlay && els.chatOverlay.removeAttribute('data-open');
      }
    }
    function getActiveArtifactId() {
      if (state.currentArtifactId) return state.currentArtifactId;
      const arr = Array.from(state.selectedArtifacts);
      return arr.length ? arr[0] : null;
    }
    function ensureChatSession() {
      if (!state.chatSessionId) {
        state.chatSessionId = `chat_${createAnalysisId()}`;
        state.chatMessagesHistory = [];
      }
    }

    function openChatDrawer() {
      const aid = getActiveArtifactId();
      if (!aid) {
        logEvent('[Chat] Drawer blocked – no artifact selected', 'warning');
        showToast('Select artifact', 'Preview or check an artifact to chat about it.', 'warning');
        return;
      }
      ensureChatSession();
      setChatDrawerOpen(true);
      if (els.chatMessages) {
        els.chatMessages.innerHTML = '';
        if (state.chatMessagesHistory.length) {
          state.chatMessagesHistory.forEach((msg) => {
            appendChat(msg.role, msg.content);
          });
        } else {
          els.chatMessages.innerHTML = '<div style="color:#9ca3af; font-size:0.85rem;">Select an artifact and ask a question.</div>';
        }
      }
      logEvent(`[Chat] Drawer opened for artifact ${aid}`);
    }
    function closeChatDrawer() {
      setChatDrawerOpen(false);
      logEvent('[Chat] Drawer closed');
    }
    function appendChat(role, text, options = {}) {
      if (!els.chatMessages) return;
      const div = document.createElement('div');
      div.style.margin = '8px 0';
      const roleColor = role === 'user' ? '#93c5fd' : '#a7f3d0';
      let extra = '';
      const strategyLabel = getStrategyLabel(options.strategy);
      if (strategyLabel) {
        extra += `
          <div style="margin-top:4px;">
            <span style="display:inline-flex; align-items:center; font-size:0.65rem; letter-spacing:0.05em; text-transform:uppercase; color:#e5e7eb; background:#1f2937; border-radius:999px; padding:2px 10px;">
              ${escapeHTML(strategyLabel)}
            </span>
          </div>`;
      }
      if (Array.isArray(options.citations) && options.citations.length) {
        const citeHtml = options.citations
          .map((cite, idx) => {
            const sourceType = (cite.type || 'artifact').toLowerCase();
            const label = cite.label || cite.index || (sourceType === 'chat' ? `U${idx + 1}` : `C${cite.seq ?? idx + 1}`);
            const quote = escapeHTML((cite.quote || '').slice(0, 280));
            const context = sourceType === 'chat'
              ? (cite.role === 'assistant' ? 'Assistant turn' : 'User turn')
              : (sourceType === 'summary' ? 'Summary section' : 'Artifact excerpt');
            return `<li><strong>[${label}]</strong> <em>${context}</em> — ${quote}</li>`;
          })
          .join('');
        extra += `<div style="margin-top:6px;">
          <div style="font-size:0.7rem; color:#9ca3af;">Sources</div>
          <ul style="margin:4px 0 0 16px; font-size:0.8rem; color:#d1d5db;">${citeHtml}</ul>
        </div>`;
      }
      div.innerHTML = `<div style="font-weight:600; color:${roleColor}">${role}</div><div>${text}</div>${extra}`;
      els.chatMessages.appendChild(div);
      els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
    }
    async function sendChatFallback(aid, msg) {
      try {
        const artifact = getArtifactData(aid);
        const contextBody = artifact?.body || state.latestStreamSections.join('\n\n');
        const historyForServer = state.chatMessagesHistory.slice(0, -1).map((entry) => ({
          role: entry.role,
          content: entry.content,
        }));
        const payload = {
          query: contextBody ? `${msg}\n\nContext:\n${contextBody}` : msg,
          max_tokens: 384,
          temperature: 0.4,
          top_k_results: 4,
          session_id: state.chatSessionId,
          history_messages: historyForServer,
          user_message: msg,
        };
        const resp = await api.gemmaChatRag(payload);
        logEvent('[Chat] Used fallback RAG chat for response', 'warning');
        return resp || {};
      } catch (fallbackError) {
        logEvent(`[Chat] Fallback failed: ${describeError(fallbackError)}`, 'error');
        throw fallbackError;
      }
    }

    async function sendChat({ presetMessage = null, summarize = false } = {}) {
      if (!els.chatInput && !presetMessage) return;
      const raw = presetMessage || (els.chatInput.value || '').trim();
      if (!raw) return;
      const aid = getActiveArtifactId();
      if (!aid) {
        logEvent('[Chat] Send blocked – no artifact selected', 'warning');
        showToast('Select artifact', 'Pick an artifact before chatting.', 'warning');
        return;
      }
      ensureChatSession();
      const userMessage = raw;
      appendChat('user', userMessage);
      state.chatMessagesHistory.push({ role: 'user', content: userMessage });
      trimClientChat();
      if (!presetMessage && els.chatInput) {
        els.chatInput.value = '';
      }
      if (els.chatSend) {
        els.chatSend.disabled = true;
        els.chatSend.textContent = 'Sending…';
      }
      try {
        const mode = els.chatModeSelect ? els.chatModeSelect.value : 'rag';
        logEvent(`[Chat] Sending question (${mode}) to artifact ${aid}`);
        let assistantText = '';
        let usedFallback = false;
        const payload = {
          artifact_id: aid,
          chat_session_id: state.chatSessionId,
          messages: state.chatMessagesHistory.concat({ role: 'user', content: userMessage }),
          mode,
          summarize_chat: summarize,
        };
        let responsePayload = null;
        const useLocalOnly = isLocalArtifact(aid);
        if (!useLocalOnly) {
          try {
            responsePayload = await api.chatOnArtifactV2(payload);
          } catch (primaryError) {
            if (primaryError?.status === 404) {
              logEvent('[Chat] v2 endpoint unavailable; falling back to legacy path', 'warning');
            } else {
              logEvent(`[Chat] chat-on-artifact/v2 error: ${describeError(primaryError)}`, 'warning');
            }
          }
        }
        if (responsePayload) {
          assistantText = responsePayload.text || '[no answer]';
          state.chatSessionId = responsePayload.chat_session_id || state.chatSessionId;
          state.chatMessagesHistory.push({ role: 'assistant', content: assistantText });
          trimClientChat();
          appendChat('assistant', assistantText, {
            citations: responsePayload.citations,
            strategy: responsePayload.used_strategy,
          });
          if (responsePayload.router_notes) {
            const notes = responsePayload.router_notes;
            const intent = notes.intent || responsePayload.used_strategy || 'unknown';
            const action = notes.action || '—';
            const latency = typeof notes.latency_ms === 'number' ? `${notes.latency_ms}ms` : 'unknown latency';
            logEvent(`[Chat] Router intent=${intent} action=${action} citations=${notes.citations ?? 0} latency=${latency}`);
          }
          logEvent(`[Chat] Response received (${responsePayload.used_strategy || 'unknown'})`, 'success');
        } else {
          usedFallback = true;
          const fallbackResponse = await sendChatFallback(aid, userMessage);
          const fallbackAnswer = fallbackResponse.text
            || fallbackResponse.answer
            || fallbackResponse.message
            || '[no answer]';
          state.chatSessionId = fallbackResponse.chat_session_id || state.chatSessionId;
          state.chatMessagesHistory.push({ role: 'assistant', content: fallbackAnswer });
          trimClientChat();
          appendChat('assistant', fallbackAnswer, {
            citations: fallbackResponse.citations,
            strategy: fallbackResponse.used_strategy,
          });
          if (fallbackResponse.router_notes) {
            const notes = fallbackResponse.router_notes;
            const intent = notes.intent || fallbackResponse.used_strategy || 'unknown';
            const action = notes.action || '—';
            const latency = typeof notes.latency_ms === 'number' ? `${notes.latency_ms}ms` : 'unknown latency';
            logEvent(`[Chat] Fallback router intent=${intent} action=${action} citations=${notes.citations ?? 0} latency=${latency}`,'warning');
          } else {
            logEvent('[Chat] Response received via fallback', 'warning');
          }
        }
      } catch (e) {
        const errMsg = describeError(e);
        appendChat('assistant', `[error] ${errMsg}`);
        logEvent(`[Chat] Error: ${errMsg}`, 'error');
        showToast('Chat failed', errMsg, 'error');
      } finally {
        if (els.chatSend) {
          els.chatSend.disabled = false;
          els.chatSend.textContent = 'Send';
        }
      }
    }

    async function summarizeChat() {
      await sendChat({ presetMessage: 'Please summarize this entire chat so far.', summarize: true });
    }

    function bindEvents() {
      els.dateButtons.forEach((btn) => {
        btn.addEventListener('click', () => {
          const days = parseInt(btn.dataset.days, 10);
          applyDatePreset(days);
        });
      });

      els.customButton.addEventListener('click', () => {
        els.dateButtons.forEach((b) => b.removeAttribute('data-active'));
        els.customButton.setAttribute('data-active', 'true');
        els.startDate.disabled = false;
        els.endDate.disabled = false;
        els.startDate.focus();
      });

      [els.startDate, els.endDate].forEach((input) => {
        input.addEventListener('change', () => {
          els.customButton.setAttribute('data-active', 'true');
          els.dateButtons.forEach((b) => b.removeAttribute('data-active'));
          updateCount();
        });
      });

      [els.speakerSelect, els.limitInput, els.keywords, els.contextLines, els.matchMode, els.searchType].forEach((control) => {
        control.addEventListener('change', () => { updateCount(); refreshDb(true); });
        control.addEventListener('keyup', () => { updateCount(); /* no immediate refresh for typing */ });
      });

      if (els.analysisCountInput) {
        els.analysisCountInput.addEventListener('change', () => {
          const limit = getAnalysisLimit();
          logEvent(`[Filters] Analysis limit set to ${limit} statements`);
        });
      }

      els.emotionAll.addEventListener('change', () => {
        const checked = els.emotionAll.checked;
        els.emotionChecks.forEach((cb) => {
          cb.checked = checked;
        });
        updateCount();
        refreshDb(true);
      });

      els.emotionChecks.forEach((cb) => {
        cb.addEventListener('change', () => {
          if (!cb.checked) {
            els.emotionAll.checked = false;
          } else if (els.emotionChecks.every((c) => c.checked)) {
            els.emotionAll.checked = true;
          }
          updateCount();
          refreshDb(true);
        });
      });

      window.addEventListener('gemmaEmotionFiltersChanged', (event) => {
        const payload = Array.isArray(event.detail) ? event.detail : [];
        if (!payload.length) {
          els.emotionAll.checked = true;
          els.emotionChecks.forEach((cb) => (cb.checked = true));
        } else {
          const selected = new Set(payload);
          els.emotionChecks.forEach((cb) => {
            cb.checked = selected.has(cb.value);
          });
          els.emotionAll.checked = els.emotionChecks.every((cb) => cb.checked);
        }
        updateCount();
        refreshDb(true);
      });

      els.resetPrompt.addEventListener('click', () => {
        els.prompt.value = defaultPrompt;
        showToast('Prompt reset', 'Prompt restored to default template.', 'success');
      });

      els.runStream.addEventListener('click', () => runStreamingAnalysis());
      els.runQuick.addEventListener('click', () => runQuickSummary());
      els.cancel.addEventListener('click', () => stopStream('cancelled'));

      // Sorting controls
      els.sortSelect?.addEventListener('change', (event) => {
        const value = (event.target?.value || '').toLowerCase();
        state.viewer.sort_by = value || 'created_at';
        updateSortControls();
        refreshDb(true);
      });
      els.orderToggle?.addEventListener('click', () => {
        state.viewer.order = state.viewer.order === 'asc' ? 'desc' : 'asc';
        updateSortControls();
        refreshDb(true);
      });

      // DB viewer helpers
      els.dbSearch && els.dbSearch.addEventListener('keyup', (e) => {
        filterDbList(e.target.value);
      });
      els.dbExport && els.dbExport.addEventListener('click', () => exportDbCsv());
      // Column visibility controls
      loadColumnPrefs();
      syncColumnToggles();
      renderDbHeader();

      // Archive UI bindings
      els.artifactsRefresh && els.artifactsRefresh.addEventListener('click', () => loadArtifacts(true));
      els.artifactsMore && els.artifactsMore.addEventListener('click', () => loadArtifacts(false));
      els.metaRun && els.metaRun.addEventListener('click', () => runMetaAnalysis());
      els.chatOpen && els.chatOpen.addEventListener('click', () => openChatDrawer());
      els.chatClose && els.chatClose.addEventListener('click', () => closeChatDrawer());
      els.chatSend && els.chatSend.addEventListener('click', () => sendChat());
      els.chatSummary && els.chatSummary.addEventListener('click', () => summarizeChat());
      els.chatInput && els.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendChat();
        }
      });
      els.chatOverlay && els.chatOverlay.addEventListener('click', (e) => {
        if (e.target === els.chatOverlay) closeChatDrawer();
      });
      els.logToggle && els.logToggle.addEventListener('click', () => {
        if (els.logOverlay?.getAttribute('data-open') === 'true') {
          closeLogOverlay();
        } else {
          openLogOverlay();
        }
      });
      els.logClose && els.logClose.addEventListener('click', () => closeLogOverlay());
      els.logOverlay && els.logOverlay.addEventListener('click', (e) => {
        if (e.target === els.logOverlay) closeLogOverlay();
      });
      els.dbDensity && els.dbDensity.addEventListener('click', () => {
        state.viewer.dense = !state.viewer.dense;
        applyDbDensity();
        refreshDb(true);
      });
    }

    async function warmupGPU() {
      try {
        const result = await api.gemmaWarmup();
        const status = result?.status || 'unknown';
        setGPUStatus(`GPU warmup: ${status}`, result?.model_on_gpu ? 'success' : 'warning');
        logEvent(`GPU warmup: ${status}`);
      } catch (error) {
        console.warn('[Analyzer] Warmup failed', error);
      }
    }

    bindEvents();
    refreshTranscriptWindow();

    const activePresetBtn = els.dateButtons.find((btn) => btn.dataset.active === 'true');
    if (activePresetBtn) {
      applyDatePreset(parseInt(activePresetBtn.dataset.days, 10), { triggerCount: false });
    }
    fetchSpeakers();
    updateCount(false);
    loadGPUStats();
    warmupGPU();
    loadArtifacts(true);
    // Init DB viewer
    applyDbDensity();
    bindDbScroll();
    updateSortControls();
    renderDbHeader();
    refreshDb(true);

    if (global.lucide && global.lucide.createIcons) {
      global.lucide.createIcons();
    }

    return {
      refreshCount: () => updateCount(false),
      reloadSpeakers: fetchSpeakers,
      warmup: warmupGPU,
    };
  }

  global.initGemmaAnalyzer = initGemmaAnalyzer;
})(window);
