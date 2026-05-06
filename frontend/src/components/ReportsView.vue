<template>
  <div class="reports-view">
    <div class="rv-header">
      <span class="rv-title">QC Reports</span>
      <button class="icon-btn" :class="{ spinning: loading }" @click="load" title="Refresh">
        <span class="mdi mdi-refresh"></span>
      </button>
    </div>

    <div v-if="totalPages > 1" class="rv-pagination">
      <button class="page-btn" :disabled="page <= 1" @click="page--; load()">‹</button>
      <span class="page-info">{{ page }} / {{ totalPages }}</span>
      <button class="page-btn" :disabled="page >= totalPages" @click="page++; load()">›</button>
    </div>

    <div class="rv-body">
      <div v-if="loading" class="rv-empty">Loading…</div>
      <div v-else-if="!items.length" class="rv-empty">No reports yet. Run a QC scan to generate one.</div>
      <table v-else class="rv-table">
        <thead>
          <tr>
            <th>Run ID</th>
            <th>Timestamp</th>
            <th>FEMB Serial</th>
            <th>Config</th>
            <th>Status</th>
            <th>Channels</th>
            <th>Anomalous</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in items" :key="r.id" @click="$router.push('/reports/' + r.id)">
            <td class="mono">#{{ r.id }}</td>
            <td>{{ formatTime(r.timestamp) }}</td>
            <td class="mono">{{ r.femb_serial }}</td>
            <td>{{ r.config_label }}</td>
            <td>
              <span class="status-dot" :class="r.passed ? 'dot-ok' : 'dot-err'"></span>
              <span class="status-text" :class="r.passed ? 'text-ok' : 'text-err'">{{ r.passed ? 'PASS' : 'FAIL' }}</span>
            </td>
            <td>{{ r.n_channels }}</td>
            <td>{{ r.n_anomalous }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
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

<style scoped>
.reports-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--bg-0);
}

.rv-header {
  display: flex;
  align-items: center;
  height: 48px;
  padding: 0 16px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}

.rv-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-0);
}

.icon-btn {
  margin-left: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  background: transparent;
  color: var(--ink-2);
  font-size: 18px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: background 120ms, color 120ms;
}
.icon-btn:hover { background: var(--bg-2); color: var(--ink-0); }
.icon-btn.spinning .mdi { display: inline-block; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.rv-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 40px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}

.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--line-2);
  background: var(--bg-1);
  border-radius: var(--r-sm);
  cursor: pointer;
  color: var(--ink-1);
  font-size: 15px;
  transition: background 120ms;
}
.page-btn:disabled { opacity: 0.4; cursor: default; }
.page-btn:not(:disabled):hover { background: var(--bg-2); }

.page-info {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-2);
}

.rv-body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.rv-empty {
  padding: 48px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--ink-3);
}

.rv-table {
  width: 100%;
  border-collapse: collapse;
}

.rv-table thead th {
  text-transform: uppercase;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--ink-2);
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
  background: var(--bg-1);
}

.rv-table tbody tr {
  cursor: pointer;
  transition: background 120ms;
  border-bottom: 1px solid var(--line);
}
.rv-table tbody tr:last-child { border-bottom: none; }
.rv-table tbody tr:hover { background: var(--bg-2); }

.rv-table tbody td {
  padding: 10px 12px;
  font-size: 12.5px;
  color: var(--ink-1);
}

.mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--ink-0);
}

.status-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.dot-ok  { background: var(--ok);  box-shadow: 0 0 5px var(--ok); }
.dot-err { background: var(--err); box-shadow: 0 0 5px var(--err); }

.status-text { font-size: 11px; font-weight: 600; vertical-align: middle; }
.text-ok  { color: var(--ok); }
.text-err { color: var(--err); }
</style>
