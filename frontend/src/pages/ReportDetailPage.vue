<template>
  <div style="padding: 8px">
    <v-btn
      variant="text"
      prepend-icon="mdi-arrow-left"
      class="mb-3"
      @click="$router.push('/reports')"
    >Back to Reports</v-btn>

    <div v-if="loading" class="d-flex justify-center py-8">
      <v-progress-circular indeterminate />
    </div>
    <div v-else-if="!report" class="text-center text-medium-emphasis py-8">
      Report not found.
    </div>
    <template v-else>
      <v-card class="mb-3">
        <v-card-title class="d-flex align-center gap-3">
          Run #{{ report.id }}
          <v-chip :color="report.passed ? 'success' : 'error'" size="small">
            {{ report.passed ? 'PASS' : 'FAIL' }}
          </v-chip>
        </v-card-title>
        <v-card-text>
          <v-row dense>
            <v-col cols="6" sm="3"><strong>Timestamp</strong><br>{{ formatTime(report.timestamp) }}</v-col>
            <v-col cols="6" sm="3"><strong>Channels</strong><br>{{ report.n_channels }}</v-col>
            <v-col cols="6" sm="3"><strong>Anomalous</strong><br>{{ report.n_anomalous }}</v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <v-card>
        <v-card-title>Report Summary</v-card-title>
        <v-divider />
        <v-card-text class="report-summary" v-html="render(report.summary)" />
      </v-card>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'

const route = useRoute()
const report = ref(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await fetch(`/reports/${route.params.id}`)
    if (res.ok) report.value = await res.json()
  } finally {
    loading.value = false
  }
}

function formatTime(iso) {
  return new Date(iso).toLocaleString()
}

function render(text) {
  return text ? marked.parse(text) : ''
}

onMounted(load)
</script>

<style scoped>
.report-summary :deep(p)  { margin: 0 0 4px; }
.report-summary :deep(ul) { padding-left: 1.4em; margin: 4px 0; }
.report-summary :deep(li) { margin-bottom: 2px; }
</style>
