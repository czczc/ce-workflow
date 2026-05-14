<template>
  <div class="monitor-shell">
    <div class="monitor-topbar">
      <div class="topbar-left">
        <label class="topbar-label">Session</label>
        <SessionPicker
          :model-value="selectedSessionId"
          :sessions-tree="sessionsTree"
          :sessions-loading="sessionsLoading"
          :on-load-sessions="loadSessions"
          @select="onPickSession"
        />
        <button
          v-if="remoteStatus.configured"
          class="remote-chip"
          :class="remoteChipClass"
          @click="retryRemote"
          :disabled="sessionsLoading"
          :title="remoteTitle"
        >
          <span class="mdi" :class="remoteChipIcon"></span>
          <span class="remote-host">{{ remoteStatus.host || 'remote' }}</span>
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
        <span v-if="syncing" class="meta-chip syncing">
          <span class="mdi mdi-cloud-download-outline"></span>
          syncing…
        </span>
        <span v-if="syncStalled" class="meta-chip stalled" title="3+ consecutive rsync cycles failed">
          <span class="mdi mdi-sync-alert"></span>
          sync stalled
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
            :ref="(el) => setTimelineRef(f.femb_id, el)"
            :femb="f"
            :state="eventsByFemb[f.femb_id] || { tests: {}, final: false, diagnostics: {} }"
            :test-labels="testLabels"
            :on-regenerate="regenerateDiagnostic"
            :on-clear="clearDiagnostic"
            @show-report="onShowReport"
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

    <ReportModal
      :open="reportModal.open"
      :loading="reportModal.loading"
      :error="reportModal.error"
      :test-id="reportModal.testId"
      :test-name="testLabels[reportModal.testId] || ''"
      :report="reportModal.report"
      @close="closeReport"
      @jump-diagnostic="onJumpDiagnostic"
    />
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, computed } from 'vue'
import { useMonitor } from '../composables/useMonitor'
import FembTimeline from '../components/monitor/FembTimeline.vue'
import MonitorChat from '../components/monitor/MonitorChat.vue'
import ReportModal from '../components/monitor/ReportModal.vue'
import SessionPicker from '../components/monitor/SessionPicker.vue'

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

const timelineRefs = new Map()
function setTimelineRef(fembId, el) {
  if (el) timelineRefs.set(fembId, el)
  else timelineRefs.delete(fembId)
}

const reportModal = ref({
  open: false,
  loading: false,
  error: '',
  fembId: '',
  testId: '',
  report: null,
})

async function onShowReport({ femb_id, test_id }) {
  reportModal.value = {
    open: true,
    loading: true,
    error: '',
    fembId: femb_id,
    testId: test_id,
    report: null,
  }
  const data = await loadTestReport(femb_id, test_id)
  if (!reportModal.value.open) return  // user dismissed mid-fetch
  if (data) {
    reportModal.value.loading = false
    reportModal.value.report = data
  } else {
    reportModal.value.loading = false
    reportModal.value.error = 'Report not found (file may not exist yet).'
  }
}

function closeReport() {
  reportModal.value.open = false
}

function onJumpDiagnostic() {
  const { fembId, testId } = reportModal.value
  closeReport()
  const tl = timelineRefs.get(fembId)
  tl?.scrollToDiagnostic?.(testId)
}

const {
  sessionsTree,
  sessionsLoading,
  remoteStatus,
  syncing,
  syncStalled,
  selectedSessionId,
  sessionMeta,
  testLabels,
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
  loadTestReport,
} = useMonitor()

onMounted(() => loadSessions())
onBeforeUnmount(() => stopWatching())

function onPickSession(sid) {
  if (!sid) return
  startWatching(sid)
}

function retryRemote() {
  loadSessions(null)
}

const remoteTitle = computed(() => {
  const s = remoteStatus.value
  if (!s.configured) return ''
  if (s.stalled) {
    return `remote ${s.host || ''} sync stalled${s.error ? ` (${s.error})` : ''} · click to retry`
  }
  if (s.ok === false) {
    return `remote ${s.host || ''} unreachable${s.error ? ` (${s.error})` : ''} · click to retry`
  }
  return `remote ${s.host} · click to refresh`
})

const remoteChipClass = computed(() => {
  const s = remoteStatus.value
  if (s.stalled) return 'bad'
  if (s.ok === false) return 'warn'
  return 'ok'
})

const remoteChipIcon = computed(() => {
  const s = remoteStatus.value
  if (s.stalled) return 'mdi-cloud-off-outline'
  if (s.ok === false) return 'mdi-cloud-alert-outline'
  return 'mdi-cloud-check-outline'
})
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

.remote-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 999px;
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--line-2);
  font-family: inherit;
  letter-spacing: 0.03em;
}
.remote-chip:disabled { cursor: wait; opacity: 0.6; }
.remote-chip .mdi { font-size: 13px; }
.remote-chip.ok   { color: var(--ok);     background: rgba(57, 211, 83, 0.10);  border-color: rgba(57, 211, 83, 0.35); }
.remote-chip.warn { color: var(--warning, #d29922); background: rgba(210, 153, 34, 0.12); border-color: rgba(210, 153, 34, 0.40); }
.remote-chip.bad  { color: var(--danger); background: rgba(248, 81, 73, 0.10); border-color: rgba(248, 81, 73, 0.35); }
.remote-host { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; }

.meta-chip.syncing {
  color: var(--info);
  background: rgba(56, 139, 253, 0.10);
}
.meta-chip.syncing .mdi { font-size: 12px; }

.meta-chip.stalled {
  color: var(--danger);
  background: rgba(248, 81, 73, 0.10);
}
.meta-chip.stalled .mdi { font-size: 13px; }

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
