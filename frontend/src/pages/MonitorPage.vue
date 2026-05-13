<template>
  <div class="monitor-shell">
    <div class="monitor-topbar">
      <div class="topbar-left">
        <label class="topbar-label">Session</label>
        <select
          class="session-select"
          :value="selectedSessionId"
          @change="onPickSession($event.target.value)"
        >
          <option value="" disabled>— choose a run dir —</option>
          <option v-for="s in sessions" :key="s.session_id" :value="s.session_id">
            {{ formatSessionLabel(s) }}
          </option>
        </select>
        <button class="link-btn" @click="refreshSessions" title="Refresh session list">
          <span class="mdi mdi-refresh"></span>
        </button>
      </div>

      <div class="topbar-meta" v-if="sessionMeta">
        <span class="meta-chip">
          <span class="mdi mdi-calendar-clock"></span>
          {{ sessionMeta.started_at || '—' }}
        </span>
        <span class="meta-chip">
          <span class="mdi mdi-flask-outline"></span>
          {{ sessionMeta.test_type_hint }}
        </span>
        <span
          v-if="sessionComplete"
          class="meta-chip"
          :class="sessionComplete.overall_passed ? 'pass' : 'fail'"
        >
          <span
            class="mdi"
            :class="sessionComplete.overall_passed ? 'mdi-check-circle-outline' : 'mdi-close-circle-outline'"
          ></span>
          {{ sessionComplete.overall_passed ? 'session passed' : 'session failed' }}
        </span>
        <span class="meta-chip" :class="streaming ? 'live' : ''">
          <span class="dot" :class="streaming ? 'live' : 'idle'"></span>
          {{ streaming ? 'watching' : 'idle' }}
        </span>
      </div>

      <div class="topbar-right">
        <button
          class="stop-btn"
          :disabled="!streaming"
          @click="stopWatching"
        >
          <span class="mdi mdi-stop-circle-outline"></span>
          Stop watching
        </button>
      </div>
    </div>

    <div class="monitor-body" :style="bodyStyle">
      <div class="monitor-center">
        <div v-if="error" class="err-box">{{ error }}</div>
        <div v-else-if="!sessionMeta" class="empty-state">
          Pick a run directory from the selector above to begin.
        </div>
        <div v-else class="femb-cols">
          <FembTimeline
            v-for="f in fembs"
            :key="f.femb_id"
            :femb="f"
            :state="eventsByFemb[f.femb_id] || { tests: {}, final: false, diagnostics: {} }"
            :on-regenerate="regenerateDiagnostic"
            :on-clear="clearDiagnostic"
          />
        </div>
      </div>

      <div
        v-if="chatOpen"
        class="resizer"
        :class="{ dragging: resizing }"
        @mousedown="startResize"
        @dblclick="resetWidth"
        title="Drag to resize · double-click to reset"
      ></div>

      <aside class="monitor-right" :class="{ collapsed: !chatOpen }">
        <MonitorChat
          v-if="chatOpen"
          :session-id="selectedSessionId"
          @collapse="chatOpen = false"
        />
        <button
          v-else
          class="rail-expand-btn"
          @click="chatOpen = true"
          title="Open session chat"
        >
          <span class="mdi mdi-forum-outline"></span>
        </button>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, computed } from 'vue'
import { useMonitor } from '../composables/useMonitor'
import FembTimeline from '../components/monitor/FembTimeline.vue'
import MonitorChat from '../components/monitor/MonitorChat.vue'

const DEFAULT_CHAT_WIDTH = 400
const MIN_CHAT_WIDTH = 280
const MAX_CHAT_WIDTH = 900

const chatOpen = ref(true)
const chatWidth = ref(Number(localStorage.getItem('monitor.chatWidth')) || DEFAULT_CHAT_WIDTH)
const resizing = ref(false)

const bodyStyle = computed(() => ({
  gridTemplateColumns: chatOpen.value
    ? `1fr 5px ${chatWidth.value}px`
    : '1fr 36px',
}))

