<template>
  <div class="upload-panel">
    <div class="panel-head">
      <span class="mdi mdi-file-upload-outline sect-icon"></span>
      <span>Documents</span>
    </div>

    <div class="panel-body">
      <div class="field-group">
        <label class="field-label">File</label>
        <label class="file-pick" :class="{ 'has-file': hasFile }">
          <input type="file" class="file-hidden" @change="onFile" />
          <span class="mdi mdi-paperclip file-icon"></span>
          <span class="file-name">{{ hasFile ? fileName : 'Choose file…' }}</span>
        </label>
      </div>

      <div class="field-row">
        <div class="field-group">
          <label class="field-label">Chunk size</label>
          <input class="plain-input" type="number" v-model.number="chunkSize" />
        </div>
        <div class="field-group">
          <label class="field-label">Overlap</label>
          <input class="plain-input" type="number" v-model.number="overlap" />
        </div>
      </div>

      <button class="upload-btn" :disabled="!hasFile || uploading" @click="upload">
        {{ uploading ? 'Uploading…' : 'Upload' }}
      </button>

      <div v-if="uploadMsg" class="alert" :class="uploadErr ? 'alert-err' : 'alert-ok'">
        {{ uploadMsg }}
        <button class="alert-close" @click="uploadMsg = ''">×</button>
      </div>

      <div class="divider"></div>

      <div class="docs-head">Uploaded Documents</div>
      <div v-if="loadingDocs" class="docs-state">Loading…</div>
      <div v-else-if="!docs.length" class="docs-state">No documents uploaded yet.</div>
      <div v-else class="docs-list">
        <div v-for="doc in docs" :key="doc.id" class="doc-row">
          <span class="doc-name">{{ doc.filename || doc.id }}</span>
          <span class="doc-time">{{ doc.ingested_at }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const API = ''

const file = ref(null)
const chunkSize = ref(500)
const overlap = ref(50)
const uploading = ref(false)
const uploadMsg = ref('')
const uploadErr = ref(false)
const docs = ref([])
const loadingDocs = ref(false)

const hasFile = computed(() => !!file.value)
const fileName = computed(() => file.value?.name ?? '')

function onFile(e) {
  file.value = e.target.files[0] ?? null
}

async function fetchDocs() {
  loadingDocs.value = true
  try {
    const resp = await fetch(`${API}/documents`)
    docs.value = await resp.json()
  } catch {
    // backend may be unavailable on first load
  } finally {
    loadingDocs.value = false
  }
}

async function upload() {
  if (!file.value) return

  uploading.value = true
  uploadMsg.value = ''
  uploadErr.value = false

  const form = new FormData()
  form.append('file', file.value)
  form.append('chunk_size', chunkSize.value)
  form.append('overlap', overlap.value)

  try {
    const resp = await fetch(`${API}/documents/upload`, { method: 'POST', body: form })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    uploadMsg.value = `Uploaded (id: ${data.doc_id})`
    file.value = null
    await fetchDocs()
  } catch (err) {
    uploadMsg.value = err.message
    uploadErr.value = true
  } finally {
    uploading.value = false
  }
}

onMounted(fetchDocs)
</script>

<style scoped>
.upload-panel {
  background: var(--bg-0);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 16px;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-2);
  background: var(--bg-1);
}

.sect-icon { font-size: 15px; }

.panel-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.field-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-2);
}

.file-pick {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: border-color 120ms, background 120ms;
}
.file-pick:hover { background: var(--bg-2); border-color: var(--ink-3); }
.file-pick.has-file { border-color: var(--accent); }

.file-hidden { display: none; }

.file-icon { font-size: 15px; color: var(--ink-2); flex-shrink: 0; }
.file-name  { font-size: 12.5px; color: var(--ink-1); }

.field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.plain-input {
  width: 100%;
  padding: 7px 10px;
  background: var(--bg-1);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  font-size: 13px;
  color: var(--ink-0);
  font-family: inherit;
  box-sizing: border-box;
  outline: none;
  transition: border-color 120ms, box-shadow 120ms;
}
.plain-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

.upload-btn {
  padding: 9px 0;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--r-md);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 120ms;
}
.upload-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.upload-btn:not(:disabled):hover { opacity: 0.88; }

.alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 12px;
  border-radius: var(--r-md);
  font-size: 12.5px;
}
.alert-ok  { background: rgba(31,157,88,0.12); color: var(--ok);  border: 1px solid rgba(31,157,88,0.25); }
.alert-err { background: rgba(220,53,69,0.12); color: var(--err); border: 1px solid rgba(220,53,69,0.25); }

.alert-close {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 16px;
  color: inherit;
  opacity: 0.6;
  flex-shrink: 0;
  line-height: 1;
}
.alert-close:hover { opacity: 1; }

.divider {
  height: 1px;
  background: var(--line);
}

.docs-head {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--ink-2);
}

.docs-state {
  font-size: 12.5px;
  color: var(--ink-3);
  padding: 8px 0;
}

.docs-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.doc-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 10px;
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}

.doc-name {
  font-size: 12.5px;
  color: var(--ink-0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.doc-time {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--ink-3);
  flex-shrink: 0;
}
</style>
