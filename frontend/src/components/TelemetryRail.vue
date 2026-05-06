<template>
  <div class="telemetry-rail">

    <!-- Section 1: Bench Telemetry -->
    <div class="t-section">
      <div class="sect-head">
        <span class="mdi mdi-cpu-64-bit sect-icon"></span>
        <span>Bench Telemetry</span>
        <span class="sect-badge">live</span>
      </div>
      <div class="tele-grid">
        <div v-for="tile in tiles" :key="tile.id" class="stat-tile">
          <span class="stat-label">{{ tile.label }}</span>
          <div class="stat-value-row">
            <span class="stat-val">{{ tile.value }}</span>
            <span class="stat-unit">{{ tile.unit }}</span>
          </div>
          <Sparkline v-if="tile.hist" :data="tile.hist" :color="tile.color" :height="32" class="tile-spark" />
          <span v-else class="stat-trend" :class="tile.trendOk ? 'trend-ok' : ''">{{ tile.trend }}</span>
        </div>
      </div>
    </div>

    <!-- Section 2: Recent Runs -->
    <div class="t-section">
      <div class="sect-head">
        <span class="mdi mdi-history sect-icon"></span>
        <span>Recent Runs</span>
        <span class="sect-badge">last 3</span>
      </div>
      <div v-if="!recentRuns.length" class="section-empty">No recent runs.</div>
      <div v-else class="runs-list">
        <div v-for="run in recentRuns" :key="run.id" class="run-row"
          @click="router.push('/reports/' + run.id)">
          <span class="run-dot" :class="run.passed ? 'dot-ok' : 'dot-err'"></span>
          <div class="run-body">
            <div class="run-id">#{{ run.id }} · FEMB {{ run.femb_serial }}</div>
            <div class="run-meta">
              {{ run.passed
                ? `${run.n_channels}/${run.n_channels} pass`
                : `${run.n_anomalous} anomalous` }}
            </div>
          </div>
          <span class="run-time">{{ shortTime(run.timestamp) }}</span>
        </div>
      </div>
    </div>

    <!-- Section 3: Retrieval Context -->
    <div class="t-section">
      <div class="sect-head">
        <span class="mdi mdi-magnify sect-icon"></span>
        <span>Retrieval Context</span>
        <span class="sect-badge">{{ contextChunks.length }} chunks</span>
        <button class="collapse-btn" @click="showContext = !showContext" :title="showContext ? 'Collapse' : 'Expand'">
          <span class="mdi" :class="showContext ? 'mdi-chevron-up' : 'mdi-chevron-down'"></span>
        </button>
      </div>
      <template v-if="showContext">
      <div v-if="!contextChunks.length" class="section-empty">
        Sources cited by the agent will appear here.
      </div>
      <div v-else class="context-list">
        <div v-for="(chunk, i) in contextChunks" :key="i" class="context-item">
          <div class="context-name-row">
            <span class="context-name">{{ sourceName(chunk) }}</span>
            <span v-if="sourceExt(chunk)" class="context-ext">{{ sourceExt(chunk) }}</span>
          </div>
          <div v-if="chunk.text" class="context-snippet">{{ chunk.text }}</div>
          <div class="context-foot">
            <span class="context-rrf">RRF {{ chunk.rrf_score?.toFixed(3) ?? '—' }}</span>
            <span class="context-mode">· {{ sourceMode(chunk) }}</span>
          </div>
        </div>
      </div>
      </template>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSharedSession } from '../composables/useChat.js'
import Sparkline from './Sparkline.vue'

const router = useRouter()
const { messages, streaming } = useSharedSession()
const showContext = ref(false)

// ── Bench Telemetry mock data ──────────────────────────────────────────────
const HIST_LEN = 24
const tempHist = ref(Array.from({ length: HIST_LEN }, () => 89 + Math.random() * 0.4))
const rmsHist  = ref(Array.from({ length: HIST_LEN }, () => 410 + Math.random() * 8))

const tiles = computed(() => [
  { id: 'temp',  label: 'Cryo Temp',     value: tempHist.value[HIST_LEN-1].toFixed(1),           unit: 'K',    hist: tempHist.value, color: 'var(--accent)' },
  { id: 'bias',  label: 'Bias',          value: '1.80',                                           unit: 'V',    trend: '▴ within tol.', trendOk: true },
  { id: 'rms',   label: 'RMS Noise',     value: String(Math.round(rmsHist.value[HIST_LEN - 1])), unit: 'ADC',  hist: rmsHist.value,  color: 'var(--ok)' },
  { id: 'drift', label: 'Pedestal Drift',value: '0.02',                                           unit: '/min', trend: 'stable' },
])

