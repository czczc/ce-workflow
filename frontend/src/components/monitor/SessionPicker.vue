<template>
  <div class="picker" ref="rootRef">
    <button
      class="picker-trigger"
      :class="{ open }"
      @click="toggle"
      @keydown.down.prevent="onTriggerArrow"
      :title="selectedLabel || 'choose a run'"
    >
      <span class="trigger-label">{{ triggerLabel }}</span>
      <span
        v-if="selectedRun?.status"
        class="status-icon trigger-status"
        :class="selectedRun.status"
      >{{ statusSymbol(selectedRun.status) }}</span>
      <span class="mdi mdi-chevron-down trigger-caret" :class="{ open }"></span>
    </button>

    <div v-if="open" class="picker-panel" @keydown="onPanelKey" tabindex="-1" ref="panelRef">
      <div class="picker-header">
        <button
          v-if="view === 'runs'"
          class="back-row"
          @click="viewMonths"
          :title="'browse other months'"
        >
          <span class="mdi mdi-arrow-up-left"></span>
          <span class="back-label">{{ currentMonth }}</span>
          <span class="back-hint">../</span>
        </button>
        <span v-else class="header-title">browse months</span>

        <button
          class="refresh-btn"
          @click.stop="onRefresh"
          :disabled="sessionsLoading"
          :title="refreshTitle"
        >
          <span class="mdi mdi-refresh" :class="{ spin: sessionsLoading }"></span>
        </button>
      </div>

      <ul class="picker-list">
        <template v-if="view === 'months'">
          <li
            v-for="(m, i) in months"
            :key="m.name"
            class="row month-row"
            :class="{ highlight: highlightIdx === i }"
            @click="selectMonth(m)"
            @mouseover="highlightIdx = i"
          >
            <span class="month-name">{{ m.name }}</span>
            <span class="month-count">{{ m.runs.length }}</span>
            <span class="mdi mdi-chevron-right month-chev"></span>
          </li>
          <li v-if="!months.length" class="empty-row">no months found</li>
        </template>

        <template v-else>
          <li
            v-for="(r, i) in currentMonthRuns"
            :key="r.session_id"
            class="row run-row"
            :class="{
              active: r.session_id === modelValue,
              highlight: highlightIdx === i,
            }"
            @click="selectRun(r)"
            @mouseover="highlightIdx = i"
          >
            <span class="run-ts">{{ formatTs(r.started_at) }}</span>
            <span class="run-hint">{{ r.test_type_hint }}</span>
            <span class="status-icon" :class="r.status">{{ statusSymbol(r.status) }}</span>
          </li>
          <li v-if="!currentMonthRuns.length" class="empty-row">no runs in {{ currentMonth }}</li>
        </template>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },             // selected session_id
  sessionsTree: { type: Object, required: true },        // { months: [{ name, runs: [...] }] }
  sessionsLoading: { type: Boolean, default: false },
  onLoadSessions: { type: Function, required: true },    // async (month=null) => void
})

const emit = defineEmits(['update:modelValue', 'select'])

const open = ref(false)
const view = ref('runs')          // 'months' | 'runs'
const currentMonth = ref('')
const highlightIdx = ref(0)
const rootRef = ref(null)
const panelRef = ref(null)

const months = computed(() => props.sessionsTree?.months || [])
const currentMonthData = computed(
  () => months.value.find((m) => m.name === currentMonth.value) || null
)
const currentMonthRuns = computed(() => currentMonthData.value?.runs || [])

const selectedRun = computed(() => {
  for (const m of months.value) {
    const r = m.runs.find((rr) => rr.session_id === props.modelValue)
    if (r) return r
  }
  return null
})
const selectedLabel = computed(() => {
  if (!selectedRun.value) return ''
  return `${formatTs(selectedRun.value.started_at)} · ${selectedRun.value.test_type_hint}`
})
const triggerLabel = computed(() => selectedLabel.value || '— choose a run —')

const refreshTitle = computed(() => {
  if (view.value === 'runs' && currentMonth.value) {
    return `refresh ${currentMonth.value}`
  }
  return 'refresh all months'
})

function formatTs(iso) {
  if (!iso) return '—'
  // 2026-05-10T10:02:58 → 10 May 10:02:58
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/)
  if (!m) return iso
  return `${m[3]}/${m[2]} ${m[4]}:${m[5]}:${m[6]}`
}

function statusSymbol(status) {
  if (status === 'in_progress') return '●'
  if (status === 'passed') return '✓'
  if (status === 'failed') return '✗'
  return '–'
}

