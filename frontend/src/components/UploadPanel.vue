<template>
  <v-card class="mb-2">
    <v-card-title>Documents</v-card-title>
    <v-card-text>
      <v-file-input
        v-model="file"
        label="Choose file"
        variant="outlined"
        density="compact"
        hide-details
        class="mb-3"
      />
      <v-row dense class="mb-3">
        <v-col cols="6">
          <v-text-field
            v-model.number="chunkSize"
            label="Chunk size"
            type="number"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="6">
          <v-text-field
            v-model.number="overlap"
            label="Overlap"
            type="number"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>
      <v-btn color="primary" block :loading="uploading" :disabled="!hasFile" @click="upload">
        Upload
      </v-btn>
      <v-alert v-if="uploadMsg" :type="uploadErr ? 'error' : 'success'" class="mt-3" density="compact" closable @click:close="uploadMsg = ''">
        {{ uploadMsg }}
      </v-alert>
      <v-divider class="my-3" />
      <div class="text-subtitle-2 mb-2">Uploaded Documents</div>
      <v-progress-linear v-if="loadingDocs" indeterminate />
      <v-list v-else-if="docs.length" density="compact">
        <v-list-item
          v-for="doc in docs"
          :key="doc.id"
          :title="doc.filename || doc.id"
          :subtitle="doc.ingested_at"
        />
      </v-list>
      <div v-else class="text-grey text-caption">No documents uploaded yet.</div>
    </v-card-text>
  </v-card>
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

const hasFile = computed(() => {
  if (!file.value) return false
  return Array.isArray(file.value) ? file.value.length > 0 : true
})

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
  const f = Array.isArray(file.value) ? file.value[0] : file.value
  if (!f) return

  uploading.value = true
  uploadMsg.value = ''
  uploadErr.value = false

  const form = new FormData()
  form.append('file', f)
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