let teleTimer
onMounted(() => {
  teleTimer = setInterval(() => {
    tempHist.value = [...tempHist.value.slice(1), 89 + Math.random() * 0.4]
    rmsHist.value  = [...rmsHist.value.slice(1),  410 + Math.random() * 8]
  }, 1400)
})
onUnmounted(() => clearInterval(teleTimer))

// ── Recent Runs ────────────────────────────────────────────────────────────
const recentRuns = ref([])

async function loadRuns() {
  try {
    const res  = await fetch('/reports?page=1&limit=3')
    const data = await res.json()
    recentRuns.value = data.items ?? []
  } catch { /* backend may not be running */ }
}

onMounted(loadRuns)
watch(streaming, (val) => { if (!val) loadRuns() })

function shortTime(iso) {
  if (!iso) return ''
  return new Date(iso).toISOString().slice(11, 16) + ' UTC'
}

// ── Retrieval Context ──────────────────────────────────────────────────────
const contextChunks = computed(() => {
  const msgs = messages.value
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i]
    if (m.role !== 'agent') continue
    if (m.retrieval?.length) return m.retrieval
    if (m.sources?.length)   return m.sources.map(s => ({ source: s }))
  }
  return []
})

function sourceName(chunk) {
  const base = (chunk.source ?? '').split('/').pop()
  const dot  = base.lastIndexOf('.')
  return dot > 0 ? base.slice(0, dot) : base
}

function sourceExt(chunk) {
  const base = (chunk.source ?? '').split('/').pop()
  const dot  = base.lastIndexOf('.')
  return dot > 0 ? base.slice(dot + 1).toUpperCase() : ''
}

function sourceMode(chunk) {
  if (chunk.in_dense && chunk.in_sparse) return 'dense + sparse'
  if (chunk.in_dense)  return 'dense'
  if (chunk.in_sparse) return 'sparse'
  return '—'
}
</script>

<style scoped>
.telemetry-rail {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  background: var(--bg-0);
}

/* Section */
.t-section { border-bottom: 1px solid var(--line); }

.sect-head {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 14px;
  border-bottom: 1px solid var(--line);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-2);
}

.sect-icon  { font-size: 14px; }
.collapse-btn {
  display: flex;
  align-items: center;
  padding: 2px 4px;
  border: none;
  background: transparent;
  color: var(--ink-3);
  font-size: 16px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: color 120ms;
}
.collapse-btn:hover { color: var(--ink-1); }

.sect-badge {
  margin-left: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  color: var(--ink-3);
}

/* ── Bench Telemetry ── */
.tele-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 12px 14px;
}

.stat-tile {
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 10px 11px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.stat-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-2);
}

.stat-value-row { display: flex; align-items: baseline; gap: 3px; }

.stat-val  { font-family: 'JetBrains Mono', monospace; font-size: 18px; font-weight: 500; color: var(--ink-0); line-height: 1; }
.stat-unit { font-size: 11px; color: var(--ink-2); }

.tile-spark { margin-top: 4px; }

.stat-trend { font-size: 10.5px; color: var(--ink-2); margin-top: 4px; }
.trend-ok   { color: var(--ok); }

/* ── Recent Runs ── */
.runs-list { display: flex; flex-direction: column; }

.run-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  transition: background 120ms;
}
.run-row:last-child { border-bottom: none; }
.run-row:hover { background: var(--bg-1); }

.run-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-ok  { background: var(--ok);  box-shadow: 0 0 6px var(--ok); }
.dot-err { background: var(--err); box-shadow: 0 0 6px var(--err); }

.run-body { min-width: 0; }
.run-id   { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: var(--ink-0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.run-meta { font-size: 10.5px; color: var(--ink-2); margin-top: 1px; }
.run-time { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: var(--ink-3); white-space: nowrap; }

/* ── Retrieval Context ── */
.context-list { display: flex; flex-direction: column; }

.context-item {
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  transition: background 120ms;
}
.context-item:last-child { border-bottom: none; }
.context-item:hover { background: var(--bg-1); }

.context-name-row { display: flex; align-items: center; gap: 6px; }
.context-name { font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: var(--ink-0); }
.context-ext  {
  font-size: 9px;
  text-transform: uppercase;
  background: var(--bg-3);
  color: var(--ink-2);
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}

.context-snippet {
  font-size: 11px;
  color: var(--ink-2);
  line-height: 1.45;
  margin-top: 3px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.context-foot {
  display: flex;
  gap: 4px;
  margin-top: 5px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--ink-3);
}
.context-rrf { color: var(--accent); }

/* Empty states */
.section-empty {
  padding: 30px 14px;
  text-align: center;
  font-size: 11.5px;
  color: var(--ink-3);
}
</style>
