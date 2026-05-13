<template>
  <div class="monitor-chat" v-if="sessionId">
    <div class="chat-head">
      <div class="head-title">
        <span class="mdi mdi-forum-outline"></span>
        Session chat
        <span v-if="messages.length" class="msg-count">{{ messages.length }}</span>
      </div>
      <div class="head-actions">
        <button
          class="text-btn"
          :disabled="streaming || !messages.length"
          @click="onClearClick"
          :title="messages.length ? 'Delete all chat messages for this session' : 'No history yet'"
        >
          <span class="mdi mdi-trash-can-outline"></span>
          <span>clear</span>
        </button>
        <button
          class="icon-btn"
          @click="$emit('collapse')"
          title="Collapse chat panel"
        >
          <span class="mdi mdi-chevron-double-right"></span>
        </button>
      </div>
    </div>

    <div class="thread" ref="threadRef">
      <div v-if="!messages.length" class="empty">
        Ask anything about this run. The model can see the FEMB outcomes,
        saved diagnostics, and the QC docs index.
      </div>
      <MessageBubble
        v-for="(msg, i) in messages"
        :key="i"
        :role="msg.role === 'assistant' ? 'agent' : 'user'"
        :text="msg.text"
        :sources="msg.sources"
        :ts="msg.ts"
        :streaming="isStreaming(i, msg)"
        :thinking="isThinking(i, msg)"
      />
    </div>

    <div class="composer-wrap">
      <div class="composer">
        <textarea
          ref="textareaRef"
          v-model="input"
          :placeholder="streaming ? 'Streaming…' : 'Ask about this run…'"
          :disabled="streaming"
          rows="1"
          @keydown="onKeydown"
          @input="autoResize"
        />
        <button class="send-btn" :disabled="streaming || !input.trim()" @click="send">
          <span class="mdi mdi-send"></span>
        </button>
      </div>
      <div class="composer-foot">
        <span class="foot-item"><kbd>↵</kbd> send</span>
        <span class="foot-item"><kbd>⇧↵</kbd> newline</span>
      </div>
    </div>
  </div>

  <div v-else class="monitor-chat empty-chat">
    Pick a session to start chatting.
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { readStream } from '../../composables/useStream'
import MessageBubble from '../chat/MessageBubble.vue'

const props = defineProps({
  sessionId: { type: String, default: '' },
})
defineEmits(['collapse'])

// messages: [{role: 'user'|'assistant', text, sources, ts}]
const messages = ref([])
const input = ref('')
const streaming = ref(false)
const threadRef = ref(null)
const textareaRef = ref(null)

let abortCtrl = null

async function loadHistory() {
  messages.value = []
  if (!props.sessionId) return
  try {
    const resp = await fetch(`/monitor/sessions/${props.sessionId}/chat`)
    if (!resp.ok) return
    const rows = await resp.json()
    messages.value = rows.map((r) => ({
      role: r.role,
      text: r.content,
      sources: [],
      ts: r.ts ? Date.parse(r.ts) : Date.now(),
    }))
    scrollToBottom()
  } catch {/* offline ok */}
}

watch(() => props.sessionId, () => {
  cancelInflight()
  loadHistory()
})
onMounted(loadHistory)
onUnmounted(() => cancelInflight())

function cancelInflight() {
  if (abortCtrl) {
    abortCtrl.abort()
    abortCtrl = null
  }
  streaming.value = false
}

