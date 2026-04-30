<template>
  <v-card style="height: 100%; display: flex; flex-direction: column; overflow: hidden">
    <v-card-title>Chat</v-card-title>
    <v-divider />
    <v-card-text ref="threadRef" style="flex: 1; overflow-y: auto; min-height: 0">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="mb-3 d-flex"
        :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <div class="msg-bubble" :class="msg.role === 'user' ? 'msg-user' : 'msg-agent'">
          <div v-if="msg.role === 'agent'" v-html="render(msg.text)" />
          <div v-else>{{ msg.text }}</div>
          <div v-if="msg.sources?.length" class="msg-sources">
            <span v-for="s in msg.sources" :key="s" class="msg-source-tag">{{ s }}</span>
          </div>
          <details v-if="msg.retrieval?.length" class="msg-retrieval">
            <summary>Retrieved chunks ({{ msg.retrieval.length }})</summary>
            <div v-for="(c, i) in msg.retrieval" :key="i" class="retrieval-chunk">
              <div class="retrieval-chunk-meta">
                <span class="retrieval-source">{{ c.source }}</span>
                <span class="retrieval-index">#{{ c.chunk_index }}</span>
                <span class="retrieval-score">RRF {{ c.rrf_score.toFixed(3) }}</span>
                <span v-if="c.in_dense" class="retrieval-badge retrieval-badge-dense">dense</span>
                <span v-if="c.in_sparse" class="retrieval-badge retrieval-badge-sparse">sparse</span>
              </div>
              <div class="retrieval-chunk-text">{{ c.text }}</div>
            </div>
          </details>
        </div>
      </div>
      <div v-if="streaming && !messages[messages.length - 1]?.text" class="d-flex justify-start mb-3">
        <div class="msg-bubble msg-agent">
          <v-progress-circular indeterminate size="16" width="2" class="mr-2" />
          Thinking...
        </div>
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
import { marked } from 'marked'

const API = ''

const messages = ref([])
const input = ref('')
const streaming = ref(false)
const threadRef = ref(null)

function render(text) {
  return text ? marked.parse(text) : ''
}

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
  messages.value.push({ role: 'agent', text: '', sources: [], retrieval: [] })
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
        } else if (evt.type === 'sources') {
          messages.value[idx].sources = evt.sources
        } else if (evt.type === 'retrieval') {
          messages.value[idx].retrieval = evt.chunks
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

<style scoped>
.msg-bubble {
  max-width: 80%;
  padding: 8px 14px;
  border-radius: 8px;
  word-break: break-word;
  line-height: 1.5;
}
.msg-user {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.msg-agent {
  background: #f1f3f4;
  color: #202124;
}
.msg-sources {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px solid rgba(0, 0, 0, 0.12);
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.msg-source-tag {
  font-size: 0.72rem;
  padding: 1px 7px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.1);
}
.msg-bubble :deep(p) { margin: 0 0 6px; }
.msg-bubble :deep(p:last-child) { margin-bottom: 0; }
.msg-bubble :deep(ul),
.msg-bubble :deep(ol) { padding-left: 1.4em; margin: 4px 0; }
.msg-bubble :deep(li) { margin-bottom: 2px; }
.msg-bubble :deep(pre) { white-space: pre-wrap; margin: 6px 0; }
.msg-bubble :deep(code) { font-size: 0.85em; }
.msg-bubble :deep(h1),
.msg-bubble :deep(h2),
.msg-bubble :deep(h3) { margin: 8px 0 4px; font-size: 1em; font-weight: 600; }
.msg-retrieval {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px solid rgba(0, 0, 0, 0.12);
  font-size: 0.75rem;
}
.msg-retrieval summary {
  cursor: pointer;
  color: rgba(0, 0, 0, 0.5);
  user-select: none;
}
.retrieval-chunk {
  margin-top: 8px;
  padding: 6px 8px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
}
.retrieval-chunk-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 4px;
}
.retrieval-source { font-weight: 600; }
.retrieval-index  { color: rgba(0, 0, 0, 0.45); }
.retrieval-score  { color: rgba(0, 0, 0, 0.45); }
.retrieval-badge {
  font-size: 0.68rem;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.retrieval-badge-dense  { background: #dbeafe; color: #1d4ed8; }
.retrieval-badge-sparse { background: #fef9c3; color: #854d0e; }
.retrieval-chunk-text {
  white-space: pre-wrap;
  color: rgba(0, 0, 0, 0.7);
  line-height: 1.4;
}
</style>
