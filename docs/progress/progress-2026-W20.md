# CE-Workflow: Weekly Progress Report
**Week of May 11 – May 17, 2026**

---

## Executive Summary

Shipped the **`/monitor` page** — a live, session-scoped FEMB QC dashboard that ingests real bench output (locally or over SSH+rsync), surfaces per-test pass/fail status in a streaming timeline, dispatches RAG-backed failure diagnostics, and exposes a session-scoped RAG chat assistant. This expands the platform from "synthetic QC pipeline + reports library" to **operator-facing monitoring of actual hardware runs**, end-to-end in a single week.

**10 issues closed. ~5,800 insertions across 74 files**, including 4 new backend modules (`monitor_session.py`, `monitor_sync.py`, `monitor_chat.py`, `monitor_db.py`, `ssh_helper.py`) and 4 new frontend components plus a dedicated `MonitorPage`.

---

## What Was Built

### Phase 1 — Live Session Plumbing (May 13): Mock DAQ + Timeline + Persistence

| Issue | Deliverable |
|-------|-------------|
| #58 | Mock DAQ generator CLI — emits realistic per-test `.md` reports + PNG assets into a session directory; supports `--random` and per-slot fail injection (`9b7f8f1`) |
| #59 | Live FEMB QC timeline — sessions list + filesystem watcher SSE + two-column UI; t1–t17 grid with status icons |
| #60 | RAG-backed failure diagnostic — auto-dispatched on the first failing test per FEMB run; streams a markdown diagnosis into the session record |
| #61 | Session persistence — `femb_sessions` / `femb_runs` schema in SQLite + LLM-written run summary on session completion |
| #62 | Replay finished sessions — re-open a completed session in the UI; per-test diagnostic regenerate/clear |

**Result:** A monitor that tails a live FEMB QC run on disk, classifies each test as it lands, and writes a durable session record once the run is idle.

---

### Phase 2 — Session-Scoped Chat & Remote Source (May 13–14): RAG + SSH

| Issue | Deliverable |
|-------|-------------|
| #63 | Session-scoped RAG chat — right-rail `/monitor` chat grounded in the open session's reports + global RAG corpus |
| #64 | Cascade month/run picker — collapsible by month, runs grouped, status icons (pass/fail/in-progress) |
| #65 | Remote SSH source — list sessions over SSH, one-shot rsync into local cache, connectivity chip |
| #66 | Live rsync loop — periodic pull with idle timeout + file-stability check; cached-run fast-path skips re-sync |
| #67 | Force-resync button — invalidates the cache for a single run and re-pulls from the remote |

**Result:** Operators can point `/monitor` at a remote DAQ host, watch tests stream in over rsync, and ask questions of the running session in plain English.

---

### Hardening & UX (interleaved)

