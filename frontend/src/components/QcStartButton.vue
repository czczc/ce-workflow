<template>
  <section class="qc-section">
    <div class="sect-head">
      <span class="mdi mdi-chip sect-icon"></span>
      <span>QC Run</span>
    </div>
    <div class="sect-body">
      <div class="field-row">
        <span class="field-label">FEMB Serial</span>
        <span class="field-hint">optional</span>
      </div>
      <input
        v-model="componentId"
        class="femb-input"
        placeholder="e.g. 00030"
        :disabled="anyRunning || streaming"
      />
      <div class="btn-row">
        <button class="btn-primary" :disabled="anyRunning || streaming" @click="startQc(false)">
          <span :class="runningNormal ? 'mdi mdi-loading spin' : 'mdi mdi-lightning-bolt'"></span>
          QC Start
        </button>
        <button class="btn-warn" :disabled="anyRunning || streaming" @click="startQc(true)">
          Inject Test
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useSharedSession } from '../composables/useChat.js'
import { readStream } from '../composables/useStream.js'

const API = ''
const { messages, streaming, activeNode, completedNodes } = useSharedSession()
const runningNormal = ref(false)
const runningTest = ref(false)
const anyRunning = computed(() => runningNormal.value || runningTest.value)
const componentId = ref('')

async function startQc(test) {
  if (anyRunning.value || streaming.value) return

  if (test) runningTest.value = true
  else runningNormal.value = true
  streaming.value = true
  activeNode.value = null
  completedNodes.value = new Set()
  messages.value.push({ role: 'agent', text: '', sources: [], retrieval: [] })
  const idx = messages.value.length - 1

  try {
    const params = new URLSearchParams()
    if (test) params.set('test', 'true')
    if (componentId.value) params.set('component_id', componentId.value.trim())
    const url = `${API}/qc/start${params.size ? '?' + params : ''}`
    const resp = await fetch(url, { method: 'POST' })
    await readStream(resp, {
      token: (evt) => { messages.value[idx].text += evt.text },
      node_active: (evt) => {
        if (activeNode.value) completedNodes.value.add(activeNode.value)
        activeNode.value = evt.node
        completedNodes.value = new Set(completedNodes.value)
      },
      node_done: () => {
        if (activeNode.value) {
          completedNodes.value.add(activeNode.value)
          completedNodes.value = new Set(completedNodes.value)
        }
        activeNode.value = null
      },
    })
  } catch (err) {
    messages.value[idx].text = `Error: ${err.message}`
  } finally {
    if (activeNode.value) {
      completedNodes.value.add(activeNode.value)
      completedNodes.value = new Set(completedNodes.value)
      activeNode.value = null
    }
    runningNormal.value = false
    runningTest.value = false
    streaming.value = false
  }
}
</script>

<style scoped>
.qc-section { border-bottom: 1px solid var(--line); }

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

.sect-icon { font-size: 14px; }

.sect-body { padding: 14px; }

.field-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}

.field-label {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.04em;
  color: var(--ink-2);
}

.field-hint {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--ink-3);
}

.femb-input {
  width: 100%;
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  padding: 8px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--ink-0);
  outline: none;
  box-sizing: border-box;
}

.femb-input::placeholder { color: var(--ink-3); }

.femb-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.femb-input:disabled { opacity: 0.45; cursor: not-allowed; }

.btn-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}

.btn-primary,
.btn-warn {
  padding: 7px 10px;
  border-radius: var(--r-md);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: background 120ms, border-color 120ms;
}

.btn-primary:active:not(:disabled),
.btn-warn:active:not(:disabled) { transform: translateY(1px); }

.btn-primary {
  background: var(--accent);
  color: #fff;
  border: none;
}
.btn-primary:hover:not(:disabled) { background: #0a7e8e; }
.btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }

.btn-warn {
  background: transparent;
  color: var(--warn);
  border: 1px solid rgba(201,122,20,0.4);
}
.btn-warn:hover:not(:disabled) {
  background: rgba(201,122,20,0.08);
  border-color: var(--warn);
}
.btn-warn:disabled { opacity: 0.45; cursor: not-allowed; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.spin { display: inline-block; animation: spin 0.7s linear infinite; }
</style>
