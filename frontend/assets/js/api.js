/**
 * WhisperServer - API Client
 * Wrapper for all 30 backend endpoints
 */

const API_DEFAULT_EMOTION_CONFIDENCE = 0.7;

function resolveEmotionConfidence(raw) {
  if (typeof window !== 'undefined' && typeof window.normalizeEmotionConfidence === 'function') {
    return window.normalizeEmotionConfidence(raw);
  }
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    const clamped = Math.max(0, Math.min(1, raw));
    return clamped;
  }
  return API_DEFAULT_EMOTION_CONFIDENCE;
}

class WhisperAPI {
  constructor(baseURL, options = {}) {
    const globalOptions = (typeof window !== 'undefined' && window.NEMO_API_OPTIONS) || {};
    const mergedOptions = { ...globalOptions, ...options };
    // Default to same-origin in browsers; fall back to provided baseURL or localhost
    const origin = (typeof window !== 'undefined' && window.location && window.location.origin) || '';
    const fallback = (typeof window !== 'undefined' && window.API_BASE_URL) || baseURL || 'http://localhost:8000';
    this.baseURL = (origin || fallback || '').replace(/\/+$/, '');
    this.cache = new Map();
    this.cacheTimeout = 5000; // 5 seconds
    this.useLegacyRoutes = Boolean(mergedOptions.useLegacyRoutes || (typeof window !== 'undefined' && window.USE_LEGACY_API_ROUTES));
    this.apiPrefix = this.useLegacyRoutes ? '' : '/api';
    // CSRF config per backend defaults (gateway sets ws_csrf cookie)
    this.csrfCookieName = (typeof window !== 'undefined' && window.CSRF_COOKIE_NAME) || 'ws_csrf';
    this.csrfHeaderName = (typeof window !== 'undefined' && window.CSRF_HEADER_NAME) || 'X-CSRF-Token';
  }

  normalizePath(path) {
    if (!path) return this.apiPrefix || '/';
    let normalized = path.startsWith('/') ? path : `/${path}`;
    if (this.useLegacyRoutes || normalized.startsWith('/api/')) {
      return normalized;
    }
    if (!this.apiPrefix) {
      return normalized;
    }
    return `${this.apiPrefix}${normalized}`.replace(/\/{2,}/g, '/');
  }

  buildURL(path) {
    const normalizedPath = this.normalizePath(path);
    if (!this.baseURL) {
      return normalizedPath;
    }
    return `${this.baseURL}${normalizedPath}`;
  }

