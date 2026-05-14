import { ref, computed } from 'vue'
import { readStream } from './useStream'

export function useMonitor() {
  // Tree of months: { months: [{ name, runs: [...] }, ...] }, newest-first.
  const sessionsTree = ref({ months: [] })
  const sessionsLoading = ref(false)
  // Connectivity state for the remote-host chip: { configured, ok?, host?,
  // error?, stalled? }. Listing calls overwrite the whole object; sync_status
  // events merge into it. `stalled` flips the chip red and triggers the
  // session-level "sync stalled" badge.
  const remoteStatus = ref({ configured: false })
  // Per-session one-shot rsync progress flag (true between sync_start and sync_done)
  const syncing = ref(false)
  const syncStalled = ref(false)
  const selectedSessionId = ref('')
  const sessionMeta = ref(null)
  const testLabels = ref({})    // { "t1": "pwr_consumption", ... }
  const eventsByFemb = ref({})  // femb_id -> { tests, final, diagnostics, summary }
  const sessionComplete = ref(null) // { finished_at, overall_passed } | null
  const streaming = ref(false)
  const error = ref('')
  let abortCtrl = null

  const fembs = computed(() => sessionMeta.value?.fembs ?? [])

  async function loadSessions(month = null) {
    sessionsLoading.value = true
    try {
      const url = month
        ? `/monitor/sessions?month=${encodeURIComponent(month)}`
        : '/monitor/sessions'
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      if (data.remote) remoteStatus.value = data.remote
      if (month) {
        // Merge: replace this month's runs in place, or insert newest-first.
        const months = sessionsTree.value.months.slice()
        const idx = months.findIndex((m) => m.name === data.name)
        if (idx >= 0) months[idx] = { name: data.name, runs: data.runs }
        else {
          months.push({ name: data.name, runs: data.runs })
          months.sort((a, b) => (a.name < b.name ? 1 : -1))
        }
        sessionsTree.value = { months }
      } else {
        sessionsTree.value = { months: data.months || [] }
      }
    } catch (e) {
      error.value = `Failed to load sessions: ${e.message}`
    } finally {
      sessionsLoading.value = false
    }
  }

  function _resetSessionState() {
    sessionMeta.value = null
    testLabels.value = {}
    eventsByFemb.value = {}
    sessionComplete.value = null
    syncing.value = false
    syncStalled.value = false
    error.value = ''
  }

  function _ensureFemb(femb_id) {
    if (!eventsByFemb.value[femb_id]) {
      eventsByFemb.value[femb_id] = {
        tests: {},
        final: false,
        diagnostics: {},
        summary: null,   // { summary_md, n_tests, n_failed, passed, from_cache }
      }
    }
    return eventsByFemb.value[femb_id]
  }

  function _ensureDiag(femb_id, test_id) {
    const f = _ensureFemb(femb_id)
    if (!f.diagnostics[test_id]) {
      f.diagnostics[test_id] = {
        status: 'pending',
        sources: [],
        chunks: [],
        text: '',
        error: '',
        cached: false,
      }
    }
    return f.diagnostics[test_id]
  }

  async function startWatching(sessionId, { force = false } = {}) {
    stopWatching()
    if (!sessionId) return
    _resetSessionState()
    selectedSessionId.value = sessionId
    streaming.value = true
    abortCtrl = new AbortController()

    try {
      const url = force
        ? `/monitor/sessions/${sessionId}/stream?force=1`
        : `/monitor/sessions/${sessionId}/stream`
      const resp = await fetch(url, {
        signal: abortCtrl.signal,
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      await readStream(resp, {
        sync_start: () => { syncing.value = true },
        sync_done: () => { syncing.value = false },
        sync_status: (evt) => {
          remoteStatus.value = {
            ...remoteStatus.value,
            ok: !!evt.ok,
            stalled: !!evt.stalled,
            error: evt.error || '',
          }
          syncStalled.value = !!evt.stalled
        },
        sync_loop_done: () => {
          // Loop ended (finalized / idle timeout / one-shot). Drop the
          // stalled badge; the connectivity chip stays at its last state
          // until the next listing call.
          syncStalled.value = false
        },
        session_info: (evt) => {
          syncing.value = false
          sessionMeta.value = evt
          testLabels.value = evt.test_labels || {}
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
        diagnostic_start: (evt) => {
          const d = _ensureDiag(evt.femb_id, evt.test_id)
          d.status = 'streaming'
          d.cached = !!evt.cached
        },
        diagnostic_sources: (evt) => {
          _ensureDiag(evt.femb_id, evt.test_id).sources = evt.sources || []
        },
        diagnostic_retrieval: (evt) => {
          _ensureDiag(evt.femb_id, evt.test_id).chunks = evt.chunks || []
        },
        diagnostic_token: (evt) => {
          _ensureDiag(evt.femb_id, evt.test_id).text += evt.text
        },
        diagnostic_done: (evt) => {
          const d = _ensureDiag(evt.femb_id, evt.test_id)
          if (d.status !== 'error') d.status = 'done'
        },
        diagnostic_error: (evt) => {
          const d = _ensureDiag(evt.femb_id, evt.test_id)
          d.status = 'error'
          d.error = evt.message || 'diagnostic failed'
        },
        femb_summary_start: (evt) => {
          _ensureFemb(evt.femb_id).summary = {
            summary_md: '',
            n_tests: evt.n_tests ?? 0,
            n_failed: evt.n_failed ?? 0,
            passed: !!evt.passed,
            from_cache: false,
            femb_run_id: null,
            streaming: true,
          }
        },
        femb_summary_token: (evt) => {
          const s = _ensureFemb(evt.femb_id).summary
          if (s) s.summary_md += evt.text
        },
        femb_summary: (evt) => {
          const f = _ensureFemb(evt.femb_id)
          f.summary = {
            summary_md: evt.summary_md || f.summary?.summary_md || '',
            n_tests: evt.n_tests ?? 0,
            n_failed: evt.n_failed ?? 0,
            passed: !!evt.passed,
            from_cache: !!evt.from_cache,
            femb_run_id: evt.femb_run_id ?? null,
            streaming: false,
          }
        },
        session_complete: (evt) => {
          sessionComplete.value = {
            finished_at: evt.finished_at,
            overall_passed: !!evt.overall_passed,
          }
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

  function _resetDiagForRegen(femb_id, test_ids) {
    const f = _ensureFemb(femb_id)
    for (const tid of test_ids) {
      f.diagnostics[tid] = {
        status: 'streaming',
        sources: [],
        chunks: [],
        text: '',
        error: '',
        cached: false,
      }
    }
  }

  async function regenerateDiagnostic(fembRunId, fembId, testId = null) {
    const fembState = _ensureFemb(fembId)
    // Mark targeted card(s) as streaming
    const targets = testId ? [testId] : Object.keys(fembState.diagnostics)
    _resetDiagForRegen(fembId, targets)

    const url = testId
      ? `/monitor/femb-runs/${fembRunId}/diagnostic/regenerate?test_id=${encodeURIComponent(testId)}`
      : `/monitor/femb-runs/${fembRunId}/diagnostic/regenerate`
    try {
      const resp = await fetch(url, { method: 'POST' })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      await readStream(resp, {
        regenerate_start: () => {},
        diagnostic_start: (evt) => {
          const d = _ensureDiag(evt.femb_id, evt.test_id)
          d.status = 'streaming'
          d.text = ''
          d.cached = false
        },
        diagnostic_sources: (evt) => {
          _ensureDiag(evt.femb_id, evt.test_id).sources = evt.sources || []
        },
        diagnostic_retrieval: (evt) => {
          _ensureDiag(evt.femb_id, evt.test_id).chunks = evt.chunks || []
        },
        diagnostic_token: (evt) => {
          _ensureDiag(evt.femb_id, evt.test_id).text += evt.text
        },
        diagnostic_done: (evt) => {
          const d = _ensureDiag(evt.femb_id, evt.test_id)
          if (d.status !== 'error') d.status = 'done'
        },
        diagnostic_error: (evt) => {
          const d = _ensureDiag(evt.femb_id, evt.test_id)
          d.status = 'error'
          d.error = evt.message || 'diagnostic failed'
        },
        regenerate_complete: () => {},
        error: (evt) => {
          error.value = evt.message || 'regenerate failed'
        },
      })
    } catch (e) {
      error.value = `Regenerate failed: ${e.message}`
    }
  }

  async function loadTestReport(fembId, testId) {
    if (!selectedSessionId.value || !fembId || !testId) return null
    const url = `/monitor/sessions/${selectedSessionId.value}/femb/${encodeURIComponent(fembId)}/report/${encodeURIComponent(testId)}`
    try {
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      return await resp.json()
    } catch (e) {
      error.value = `Failed to load report: ${e.message}`
      return null
    }
  }

  async function clearDiagnostic(fembRunId, fembId, testId = null) {
    const url = testId
      ? `/monitor/femb-runs/${fembRunId}/diagnostic?test_id=${encodeURIComponent(testId)}`
      : `/monitor/femb-runs/${fembRunId}/diagnostic`
    try {
      const resp = await fetch(url, { method: 'DELETE' })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const fembState = _ensureFemb(fembId)
      if (testId) {
        delete fembState.diagnostics[testId]
      } else {
        fembState.diagnostics = {}
      }
    } catch (e) {
      error.value = `Clear failed: ${e.message}`
    }
  }

  return {
    sessionsTree,
    sessionsLoading,
    remoteStatus,
    syncing,
    syncStalled,
    selectedSessionId,
    sessionMeta,
    testLabels,
    fembs,
    eventsByFemb,
    sessionComplete,
    streaming,
    error,
    loadSessions,
    startWatching,
    stopWatching,
    regenerateDiagnostic,
    clearDiagnostic,
    loadTestReport,
  }
}
