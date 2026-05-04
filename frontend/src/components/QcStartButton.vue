<template>
  <v-card class="mt-2">
    <v-card-text class="d-flex flex-column gap-2">
      <v-text-field
        v-model="componentId"
        label="FEMB Serial Number (optional)"
        placeholder="e.g. 00030"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        :disabled="anyRunning || streaming"
      />
      <div class="d-flex gap-2">
        <v-btn
          class="flex-grow-1"
          color="secondary"
          :loading="runningNormal"
          :disabled="anyRunning || streaming"
          @click="startQc(false)"
        >QC Start</v-btn>
        <v-btn
          class="flex-grow-1"
          color="warning"
          :loading="runningTest"
          :disabled="anyRunning || streaming"
          @click="startQc(true)"
        >QC Start (Test)</v-btn>
      </div>
    </v-card-text>
  </v-card>
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
