(function () {
  const escapeHTML = typeof window !== 'undefined' && typeof window.escapeHTML === 'function'
    ? window.escapeHTML
    : (value) => {
        if (value === null || value === undefined) return '';
        return String(value)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      };
  const selectors = {
    userSelect: document.getElementById('email-user-select'),
    authorsGroup: document.getElementById('email-authors'),
    authorsActive: document.getElementById('email-authors-active'),
    authorsTotal: document.getElementById('email-authors-total'),
    authorsAllButton: document.getElementById('email-authors-all'),
    participants: document.getElementById('email-participants'),
    labels: document.getElementById('email-labels'),
    startDate: document.getElementById('email-start-date'),
    endDate: document.getElementById('email-end-date'),
    keywords: document.getElementById('email-keywords'),
    matchAll: document.getElementById('email-match-all'),
    refresh: document.getElementById('email-refresh'),
    tableBody: document.querySelector('#email-table tbody'),
    summaryForm: document.getElementById('email-summary-form'),
    questionInput: document.getElementById('email-question'),
    summaryResult: document.getElementById('email-summary-result'),
    streamForm: document.getElementById('email-stream-form'),
    streamPrompt: document.getElementById('email-stream-prompt'),
    streamStop: document.getElementById('email-stream-stop'),
    streamLog: document.getElementById('email-stream-log'),
    statMessages: document.getElementById('email-stat-messages'),
    statThreads: document.getElementById('email-stat-threads'),
    statVip: document.getElementById('email-stat-vip'),
    sortSelect: document.getElementById('email-sort'),
    gpuStatus: document.getElementById('email-gpu-status'),
  };

  const state = {
    labels: [],
    authors: [],
    selectedAuthors: new Set(),
    streamSource: null,
    streamCompleted: false,
    gpuMode: 'unknown',
    gpuReady: false,
    gpuReadyAt: 0,
    gpuWarmupPromise: null,
  };

  function encodePayload(payload) {
    const jsonStr = JSON.stringify(payload);
    let b64 = btoa(unescape(encodeURIComponent(jsonStr)));
    b64 = b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    return b64;
  }

  function gatherFilters() {
    const labelValues = Array.from(selectors.labels.querySelectorAll('[data-label] input:checked'))
      .map((input) => input.value);
    const participants = (selectors.participants.value || '')
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean);
    const authorFilter = getSelectedAuthors();
    return {
      users: authorFilter,
      participants: participants.length ? participants : undefined,
      labels: labelValues.length ? labelValues : undefined,
      start_date: selectors.startDate.value || undefined,
      end_date: selectors.endDate.value || undefined,
      keywords: selectors.keywords.value || undefined,
      match: selectors.matchAll.checked ? 'all' : 'any',
    };
  }

  function appendLog(message, level = 'info') {
    if (!selectors.streamLog) return;
    const item = document.createElement('div');
    item.className = `analyzer-log-item level-${level}`;
    const ts = new Date().toLocaleTimeString();
    item.innerHTML = `<span class="analyzer-log-time">${ts}</span><span class="analyzer-log-message">${message}</span>`;
    selectors.streamLog.prepend(item);
  }

  const GPU_READY_BUFFER_MS = 800;

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function setGPUStatus(text, variant = 'muted') {
    if (!selectors.gpuStatus) return;
    selectors.gpuStatus.textContent = text;
    selectors.gpuStatus.dataset.variant = variant;
  }

  async function warmupGPU(force = false) {
    if (state.gpuReady && !force) {
      return state.gpuMode;
    }
    if (state.gpuWarmupPromise) {
      await state.gpuWarmupPromise;
      return state.gpuMode;
    }
    state.gpuWarmupPromise = (async () => {
      setGPUStatus('GPU status: loading coordinator…', 'warning');
      try {
        const result = await api.gemmaWarmup();
        const onDevice = Boolean(result?.model_on_gpu);
        state.gpuMode = onDevice ? 'gpu' : 'cpu';
        state.gpuReady = true;
        state.gpuReadyAt = Date.now();
        setGPUStatus(
          onDevice ? 'GPU ready • model pinned to device' : 'GPU ready • running in CPU fallback',
          onDevice ? 'success' : 'warning'
        );
      } catch (error) {
        console.error('[EMAIL][UI] GPU warmup failed', error);
        state.gpuMode = 'error';
        state.gpuReady = false;
        state.gpuReadyAt = Date.now();
        setGPUStatus('GPU warmup failed – retry before running analysis', 'error');
        throw error;
      } finally {
        state.gpuWarmupPromise = null;
      }
    })();
    try {
      await state.gpuWarmupPromise;
    } catch (_) {
      /* swallow so callers can handle fallback */
    }
    return state.gpuMode;
  }

  async function ensureGPUReady(options = {}) {
    const { log = false } = options;
    if (log) appendLog('Preparing GPU coordinator…');
    if (!state.gpuReady || state.gpuWarmupPromise) {
      try {
        await warmupGPU();
      } catch (error) {
        if (log) appendLog('GPU warmup failed – using CPU fallback.', 'warning');
      }
    }
    const readyAt = state.gpuReadyAt || Date.now();
    const elapsed = Date.now() - readyAt;
    if (elapsed < GPU_READY_BUFFER_MS) {
      await delay(GPU_READY_BUFFER_MS - elapsed);
    }
    if (log) {
      if (state.gpuMode === 'gpu') {
        appendLog('GPU ready – model pinned.', 'success');
      } else if (state.gpuMode === 'cpu') {
        appendLog('GPU fallback active (CPU mode).', 'warning');
      } else {
        appendLog('GPU state unknown – proceeding cautiously.', 'warning');
      }
    }
    return state.gpuMode;
  }

  async function loadUsers() {
    const data = await api.getEmailUsers();
    const select = selectors.userSelect;
    if (select) {
      select.innerHTML = '<option value="">All users</option>';
    }
    state.authors = data?.items || [];
    state.authors.forEach((user) => {
      if (!select) return;
      const option = document.createElement('option');
      option.value = user.email;
      option.textContent = `${user.display_name || user.email} (${user.mailbox_count || 0})`;
      select.appendChild(option);
    });
    if (!state.selectedAuthors.size) {
      state.selectedAuthors = new Set(state.authors.map((author) => author.email));
    } else {
      const validAuthors = state.authors
        .map((author) => author.email)
        .filter((email) => state.selectedAuthors.has(email));
      state.selectedAuthors = new Set(validAuthors.length ? validAuthors : state.authors.map((author) => author.email));
    }
    renderAuthorsChips();
    updateAuthorsMeta();
    console.info('[EMAIL][UI] Loaded users', data?.count || 0);
  }

  function renderAuthorsChips() {
    const container = selectors.authorsGroup;
    if (!container) return;
    container.innerHTML = '';
    if (!state.authors.length) {
      container.innerHTML = '<p class="chip-panel-meta">No authors detected.</p>';
      updateAuthorsMeta();
      return;
    }
    state.authors.forEach((author) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'chip-toggle email-author-chip';
      button.dataset.author = author.email;
      const isActive = state.selectedAuthors.has(author.email);
      button.setAttribute('aria-pressed', isActive);
      button.innerHTML = `
        <span>${escapeHTML(author.display_name || author.email)}</span>
        <span class="chip-count-pill">${author.mailbox_count || 0}</span>
      `;
      button.addEventListener('click', () => toggleAuthor(author.email));
      container.appendChild(button);
    });
    updateAuthorsMeta();
  }

  function updateAuthorsMeta() {
    if (selectors.authorsActive) {
      selectors.authorsActive.textContent = state.selectedAuthors.size.toString();
    }
    if (selectors.authorsTotal) {
      selectors.authorsTotal.textContent = state.authors.length.toString();
    }
  }

  function selectAllAuthors() {
    if (!state.authors.length) return;
    state.selectedAuthors = new Set(state.authors.map((author) => author.email));
    renderAuthorsChips();
    refreshTable();
  }

  function toggleAuthor(email) {
    if (!email) return;
    if (state.selectedAuthors.has(email)) {
      state.selectedAuthors.delete(email);
    } else {
      state.selectedAuthors.add(email);
    }
    if (!state.selectedAuthors.size) {
      state.selectedAuthors = new Set(state.authors.map((author) => author.email));
    }
    renderAuthorsChips();
    refreshTable();
  }

  function getSelectedAuthors() {
    const total = state.authors.length;
    const selected = state.selectedAuthors.size;
    if (!selected || !total || selected === total) {
      return undefined;
    }
    return Array.from(state.selectedAuthors);
  }

  async function loadLabels() {
    const data = await api.getEmailLabels();
    state.labels = data?.items || [];
    selectors.labels.innerHTML = '';
    state.labels.forEach((label) => {
      const id = `label-${label.label}`;
      const wrapper = document.createElement('label');
      wrapper.className = 'checkbox';
      wrapper.setAttribute('data-label', label.label);
      wrapper.innerHTML = `
        <input type="checkbox" value="${label.label}" id="${id}">
        <span>${label.label} (${label.count})</span>
      `;
      selectors.labels.appendChild(wrapper);
    });
    console.info('[EMAIL][UI] Loaded labels', state.labels.length);
  }

  async function loadStats() {
    const stats = await api.getEmailStats();
    const totals = stats?.totals || {};
    selectors.statMessages.textContent = totals.messages ?? '0';
    selectors.statThreads.textContent = totals.threads ?? '0';
    selectors.statVip.textContent = totals.vip_flags ?? '0';
  }

  function sortSelection() {
    const value = selectors.sortSelect.value || 'date:desc';
    const [sort_by, order] = value.split(':');
    return { sort_by, order };
  }

  async function refreshTable() {
    const filters = gatherFilters();
    const { sort_by, order } = sortSelection();
    const payload = { filters, limit: 25, offset: 0, sort_by, order };
    const data = await api.queryEmails(payload);
    renderTable(data?.items || []);
    console.info('[EMAIL][UI] query matched', data?.count ?? 0);
  }

  function renderTable(items) {
    const tbody = selectors.tableBody;
    if (!tbody) return;
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;">No emails match the current filters.</td></tr>';
      return;
    }
    tbody.innerHTML = items
      .map((item) => {
        const date = new Date(item.date || Date.now()).toLocaleString();
        const labels = Array.isArray(item.labels) ? item.labels.join(', ') : '';
        return `
          <tr>
            <td>${date}</td>
            <td>${escapeHTML(item.subject || 'Untitled')}</td>
            <td>${escapeHTML(item.from_addr || '')}</td>
            <td>${escapeHTML(labels)}</td>
          </tr>
        `;
      })
      .join('');
  }

  async function handleSummary(event) {
    event.preventDefault();
    const question = selectors.questionInput.value.trim();
    if (!question || question.length < 3) {
      appendLog('Question must be at least 3 characters.', 'warning');
      selectors.summaryResult.textContent = 'Enter a longer question (>= 3 chars).';
      return;
    }
    selectors.summaryResult.textContent = 'Preparing GPU…';
    await ensureGPUReady();
    selectors.summaryResult.textContent = 'Generating summary…';
    appendLog('GPU ready – running quick summary.', 'info');
    try {
      const response = await api.emailAnalyzeGemmaQuick({ question, filters: gatherFilters() });
      selectors.summaryResult.textContent = response?.summary || 'No summary returned.';
      appendLog('Quick summary completed.', 'success');
    } catch (error) {
      console.error('[EMAIL][UI] quick summary failed', error);
      selectors.summaryResult.textContent = 'Summary failed. Check logs.';
      appendLog('Quick summary failed', 'error');
    }
  }

  function stopStream(reason = 'manual', { silent = false } = {}) {
    if (!state.streamSource) return;
    const source = state.streamSource;
    state.streamSource = null; // Unset before closing so onerror knows this stream is done
    if (reason === 'complete') {
      state.streamCompleted = true;
    }
    try {
      source.close();
    } catch (_) {
      /* ignore */
    }
    if (silent) return;
    if (reason === 'complete') {
      appendLog('Streaming complete.', 'success');
    } else if (reason === 'error') {
      appendLog('Streaming stopped due to error.', 'error');
    } else {
      appendLog('Streaming stopped.', 'warning');
    }
  }

  async function handleStream(event) {
    event.preventDefault();
    stopStream('manual', { silent: true });
    const prompt = selectors.streamPrompt.value.trim();
    if (!prompt) return;
    await ensureGPUReady({ log: true });
    const payload = { prompt, filters: gatherFilters(), max_chunks: 20 };
    const encoded = encodePayload(payload);
    const url = api.buildURL(`/email/analyze/gemma/stream?payload=${encoded}`);
    appendLog('Streaming started…');
    const source = new EventSource(url, { withCredentials: true });
    state.streamSource = source;
    state.streamCompleted = false;

    const logEvent = (type) => (event) => {
      const data = event.data ? (() => {
        try { return JSON.parse(event.data); } catch (_) { return event.data; }
      })() : null;
      appendLog(`${type}: ${JSON.stringify(data)}`);
    };

    source.addEventListener('progress', logEvent('progress'));
    source.addEventListener('note', logEvent('note'));
    source.addEventListener('summary', logEvent('summary'));
    source.addEventListener('done', (event) => {
      state.streamCompleted = true;
      logEvent('done')(event);
      if (state.streamSource === source) {
        stopStream('complete');
      } else {
        try {
          source.close();
        } catch (_) {
          /* ignore */
        }
      }
    });
    source.onerror = (event) => {
      // Ignore events from previous sources or runs already marked complete
      const isCurrent = state.streamSource === source;
      const closed = source.readyState === EventSource.CLOSED;
      if (state.streamCompleted || closed) {
        if (isCurrent) stopStream('complete', { silent: true });
        return;
      }
      if (!isCurrent) {
        return;
      }
      appendLog('Stream error – check backend logs.', 'error');
      console.error('[EMAIL][UI] stream error', event);
      stopStream('error');
    };
  }

  function attachHandlers() {
    selectors.refresh?.addEventListener('click', refreshTable);
    selectors.summaryForm?.addEventListener('submit', handleSummary);
    selectors.streamForm?.addEventListener('submit', handleStream);
    selectors.streamStop?.addEventListener('click', () => stopStream());
    selectors.sortSelect?.addEventListener('change', refreshTable);
    selectors.authorsAllButton?.addEventListener('click', selectAllAuthors);
  }

  async function init() {
    const authenticated = await Auth.init({ requireAuth: true });
    if (!authenticated) return;
    attachHandlers();
    setGPUStatus('GPU status: initializing…', 'muted');
    warmupGPU().catch(() => {});
    await Promise.all([loadUsers(), loadLabels(), loadStats()]);
    await refreshTable();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
