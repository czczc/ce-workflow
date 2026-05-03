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
| `App.vue` | Root layout — top nav bar, `<RouterView>` fills the main area |
| `ChatView.vue` | Chat thread with RAG support — sends to `POST /chat/stream`, renders markdown, shows sources and retrieval debug panel |
| `QcStartButton.vue` | Two buttons: **QC Start** (normal waveforms, `POST /qc/start`) and **QC Start (Test)** (anomaly injection, `POST /qc/start?test=true`). Both stream agent output into the shared message thread. Both disable while any run is active; only the clicked button shows a spinner. |
| `UploadPanel.vue` | Document ingestion — `POST /documents/upload` with chunk size / overlap controls |
| `ReportsView.vue` | Paginated `v-table` of QC runs — 20 rows per page, server-side pagination via `GET /reports?page&limit`. Row click navigates to `/reports/:id`. |
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
{ role: 'user' | 'agent', text: string, sources: string[], retrieval: Chunk[] }
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
| `/chat/stream` | POST `{message}` | `ChatView` |
| `/qc/start` | POST `?test=false` | `QcStartButton` (normal) |
| `/qc/start?test=true` | POST | `QcStartButton` (anomaly injection) |
| `/documents/upload` | POST (multipart) | `UploadPanel` |
| `/documents` | GET | `UploadPanel` |
| `/reports` | GET `?page=1&limit=20` | `ReportsView` |
| `/reports/:id` | GET | `ReportDetailPage` |
