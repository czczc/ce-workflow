# Frontend Context

## Stack

| Layer | Technology |
|---|---|
| Framework | Vue 3 (Composition API, `<script setup>`) |
| UI library | Vuetify 3 |
| Build tool | Vite |
| Markdown | `marked` |

## Components

| File | Role |
|---|---|
| `App.vue` | Root layout — two-column (left: upload + QC button, right: chat) |
| `ChatView.vue` | Chat thread with RAG support — sends to `POST /chat/stream`, renders markdown, shows sources and retrieval debug panel |
| `QcStartButton.vue` | Triggers the QC workflow via `POST /qc/start`, streams agent output into the shared message thread |
| `UploadPanel.vue` | Document ingestion — `POST /documents/upload` with chunk size / overlap controls |

## Shared state

`src/composables/useChat.js` exports module-level singletons so `ChatView` and `QcStartButton` share the same thread:

```js
const messages = ref([])   // Message[]
const streaming = ref(false)
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
    // dispatch on evt.type: 'token' | 'sources' | 'retrieval' | 'tool_result' | 'loading'
  }
}
```

`QcStartButton` handles `token` only (agent narrative). `ChatView` also handles `sources` and `retrieval`.

## API

Base URL is `''` (same origin). Vite proxies to `http://localhost:8000` in dev via vite config (or the browser hits the FastAPI server directly if served together).

| Endpoint | Method | Used by |
|---|---|---|
| `/chat/stream` | POST `{message}` | `ChatView` |
| `/qc/start` | POST | `QcStartButton` |
| `/documents/upload` | POST (multipart) | `UploadPanel` |
| `/documents` | GET | `UploadPanel` |
