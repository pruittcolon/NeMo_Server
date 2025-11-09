/**
 * WhisperServer - Main Application Logic
 * Handles UI updates, data formatting, and utilities
 */

// ============================================================================
// UTILITIES
// ============================================================================

let toastContainer = null;
let defaultEmotionConfidence = 0.7;

function clampEmotionConfidence(value) {
  if (typeof value === 'string') {
    const parsed = parseFloat(value);
    if (!Number.isNaN(parsed)) {
      value = parsed;
    }
  }
  if (!Number.isFinite(value)) return defaultEmotionConfidence;
  if (value > 1) value = value / 100;
  if (value < 0) value = 0;
  if (value > 1) value = 1;
  return value;
}

function ensureToastContainer() {
  if (toastContainer) return toastContainer;
  if (typeof document === 'undefined') return null;

  const existing = document.querySelector('.toast-container');
  if (existing) {
    toastContainer = existing;
    return toastContainer;
  }

  if (!document.body) {
    const readyHandler = () => {
      document.removeEventListener('DOMContentLoaded', readyHandler);
      ensureToastContainer();
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', readyHandler, { once: true });
    } else {
      requestAnimationFrame(ensureToastContainer);
    }
    return null;
  }

  toastContainer = document.createElement('div');
  toastContainer.className = 'toast-container';
  document.body.appendChild(toastContainer);
  return toastContainer;
}

let autoRefreshInterval = null;

/**
 * Format timestamp to readable string
 */
