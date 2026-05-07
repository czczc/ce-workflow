<template>
  <div class="chat-view">

    <!-- Header -->
    <div class="chat-header">
      <div class="header-title-group">
        <span class="header-title">Agent Console</span>
      </div>
      <div class="header-actions">
        <button class="icon-btn" title="Export" disabled>
          <span class="mdi mdi-download-outline"></span>
        </button>
        <button class="icon-btn" :class="{ 'icon-btn-active': showChips }"
          title="Toggle suggestions" @click="showChips = !showChips">
          <span class="mdi mdi-lightbulb-outline"></span>
        </button>
        <button class="icon-btn" title="Clear"
          :disabled="streaming || !messages.length"
          @click="clearHistory">
          <span class="mdi mdi-delete-outline"></span>
        </button>
      </div>
    </div>

    <!-- Thread -->
    <div class="thread" ref="threadRef">
      <div v-for="(msg, i) in messages" :key="i" class="msg-row" :class="msg.role">
        <div class="avatar" :class="msg.role">{{ avatarText(msg.role) }}</div>

        <div class="msg-body">
          <div class="msg-meta">
            <span>{{ roleLabel(msg.role) }}</span>
            <span class="meta-sep">·</span>
            <span>{{ formatTime(msg.ts) }}</span>
          </div>

          <div class="bubble" :class="msg.role">
            <!-- Thinking indicator -->
            <div v-if="isThinking(i, msg)" class="thinking">
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="thinking-label">Thinking…</span>
            </div>

            <!-- Message text -->
            <template v-else>
              <div v-if="msg.role === 'agent'" v-html="render(msg.text)" class="md-body" />
              <div v-else>{{ msg.text }}</div>
              <span v-if="isStreaming(i, msg)" class="cursor" />
            </template>

            <!-- Findings card -->
            <div v-if="msg.findings"
              class="findings"
              :class="msg.findings.passed ? 'findings-pass' : 'findings-fail'">
              <div class="findings-title">
                <span class="mdi"
                  :class="msg.findings.passed ? 'mdi-check-circle-outline' : 'mdi-lightning-bolt'">
                </span>
                <span>{{ msg.findings.passed
                  ? 'All Channels Passed'
                  : `${msg.findings.items.length} Anomalies Detected` }}</span>
              </div>
              <div v-for="(item, j) in msg.findings.items" :key="j" class="findings-row">
                <span class="findings-ch">{{ item.channel }}</span>
                <span class="findings-desc">{{ item.description }}</span>
                <span class="severity-badge" :class="`sev-${item.severity}`">{{ item.severity }}</span>
              </div>
            </div>

            <!-- Source tags -->
            <div v-if="msg.sources?.length" class="source-tags">
              <span v-for="s in msg.sources" :key="s" class="source-tag">
                <span class="source-dot"></span>{{ s }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Quick chips -->
    <div v-if="showChips && !streaming" class="quick-chips">
      <button v-for="chip in CHIPS" :key="chip" class="chip" @click="input = chip">
        {{ chip }}
      </button>
    </div>

    <!-- Composer -->
    <div class="composer-wrap">
      <div class="composer">
        <textarea
          ref="textareaRef"
          v-model="input"
          placeholder="Ask a question…"
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
        <span class="foot-spacer"></span>
        <div class="subtitle-wrap" ref="settingsWrapRef">
          <button class="foot-subtitle" :class="{ 'subtitle-active': showSettings }" @click="showSettings = !showSettings">
            {{ subtitle }}
          </button>
          <div v-if="showSettings" class="settings-popover">
            <div class="sp-row">
              <label class="sp-label">Model</label>
              <select class="sp-select" v-model="params.model">
                <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
              </select>
            </div>
            <div class="sp-row">
              <label class="sp-label">Retrieval top-k</label>
              <input class="sp-input" type="number" min="1" max="50" v-model.number="params.retrieval_top_k" />
            </div>
            <div class="sp-row">
              <label class="sp-label">Generation top-k</label>
              <input class="sp-input" type="number" min="1" max="20" v-model.number="params.generation_top_k" />
            </div>
            <div class="sp-row">
              <label class="sp-label">Reranker</label>
              <button class="sp-toggle" :class="{ 'sp-toggle-on': params.reranker_enabled }" @click="params.reranker_enabled = !params.reranker_enabled">
                {{ params.reranker_enabled ? 'on' : 'off' }}
              </button>
            </div>
            <div class="sp-row">
              <label class="sp-label">Think mode</label>
              <button class="sp-toggle" :class="{ 'sp-toggle-on': params.think }" @click="params.think = !params.think">
                {{ params.think ? 'on' : 'off' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { marked } from 'marked'
import { useSharedSession } from '../composables/useChat.js'
import { readStream } from '../composables/useStream.js'

const API = ''
const { messages, streaming } = useSharedSession()
const input = ref('')
const threadRef = ref(null)
const textareaRef = ref(null)
const showChips = ref(false)
const showSettings = ref(false)
const settingsWrapRef = ref(null)

const inputHistory = ref([])
const historyIndex = ref(-1)
const inputDraft = ref('')

const params = reactive({
  model: '',
  retrieval_top_k: 10,
  generation_top_k: 3,
  reranker_enabled: false,
  think: false,
})
const availableModels = ref([])

const subtitle = computed(() =>
  params.model
    ? `RAG · ${params.model} · top-${params.retrieval_top_k} RRF · top-${params.generation_top_k} Rerank`
    : 'RAG · … · … · …'
)

function onDocClick(e) {
  if (showSettings.value && settingsWrapRef.value && !settingsWrapRef.value.contains(e.target)) {
    showSettings.value = false
  }
}

onMounted(async () => {
  document.addEventListener('click', onDocClick)
  try {
    const [cfg, models] = await Promise.all([
      fetch('/settings').then(r => r.json()),
      fetch('/models').then(r => r.json()),
    ])
    params.model = cfg.reasoning_model
    params.retrieval_top_k = cfg.retrieval_top_k
    params.generation_top_k = cfg.generation_top_k
    params.reranker_enabled = cfg.reranker_enabled
    params.think = cfg.think ?? false
    availableModels.value = models
  } catch { /* backend offline */ }
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
})

const CHIPS = [
  'What is LArASIC?',
  'List the most recently tested FEMBs from the database',
  'What should I do if a channel shows high noise?',
]

watch(() => messages.value.length, scrollToBottom)
watch(() => messages.value.at(-1)?.text, () => { if (streaming.value) scrollToBottom() })

function avatarText(role) {
  if (role === 'agent') return 'QC'
  if (role === 'system') return '◇'
  return 'Me'
}

function roleLabel(role) {
  if (role === 'agent') return 'Agent'
  if (role === 'system') return 'System'
  return 'You'
}

function formatTime(ts) {
  if (!ts) return ''
  return new Date(ts).toISOString().slice(11, 19)
}

function isThinking(i, msg) {
  return streaming.value
    && i === messages.value.length - 1
    && msg.role === 'agent'
    && !msg.text
}

function isStreaming(i, msg) {
  return streaming.value
    && i === messages.value.length - 1
    && msg.role === 'agent'
    && !!msg.text
}

function render(text) {
  return text ? marked.parse(text) : ''
}

function scrollToBottom() {
  nextTick(() => {
    requestAnimationFrame(() => {
      const el = threadRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  })
}

function clearHistory() {
  messages.value = []
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
    return
  }
  const el = textareaRef.value
  if (!el) return
  if (e.key === 'ArrowUp' && el.selectionStart === 0 && inputHistory.value.length > 0) {
    e.preventDefault()
    if (historyIndex.value === -1) {
      inputDraft.value = input.value
      historyIndex.value = inputHistory.value.length - 1
    } else if (historyIndex.value > 0) {
      historyIndex.value--
    }
    input.value = inputHistory.value[historyIndex.value]
    nextTick(() => autoResize())
  } else if (e.key === 'ArrowDown' && historyIndex.value !== -1) {
    e.preventDefault()
    if (historyIndex.value < inputHistory.value.length - 1) {
      historyIndex.value++
      input.value = inputHistory.value[historyIndex.value]
    } else {
      historyIndex.value = -1
      input.value = inputDraft.value
    }
    nextTick(() => autoResize())
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return

  inputHistory.value.push(text)
  historyIndex.value = -1
  inputDraft.value = ''
  input.value = ''
  nextTick(() => {
    if (textareaRef.value) textareaRef.value.style.height = 'auto'
  })

  const history = messages.value.slice(-6).map((m) => ({
    role: m.role === 'user' ? 'user' : 'assistant',
    content: m.text,
  }))
  messages.value.push({ role: 'user', text, ts: Date.now() })
  scrollToBottom()

  streaming.value = true
  messages.value.push({ role: 'agent', text: '', sources: [], retrieval: [], ts: Date.now() })
  const idx = messages.value.length - 1

  try {
    const resp = await fetch(`${API}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history, ...params }),
    })
    await readStream(resp, {
      token:     (evt) => { messages.value[idx].text += evt.text; scrollToBottom() },
      sources:   (evt) => { messages.value[idx].sources = evt.sources },
      retrieval: (evt) => { messages.value[idx].retrieval = evt.chunks },
    })
  } catch (err) {
    messages.value[idx].text = `Error: ${err.message}`
  } finally {
    streaming.value = false
    scrollToBottom()
  }
}
</script>

<style scoped>
/* ── Layout ── */
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink-0);
  font-family: 'Inter', sans-serif;
}

/* ── Header ── */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 18px;
  background: var(--bg-1);
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}

.header-title-group { display: flex; align-items: center; }
.header-title       { font-size: 13px; font-weight: 600; color: var(--ink-0); }

.header-actions { display: flex; gap: 4px; }

.icon-btn {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border: none;
  background: transparent;
  color: var(--ink-2);
  font-size: 16px;
  border-radius: var(--r-md);
  cursor: pointer;
  transition: background 120ms;
}
.icon-btn:hover:not(:disabled) { background: var(--bg-2); color: var(--ink-0); }
.icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.icon-btn-active { color: var(--accent) !important; background: var(--accent-dim); }

/* ── Thread ── */
.thread {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 22px 10% 18px;
  background:
    radial-gradient(ellipse 800px 400px at 30% 0%, rgba(14,149,168,0.05), transparent 60%),
    var(--bg-0);
  scroll-behavior: smooth;
}

/* ── Message row ── */
.msg-row        { display: flex; gap: 12px; margin-bottom: 18px; align-items: flex-start; }
.msg-row.user   { flex-direction: row-reverse; }

/* ── Avatar ── */
.avatar {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: 1px solid var(--line-2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 700;
  flex-shrink: 0;
  letter-spacing: 0;
}
.avatar.agent  { background: linear-gradient(135deg, var(--accent) 0%, var(--brand-end) 100%); color: var(--accent-fg); border: none; }
.avatar.user   { background: var(--bg-2); color: var(--ink-1); }
.avatar.system { background: var(--bg-2); color: var(--ink-2); font-size: 11px; }

/* ── Message body ── */
.msg-body { max-width: 78%; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.msg-row.user .msg-body { align-items: flex-end; }

/* ── Meta line ── */
.msg-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--ink-3);
}
.meta-sep { font-size: 7px; }

/* ── Bubble ── */
.bubble {
  padding: 10px 14px;
  border-radius: var(--r-lg);
  border: 1px solid var(--line);
  background: var(--bg-1);
  color: var(--ink-0);
  line-height: 1.55;
  word-break: break-word;
}
.bubble.agent  { border-top-left-radius: 3px; }
.bubble.user   { background: var(--user-bubble); border-color: rgba(14,149,168,0.25); border-top-right-radius: 3px; color: var(--bubble-user-fg); }
.bubble.system { background: transparent; border-style: dashed; border-color: var(--line-2); color: var(--ink-1); font-size: 12px; }

/* ── Markdown overrides ── */
.md-body :deep(h3) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
  background: var(--accent-dim);
  border-left: 3px solid var(--accent);
  padding: 5px 10px;
  margin: 4px 0 10px;
  border-radius: 0 4px 4px 0;
}
.md-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--line);
  margin: 16px 0 4px;
}
.md-body :deep(strong)        { color: var(--strong-color); font-weight: 600; }
.md-body :deep(code)          { font-family: 'JetBrains Mono', monospace; font-size: 0.88em; background: rgba(14,149,168,0.1); color: var(--code-text); padding: 1px 5px; border-radius: 3px; }
.md-body :deep(table)         { border-collapse: collapse; font-size: 12px; width: 100%; margin: 6px 0; }
.md-body :deep(th)            { font-size: 11px; text-transform: uppercase; color: var(--ink-2); padding: 5px 10px; border-bottom: 1px solid var(--line); text-align: left; }
.md-body :deep(td)            { color: var(--ink-1); padding: 5px 10px; border-bottom: 1px solid var(--line); }
.md-body :deep(td:first-child){ font-family: 'JetBrains Mono', monospace; color: var(--ink-0); }
.md-body :deep(ul),
.md-body :deep(ol)            { padding-left: 20px; margin: 4px 0; }
.md-body :deep(li)            { margin-bottom: 4px; }
.md-body :deep(p)             { margin: 0 0 8px; }
.md-body :deep(p:last-child)  { margin: 0; }

/* ── Thinking indicator ── */
.thinking { display: flex; align-items: center; gap: 4px; }

.dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--accent);
  animation: bob 1.2s ease-in-out infinite;
}
.dot:nth-child(2) { animation-delay: 0.15s; }
.dot:nth-child(3) { animation-delay: 0.30s; }
.thinking-label   { font-size: 13px; color: var(--ink-2); margin-left: 4px; }

@keyframes bob {
  0%, 100% { transform: translateY(0);     opacity: 0.4; }
  40%       { transform: translateY(-3px); opacity: 1;   }
}

/* ── Typing cursor ── */
.cursor {
  display: inline-block;
  width: 6px;
  height: 13px;
  background: var(--accent);
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink 1s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }

/* ── Findings card ── */
.findings      { margin-top: 10px; padding: 10px 12px; border-radius: var(--r-md); }
.findings-fail { background: rgba(216,58,58,0.06); border: 1px solid rgba(216,58,58,0.25); border-left: 3px solid var(--err); }
.findings-pass { background: rgba(31,157,88,0.06);  border: 1px solid rgba(31,157,88,0.25);  border-left: 3px solid var(--ok); }

.findings-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.findings-fail .findings-title { color: var(--err); }
.findings-pass .findings-title { color: var(--ok); }

.findings-row {
  display: grid;
  grid-template-columns: 70px 1fr auto;
  gap: 8px;
  padding: 4px 0;
  border-top: 1px solid var(--line);
  align-items: center;
}
.findings-ch   { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--ink-1); }
.findings-desc { font-size: 11px; color: var(--ink-1); }

.severity-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.sev-high { background: rgba(216,58,58,0.14);  color: #b22f2f; }
.sev-med  { background: rgba(201,122,20,0.16); color: #8e560e; }
.sev-low  { background: rgba(47,111,218,0.14); color: #2856a8; }

/* ── Source tags ── */
.source-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }

.source-tag {
  display: flex;
  align-items: center;
  gap: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  color: var(--ink-1);
  padding: 2px 8px;
  border-radius: 4px;
}
.source-dot { width: 4px; height: 4px; border-radius: 50%; background: var(--info); flex-shrink: 0; }

/* ── Quick chips ── */
.quick-chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 10% 10px; background: var(--bg-0); }

.chip {
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--line-2);
  background: var(--bg-1);
  color: var(--ink-1);
  font-size: 11.5px;
  font-family: inherit;
  cursor: pointer;
  transition: background 120ms, color 120ms;
}
.chip:hover { background: var(--bg-2); color: var(--ink-0); }

/* ── Composer ── */
.composer-wrap {
  border-top: 1px solid var(--line);
  background: var(--bg-0);
  padding: 12px 10% 14px;
  flex-shrink: 0;
}

.composer {
  display: flex;
  align-items: flex-end;
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  border-radius: 10px;
  padding: 6px 6px 6px 12px;
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
  font-size: 13px;
  font-family: inherit;
  line-height: 1.5;
  padding: 7px 0;
  min-height: 24px;
  max-height: 140px;
}
.composer textarea::placeholder { color: var(--ink-3); }
.composer textarea:disabled { opacity: 0.5; cursor: not-allowed; }

.send-btn {
  width: 32px;
  height: 32px;
  border-radius: 7px;
  border: none;
  background: var(--accent);
  color: var(--accent-fg);
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 120ms;
  margin-left: 6px;
}
.send-btn:hover:not(:disabled) { background: var(--accent-hover); }
.send-btn:disabled { background: var(--bg-3); color: var(--ink-3); cursor: not-allowed; }

.composer-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--ink-3);
}
.foot-spacer { flex: 1; }
.foot-subtitle { color: var(--ink-3); font-family: 'JetBrains Mono', monospace; font-size: 10.5px; }

kbd {
  font-family: 'JetBrains Mono', monospace;
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  padding: 1px 5px;
  border-radius: 3px;
  color: var(--ink-2);
  font-size: 10.5px;
}

/* ── Settings popover ── */
.subtitle-wrap { position: relative; }

.foot-subtitle {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  color: var(--ink-3);
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  transition: color 120ms;
}
.foot-subtitle:hover,
.subtitle-active { color: var(--ink-1); }

.settings-popover {
  position: absolute;
  bottom: calc(100% + 8px);
  right: 0;
  width: 260px;
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  padding: 12px 14px;
  z-index: 100;
  box-shadow: 0 4px 20px rgba(0,0,0,0.2);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sp-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.sp-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--ink-2);
  white-space: nowrap;
}

.sp-select,
.sp-input {
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  color: var(--ink-0);
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  padding: 3px 6px;
  outline: none;
  min-width: 0;
}
.sp-select { flex: 1; }
.sp-input  { width: 52px; text-align: right; }
.sp-select:focus,
.sp-input:focus { border-color: var(--accent); }

.sp-toggle {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  padding: 2px 10px;
  border-radius: var(--r-md);
  border: 1px solid var(--line-2);
  background: var(--bg-2);
  color: var(--ink-2);
  cursor: pointer;
  transition: background 120ms, color 120ms, border-color 120ms;
  min-width: 36px;
  text-align: center;
}
.sp-toggle-on {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}
</style>
