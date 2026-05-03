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
      <div v-else-if="!items.length" class="text-center text-medium-emphasis py-8">
        No reports yet. Run a QC scan to generate one.
      </div>
      <template v-else>
        <v-table hover>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Timestamp</th>
              <th>Status</th>
              <th>Channels</th>
              <th>Anomalous</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in items"
              :key="r.id"
              style="cursor: pointer"
              @click="$router.push('/reports/' + r.id)"
            >
              <td>#{{ r.id }}</td>
              <td>{{ formatTime(r.timestamp) }}</td>
              <td>
                <v-chip :color="r.passed ? 'success' : 'error'" size="small">
                  {{ r.passed ? 'PASS' : 'FAIL' }}
                </v-chip>
              </td>
              <td>{{ r.n_channels }}</td>
              <td>{{ r.n_anomalous }}</td>
            </tr>
          </tbody>
        </v-table>
        <div class="d-flex justify-center mt-4">
          <v-pagination
            v-model="page"
            :length="totalPages"
            :total-visible="7"
            @update:model-value="load"
          />
        </div>
      </template>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const LIMIT = 20

const totalPages = computed(() => Math.ceil(total.value / LIMIT))

async function load() {
  loading.value = true
  try {
    const res = await fetch(`/reports?page=${page.value}&limit=${LIMIT}`)
    const data = await res.json()
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function formatTime(iso) {
  return new Date(iso).toLocaleString()
}

onMounted(load)
</script>
