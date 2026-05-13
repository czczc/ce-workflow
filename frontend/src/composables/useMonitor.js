import { ref, computed } from 'vue'
import { readStream } from './useStream'

export function useMonitor() {
  const sessions = ref([])
  const selectedSessionId = ref('')
  const sessionMeta = ref(null)
  const eventsByFemb = ref({})  // femb_id -> { tests: { tN: 'pass'|'fail' }, final: bool }
  const streaming = ref(false)
  const error = ref('')
  let abortCtrl = null

  const fembs = computed(() => sessionMeta.value?.fembs ?? [])

  async function loadSessions() {
    try {
      const resp = await fetch('/monitor/sessions')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      sessions.value = await resp.json()
    } catch (e) {
      error.value = `Failed to load sessions: ${e.message}`
    }
  }

  function _resetSessionState() {
    sessionMeta.value = null
    eventsByFemb.value = {}
    error.value = ''
  }

  function _ensureFemb(femb_id) {
    if (!eventsByFemb.value[femb_id]) {
      eventsByFemb.value[femb_id] = { tests: {}, final: false }
    }
    return eventsByFemb.value[femb_id]
  }

  async function startWatching(sessionId) {
    stopWatching()
    if (!sessionId) return
    _resetSessionState()
    selectedSessionId.value = sessionId
    streaming.value = true
    abortCtrl = new AbortController()

    try {
      const resp = await fetch(`/monitor/sessions/${sessionId}/stream`, {
        signal: abortCtrl.signal,
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      await readStream(resp, {
        session_info: (evt) => {
          sessionMeta.value = evt
          // Pre-populate FEMB entries so empty columns render
          for (const f of evt.fembs || []) _ensureFemb(f.femb_id)
        },
        test_pass: (evt) => {
          _ensureFemb(evt.femb_id).tests[evt.test_id] = 'pass'
        },
        test_fail: (evt) => {
          _ensureFemb(evt.femb_id).tests[evt.test_id] = 'fail'
        },
        final_report: (evt) => {
          _ensureFemb(evt.femb_id).final = true
        },
        error: (evt) => {
          error.value = evt.message || 'stream error'
        },
      })
    } catch (e) {
      if (e.name !== 'AbortError') error.value = `Stream failed: ${e.message}`
    } finally {
      streaming.value = false
      abortCtrl = null
    }
  }

  function stopWatching() {
    if (abortCtrl) {
      abortCtrl.abort()
      abortCtrl = null
    }
    streaming.value = false
  }

  return {
    sessions,
    selectedSessionId,
    sessionMeta,
    fembs,
    eventsByFemb,
    streaming,
    error,
    loadSessions,
    startWatching,
    stopWatching,
  }
}
