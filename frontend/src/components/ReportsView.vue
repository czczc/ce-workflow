<template>
  <v-card style="height: 100%; display: flex; flex-direction: column; overflow: hidden">
    <v-card-title class="d-flex align-center">
      QC Reports
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" :loading="loading" @click="load" />
    </v-card-title>
    <v-divider />
    <v-card-text style="flex: 1; overflow-y: auto; min-height: 0">
      <div v-if="loading" class="d-flex justify-center py-8">
        <v-progress-circular indeterminate />
      </div>
      <div v-else-if="!reports.length" class="text-center text-medium-emphasis py-8">
        No reports yet. Run a QC scan to generate one.
      </div>
      <v-list v-else lines="two">
        <template v-for="(r, i) in reports" :key="r.id">
          <v-list-item style="cursor: pointer" @click="toggle(i)">
            <template #prepend>
              <v-chip :color="r.passed ? 'success' : 'error'" size="small" class="mr-3">
                {{ r.passed ? 'PASS' : 'FAIL' }}
              </v-chip>
            </template>
            <v-list-item-title>Run #{{ r.id }} — {{ formatTime(r.timestamp) }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ r.n_anomalous }} / {{ r.n_channels }} channels anomalous &nbsp;·&nbsp;
              <span class="text-mono">{{ runName(r.run_dir) }}</span>
            </v-list-item-subtitle>
            <template #append>
              <v-icon>{{ expanded === i ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
            </template>
          </v-list-item>
          <v-expand-transition>
            <div v-if="expanded === i" class="px-4 pb-3">
              <v-card variant="tonal" class="pa-3 report-summary">
                <div v-html="render(r.summary)" />
              </v-card>
            </div>
          </v-expand-transition>
          <v-divider v-if="i < reports.length - 1" />
        </template>
      </v-list>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { marked } from 'marked'

const reports = ref([])
const loading = ref(false)
const expanded = ref(null)

async function load() {
  loading.value = true
  try {
    const res = await fetch('/reports')
    reports.value = await res.json()
  } finally {
    loading.value = false
  }
}

function toggle(i) {
  expanded.value = expanded.value === i ? null : i
}

function formatTime(iso) {
  return new Date(iso).toLocaleString()
}

function runName(runDir) {
  return runDir.split('/').pop()
}

function render(text) {
  return text ? marked.parse(text) : ''
}

onMounted(load)
</script>

<style scoped>
.text-mono { font-family: monospace; font-size: 0.85em; }
.report-summary :deep(p)  { margin: 0 0 4px; }
.report-summary :deep(ul) { padding-left: 1.4em; margin: 4px 0; }
.report-summary :deep(li) { margin-bottom: 2px; }
</style>
