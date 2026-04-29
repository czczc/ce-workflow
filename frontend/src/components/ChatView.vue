<template>
  <v-card style="height: 100%; display: flex; flex-direction: column">
    <v-card-title>Chat</v-card-title>
    <v-divider />
    <v-card-text ref="threadRef" style="flex: 1; overflow-y: auto">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="mb-3 d-flex"
        :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <v-chip
          :color="msg.role === 'user' ? 'primary' : 'surface-variant'"
          style="max-width: 80%; height: auto; white-space: normal; padding: 8px 12px"
        >{{ msg.text }}</v-chip>
      </div>
      <div v-if="streaming && !messages[messages.length - 1]?.text" class="d-flex justify-start mb-3">
        <v-chip color="surface-variant">
          <v-progress-circular indeterminate size="16" width="2" class="mr-2" />
          Thinking...
        </v-chip>
      </div>
    </v-card-text>
    <v-divider />
    <v-card-actions class="pa-3">
      <v-text-field
        v-model="input"
        placeholder="Ask a question..."
        variant="outlined"
        density="compact"
        hide-details
        :disabled="streaming"
        class="flex-grow-1 mr-2"
        @keydown.enter.prevent="send"
      />
      <v-btn color="primary" :disabled="streaming || !input.trim()" @click="send">Send</v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const API = ''

const messages = ref([])
const input = ref('')
const streaming = ref(false)
const threadRef = ref(null)

function scrollToBottom() {
  nextTick(() => {
    const el = threadRef.value?.$el
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return

  input.value = ''
  messages.value.push({ role: 'user', text })
  scrollToBottom()

  streaming.value = true
  messages.value.push({ role: 'agent', text: '' })
  const idx = messages.value.length - 1

  try {
    const resp = await fetch(`${API}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })

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
          scrollToBottom()
        }
      }
    }
  } catch (err) {
    messages.value[idx].text = `Error: ${err.message}`
  } finally {
    streaming.value = false
    scrollToBottom()
  }
}
</script>