- `7fe9cd1` — fixed a `final_report` race vs. the SSE summary stream; persistence is now crash-safe (atomic temp-file swap on the session JSON).
- `8f4641e` — test names rendered alongside `t1–t17` codes in the timeline (operator-readable).
- `3cb0965` — per-test report modal: renders the test's source `.md` with embedded PNG assets served from the session asset endpoint.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Browser (Vue 3 + Vuetify 3 + Vite)                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  MonitorPage.vue  (3-column: SessionPicker │ FembTimeline │ Chat)    │    │
│  │    ├── SessionPicker.vue   cascade month → run, status icons        │    │
│  │    ├── FembTimeline.vue    t1–t17 status grid, SSE-driven           │    │
│  │    ├── ReportModal.vue     per-test .md + embedded PNGs             │    │
│  │    └── MonitorChat.vue     session-scoped RAG chat (right rail)     │    │
│  └────────────────────────────────┬─────────────────────────────────────┘    │
└───────────────────────────────────┼──────────────────────────────────────────┘
                                    │  SSE / JSON   (/monitor/*)
┌───────────────────────────────────▼──────────────────────────────────────────┐
│  FastAPI backend                                                              │
│  ┌────────────────────┐  ┌────────────────────┐  ┌─────────────────────────┐ │
│  │ monitor_session.py │  │ monitor_sync.py    │  │ monitor_chat.py         │ │
│  │  watcher + SSE     │  │  rsync loop + idle │  │  session-scoped RAG     │ │
│  │  per-test classify │  │  cached-run fast-  │  │  (Qdrant + session ctx) │ │
│  │  final_report write│  │  path + force      │  │                         │ │
│  └─────────┬──────────┘  └─────────┬──────────┘  └─────────────┬───────────┘ │
│            │                       │                           │             │
│            ▼                       ▼                           ▼             │
│  ┌────────────────────┐  ┌────────────────────┐  ┌─────────────────────────┐ │
│  │ monitor_db.py      │  │ ssh_helper.py      │  │ diagnostic_agent.py     │ │
│  │ femb_sessions /    │  │ paramiko-backed    │  │ RAG-backed failure      │ │
│  │ femb_runs (SQLite) │  │ ls + rsync wrappers│  │ diagnosis (regen/clear) │ │
│  └────────────────────┘  └────────────────────┘  └─────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
        │                          │                          │
        ▼                          ▼                          ▼
   qc.db (SQLite)        Local cache: data/monitor/       Qdrant (RAG corpus)
                         ← rsync ←  remote DAQ host (SSH)
```

---

## Key Technical Decisions

### Filesystem as source of truth, DB as derived index

`monitor_session.py` watches the on-disk session directory and emits SSE events as test artifacts appear. The SQLite schema (`femb_sessions` / `femb_runs`, #61) is written only when a session goes idle.

- **Why it matters:** lets us handle remote sessions identically to local ones — rsync writes files, the watcher reacts. No coupling to the DAQ application.
- **Concrete benefit:** replay (#62) is "re-read the directory"; force-resync (#67) is "clear the cache row and re-rsync." Both are one-liners on top of the same primitive.

### Idle-timeout + file-stability check on the rsync loop

`monitor_sync.py` doesn't poll on a fixed interval — it pulls, checks whether file mtimes have stabilized for N seconds, then either sleeps or declares the run complete.

- **Why it matters:** avoids both the busy-poll case (DAQ still writing → never converge) and the premature-finalize case (one slow file → declared "done" too early).
- **Concrete benefit:** the cached-run fast-path (#66) drops directly out of this: a completed run skips the loop entirely.

### Crash-safe session persistence via atomic rename

`final_report` writes go through a temp-file + `os.replace` swap (fix in `7fe9cd1`) after a race surfaced between the in-flight LLM summary stream and the on-disk JSON.

- **Why it matters:** a partial summary write would have left the session looking "complete but empty" on reload.
- **Concrete benefit:** the watcher and the chat reader can hold open references to the session JSON without ever observing a torn write.

### Session-scoped RAG = global corpus + session-local context

`monitor_chat.py` injects the active session's per-test `.md` reports and the LLM-written run summary alongside Qdrant retrieval, so the chat can answer "why did t7 fail on this FEMB?" without the operator having to ingest the session into the global corpus.

- **Why it matters:** sessions are ephemeral; they shouldn't bloat the long-lived vector store.
- **Concrete benefit:** zero ingestion latency — the chat is usable the moment the first test report appears on disk.

### Mock DAQ generator co-developed with the consumer

`scripts/mock_daq.py` (#58) emits the same `.md` + PNG layout the real DAQ produces, with `--random` and per-slot fail injection (`9b7f8f1`).

- **Why it matters:** the entire `/monitor` UI was developed against the mock; the SSH path (#65) is the same code with a different filesystem under it.
- **Concrete benefit:** no bench access needed for development; failure-path testing is one CLI flag.

---

## Metrics

| Metric | Value |
|---|---|
| Issues closed | 10 (#58–#67) |
| Commits | 14 |
| Lines added / removed | 5,820 / 411 |
| New backend modules | 5 (`monitor_session`, `monitor_sync`, `monitor_chat`, `monitor_db`, `ssh_helper`) |
| New frontend components | 4 (`MonitorPage`, `FembTimeline`, `SessionPicker`, `MonitorChat`, `ReportModal`) |
| Backend Python files (total) | 27 |
| Frontend Vue files (total) | 19 |
| New `/monitor/*` HTTP endpoints | 9 |

---

## Current System Capabilities

1. Browse FEMB QC sessions on a local directory **or** a remote DAQ host over SSH, with a connectivity indicator.
2. Cascade month → run picker with pass/fail/in-progress icons; one-click force-resync per run.
3. Live-tail an in-progress session: per-FEMB t1–t17 grid updates as artifacts hit disk, via filesystem watcher → SSE.
4. Click any test cell to open the source markdown report with embedded PNGs.
5. On the first failing test of a FEMB run, auto-dispatch a RAG-backed diagnostic; regenerate or clear it per run.
6. Once a session goes idle, persist `femb_sessions` / `femb_runs` and an LLM-written run summary.
7. Re-open any completed session and replay its timeline; chat against it in a session-scoped RAG window.
8. Mock real DAQ output locally for development (`scripts/mock_daq.py --random` + per-slot fail injection).

---

## Open / Next

- Real-DAQ smoke test: the SSH+rsync path has only been exercised against the mock generator over loopback.
- No notification/escalation when a remote session goes idle with failures — the UI shows it, but nothing pages the operator.
- Session-scoped chat doesn't yet cite which test report a claim came from (it cites the global RAG corpus only).
- `monitor_session.py` is 1,450 lines and absorbing most of the orchestration logic; worth a structural pass before the next round of features.
- Diagnostic regenerate/clear is per-test, but there's no bulk "rerun diagnostics for this whole session" action.
