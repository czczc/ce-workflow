<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @mousedown.self="emit('close')">
      <div class="modal" role="dialog" aria-modal="true" @keydown.esc.stop="emit('close')" tabindex="-1" ref="rootRef">
        <header class="modal-head">
          <span class="head-id">{{ testId }}</span>
          <span v-if="testName" class="head-name">{{ testName }}</span>
          <span
            v-if="report?.status"
            class="status-pill"
            :class="report.status"
          >
            <span class="mdi" :class="statusIcon"></span>
            {{ report.status }}
          </span>
          <span class="head-filename" :title="report?.filename">{{ report?.filename || '' }}</span>
          <button class="close-btn" @click="emit('close')" title="Close (Esc)">
            <span class="mdi mdi-close"></span>
          </button>
        </header>

        <div class="modal-body">
          <div v-if="loading" class="body-state">loading report…</div>
          <div v-else-if="error" class="body-state error">{{ error }}</div>
          <div
            v-else-if="report"
            class="markdown-body"
            v-html="rendered"
          ></div>
          <div v-else class="body-state">no report available</div>
        </div>

        <footer v-if="report?.status === 'fail'" class="modal-foot">
          <button class="link-btn" @click="emit('jump-diagnostic')">
            <span class="mdi mdi-arrow-down"></span>
            scroll to diagnostic
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  open: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  testId: { type: String, default: '' },        // e.g. "t5"
  testName: { type: String, default: '' },      // e.g. "rms_noise"
  report: { type: Object, default: null },      // { test_id, status, md, filename } | null
})
const emit = defineEmits(['close', 'jump-diagnostic'])

const rootRef = ref(null)

const rendered = computed(() =>
  props.report?.md ? marked.parse(props.report.md) : ''
)
const statusIcon = computed(() =>
  props.report?.status === 'pass' ? 'mdi-check-circle' : 'mdi-close-circle'
)

watch(
  () => props.open,
  (v) => {
    if (v) nextTick(() => rootRef.value?.focus())
  },
)
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 32px 16px;
}

.modal {
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
  width: min(900px, 100%);
  max-height: 100%;
  display: flex;
  flex-direction: column;
  outline: none;
}

.modal-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line-2);
  flex-wrap: wrap;
}
.head-id {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 13px;
  color: var(--ink-0);
  padding: 2px 8px;
  background: var(--bg-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
}
.head-name {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--ink-2);
}
.head-filename {
  flex: 1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: right;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  font-size: 10.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-radius: 999px;
}
.status-pill .mdi { font-size: 13px; }
.status-pill.pass { color: var(--ok);     background: rgba(57, 211, 83, 0.12); }
.status-pill.fail { color: var(--danger); background: rgba(248, 81, 73, 0.12); }

.close-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-2);
  cursor: pointer;
}
.close-btn:hover { color: var(--ink-0); background: var(--bg-2); }
.close-btn .mdi { font-size: 14px; }

.modal-body {
  padding: 14px 18px;
  overflow-y: auto;
  flex: 1;
}
.body-state {
  font-size: 12px;
  color: var(--ink-2);
  font-style: italic;
  padding: 8px 0;
}
.body-state.error { color: var(--danger); font-style: normal; }

.markdown-body {
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-1);
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  color: var(--ink-0);
  margin: 16px 0 8px;
}
.markdown-body :deep(h1) { font-size: 18px; }
.markdown-body :deep(h2) { font-size: 15px; }
.markdown-body :deep(h3) { font-size: 13.5px; }
.markdown-body :deep(p)  { margin: 0 0 10px; }
.markdown-body :deep(code) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  background: var(--bg-2);
  padding: 1px 5px;
  border-radius: 3px;
}
.markdown-body :deep(pre) {
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  padding: 10px 12px;
  border-radius: var(--r-sm);
  overflow-x: auto;
  font-size: 12px;
}
.markdown-body :deep(pre code) { background: transparent; padding: 0; }
.markdown-body :deep(table) {
  border-collapse: collapse;
  font-size: 12px;
  margin: 8px 0;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--line-2);
  padding: 4px 8px;
  text-align: left;
}
.markdown-body :deep(th) { background: var(--bg-2); }

.modal-foot {
  padding: 8px 16px;
  border-top: 1px solid var(--line-2);
  display: flex;
  justify-content: flex-end;
}
.link-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  font-size: 11px;
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-1);
  cursor: pointer;
}
.link-btn:hover { color: var(--ink-0); background: var(--bg-2); }
</style>
