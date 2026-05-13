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

    <div v-if="diagnosticTestIds.length" class="diag-list">
      <div
        v-for="testId in diagnosticTestIds"
        :key="testId"
        class="diag-card"
        :ref="(el) => setDiagRef(testId, el)"
      >
        <div class="diag-head">
          <span class="diag-id mdi mdi-close-circle"></span>
          <span class="diag-title">{{ testId }} — diagnostic</span>
          <span class="diag-status" :class="state.diagnostics[testId]?.status">
            <span v-if="state.diagnostics[testId]?.status === 'streaming'" class="dot pulse"></span>
            {{ state.diagnostics[testId]?.status || 'pending' }}
          </span>
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
  </div>
</template>

<script setup>
import { computed, nextTick } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  femb: { type: Object, required: true },         // { femb_id, serial, subdir }
  state: { type: Object, required: true },        // { tests: {tN: 'pass'|'fail'}, final: bool, diagnostics: {tN: {...}} }
  totalSlots: { type: Number, default: 17 },
})

const doneCount = computed(() =>
  Object.keys(props.state.tests || {}).length
)
const anyDone = computed(() => doneCount.value > 0)

const anyFail = computed(() =>
  Object.values(props.state.tests || {}).some((v) => v === 'fail')
)

const overallClass = computed(() => (anyFail.value ? 'fail' : 'pass'))
const overallLabel = computed(() => (anyFail.value ? 'FAIL' : 'PASS'))
const overallIcon  = computed(() => (anyFail.value ? 'mdi-close-circle' : 'mdi-check-circle'))

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
  const v = props.state.tests?.[`t${t}`]
  if (!v) return `t${t} — pending`
  if (v === 'fail') return `t${t} — fail (click to jump to diagnostic)`
  return `t${t} — ${v}`
}

const diagRefs = new Map()
function setDiagRef(testId, el) {
  if (el) diagRefs.set(testId, el)
}
function onCellClick(t) {
  const tid = `t${t}`
  if (props.state.tests?.[tid] !== 'fail') return
  nextTick(() => {
    diagRefs.get(tid)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
}
.cell.pass .cell-icon { color: var(--ok); }
.cell.fail {
  background: rgba(248, 81, 73, 0.08);
  border-color: rgba(248, 81, 73, 0.4);
  cursor: pointer;
}
.cell.fail .cell-icon { color: var(--danger); }
.cell.fail:hover { border-color: var(--danger); }

.diag-list {
  margin-top: 14px;
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
</style>
