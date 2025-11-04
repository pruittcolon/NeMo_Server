/**
 * WhisperServer - API Client
 * Wrapper for all 30 backend endpoints
 */

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
    // CSRF config per backend defaults (gateway sets csrf_token cookie)
    this.csrfCookieName = (typeof window !== 'undefined' && window.CSRF_COOKIE_NAME) || 'csrf_token';
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
  async get(path, useCache = false) {
    // Check cache
    if (useCache && this.cache.has(path)) {
      const cached = this.cache.get(path);
      if (Date.now() - cached.timestamp < this.cacheTimeout) {
        return cached.data;
      }
    }

    try {
      const response = await fetch(this.buildURL(path), {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
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
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
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

  async post(path, body) {
    try {
      const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      };
      const csrf = this.getCookie(this.csrfCookieName);
      if (csrf) {
        headers[this.csrfHeaderName] = csrf;
      } else {
        console.warn('[API] No CSRF token found in cookies; POST may be rejected');
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
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
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
  async postForm(path, formData) {
    try {
      const headers = {};
      const csrf = this.getCookie(this.csrfCookieName);
      if (csrf) {
        headers[this.csrfHeaderName] = csrf;
      } else {
        console.warn('[API] No CSRF token found in cookies; POST_FORM may be rejected');
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
        return {
          type: 'transcript_segment',
          speaker: t.speaker || t.primary_speaker || '',
          title: t.title || t.speaker || 'Transcript',
          snippet: t.snippet || t.text || t.preview || '',
          score: null,
          emotion: t.emotion || null,
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
      return {
        type: r.type || 'result',
        speaker: md.speaker || (r.type === 'memory' ? 'Memory Note' : ''),
        title,
        snippet: r.text || '',
        score: typeof r.score === 'number' ? r.score : 0,
        emotion: md.emotion || null,
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
   * RAG-enhanced Gemma chat (retrieves context from RAG)
   */
  async gemmaChatRag(payload) {
    return await this.post('/gemma/chat-rag', payload);
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
