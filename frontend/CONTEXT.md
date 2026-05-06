# Frontend Context

## Stack

| Layer | Technology |
|---|---|
| Framework | Vue 3 (Composition API, `<script setup>`) |
| UI library | Vuetify 3 |
| Build tool | Vite |
| Markdown | `marked` |

## Pages & routing

Vue Router (history mode). Routes:

| Route | Page component | Notes |
|---|---|---|
| `/chat` | `ChatPage.vue` | Default redirect from `/` |
| `/documents` | `DocumentsPage.vue` | |
| `/reports` | `ReportsPage.vue` | Paginated table |
| `/reports/:id` | `ReportDetailPage.vue` | Single run detail |

## Components

| File | Role |
|---|---|
| `App.vue` | Root layout — 48px topbar with brand, nav buttons, system pill; 24px statusbar; `<RouterView>` fills the main area |
| `ChatPage.vue` | 3-column CSS grid (`320px 1fr 320px`): left rail (QC controls + pipeline graph), center (chat), right rail (telemetry) |
| `ChatView.vue` | Chat thread — sends to `POST /chat/stream`, renders markdown via `marked`, auto-scroll during streaming, composer with auto-resize textarea, quick-prompt chips (toggled by lightbulb button) |
| `QcStartButton.vue` | FEMB Serial input + **QC Start** / **Inject Test** buttons. Both stream agent output into the shared message thread and disable while any run is active. |
| `GraphFlow.vue` | Left-rail wrapper showing pipeline node count; mounts `PipelineGraph.vue` |
| `PipelineGraph.vue` | Pure SVG pipeline graph (280×480 viewBox, 8 nodes, bezier edges). Node states (pending/active/completed) driven by `activeNode` + `completedNodes`. Active nodes show a pulsing ring animation; completed nodes show a checkmark. |
| `TelemetryRail.vue` | Right rail — three sections: Bench Telemetry (2×2 stat tiles with sparklines, mock rolling data), Recent Runs (last 3 from `GET /reports`, click to navigate), Retrieval Context (collapsible, shows chunks from last agent message) |
| `Sparkline.vue` | Generic SVG polyline sparkline — props: `data: number[]`, `color`, `height` |
| `UploadPanel.vue` | Document ingestion — `POST /documents/upload` with chunk size / overlap controls; lists uploaded docs from `GET /documents` |
| `ReportsView.vue` | Paginated plain `<table>` of QC runs — 20 rows per page, server-side pagination via `GET /reports?page&limit`. Status shown as colored glow dot. Run ID and FEMB Serial in JetBrains Mono. Row click navigates to `/reports/:id`. |
| `ReportDetailPage.vue` | Fetches `GET /reports/:id`, renders metadata card + markdown summary. Back button returns to list. |

## Shared state

`src/composables/useChat.js` exports module-level singletons so `ChatView` and `QcStartButton` share the same thread:

```js
const messages = ref([])        // Message[]
const streaming = ref(false)
const activeNode = ref(null)    // currently-executing pipeline node name
const completedNodes = ref(new Set())
```

**Message shape:**
```js
{ role: 'user' | 'agent', text: string, sources: string[], retrieval: Chunk[], ts: number }
// ts: Date.now() at send/receive time, used for the mono meta line in ChatView
```

## SSE consumer pattern

Both `ChatView` and `QcStartButton` use the same fetch → ReadableStream loop:

```js
const reader = resp.body.getReader()
const decoder = new TextDecoder()
let buffer = ''

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  buffer += decoder.decode(value, { stream: true })
  const parts = buffer.split('\n\n')
  buffer = parts.pop()                      // hold incomplete frame
  for (const part of parts) {
    const line = part.trim()
    if (!line.startsWith('data: ')) continue
    const data = line.slice(6)
    if (data === '[DONE]') break
    const evt = JSON.parse(data)
    // dispatch on evt.type: 'token' | 'sources' | 'retrieval' | 'tool_result' | 'node_active' | 'node_done' | 'loading'
  }
}
```

`QcStartButton` handles `token`, `node_active`, `node_done`. `ChatView` also handles `sources` and `retrieval`.

## API

Base URL is `''` (same origin). Vite proxies to `http://localhost:8000` in dev.

| Endpoint | Method | Used by |
|---|---|---|
| `/chat/stream` | POST `{message, history}` | `ChatView` |
| `/qc/start` | POST `?test=false` | `QcStartButton` (normal) |
| `/qc/start?test=true` | POST | `QcStartButton` (anomaly injection) |
| `/documents/upload` | POST (multipart) | `UploadPanel` |
| `/documents` | GET | `UploadPanel` |
| `/reports` | GET `?page=1&limit=20` | `ReportsView`, `TelemetryRail` |
| `/reports/:id` | GET | `ReportDetailPage` |
| `/settings` | GET | `ChatView` (composer subtitle: model, top-k RRF, top-k Rerank) |
