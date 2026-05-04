import { ref } from 'vue'

export function createChatSession() {
  return {
    messages: ref([]),
    streaming: ref(false),
    activeNode: ref(null),
    completedNodes: ref(new Set()),
  }
}

let _shared = null

export function useSharedSession() {
  if (!_shared) _shared = createChatSession()
  return _shared
}