function scrollToBottom() {
  nextTick(() => {
    requestAnimationFrame(() => {
      const el = threadRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  })
}

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 140) + 'px'
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function isThinking(i, msg) {
  return streaming.value && i === messages.value.length - 1 && msg.role === 'assistant' && !msg.text
}
function isStreaming(i, msg) {
  return streaming.value && i === messages.value.length - 1 && msg.role === 'assistant' && !!msg.text
}

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value || !props.sessionId) return

  input.value = ''
  nextTick(() => { if (textareaRef.value) textareaRef.value.style.height = 'auto' })

  messages.value.push({ role: 'user', text, sources: [], ts: Date.now() })
  messages.value.push({ role: 'assistant', text: '', sources: [], ts: Date.now() })
  const idx = messages.value.length - 1
  streaming.value = true
  scrollToBottom()

  abortCtrl = new AbortController()
  try {
    const resp = await fetch(`/monitor/sessions/${props.sessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
      signal: abortCtrl.signal,
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    await readStream(resp, {
      token:     (evt) => { messages.value[idx].text += evt.text; scrollToBottom() },
      sources:   (evt) => { messages.value[idx].sources = evt.sources || [] },
      retrieval: () => {},
      error:     (evt) => { messages.value[idx].text += `\n\n_${evt.message}_` },
    })
  } catch (err) {
    if (err.name !== 'AbortError') {
      messages.value[idx].text += `\n\n_Error: ${err.message}_`
    }
  } finally {
    streaming.value = false
    abortCtrl = null
    scrollToBottom()
  }
}

async function onClearClick() {
  if (!props.sessionId || !messages.value.length) return
  const ok = window.confirm(
    `Delete all ${messages.value.length} chat message(s) for this session?\n\n` +
    `The persisted run summaries and diagnostics are NOT affected.`
  )
  if (!ok) return
  try {
    const resp = await fetch(`/monitor/sessions/${props.sessionId}/chat`, { method: 'DELETE' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    messages.value = []
  } catch (e) {
    window.alert(`Clear failed: ${e.message}`)
  }
}
</script>

<style scoped>
.monitor-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-1);
  font-size: 13px;
}
.empty-chat {
  align-items: center;
  justify-content: center;
  color: var(--ink-3);
  font-size: 12px;
  text-align: center;
  padding: 24px;
}

.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 40px;
  padding: 0 14px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.head-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-1);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.head-title .mdi { font-size: 14px; color: var(--ink-2); }

.msg-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--ink-2);
  background: var(--bg-3);
  border: 1px solid var(--line-2);
  border-radius: 999px;
  padding: 1px 6px;
  margin-left: 2px;
  letter-spacing: 0;
  text-transform: none;
}

.head-actions { display: flex; gap: 4px; }
.text-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-size: 11px;
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-2);
  cursor: pointer;
  font-family: inherit;
}
.text-btn:hover:not(:disabled) {
  color: var(--danger);
  border-color: rgba(248, 81, 73, 0.4);
  background: rgba(248, 81, 73, 0.06);
}
.text-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.text-btn .mdi { font-size: 13px; }

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  color: var(--ink-2);
  cursor: pointer;
}
.icon-btn:hover { color: var(--ink-0); background: var(--bg-2); }
.icon-btn .mdi { font-size: 14px; }

.thread {
  flex: 1;
  overflow-y: auto;
  padding: 14px 14px 8px;
  min-height: 0;
}
.empty {
  font-size: 11.5px;
  color: var(--ink-3);
  line-height: 1.55;
  padding: 8px 4px;
}

.composer-wrap {
  border-top: 1px solid var(--line);
  background: var(--bg-0);
  padding: 10px 12px 12px;
  flex-shrink: 0;
}

.composer {
  display: flex;
  align-items: flex-end;
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: 4px 4px 4px 10px;
  transition: border-color 120ms, box-shadow 120ms;
}
.composer:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
.composer textarea {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  color: var(--ink-0);
  font-size: 12.5px;
  font-family: inherit;
  line-height: 1.5;
  padding: 6px 0;
  min-height: 22px;
  max-height: 140px;
}
.composer textarea::placeholder { color: var(--ink-3); }
.composer textarea:disabled { opacity: 0.5; }

.send-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: var(--accent);
  color: var(--accent-fg);
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: 4px;
}
.send-btn:hover:not(:disabled) { background: var(--accent-hover); }
.send-btn:disabled { background: var(--bg-3); color: var(--ink-3); cursor: not-allowed; }

.composer-foot {
  display: flex;
  gap: 10px;
  margin-top: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--ink-3);
}
kbd {
  font-family: 'JetBrains Mono', monospace;
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  padding: 1px 5px;
  border-radius: 3px;
  color: var(--ink-2);
  font-size: 10px;
}
</style>
