/**
 * WhisperServer - API Client
 * Wrapper for all 30 backend endpoints
 */

class WhisperAPI {
  constructor(baseURL = 'http://localhost:8000') {
    this.baseURL = baseURL;
    this.cache = new Map();
    this.cacheTimeout = 5000; // 5 seconds
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
      const response = await fetch(`${this.baseURL}${path}`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
        credentials: 'include',  // Send cookies for authentication
      });

      // Check for authentication errors
      if (response.status === 401) {
        console.warn('[API] Authentication required - redirecting to login');
        window.location.href = '/ui/login.html';
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
  async post(path, body) {
    try {
      const response = await fetch(`${this.baseURL}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        credentials: 'include',  // Send cookies for authentication
        body: JSON.stringify(body),
      });

      // Check for authentication errors
      if (response.status === 401) {
        console.warn('[API] Authentication required - redirecting to login');
        window.location.href = '/ui/login.html';
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
      const response = await fetch(`${this.baseURL}${path}`, {
        method: 'POST',
        credentials: 'include',  // Send cookies for authentication
        body: formData,
      });

      // Check for authentication errors
      if (response.status === 401) {
        console.warn('[API] Authentication required - redirecting to login');
        window.location.href = '/ui/login.html';
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
    return await this.get(`/transcript/all?limit=${limit}`);
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
    formData.append('speaker_id', speakerId);

    return await this.postForm('/enroll', formData);
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
    return await this.get('/speaker/list');
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

  /**
   * Get emotion stats
   */
  async getEmotionStats(timePeriod = 'today') {
    return await this.get(`/analyze/emotion_stats?time_period=${timePeriod}`);
  }

  // ============================================================================
  // MEMORY / RAG
  // ============================================================================

  /**
   * Search memories
   */
  async searchMemories(query, limit = 10) {
    // Backend expects 'q' parameter, not 'query'
    return await this.get(`/memory/search?q=${encodeURIComponent(query)}&top_k=${limit}`);
  }

  /**
   * Get all memories
   */
  async getAllMemories(limit = 100) {
    // Backend expects '/memory/list', not '/memory/all'
    return await this.get(`/memory/list?limit=${limit}`);
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
   * Synchronous Gemma chat
   */
  async gemmaChat(message) {
    return await this.post('/analyze/chat', { message, max_length: 150 });
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
    return await this.get('/analyze/stats');
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
    this.baseURL = url;
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


