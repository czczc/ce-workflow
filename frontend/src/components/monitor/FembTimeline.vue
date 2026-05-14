<template>
  <div class="femb-col">
    <div class="femb-head">
      <div class="femb-id">{{ femb.femb_id }}</div>
      <div class="femb-serial">{{ femb.serial }}</div>
      <div class="femb-status">
        <span v-if="state.final" class="badge final" :class="overallClass">
          <span class="mdi" :class="overallIcon"></span>
          {{ overallLabel }}
        </span>
        <span v-else-if="anyDone" class="badge running">
          <span class="dot pulse"></span>
          {{ doneCount }} / {{ totalSlots }}
        </span>
        <span v-else class="badge idle">waiting</span>
      </div>
    </div>

    <div class="test-grid">
      <div
        v-for="t in totalSlots"
        :key="t"
        class="cell"
        :class="cellClass(t)"
        :title="cellTitle(t)"
        @click="onCellClick(t)"
      >
        <span class="cell-id">t{{ t }}</span>
        <span v-if="state.tests[`t${t}`] === 'pass'" class="mdi mdi-check-bold cell-icon"></span>
        <span v-else-if="state.tests[`t${t}`] === 'fail'" class="mdi mdi-close-thick cell-icon"></span>
        <span v-else class="cell-pending"></span>
      </div>
    </div>

    <div v-if="hasFailures" class="diag-header">
      <span class="diag-header-title">
        {{ failureCount }} failure{{ failureCount === 1 ? '' : 's' }} — diagnostics
      </span>
      <div v-if="canEditDiagnostics" class="diag-actions">
        <button
          class="action-btn"
          :disabled="regeneratingAll"
          @click="onRegenerateAll"
          title="Re-run the diagnostic LLM for every failed test of this FEMB"
        >
          <span class="mdi mdi-refresh"></span>
          <span>{{ regeneratingAll ? 'regenerating…' : 'regenerate all' }}</span>
        </button>
        <button
          class="action-btn"
          :disabled="regeneratingAll"
          @click="onClearAll"
          title="Delete all saved diagnostics for this FEMB without regenerating"
        >
          <span class="mdi mdi-trash-can-outline"></span>
          <span>clear all</span>
        </button>
      </div>
    </div>

    <div v-if="diagnosticTestIds.length" class="diag-list">
      <div
        v-for="testId in diagnosticTestIds"
        :key="testId"
        class="diag-card"
        :ref="(el) => setDiagRef(testId, el)"
      >
        <div class="diag-head">
          <span class="diag-id mdi mdi-close-circle"></span>
          <span class="diag-title">
            {{ testId }}<span v-if="labelFor(testId)" class="diag-title-name"> · {{ labelFor(testId) }}</span>
          </span>
          <span class="diag-status" :class="state.diagnostics[testId]?.status">
            <span v-if="state.diagnostics[testId]?.status === 'streaming'" class="dot pulse"></span>
            {{ state.diagnostics[testId]?.status || 'pending' }}
          </span>
          <div v-if="canEditDiagnostics" class="card-actions">
            <button
              class="card-btn"
              :disabled="isRegenerating(testId)"
              @click="onRegenerateCard(testId)"
              :title="`Regenerate just ${testId}`"
            >
              <span class="mdi mdi-refresh"></span>
            </button>
            <button
              class="card-btn"
              :disabled="isRegenerating(testId)"
              @click="onClearCard(testId)"
              :title="`Delete just ${testId}'s diagnostic`"
            >
              <span class="mdi mdi-close"></span>
            </button>
          </div>
        </div>
        <div v-if="state.diagnostics[testId]?.sources?.length" class="diag-sources">
          <span class="src-label">sources</span>
          <span
            v-for="src in state.diagnostics[testId].sources"
            :key="src"
            class="src-chip"
          >{{ src }}</span>
        </div>
        <div
          class="diag-body markdown-body"
          v-html="renderMarkdown(state.diagnostics[testId]?.text)"
        ></div>
        <div v-if="state.diagnostics[testId]?.error" class="diag-error">
          {{ state.diagnostics[testId].error }}
        </div>
      </div>
    </div>

    <div v-if="state.summary" class="summary-card" :class="state.summary.passed ? 'pass' : 'fail'">
      <div class="summary-head">
        <span class="mdi" :class="state.summary.passed ? 'mdi-clipboard-check-outline' : 'mdi-clipboard-alert-outline'"></span>
        <span class="summary-title">run summary</span>
        <span class="summary-stat">
          {{ state.summary.n_failed }} / {{ state.summary.n_tests }} failed
        </span>
        <span v-if="state.summary.streaming" class="summary-status streaming">
          <span class="dot pulse"></span>
          generating…
        </span>
        <span v-else-if="state.summary.from_cache" class="cache-chip" title="loaded from saved record">cached</span>
      </div>
      <div
        v-if="state.summary.summary_md || !state.summary.streaming"
        class="summary-body markdown-body"
        v-html="renderMarkdown(state.summary.summary_md)"
      ></div>
      <div v-else class="summary-placeholder">awaiting LLM tokens…</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  femb: { type: Object, required: true },         // { femb_id, serial, subdir }
  state: { type: Object, required: true },        // { tests, final, diagnostics, summary }
  testLabels: { type: Object, default: () => ({}) }, // { "t1": "pwr_consumption", ... }
  totalSlots: { type: Number, default: 17 },
  onRegenerate: { type: Function, default: null }, // async (fembRunId, fembId) => void
  onClear:      { type: Function, default: null }, // (fembRunId, fembId) => void
})

