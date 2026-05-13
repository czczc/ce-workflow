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

    <div class="monitor-body">
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
            :state="eventsByFemb[f.femb_id] || { tests: {}, final: false }"
          />
        </div>
      </div>

      <aside class="monitor-right">
        <div class="chat-placeholder">
          <div class="placeholder-title">Session chat</div>
          <div class="placeholder-body">Chat panel will land in #63.</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { useMonitor } from '../composables/useMonitor'
import FembTimeline from '../components/monitor/FembTimeline.vue'

const {
  sessions,
  selectedSessionId,
  sessionMeta,
  fembs,
  eventsByFemb,
  streaming,
  error,
  loadSessions,
  startWatching,
  stopWatching,
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
  const status = s.in_progress ? '● running' : '○ done'
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
  grid-template-columns: 1fr 360px;
  gap: 0;
  flex: 1;
  min-height: 0;
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
  border-left: 1px solid var(--line);
  background: var(--bg-1);
  overflow-y: auto;
}

.chat-placeholder {
  padding: 16px;
  color: var(--ink-2);
}
.placeholder-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-1);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.placeholder-body { font-size: 12px; }

@media (max-width: 1024px) {
  .monitor-body { grid-template-columns: 1fr; }
  .monitor-right { border-left: none; border-top: 1px solid var(--line); }
  .femb-cols { grid-template-columns: 1fr; }
}
</style>
