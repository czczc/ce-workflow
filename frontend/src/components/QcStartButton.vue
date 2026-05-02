<template>
  <v-card class="mt-2">
    <v-card-text>
      <v-btn
        block
        color="secondary"
        :loading="running"
        :disabled="streaming"
        @click="startQc"
      >QC Start</v-btn>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref } from 'vue'
import { useChat } from '../composables/useChat.js'

const API = ''
const { messages, streaming, activeNode, completedNodes } = useChat()
const running = ref(false)

async function startQc() {
  if (running.value || streaming.value) return

  running.value = true
  streaming.value = true
  activeNode.value = null
  completedNodes.value = new Set()
  messages.value.push({ role: 'agent', text: '', sources: [], retrieval: [] })
  const idx = messages.value.length - 1

  try {
    const resp = await fetch(`${API}/qc/start`, { method: 'POST' })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop()
      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)
        if (data === '[DONE]') break
        const evt = JSON.parse(data)
        if (evt.type === 'token') {
          messages.value[idx].text += evt.text
        } else if (evt.type === 'node_active') {
          if (activeNode.value) completedNodes.value.add(activeNode.value)
          activeNode.value = evt.node
          completedNodes.value = new Set(completedNodes.value)
        } else if (evt.type === 'node_done') {
          if (activeNode.value) {
            completedNodes.value.add(activeNode.value)
            completedNodes.value = new Set(completedNodes.value)
          }
          activeNode.value = null
        }
      }
    }
  } catch (err) {
    messages.value[idx].text = `Error: ${err.message}`
  } finally {
    if (activeNode.value) {
      completedNodes.value.add(activeNode.value)
      completedNodes.value = new Set(completedNodes.value)
      activeNode.value = null
    }
    running.value = false
    streaming.value = false
  }
}
</script>