const emit = defineEmits(['show-report'])

function labelFor(testId) {
  return props.testLabels?.[testId] || ''
}

function scrollToDiagnostic(testId) {
  diagRefs.get(testId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
defineExpose({ scrollToDiagnostic })

const regeneratingAll = ref(false)
const regeneratingCards = ref(new Set())  // test_ids currently regenerating individually

const canEditDiagnostics = computed(
  () => !!props.state.summary?.femb_run_id && (props.onRegenerate || props.onClear)
)
const failureCount = computed(() => props.state.summary?.n_failed ?? diagnosticTestIds.value.length)
const hasFailures = computed(() => failureCount.value > 0)

function isRegenerating(testId) {
  return regeneratingAll.value || regeneratingCards.value.has(testId)
}

async function onRegenerateAll() {
  if (!props.onRegenerate || !props.state.summary?.femb_run_id) return
  regeneratingAll.value = true
  try {
    await props.onRegenerate(props.state.summary.femb_run_id, props.femb.femb_id, null)
  } finally {
    regeneratingAll.value = false
  }
}
function onClearAll() {
  if (!props.onClear || !props.state.summary?.femb_run_id) return
  props.onClear(props.state.summary.femb_run_id, props.femb.femb_id, null)
}
async function onRegenerateCard(testId) {
  if (!props.onRegenerate || !props.state.summary?.femb_run_id) return
  regeneratingCards.value.add(testId)
  try {
    await props.onRegenerate(props.state.summary.femb_run_id, props.femb.femb_id, testId)
  } finally {
    regeneratingCards.value.delete(testId)
  }
}
function onClearCard(testId) {
  if (!props.onClear || !props.state.summary?.femb_run_id) return
  props.onClear(props.state.summary.femb_run_id, props.femb.femb_id, testId)
}

const doneCount = computed(() =>
  Object.keys(props.state.tests || {}).length
)
const anyDone = computed(() => doneCount.value > 0)

const anyFail = computed(() =>
  Object.values(props.state.tests || {}).some((v) => v === 'fail')
)

const hasSummary = computed(() => !!props.state.summary)
const isFail = computed(() =>
  hasSummary.value ? !props.state.summary.passed : anyFail.value
)
const overallClass = computed(() => (isFail.value ? 'fail' : 'pass'))
const overallLabel = computed(() => (isFail.value ? 'FAIL' : 'PASS'))
const overallIcon  = computed(() => (isFail.value ? 'mdi-close-circle' : 'mdi-check-circle'))

const diagnosticTestIds = computed(() => {
  const d = props.state.diagnostics || {}
  return Object.keys(d).sort((a, b) => {
    const an = parseInt(a.replace('t', ''), 10) || 0
    const bn = parseInt(b.replace('t', ''), 10) || 0
    return an - bn
  })
})

function cellClass(t) {
  const v = props.state.tests?.[`t${t}`]
  if (v === 'pass') return 'pass'
  if (v === 'fail') return 'fail'
  return 'pending'
}
function cellTitle(t) {
  const tid = `t${t}`
  const name = labelFor(tid)
  const head = name ? `${tid} · ${name}` : tid
  const v = props.state.tests?.[tid]
  if (!v) return `${head} — pending`
  return `${head} — ${v} (click to view report)`
}

const diagRefs = new Map()
function setDiagRef(testId, el) {
  if (el) diagRefs.set(testId, el)
}
function onCellClick(t) {
  const tid = `t${t}`
  const status = props.state.tests?.[tid]
  if (!status) return  // pending cells: no report yet
  emit('show-report', {
    femb_id: props.femb.femb_id,
    test_id: tid,
    status,
  })
}
function renderMarkdown(text) {
  return text ? marked.parse(text) : '<span class="diag-placeholder">awaiting LLM…</span>'
}
</script>

<style scoped>
.femb-col {
  display: flex;
  flex-direction: column;
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 14px 14px 16px;
  min-width: 0;
}

.femb-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.femb-id {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 14px;
  color: var(--ink-0);
  padding: 2px 8px;
  background: var(--bg-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
}

.femb-serial {
  flex: 1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-2);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.femb-status { display: flex; align-items: center; }

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 999px;
  letter-spacing: 0.04em;
}
.badge.idle    { color: var(--ink-2); background: var(--bg-2); }
.badge.running { color: var(--info); background: rgba(56, 139, 253, 0.12); }
.badge.final.pass { color: var(--ok);    background: rgba(57, 211, 83, 0.12); }
.badge.final.fail { color: var(--danger); background: rgba(248, 81, 73, 0.12); }
.badge .mdi { font-size: 13px; }

.dot.pulse {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--info);
  animation: pulse 1.4s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%      { opacity: 0.45; transform: scale(1.35); }
}

.test-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(64px, 1fr));
  gap: 6px;
}

.cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 4px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  min-height: 50px;
  gap: 2px;
  transition: background 120ms, border-color 120ms;
}

.cell .cell-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--ink-2);
}
.cell .cell-icon { font-size: 18px; }
.cell .cell-pending {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--line-2);
}

.cell.pending {}
.cell.pass {
  background: rgba(57, 211, 83, 0.08);
  border-color: rgba(57, 211, 83, 0.4);
  cursor: pointer;
}
.cell.pass .cell-icon { color: var(--ok); }
.cell.pass:hover { border-color: var(--ok); }
.cell.fail {
  background: rgba(248, 81, 73, 0.08);
  border-color: rgba(248, 81, 73, 0.4);
  cursor: pointer;
}
.cell.fail .cell-icon { color: var(--danger); }
.cell.fail:hover { border-color: var(--danger); }

.diag-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.diag-card {
  border: 1px solid rgba(248, 81, 73, 0.3);
  background: rgba(248, 81, 73, 0.04);
  border-radius: var(--r-md);
  padding: 10px 12px;
}

.diag-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.diag-id { color: var(--danger); font-size: 14px; }
.diag-title {
  flex: 1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-0);
}
.diag-title-name { color: var(--ink-2); font-weight: 500; }
.diag-status {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 999px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.diag-status.pending   { color: var(--ink-2); background: var(--bg-2); }
.diag-status.streaming { color: var(--info); background: rgba(56, 139, 253, 0.12); }
.diag-status.done      { color: var(--ok);   background: rgba(57, 211, 83, 0.12); }
.diag-status.error     { color: var(--danger); background: rgba(248, 81, 73, 0.12); }

.diag-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
}
.src-label {
  font-size: 9px;
  text-transform: uppercase;
  color: var(--ink-2);
  letter-spacing: 0.05em;
}
.src-chip {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--ink-1);
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  padding: 1px 7px;
  border-radius: 999px;
}

.diag-body {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--ink-1);
  word-wrap: break-word;
}
.diag-body :deep(p)      { margin: 0 0 8px; }
.diag-body :deep(p:last-child) { margin-bottom: 0; }
.diag-body :deep(strong) { color: var(--ink-0); }
.diag-body :deep(code)   {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11.5px;
  background: var(--bg-2);
  padding: 1px 5px;
  border-radius: 3px;
}
.diag-placeholder { color: var(--ink-2); font-style: italic; font-size: 11px; }

.diag-error {
  margin-top: 6px;
  color: var(--danger);
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
}

.summary-card {
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: var(--r-md);
  border: 1px solid var(--line-2);
  background: var(--bg-2);
}
.summary-card.pass {
  border-color: rgba(57, 211, 83, 0.35);
  background: rgba(57, 211, 83, 0.05);
}
.summary-card.fail {
  border-color: rgba(248, 81, 73, 0.35);
  background: rgba(248, 81, 73, 0.05);
}

.summary-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.summary-head .mdi { font-size: 14px; }
.summary-card.pass .summary-head .mdi { color: var(--ok); }
.summary-card.fail .summary-head .mdi { color: var(--danger); }
.summary-title {
  flex: 1;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-1);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.summary-stat {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-2);
}

.diag-header {
  margin-top: 16px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.diag-header-title {
  flex: 1;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-2);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.diag-actions {
  display: flex;
  gap: 4px;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-size: 11px;
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-1);
  cursor: pointer;
  font-family: inherit;
}
.action-btn:hover:not(:disabled) {
  color: var(--ink-0);
  background: var(--bg-3);
}
.action-btn:disabled { opacity: 0.4; cursor: wait; }
.action-btn .mdi { font-size: 13px; }

.card-actions {
  display: flex;
  gap: 2px;
  margin-left: 4px;
}
.card-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-2);
  cursor: pointer;
}
.card-btn:hover:not(:disabled) {
  color: var(--ink-0);
  background: var(--bg-2);
}
.card-btn:disabled { opacity: 0.35; cursor: wait; }
.card-btn .mdi { font-size: 13px; }
.cache-chip {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ink-2);
  background: var(--bg-3);
  border: 1px solid var(--line-2);
  padding: 1px 6px;
  border-radius: 999px;
}

.summary-body {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--ink-1);
}
.summary-body :deep(p) { margin: 0; }

.summary-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.summary-status.streaming {
  color: var(--info);
  background: rgba(56, 139, 253, 0.12);
}

.summary-placeholder {
  font-size: 11px;
  font-style: italic;
  color: var(--ink-2);
  padding: 2px 0;
}
</style>
