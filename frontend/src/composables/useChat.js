import { ref } from 'vue'

// Module-level singletons so ChatView and QcStartButton share the same state.
const messages = ref([])
const streaming = ref(false)
const activeNode = ref(null)
const completedNodes = ref(new Set())

export function useChat() {
  return { messages, streaming, activeNode, completedNodes }
}
