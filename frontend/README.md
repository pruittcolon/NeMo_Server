# WhisperServer - Premium HTML Frontend

## Overview

A high-quality, production-ready HTML/CSS/JavaScript frontend for WhisperServer.

- **10 Pages:** Clean, focused interfaces
- **Zero Dependencies:** Pure HTML, CSS, JS
- **Premium Design:** Glassmorphism, smooth animations
- **Responsive:** Mobile-friendly layouts
- **Fast:** No build step required

---

## Pages

### 1. **index.html** - Live Dashboard
Real-time transcription feed with auto-refresh (every 2s)
- Live transcriptions with speaker avatars
- Emotion badges
- Stats cards (total transcriptions, speakers, latency)

### 2. **search.html** - Search & Filter
Semantic search across all transcripts
- Full-text search
- Time period filters
- Highlighted results

### 3. **emotions.html** - Emotion Analytics
AI-powered emotion detection dashboard
- Pie chart (emotion distribution)
- Line chart (trends over time)
- Stats cards
- Time period filtering

### 4. **memories.html** - RAG Memory Database
FAISS vector search for semantic memory retrieval
- Create/edit/delete memories
- Semantic search
- Similarity scores
- 384-dimensional embeddings (MiniLM)

### 5. **gemma.html** - AI Insights Chat
Chat interface with Gemma 3 4B AI
- Real-time chat
- Personality analysis
- Conversation summaries
- Pattern detection

### 6. **transcripts.html** - Full Transcript Viewer
Complete conversation transcripts with export
- Export to JSON/TXT
- Speaker-colored segments
- Timestamps
- Duration tracking

### 7. **speakers.html** - Speaker Management
Enroll and manage speaker voice profiles
- Enroll new speakers
- Upload audio samples
- TitaNet embeddings (192D)
- Speaker verification

### 8. **patterns.html** - Communication Patterns
AI-detected conversation behavior patterns
- Activity by hour chart
- Speaker distribution
- Pattern confidence scores
- Peak time detection

### 9. **settings.html** - Configuration
System preferences and connection settings
- API URL configuration
- Theme toggle (dark/light)
- Notification preferences
- Data management

### 10. **about.html** - System Information
Technical details and health monitoring
- System architecture
- Model information
- GPU stats
- Health checks

---

## Design System

### Colors
- **Primary:** #6366f1 (Indigo)
- **Secondary:** #8b5cf6 (Purple)
- **Success:** #10b981 (Green)
- **Danger:** #ef4444 (Red)
- **Warning:** #f59e0b (Amber)

### Typography
- **Font:** Inter (Google Fonts)
- **Monospace:** Fira Code

### Components
- **Glassmorphism Cards:** Translucent backgrounds with blur
- **Smooth Animations:** 300ms cubic-bezier transitions
- **Icons:** Lucide Icons (CDN)
- **Charts:** Chart.js for data visualization

---

## API Integration

All pages connect to FastAPI backend via `api.js`:

```javascript
// Global API instance
const api = new WhisperAPI('http://localhost:8000');

// Example usage
const transcripts = await api.getAllTranscripts(20);
const health = await api.health();
```

### API Wrapper Methods
- Health & Status: `health()`
- Transcription: `getLatest()`, `transcribe()`, `searchTranscripts()`
- Speakers: `enrollSpeaker()`, `getSpeakers()`, `verifySpeaker()`
- Emotions: `getEmotionStats()`, `prepareEmotionAnalysis()`
- Memory/RAG: `searchMemories()`, `createMemory()`, `getAllMemories()`
- Gemma AI: `gemmaSummary()`, `startPersonalityAnalysis()`
- Patterns: `getPatterns()`

---

## Utilities (app.js)

### Time Formatting
```javascript
formatTime(timestamp)      // "5m ago", "Just now"
formatDuration(seconds)    // "02:35"
```

### UI Helpers
```javascript
showToast(title, message, type, duration)
showModal(title, bodyHTML)
createSpeakerAvatar(speakerId, size)
createEmotionBadge(emotion, confidence)
```

### Theme Management
```javascript
toggleTheme()              // Switch dark/light mode
initTheme()                // Load saved theme
```

### Auto-Refresh
```javascript
startAutoRefresh(callback, intervalMs)
stopAutoRefresh()
```

---

## Local Storage

Settings persist in browser:
- `whisper_theme` - dark/light preference
- `whisper_api-url` - backend URL
- `whisper_auto-refresh` - enable/disable
- `whisper_show-timestamps` - display preference

---

## Browser Compatibility

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

---

## Customization

### Change API URL
Edit in `settings.html` or directly in `api.js`:
```javascript
const api = new WhisperAPI('http://your-server:8001');
```

### Add Custom Page
1. Create `yourpage.html`
2. Include CSS/JS:
```html
<link rel="stylesheet" href="assets/css/main.css">
<link rel="stylesheet" href="assets/css/components.css">
<link rel="stylesheet" href="assets/css/animations.css">
<script src="assets/js/api.js"></script>
<script src="assets/js/app.js"></script>
```
3. Add to navigation

### Modify Theme
Edit CSS variables in `assets/css/main.css`:
```css
:root {
  --primary: #6366f1;  /* Change primary color */
  --radius-lg: 0.75rem; /* Change border radius */
}
```

---

## Performance

- **Load Time:** <500ms (no build step)
- **Bundle Size:** ~50KB total (CSS + JS)
- **CDN Assets:** Fonts, icons, Chart.js
- **Caching:** API responses cached 5s

---

## Accessibility

- Semantic HTML5
- ARIA labels
- Keyboard navigation (Ctrl+K for search, Esc for modals)
- High contrast themes
- Screen reader compatible

---

## License

Same as WhisperServer parent project.