function toggle() {
  open.value ? close() : openPicker()
}
function openPicker() {
  // Default: jump to selected run's month, else latest month.
  if (selectedRun.value) {
    const m = months.value.find((mm) => mm.runs.includes(selectedRun.value))
    currentMonth.value = m?.name || months.value[0]?.name || ''
    view.value = 'runs'
    highlightIdx.value = currentMonthRuns.value.findIndex(
      (r) => r.session_id === props.modelValue
    )
    if (highlightIdx.value < 0) highlightIdx.value = 0
  } else if (months.value.length) {
    currentMonth.value = months.value[0].name
    view.value = 'runs'
    highlightIdx.value = 0
  } else {
    view.value = 'months'
    highlightIdx.value = 0
  }
  open.value = true
  nextTick(() => panelRef.value?.focus())
}
function close() {
  open.value = false
}
function viewMonths() {
  view.value = 'months'
  highlightIdx.value = months.value.findIndex((m) => m.name === currentMonth.value)
  if (highlightIdx.value < 0) highlightIdx.value = 0
}
function selectMonth(m) {
  currentMonth.value = m.name
  view.value = 'runs'
  highlightIdx.value = 0
}
function selectRun(r) {
  emit('update:modelValue', r.session_id)
  emit('select', r.session_id)
  close()
}
async function onRefresh() {
  if (view.value === 'runs' && currentMonth.value) {
    await props.onLoadSessions(currentMonth.value)
  } else {
    await props.onLoadSessions(null)
  }
}

function onTriggerArrow() {
  if (!open.value) openPicker()
}
function onPanelKey(e) {
  const list = view.value === 'months' ? months.value : currentMonthRuns.value
  if (e.key === 'Escape') {
    e.preventDefault()
    close()
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (list.length) highlightIdx.value = (highlightIdx.value + 1) % list.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (list.length) highlightIdx.value = (highlightIdx.value - 1 + list.length) % list.length
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const item = list[highlightIdx.value]
    if (!item) return
    if (view.value === 'months') selectMonth(item)
    else selectRun(item)
  } else if (e.key === 'Backspace' && view.value === 'runs') {
    e.preventDefault()
    viewMonths()
  }
}

function onDocClick(e) {
  if (!open.value) return
  if (rootRef.value && !rootRef.value.contains(e.target)) close()
}
document.addEventListener('mousedown', onDocClick)
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocClick))

// Keep highlight in range when data changes
watch(currentMonthRuns, (runs) => {
  if (highlightIdx.value >= runs.length) highlightIdx.value = Math.max(0, runs.length - 1)
})
</script>

<style scoped>
.picker { position: relative; display: inline-block; }

.picker-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 280px;
  padding: 6px 10px;
  font-family: inherit;
  font-size: 13px;
  color: var(--ink-0);
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
}
.picker-trigger:hover { border-color: var(--line); }
.picker-trigger.open { border-color: var(--info); }
.trigger-label {
  flex: 1;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.trigger-status { font-size: 13px; }
.trigger-caret { transition: transform 120ms; }
.trigger-caret.open { transform: rotate(180deg); }

.picker-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 360px;
  max-width: 480px;
  max-height: 420px;
  display: flex;
  flex-direction: column;
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  z-index: 50;
  outline: none;
}

.picker-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--line-2);
}
.header-title {
  flex: 1;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ink-2);
}
.back-row {
  flex: 1;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  background: transparent;
  border: none;
  border-radius: var(--r-sm);
  color: var(--ink-1);
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  text-align: left;
}
.back-row:hover { background: var(--bg-2); color: var(--ink-0); }
.back-label { font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.back-hint  { color: var(--ink-2); font-size: 11px; }

.refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-2);
  cursor: pointer;
}
.refresh-btn:hover:not(:disabled) { color: var(--ink-0); background: var(--bg-2); }
.refresh-btn:disabled { opacity: 0.4; cursor: wait; }
.refresh-btn .mdi { font-size: 14px; }
.refresh-btn .mdi.spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.picker-list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  overflow-y: auto;
}

.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  font-size: 12.5px;
  cursor: pointer;
  color: var(--ink-1);
}
.row.highlight { background: var(--bg-2); color: var(--ink-0); }
.row.active { background: rgba(56, 139, 253, 0.10); color: var(--ink-0); }

.month-row .month-name {
  flex: 1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--ink-0);
}
.month-row .month-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-2);
}
.month-row .month-chev { color: var(--ink-2); }

.run-row .run-ts {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11.5px;
  color: var(--ink-0);
  min-width: 110px;
}
.run-row .run-hint {
  flex: 1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-icon {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  width: 14px;
  text-align: center;
}
.status-icon.in_progress { color: var(--info); }
.status-icon.passed { color: var(--ok); }
.status-icon.failed { color: var(--danger); }
.status-icon.unopened { color: var(--ink-2); }

.empty-row {
  padding: 10px 14px;
  font-size: 11px;
  color: var(--ink-2);
  font-style: italic;
}
</style>
