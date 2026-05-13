<template>
  <div class="msg-row" :class="role">
    <div class="avatar" :class="role">{{ avatarText }}</div>

    <div class="msg-body">
      <div class="msg-meta">
        <span>{{ roleLabel }}</span>
        <template v-if="ts">
          <span class="meta-sep">·</span>
          <span>{{ formattedTime }}</span>
        </template>
      </div>

      <div class="bubble" :class="role">
        <div v-if="thinking" class="thinking">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
          <span class="thinking-label">Thinking…</span>
        </div>
        <template v-else>
          <div v-if="role === 'agent'" v-html="rendered" class="md-body" />
          <div v-else class="plain-text">{{ text }}</div>
          <span v-if="streaming" class="cursor" />
        </template>

        <slot name="extra" />

        <div v-if="sources?.length" class="source-tags">
          <span v-for="s in sources" :key="s" class="source-tag">
            <span class="source-dot"></span>{{ s }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  role:      { type: String, required: true },   // 'user' | 'agent' | 'system'
  text:      { type: String, default: '' },
  sources:   { type: Array, default: () => [] },
  ts:        { type: Number, default: 0 },
  streaming: { type: Boolean, default: false },
  thinking:  { type: Boolean, default: false },
})

const avatarText = computed(() => {
  if (props.role === 'agent') return 'QC'
  if (props.role === 'system') return '◇'
  return 'Me'
})
const roleLabel = computed(() => {
  if (props.role === 'agent') return 'Agent'
  if (props.role === 'system') return 'System'
  return 'You'
})
const formattedTime = computed(() =>
  props.ts ? new Date(props.ts).toISOString().slice(11, 19) : ''
)
const rendered = computed(() => (props.text ? marked.parse(props.text) : ''))
</script>

<style scoped>
.msg-row        { display: flex; gap: 12px; margin-bottom: 18px; align-items: flex-start; }
.msg-row.user   { flex-direction: row-reverse; }

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
}
.avatar.agent  { background: linear-gradient(135deg, var(--accent) 0%, var(--brand-end) 100%); color: var(--accent-fg); border: none; }
.avatar.user   { background: var(--bg-2); color: var(--ink-1); }
.avatar.system { background: var(--bg-2); color: var(--ink-2); font-size: 11px; }

.msg-body { max-width: 80%; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.msg-row.user .msg-body { align-items: flex-end; }

.msg-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--ink-3);
}
.meta-sep { font-size: 7px; }

.bubble {
  padding: 10px 14px;
  border-radius: var(--r-lg);
  border: 1px solid var(--line);
  background: var(--bg-1);
  color: var(--ink-0);
  line-height: 1.55;
  word-break: break-word;
  font-size: 13px;
}
.bubble.agent  { border-top-left-radius: 3px; }
.bubble.user   { background: var(--user-bubble); border-color: rgba(14,149,168,0.25); border-top-right-radius: 3px; color: var(--bubble-user-fg); }
.bubble.system { background: transparent; border-style: dashed; border-color: var(--line-2); color: var(--ink-1); font-size: 12px; }

.plain-text { white-space: pre-wrap; }

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
.md-body :deep(hr)            { border: none; border-top: 1px solid var(--line); margin: 16px 0 4px; }
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
.thinking-label { font-size: 13px; color: var(--ink-2); margin-left: 4px; }
@keyframes bob {
  0%, 100% { transform: translateY(0);     opacity: 0.4; }
  40%      { transform: translateY(-3px); opacity: 1; }
}

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
</style>