  /**
   * Generic GET request
   */
  async get(path, useCache = false, options = {}) {
    // Check cache
    if (useCache && this.cache.has(path)) {
      const cached = this.cache.get(path);
      if (Date.now() - cached.timestamp < this.cacheTimeout) {
        return cached.data;
      }
    }

    const { analysisId, headers: extraHeaders } = options || {};

    try {
      const response = await fetch(this.buildURL(path), {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          ...(extraHeaders || {}),
          ...(analysisId ? { 'X-Analysis-Id': analysisId } : {}),
        },
        credentials: 'include',  // Send cookies for authentication
      });

      // Check for authentication errors
      if (response.status === 401) {
        console.warn('[API] Authentication required - redirecting to login');
        window.location.href = 'login.html';
        throw new Error('Not authenticated');
      }

      // Check for authorization errors  
      if (response.status === 403) {
        const errorData = await response.json().catch(() => ({ detail: 'Access denied' }));
        alert(`Access Denied: ${errorData.detail || 'You do not have permission to view this data.'}`);
        throw new Error('Access denied');
      }

      if (!response.ok) {
        let detail;
        try {
          const errJson = await response.clone().json();
          detail = errJson?.detail ?? errJson;
        } catch (_) {
          detail = await response.text();
        }
        const message = detail
          ? `[HTTP ${response.status}] ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`
          : `HTTP ${response.status}: ${response.statusText}`;
        const error = new Error(message);
        error.status = response.status;
        error.detail = detail;
        throw error;
      }

      const data = await response.json();

      // Cache if requested
      if (useCache) {
        this.cache.set(path, { data, timestamp: Date.now() });
      }

      return data;
    } catch (error) {
      console.error(`[API] GET ${path} failed:`, error);
      throw error;
    }
  }

  /**
   * Generic POST request
   */
  getCookie(name) {
    if (typeof document === 'undefined') return '';
    const m = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()\[\]\\\/\+^])/g, '\\$1') + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : '';
  }

  getCsrfToken() {
    // Try configured name, then common fallbacks
    const tryNames = [
      this.csrfCookieName || 'ws_csrf',
      'ws_csrf',
      'csrf_token',
    ];
    for (const name of tryNames) {
      const val = this.getCookie(name);
      if (val) return val;
    }
    return '';
  }

  async post(path, body, options = {}) {
    try {
      const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      };
      const csrf = this.getCsrfToken();
      if (csrf) {
        headers[this.csrfHeaderName] = csrf;
      } else {
        console.warn('[API] No CSRF token found in cookies; POST may be rejected');
      }
      const { analysisId, headers: extraHeaders } = options || {};
      if (analysisId) {
        headers['X-Analysis-Id'] = analysisId;
      }
      if (extraHeaders && typeof extraHeaders === 'object') {
        Object.assign(headers, extraHeaders);
      }
      const response = await fetch(this.buildURL(path), {
        method: 'POST',
        headers,
        credentials: 'include',  // Send cookies for authentication
        body: JSON.stringify(body),
      });

      // Check for authentication errors
      if (response.status === 401) {
        console.warn('[API] Authentication required - redirecting to login');
        window.location.href = 'login.html';
        throw new Error('Not authenticated');
      }

      // Check for authorization errors
      if (response.status === 403) {
        const errorData = await response.json().catch(() => ({ detail: 'Access denied' }));
        alert(`Access Denied: ${errorData.detail || 'You do not have permission to perform this action.'}`);
        throw new Error('Access denied');
      }

      if (!response.ok) {
        let detail;
        try {
          const errJson = await response.clone().json();
          detail = errJson?.detail ?? errJson;
        } catch (_) {
          detail = await response.text();
        }
        const message = detail
          ? `[HTTP ${response.status}] ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`
          : `HTTP ${response.status}: ${response.statusText}`;
        const error = new Error(message);
        error.status = response.status;
        error.detail = detail;
        throw error;
      }

      return await response.json();
    } catch (error) {
      console.error(`[API] POST ${path} failed:`, error);
      throw error;
    }
  }

  /**
   * POST with FormData (for file uploads)
   */
  async postForm(path, formData, options = {}) {
    try {
      const headers = {};
      const csrf = this.getCsrfToken();
      if (csrf) {
        headers[this.csrfHeaderName] = csrf;
      } else {
        console.warn('[API] No CSRF token found in cookies; POST_FORM may be rejected');
      }
      const { analysisId, headers: extraHeaders } = options || {};
      if (analysisId) {
        headers['X-Analysis-Id'] = analysisId;
      }
      if (extraHeaders && typeof extraHeaders === 'object') {
        Object.assign(headers, extraHeaders);
      }
      const response = await fetch(this.buildURL(path), {
        method: 'POST',
        credentials: 'include',  // Send cookies for authentication
        headers,
        body: formData,
      });

      // Check for authentication errors
      if (response.status === 401) {
        console.warn('[API] Authentication required - redirecting to login');
        window.location.href = 'login.html';
        throw new Error('Not authenticated');
      }

      // Check for authorization errors
      if (response.status === 403) {
        const errorData = await response.json().catch(() => ({ detail: 'Access denied' }));
        alert(`Access Denied: ${errorData.detail || 'You do not have permission to perform this action.'}`);
        throw new Error('Access denied');
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`[API] POST_FORM ${path} failed:`, error);
      throw error;
    }
  }

  // ============================================================================
  // HEALTH & STATUS
  // ============================================================================

  /**
   * Get server health status
   */
  async health() {
    try {
      const result = await this.get('/health');
      return result || { status: 'unknown', timestamp: new Date().toISOString() };
    } catch (error) {
      return { status: 'error', timestamp: new Date().toISOString(), error: error.message };
    }
  }

  // ============================================================================
  // TRANSCRIPTION
  // ============================================================================

  /**
   * Get latest transcription result
   */
  async getLatest() {
    return await this.get('/latest_result');
  }

  /**
   * Upload audio for transcription
   */
  async transcribe(audioFile, streamId = null, seq = null) {
    const formData = new FormData();
    formData.append('audio', audioFile);
    if (streamId) formData.append('stream_id', streamId);
    if (seq !== null) formData.append('seq', seq);

    return await this.postForm('/transcribe', formData);
  }

  /**
   * Get transcription result by job ID
   */
  async getResult(jobId) {
    return await this.get(`/result/${jobId}`);
  }

  /**
   * Search transcripts
   */
  async searchTranscripts(query, limit = 20) {
    return await this.get(`/transcript/search?query=${encodeURIComponent(query)}&limit=${limit}`);
  }

  /**
   * Get all transcripts
   */
  async getAllTranscripts(limit = 100) {
    return await this.get(`/transcripts/recent?limit=${limit}`);
  }

  /**
   * Get transcript by ID
   */
  async getTranscript(id) {
    return await this.get(`/transcript/${id}`);
  }

  // ============================================================================
  // SPEAKERS
  // ============================================================================

  /**
   * Enroll new speaker
   */
  async enrollSpeaker(audioFile, speakerId) {
    const formData = new FormData();
    formData.append('audio', audioFile);
    formData.append('speaker', speakerId);  // Gateway expects 'speaker' not 'speaker_id'

    return await this.postForm('/enroll/upload', formData);
  }

  /**
   * Verify speaker
   */
  async verifySpeaker(audioFile, speakerId) {
    const formData = new FormData();
    formData.append('audio', audioFile);
    formData.append('speaker_id', speakerId);

    return await this.postForm('/speaker/verify', formData);
  }

  /**
   * Get all speakers
   */
  async getSpeakers() {
    return await this.get('/enroll/speakers');
  }

  // ============================================================================
  // EMOTIONS
  // ============================================================================

  /**
   * Prepare emotion analysis
   */
  async prepareEmotionAnalysis(params = {}) {
    const defaults = {
      time_period: 'today',
      emotions: ['joy', 'anger', 'sadness', 'fear', 'surprise', 'neutral'],
      context_lines: 3,
      min_confidence: 0.3,
    };

    return await this.post('/analyze/prepare_emotion_analysis', { ...defaults, ...params });
  }

  // ============================================================================
  // MEMORY / RAG
  // ============================================================================

  /**
   * Search memories
   */
  async searchMemories(query, limit = 10) {
    // Backend expects POST with JSON body containing 'q' and 'top_k'
    return await this.post('/memory/search', { q: query, top_k: limit });
  }

  /**
   * Get all memories
   */
  async getAllMemories(limit = 100) {
    // Backend expects '/memory/list', not '/memory/all'
    return await this.get(`/memory/list?limit=${limit}`);
  }

  /**
   * Get recent transcripts
   */
  async getRecentTranscripts(limit = 100) {
    return await this.get(`/transcripts/recent?limit=${limit}`);
  }

  /**
   * Get indexed transcript dataset window (diagnostics)
   */
  async transcriptsTimeRange(options = {}) {
    return await this.get('/debug/transcripts/time-range', false, options);
  }

  /**
   * Get memory by ID
   */
  async getMemory(id) {
    return await this.get(`/memory/${id}`);
  }

  /**
   * Create new memory
   */
  async createMemory(title, content) {
    return await this.post('/memory/create', { title, content });
  }

  /**
   * Update memory
   */
  async updateMemory(id, title, content) {
    return await this.post(`/memory/${id}`, { title, content });
  }

  /**
   * Delete memory
   */
  async deleteMemory(id) {
    return await this.post(`/memory/${id}/delete`, {});
  }

  /**
   * Get all speakers with statistics
   */
  async listSpeakers() {
    return await this.get('/memory/speakers/list');
  }

  /**
   * Get memories for a specific speaker
   */
  async getSpeakerMemories(speakerId, limit = 100, offset = 0) {
    return await this.get(`/memory/by_speaker/${encodeURIComponent(speakerId)}?limit=${limit}&offset=${offset}`);
  }

  /**
   * Get memories with a specific emotion
   */
  async getEmotionMemories(emotion, limit = 100, offset = 0) {
    return await this.get(`/memory/by_emotion/${encodeURIComponent(emotion)}?limit=${limit}&offset=${offset}`);
  }

  /**
   * Get emotion statistics with optional date filtering
   */
  async getEmotionStats(startDate = null, endDate = null) {
    let url = '/memory/emotions/stats';
    const params = [];
    if (startDate) params.push(`start_date=${startDate}`);
    if (endDate) params.push(`end_date=${endDate}`);
    if (params.length > 0) url += '?' + params.join('&');
    return await this.get(url);
  }

  /**
   * Get composite analytics (emotions + speech signals)
   * params: { start_date, end_date, speakers, emotions, metrics }
   */
  async getAnalyticsSignals(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value === undefined || value === null) return;
      if (Array.isArray(value)) {
        if (value.length === 0) return;
        query.set(key, value.join(','));
        return;
      }
      if (String(value).length === 0) return;
      query.set(key, value);
    });
    const qs = query.toString();
    const path = qs ? `/analytics/signals?${qs}` : '/analytics/signals';
    return await this.get(path);
  }

  /**
   * Drill-down: fetch transcript segments filtered by emotion/speaker/date.
   * params: { emotions: [], speakers: [], start_date, end_date, limit, offset, order }
   */
  async getAnalyticsSegments(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value === undefined || value === null) return;
      if (Array.isArray(value)) {
        if (!value.length) return;
        query.set(key, value.join(','));
        return;
      }
      if (String(value).length === 0) return;
      query.set(key, value);
    });
    const qs = query.toString();
    const path = qs ? `/analytics/segments?${qs}` : '/analytics/segments';
    try {
      return await this.get(path);
    } catch (error) {
      if (error?.status === 404 && !this.useLegacyRoutes) {
        const original = this.useLegacyRoutes;
        try {
          this.useLegacyRoutes = true;
          return await this.get(path);
        } finally {
          this.useLegacyRoutes = original;
        }
      }
      throw error;
    }
  }

  /**
   * Run comprehensive analysis on filtered memories
   */
  async analyzeMemories(filters) {
    // filters: { speakers: [], emotions: [], start_date, end_date, limit }
    return await this.post('/memory/analyze', filters);
  }

  /**
   * Unified semantic search across transcripts and memories
   * payload: { query, top_k, last_n_transcripts, start_date, end_date }
   * Returns: { items: [...], count?, fallback? }
   */
  async searchUnified(payload = {}) {
    const q = (payload.query || '').trim();
    // Fallback: if no/short query, show recent transcripts
    if (!q || q.length < 2) {
      const limit = Number(payload.last_n_transcripts) || 50;
      const recent = await this.get(`/transcripts/recent?limit=${limit}`);
      const list = recent?.transcripts || recent?.items || recent || [];
      const items = (Array.isArray(list) ? list : []).map((t) => {
        const start = typeof t.start_time === 'number' ? t.start_time : null;
        let ts = null;
        if (typeof start === 'number') {
          const m = Math.floor(start / 60);
          const s = Math.floor(start % 60);
          ts = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        }
        const segments = Array.isArray(t.segments) ? t.segments : [];
        const combinedText = (t.full_text || segments.map((seg) => seg.text || '').join(' ')).trim();
        const emotionConfidence = resolveEmotionConfidence(t.emotion_confidence);
        return {
          type: 'transcript_segment',
          speaker: t.speaker || t.primary_speaker || '',
          title: t.title || t.speaker || 'Transcript',
          snippet: t.snippet || t.text || t.preview || combinedText || '',
          full_text: combinedText,
          segments,
          score: null,
          emotion: t.emotion || t.dominant_emotion || null,
          emotion_confidence: emotionConfidence,
          timestamp_label: t.timestamp_label || ts,
          created_at: t.created_at || null,
          job_id: t.job_id || t.transcript_id || null,
          transcript_id: t.transcript_id || null,
          start_time: start,
        };
      });
      return { items, fallback: true };
    }

    const body = {
      query: q,
      top_k: Number(payload.top_k) || 30,
      last_n_transcripts: Number(payload.last_n_transcripts) || 100,
    };
    if (payload.start_date || payload.startDate) body.start_date = payload.start_date || payload.startDate;
    if (payload.end_date || payload.endDate) body.end_date = payload.end_date || payload.endDate;

    const resp = await this.post('/search/semantic', body);
    const results = resp?.results || [];
    const items = results.map((r) => {
      const md = r.metadata || {};
      const start = typeof md.start_time === 'number' ? md.start_time : null;
      let ts = null;
      if (typeof start === 'number') {
        const m = Math.floor(start / 60);
        const s = Math.floor(start % 60);
        ts = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
      }
      const title = r.type === 'memory' ? (md.title || 'Memory Note') : (md.speaker || 'Transcript');
      const segments = Array.isArray(md.segments) ? md.segments : [];
      const combinedText = (md.full_text || r.text || segments.map((seg) => seg.text || '').join(' ')).trim();
      const emotionConfidence = resolveEmotionConfidence(md.emotion_confidence);
      return {
        type: r.type || 'result',
        speaker: md.speaker || (r.type === 'memory' ? 'Memory Note' : ''),
        title,
        snippet: r.text || combinedText || '',
        full_text: combinedText,
        segments,
        score: typeof r.score === 'number' ? r.score : 0,
        emotion: md.emotion || null,
        emotion_confidence: emotionConfidence,
        timestamp_label: ts,
        created_at: md.created_at || null,
        job_id: md.job_id || md.transcript_id || null,
        transcript_id: md.transcript_id || null,
        start_time: start,
      };
    });
    return { items, count: items.length };
  }

  // ============================================================================
  // GEMMA AI
  // ============================================================================

  /**
   * Get Gemma summary
   */
  async gemmaSummary(context, emotion = 'neutral') {
    return await this.post('/analyze/gemma_summary', { context, emotion });
  }

  /**
   * Warmup Gemma - moves model to GPU and waits until ready
   * CALL THIS FIRST before gemmaChat() for fast inference!
   */
  async gemmaWarmup() {
    return await this.post('/gemma/warmup', {});
  }

  /**
   * Synchronous Gemma chat (simple generate)
   * NOTE: Call gemmaWarmup() first for fast GPU inference!
   */
  async gemmaChat(message) {
    // Use /gemma/generate endpoint
    const response = await this.post('/gemma/generate', { 
      prompt: message, 
      max_tokens: 200,
      temperature: 0.7 
    });
    // Return in format expected by UI: { response: "text" }
    return { response: response.text };
  }
  
  /**
   * Gemma generate (basic completion)
   */
  async gemmaGenerate(prompt, maxTokens = 200) {
    return await this.post('/gemma/generate', { 
      prompt, 
      max_tokens: maxTokens,
      temperature: 0.7
    });
  }

  /**
   * Start personality analysis
   */
  async startPersonalityAnalysis() {
    return await this.post('/analyze/personality', {});
  }

  /**
   * Get personality analysis result
   */
  async getPersonalityResult(jobId) {
    return await this.get(`/analyze/personality/${jobId}`);
  }

  /**
   * Get Gemma stats
   */
  async getGemmaStats() {
    return await this.get('/gemma/stats');
  }

  /**
   * Advanced conversation analysis with custom prompts
   * @param {Object} options - Analysis options
   * @param {Object} options.filters - Filters (speakers, emotions, dates, limit)
   * @param {string} options.custom_prompt - Custom prompt template
   * @param {number} options.max_tokens - Max tokens (default 1024)
   * @param {number} options.temperature - Temperature (default 0.3)
   */
  async gemmaAnalyze(options, meta = {}) {
    return await this.post('/gemma/analyze', options, meta);
  }

  /**
   * Get all unique speakers from database
   */
  async getAllSpeakers() {
    return await this.get('/transcripts/speakers');
  }

  async getSpeakers(options = {}) {
    return await this.get('/transcripts/speakers', false, options);
  }

  /**
   * Count transcripts matching filters
   * @param {Object} filters - Filter criteria
   */
  async countTranscripts(filters, meta = {}) {
    return await this.post('/transcripts/count', filters, meta);
  }

  /**
   * Query transcript segments with pagination and sorting
   * @param {Object} filters - Filter criteria (limit, offset, sort_by, order, speakers, emotions, dates, keywords)
   * @param {Object} meta - Optional meta (e.g., analysisId)
   */
  async queryTranscripts(filters, meta = {}) {
    return await this.post('/transcripts/query', filters, meta);
  }

  /**
   * Create streaming Gemma analysis job
   */
  async startGemmaAnalyzeJob(payload, meta = {}) {
    return await this.post('/gemma/analyze/stream', payload, meta);
  }

  /**
   * RAG-enhanced Gemma chat (retrieves context from RAG)
   */
  async gemmaChatRag(payload) {
    return await this.post('/gemma/chat-rag', payload);
  }

  async chatOnArtifactV2(payload) {
    return await this.post('/gemma/chat-on-artifact/v2', payload);
  }

  // ============================================================================
  // ANALYSIS ARTIFACTS
  // ============================================================================

  async archiveAnalysis(body, meta = {}) {
    return await this.post('/analysis/archive', body, meta);
  }

  async listArtifacts(limit = 50, offset = 0) {
    const qs = `?limit=${Number(limit)}&offset=${Number(offset)}`;
    try {
      return await this.get(`/analysis/list${qs}`);
    } catch (error) {
      const msg = error?.message || '';
      if (/HTTP 404/.test(msg)) {
        console.warn('[API] /analysis/list 404 – treating as empty archive');
        return { success: true, items: [], count: 0, has_more: false };
      }
      throw error;
    }
  }

  async getArtifact(artifactId) {
    try {
      return await this.get(`/analysis/${encodeURIComponent(artifactId)}`);
    } catch (error) {
      const msg = error?.message || '';
      if (/HTTP 404/.test(msg)) {
        console.warn('[API] /analysis/{id} 404 – artifact not found');
        return { success: false, artifact: null };
      }
      throw error;
    }
  }

  async searchArtifacts(query, limit = 20) {
    return await this.post('/analysis/search', { query, limit });
  }

  // Meta-analysis (SSE)
  streamMetaAnalysis(payload, { onEvent, analysisId } = {}) {
    const headers = {};
    if (analysisId) headers['X-Analysis-Id'] = analysisId;
    // Using fetch EventSource polyfill is out of scope; rely on native EventSource
    // Serialize payload through a job creator would be ideal; API accepts direct POST SSE via gateway
    // For simplicity, we provide a helper returning a fetch stream via text/event-stream
    const url = this.buildURL('/analysis/meta');
    const controller = new AbortController();
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(headers || {}) },
      body: JSON.stringify(payload),
      credentials: 'include',
      signal: controller.signal,
    }).then(async (resp) => {
      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        if (onEvent) onEvent(chunk);
      }
    }).catch(() => {});
    return () => controller.abort();
  }

  async chatOnArtifact({ artifact_id, message, mode = 'rag', max_tokens = 384, temperature = 0.5 }) {
    return await this.post('/gemma/chat-on-artifact', { artifact_id, message, mode, max_tokens, temperature });
  }

  // =========================================================================
  // EMAIL ANALYZER
  // =========================================================================

  async getEmailUsers() {
    return await this.get('/email/users');
  }

  async getEmailLabels() {
    return await this.get('/email/labels');
  }

  async getEmailStats(params = {}) {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).length) {
        query.set(key, value);
      }
    });
    const qs = query.toString();
    return await this.get(qs ? `/email/stats?${qs}` : '/email/stats');
  }

  async queryEmails(payload) {
    return await this.post('/email/query', payload);
  }

  async emailAnalyzeQuick(payload) {
    return await this.post('/email/analyze/quick', payload);
  }

  async emailAnalyzeGemmaQuick(payload) {
    return await this.post('/email/analyze/gemma/quick', payload);
  }

  async emailAnalyzeCancel(payload) {
    return await this.post('/email/analyze/cancel', payload);
  }

  // ============================================================================
  // PATTERNS
  // ============================================================================

  /**
   * Get communication patterns
   */
  async getPatterns(timePeriod = 'today') {
    return await this.get(`/analyze/patterns?time_period=${timePeriod}`);
  }

  // ============================================================================
  // UTILITIES
  // ============================================================================

  /**
   * Clear cache
   */
  clearCache() {
    this.cache.clear();
  }

  /**
   * Get base URL
   */
  getBaseURL() {
    return this.baseURL;
  }

  /**
   * Set base URL
   */
  setBaseURL(url) {
    this.baseURL = (url || '').replace(/\/+$/, '');
    this.clearCache();
  }

  /**
   * Test connection
   */
  async testConnection() {
    try {
      const health = await this.health();
      return health.status === 'ok' || health.status === 'healthy';
    } catch (error) {
      return false;
    }
  }
}

// Create global instance
const api = new WhisperAPI();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { WhisperAPI, api };
}