function startResize(e) {
  e.preventDefault()
  const startX = e.clientX
  const startW = chatWidth.value
  resizing.value = true
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'

  const onMove = (ev) => {
    const dx = startX - ev.clientX
    chatWidth.value = Math.max(MIN_CHAT_WIDTH, Math.min(MAX_CHAT_WIDTH, startW + dx))
  }
  const onUp = () => {
    resizing.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    localStorage.setItem('monitor.chatWidth', String(chatWidth.value))
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function resetWidth() {
  chatWidth.value = DEFAULT_CHAT_WIDTH
  localStorage.setItem('monitor.chatWidth', String(chatWidth.value))
}

const {
  sessions,
  selectedSessionId,
  sessionMeta,
  fembs,
  eventsByFemb,
  sessionComplete,
  streaming,
  error,
  loadSessions,
  startWatching,
  stopWatching,
  regenerateDiagnostic,
  clearDiagnostic,
} = useMonitor()

onMounted(() => loadSessions())
onBeforeUnmount(() => stopWatching())

function refreshSessions() {
  loadSessions()
}

function onPickSession(sid) {
  if (!sid) return
  startWatching(sid)
}

function formatSessionLabel(s) {
  let status
  if (s.persisted) {
    status = s.overall_passed ? '✓ pass' : '✗ fail'
  } else if (s.in_progress) {
    status = '● running'
  } else {
    status = '○ unsaved'
  }
  const ts = s.started_at ? s.started_at.replace('T', ' ') : '—'
  return `${ts}  ·  ${s.test_type_hint}  ·  ${status}`
}
</script>

<style scoped>
.monitor-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.monitor-topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  background: var(--bg-1);
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.topbar-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-2);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.session-select {
  flex: 1;
  min-width: 0;
  max-width: 640px;
  padding: 6px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-0);
}
.session-select:focus { outline: 1px solid var(--accent); }

.link-btn {
  background: transparent;
  border: 1px solid var(--line-2);
  color: var(--ink-2);
  padding: 4px 6px;
  border-radius: var(--r-sm);
  cursor: pointer;
}
.link-btn:hover { color: var(--ink-0); background: var(--bg-2); }

.topbar-meta {
  display: flex;
  gap: 8px;
  align-items: center;
}
.meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  font-size: 11px;
  color: var(--ink-1);
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  border-radius: 999px;
}
.meta-chip.live { color: var(--info); border-color: rgba(56, 139, 253, 0.4); }
.meta-chip.pass {
  color: var(--ok);
  border-color: rgba(57, 211, 83, 0.4);
  background: rgba(57, 211, 83, 0.08);
}
.meta-chip.fail {
  color: var(--danger);
  border-color: rgba(248, 81, 73, 0.4);
  background: rgba(248, 81, 73, 0.08);
}
.meta-chip.pass .mdi { color: var(--ok); }
.meta-chip.fail .mdi { color: var(--danger); }
.meta-chip .mdi { font-size: 13px; color: var(--ink-2); }

.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.dot.idle { background: var(--ink-3, var(--line-2)); }
.dot.live { background: var(--info); box-shadow: 0 0 8px var(--info); }

.stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-1);
  font-size: 12px;
  cursor: pointer;
}
.stop-btn:hover:not(:disabled) {
  color: var(--danger);
  border-color: rgba(248, 81, 73, 0.4);
}
.stop-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.stop-btn .mdi { font-size: 14px; }

.monitor-body {
  display: grid;
  gap: 0;
  flex: 1;
  min-height: 0;
}

.resizer {
  cursor: ew-resize;
  background: transparent;
  border-left: 1px solid var(--line);
  position: relative;
  transition: background 120ms;
}
.resizer::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 24px;
  border-radius: 2px;
  background: var(--line-2);
  transition: background 120ms;
}
.resizer:hover,
.resizer.dragging {
  background: rgba(14,149,168,0.06);
}
.resizer:hover::after,
.resizer.dragging::after {
  background: var(--accent);
}

.monitor-center {
  padding: 16px;
  overflow-y: auto;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: 13px;
  color: var(--ink-2);
}

.err-box {
  padding: 10px 14px;
  background: rgba(248, 81, 73, 0.08);
  border: 1px solid rgba(248, 81, 73, 0.3);
  border-radius: var(--r-md);
  color: var(--danger);
  font-size: 12px;
}

.femb-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  align-content: start;
}

.monitor-right {
  background: var(--bg-1);
  overflow: hidden;
  display: flex;
  min-width: 0;
}
.monitor-right.collapsed {
  background: var(--bg-0);
  border-left: 1px solid var(--line);
  align-items: flex-start;
  justify-content: center;
  padding-top: 8px;
}
.monitor-right > * { flex: 1; min-width: 0; }

.rail-expand-btn {
  flex: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-2);
  cursor: pointer;
}
.rail-expand-btn:hover { color: var(--ink-0); background: var(--bg-3); }
.rail-expand-btn .mdi { font-size: 16px; }

@media (max-width: 1024px) {
  .femb-cols { grid-template-columns: 1fr; }
}
</style>