function formatTime(timestamp) {
  if (!timestamp) return 'Unknown';
  
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now - date;
  
  // Less than 1 minute
  if (diff < 60000) {
    return 'Just now';
  }
  
  // Less than 1 hour

  if (diff < 3600000) {
    const minutes = Math.floor(diff / 60000);
    return `${minutes}m ago`;
  }
  
  // Less than 1 day
  if (diff < 86400000) {
    const hours = Math.floor(diff / 3600000);
    return `${hours}h ago`;
  }
  
  // More than 1 day
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

/**
 * Format duration in seconds to MM:SS
 */
function formatDuration(seconds) {
  if (!seconds || seconds < 0) return '00:00';
  
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

/**
 * Debounce function
 */
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Get emotion color
 */
function getEmotionColor(emotion) {
  const colors = {
    joy: '#10b981',
    anger: '#ef4444',
    sadness: '#3b82f6',
    fear: '#f59e0b',
    surprise: '#8b5cf6',
    neutral: '#6b7280',
  };
  return colors[emotion?.toLowerCase()] || colors.neutral;
}

/**
 * Get speaker color (consistent hash-based color)
 */
function getSpeakerColor(speakerId) {
  const colors = [
    '#6366f1', // Indigo
    '#8b5cf6', // Purple
    '#ec4899', // Pink
    '#f43f5e', // Rose
    '#f97316', // Orange
    '#06b6d4', // Cyan
    '#10b981', // Green
    '#3b82f6', // Blue
  ];
  
  let hash = 0;
  for (let i = 0; i < speakerId.length; i++) {
    hash = speakerId.charCodeAt(i) + ((hash << 5) - hash);
  }
  
  return colors[Math.abs(hash) % colors.length];
}

/**
 * Create speaker avatar element
 */
function createSpeakerAvatar(speakerId, size = 'normal') {
  const avatar = document.createElement('div');
  avatar.className = `speaker-avatar ${size === 'large' ? 'large' : ''}`;
  avatar.style.background = getSpeakerColor(speakerId);
  
  // Extract initials (e.g., "SPK_00" -> "S0", "John Doe" -> "JD")
  const initials = speakerId
    .split(/[_\s]+/)
    .map(word => word[0])
    .join('')
    .substring(0, 2)
    .toUpperCase();
  
  avatar.textContent = initials;
  
  return avatar;
}

/**
 * Create emotion badge element
 */
function createEmotionBadge(emotion, confidence = null) {
  const badge = document.createElement('span');
  badge.className = 'badge';
  badge.style.background = `${getEmotionColor(emotion)}20`;
  badge.style.color = getEmotionColor(emotion);
  const normalized = normalizeEmotionConfidence(confidence);
  const percentText = `${Math.round(normalized * 100)}%`;
  const label = emotion ? `${emotion} ${percentText}` : percentText;
  badge.textContent = label.trim();
  
  return badge;
}

// ============================================================================
// TOAST NOTIFICATIONS
// ============================================================================

function showToast(title, message, type = 'info', duration = 3000) {
  const container = ensureToastContainer();
  if (!container) {
    console.warn('[Toast] Unable to render toast container yet:', title, message);
    return;
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  toast.innerHTML = `
    <div class="toast-content">
      <div class="toast-title">${escapeHTML(title)}</div>
      <div class="toast-message">${escapeHTML(message)}</div>
    </div>
    <button class="glass-button" onclick="this.parentElement.remove()">&times;</button>
  `;
  
  container.appendChild(toast);
  
  if (duration > 0) {
    setTimeout(() => toast.remove(), duration);
  }
}

// ============================================================================
// MODAL MANAGEMENT
// ============================================================================

function showModal(title, bodyHTML) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h3 class="modal-title">${escapeHTML(title)}</h3>
        <button class="glass-button" onclick="this.closest('.modal-overlay').remove()">&times;</button>
      </div>
      <div class="modal-body">
        ${bodyHTML}
      </div>
    </div>
  `;
  
  document.body.appendChild(overlay);
  
  // Close on overlay click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      overlay.remove();
    }
  });
  
  return overlay;
}

function closeModal() {
  const overlay = document.querySelector('.modal-overlay');
  if (overlay) overlay.remove();
}

// ============================================================================
// LOADING STATES
// ============================================================================

function showLoading(element) {
  element.classList.add('loading');
  element.style.opacity = '0.6';
  element.style.pointerEvents = 'none';
}

function hideLoading(element) {
  element.classList.remove('loading');
  element.style.opacity = '1';
  element.style.pointerEvents = 'auto';
}

// ============================================================================
// LOCAL STORAGE
// ============================================================================

function saveToStorage(key, value) {
  try {
    localStorage.setItem(`whisper_${key}`, JSON.stringify(value));
  } catch (error) {
    console.error('Failed to save to storage:', error);
  }
}

function loadFromStorage(key, defaultValue = null) {
  try {
    const value = localStorage.getItem(`whisper_${key}`);
    return value ? JSON.parse(value) : defaultValue;
  } catch (error) {
    console.error('Failed to load from storage:', error);
    return defaultValue;
  }
}

// Initialize baseline from storage if available
try {
  const storedBaseline = loadFromStorage('emotion_conf_default', 0.7);
  if (storedBaseline !== null && storedBaseline !== undefined) {
    setEmotionConfidenceBaseline(storedBaseline, { persist: false, silent: true });
  }
} catch (error) {
  console.warn('Unable to restore emotion confidence baseline:', error);
}

function normalizeEmotionConfidence(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return clampEmotionConfidence(value);
  }
  return defaultEmotionConfidence;
}

function getEmotionConfidenceBaseline() {
  return defaultEmotionConfidence;
}

function setEmotionConfidenceBaseline(value, { persist = true, silent = false } = {}) {
  defaultEmotionConfidence = clampEmotionConfidence(value);
  if (persist) {
    try {
      saveToStorage('emotion_conf_default', defaultEmotionConfidence);
    } catch (error) {
      console.warn('Failed to persist emotion confidence baseline', error);
    }
  }
  if (!silent) {
    document.dispatchEvent(new CustomEvent('emotionConfidenceBaselineChanged', {
      detail: defaultEmotionConfidence,
    }));
  }
}

// ============================================================================
// THEME MANAGEMENT
// ============================================================================

function initTheme() {
  const savedTheme = loadFromStorage('theme', 'dark');
  document.body.classList.toggle('light-mode', savedTheme === 'light');
}

function toggleTheme() {
  const isLight = document.body.classList.toggle('light-mode');
  saveToStorage('theme', isLight ? 'light' : 'dark');
  showToast('Theme Changed', `Switched to ${isLight ? 'light' : 'dark'} mode`, 'success', 2000);
}

// ============================================================================
// API CONNECTION TEST
// ============================================================================

async function testAPIConnection() {
  const statusEl = document.getElementById('api-status');
  if (!statusEl) return;
  
  try {
    const isConnected = await api.testConnection();
    
    if (isConnected) {
      statusEl.innerHTML = '<span class="badge badge-success">Connected</span>';
    } else {
      statusEl.innerHTML = '<span class="badge badge-danger">Disconnected</span>';
    }
  } catch (error) {
    statusEl.innerHTML = '<span class="badge badge-danger">Error</span>';
  }
}

// ============================================================================
// AUTO-REFRESH
// ============================================================================

function startAutoRefresh(callback, intervalMs = 2000) {
  stopAutoRefresh();
  callback(); // Run immediately
  autoRefreshInterval = setInterval(callback, intervalMs);
}

function stopAutoRefresh() {
  if (autoRefreshInterval) {
    clearInterval(autoRefreshInterval);
    autoRefreshInterval = null;
  }
}

// ============================================================================
// SEARCH FUNCTIONALITY
// ============================================================================

function highlightText(text, query) {
  if (!query) return escapeHTML(text);
  
  const escaped = escapeHTML(text);
  const regex = new RegExp(`(${escapeHTML(query)})`, 'gi');
  
  return escaped.replace(regex, '<mark>$1</mark>');
}

// ============================================================================
// NAVIGATION
// ============================================================================

function setActiveNav(pageName) {
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.remove('active');
    if (link.getAttribute('href').includes(pageName)) {
      link.classList.add('active');
    }
  });
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  // Check if we're on the login page
  const currentPage = window.location.pathname.split('/').pop() || 'index.html';
  const isLoginPage = currentPage === 'login.html';
  
  // TEMP: Skip auth until backend is running
  // Initialize authentication (skip for login page)
  // if (!isLoginPage && typeof Auth !== 'undefined') {
  //   const authenticated = await Auth.init({ requireAuth: true });
  //   if (!authenticated) {
  //     return; // Auth.init will redirect to login
  //   }
  // }
  
  // Initialize theme
  initTheme();
  
  // Test API connection
  testAPIConnection();
  
  // Retry API connection every 30 seconds if failed
  setInterval(testAPIConnection, 30000);
  
  // Add theme toggle listeners
  document.querySelectorAll('[data-toggle-theme]').forEach(btn => {
    btn.addEventListener('click', toggleTheme);
  });
  
  // Set active navigation
  setActiveNav(currentPage.replace('.html', ''));
});

// ============================================================================
// KEYBOARD SHORTCUTS
// ============================================================================

document.addEventListener('keydown', (e) => {
  // Ctrl/Cmd + K: Focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.querySelector('.search-input');
    if (searchInput) searchInput.focus();
  }
  
  // Escape: Close modal
  if (e.key === 'Escape') {
    closeModal();
  }
});

// ============================================================================
// ERROR HANDLING
// ============================================================================

window.addEventListener('error', (event) => {
  console.error('Global error:', event.error);
  showToast('Error', 'Something went wrong. Check console for details.', 'error', 5000);
});

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled promise rejection:', event.reason);
  showToast('Error', 'API request failed. Check your connection.', 'error', 5000);
});

if (typeof window !== 'undefined') {
  window.setEmotionConfidenceBaseline = setEmotionConfidenceBaseline;
  window.getEmotionConfidenceBaseline = getEmotionConfidenceBaseline;
  window.normalizeEmotionConfidence = normalizeEmotionConfidence;
}

// ============================================================================
// EXPORTS
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    formatTime,
    formatDuration,
    debounce,
    escapeHTML,
    getEmotionColor,
    getSpeakerColor,
    createSpeakerAvatar,
    createEmotionBadge,
    showToast,
    showModal,
    closeModal,
    showLoading,
    hideLoading,
    saveToStorage,
    loadFromStorage,
    toggleTheme,
    startAutoRefresh,
    stopAutoRefresh,
    highlightText,
    normalizeEmotionConfidence,
    getEmotionConfidenceBaseline,
    setEmotionConfidenceBaseline,
  };
}
