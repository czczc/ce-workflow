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
      >
        <span class="cell-id">t{{ t }}</span>
        <span v-if="state.tests[`t${t}`] === 'pass'" class="mdi mdi-check-bold cell-icon"></span>
        <span v-else-if="state.tests[`t${t}`] === 'fail'" class="mdi mdi-close-thick cell-icon"></span>
        <span v-else class="cell-pending"></span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  femb: { type: Object, required: true },         // { femb_id, serial, subdir }
  state: { type: Object, required: true },        // { tests: {tN: 'pass'|'fail'}, final: bool }
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

function cellClass(t) {
  const v = props.state.tests?.[`t${t}`]
  if (v === 'pass') return 'pass'
  if (v === 'fail') return 'fail'
  return 'pending'
}
function cellTitle(t) {
  const v = props.state.tests?.[`t${t}`]
  if (!v) return `t${t} — pending`
  return `t${t} — ${v}`
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
}
.cell.fail .cell-icon { color: var(--danger); }
</style>
