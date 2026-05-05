<template>
  <svg viewBox="0 0 280 480" preserveAspectRatio="xMidYMid meet" class="pipeline-svg">
    <defs>
      <marker id="arr-pending" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" class="arr-pending" />
      </marker>
      <marker id="arr-completed" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" class="arr-completed" />
      </marker>
      <marker id="arr-active" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" class="arr-active" />
      </marker>
    </defs>

    <!-- Edges (behind nodes) -->
    <g v-for="e in edges" :key="e.id">
      <path :d="e.d" class="edge" :class="edgeState(e)" fill="none" stroke-width="1.2"
            :marker-end="`url(#arr-${edgeState(e)})`" />
      <text v-if="e.label" :x="e.lx" :y="e.ly" class="edge-label">{{ e.label.toUpperCase() }}</text>
    </g>

    <!-- Nodes -->
    <g v-for="n in nodes" :key="n.id">
      <rect :x="n.cx - NW/2" :y="n.cy - NH/2" :width="NW" :height="NH" rx="6"
            class="node-box" :class="stateOf(n.id)" />
      <text :x="n.cx - NW/2 + 5" :y="n.cy - NH/2 + 10" class="node-step">{{ n.step }}</text>
      <text :x="n.cx" :y="n.cy + 4" text-anchor="middle" class="node-label" :class="stateOf(n.id)">
        {{ n.label }}
      </text>

      <!-- Active: filled dot + pulsing ring -->
      <template v-if="stateOf(n.id) === 'active'">
        <circle :cx="n.cx + NW/2 - 10" :cy="n.cy - NH/2 + 9" r="3" class="active-dot" />
        <circle :cx="n.cx + NW/2 - 10" :cy="n.cy - NH/2 + 9" r="4" class="active-ring" />
      </template>

      <!-- Completed: checkmark -->
      <path v-if="stateOf(n.id) === 'completed'"
        :d="`M ${n.cx+NW/2-16} ${n.cy-NH/2+10} L ${n.cx+NW/2-12} ${n.cy-NH/2+14} L ${n.cx+NW/2-5} ${n.cy-NH/2+6}`"
        class="check-mark" fill="none" stroke-linecap="round" stroke-linejoin="round" />
    </g>
  </svg>
</template>

<script setup>
import { useSharedSession } from '../composables/useChat.js'

const { activeNode, completedNodes } = useSharedSession()

const NW = 110, NH = 36

const nodes = [
  { id: 'check_hardware',   cx: 140, cy:  22, label: 'Hardware Check',  step: '01' },
  { id: 'monitor_respond',  cx: 140, cy:  78, label: 'Monitor',         step: '02' },
  { id: 'daq_acquire',      cx: 140, cy: 134, label: 'DAQ Acquire',     step: '03' },
  { id: 'qc_analyze',       cx: 140, cy: 190, label: 'QC Analysis',     step: '04' },
  { id: 'retrieve_context', cx:  60, cy: 254, label: 'Retrieve Context',step: '05' },
  { id: 'build_diagnosis',  cx:  60, cy: 310, label: 'Diagnosis',       step: '06' },
  { id: 'narrate',          cx:  60, cy: 366, label: 'Narrate',         step: '07' },
  { id: 'catalog_write',    cx: 140, cy: 430, label: 'Report',          step: '08' },
]

const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]))

function bezierPath(ax, ay, bx, by) {
  if (ax === bx) return `M ${ax} ${ay} L ${bx} ${by}`
  const midY = (ay + by) / 2
  return `M ${ax} ${ay} C ${ax} ${midY} ${bx} ${midY} ${bx} ${by}`
}

const edges = [
  { id: 'e1', source: 'check_hardware',   target: 'monitor_respond'  },
  { id: 'e2', source: 'monitor_respond',  target: 'daq_acquire',      label: 'OK',        lx: 155, ly: 106 },
  { id: 'e3', source: 'daq_acquire',      target: 'qc_analyze'        },
  { id: 'e4', source: 'qc_analyze',       target: 'retrieve_context', label: 'anomalies', lx: 105, ly: 219 },
  { id: 'e5', source: 'qc_analyze',       target: 'catalog_write',    label: 'pass',      lx: 207, ly: 310,
    d: 'M 140 208 C 220 208 220 412 140 412' },
  { id: 'e6', source: 'retrieve_context', target: 'build_diagnosis'   },
  { id: 'e7', source: 'build_diagnosis',  target: 'narrate'           },
  { id: 'e8', source: 'narrate',          target: 'catalog_write'     },
].map(e => ({
  ...e,
  d: e.d ?? bezierPath(
    nodeMap[e.source].cx, nodeMap[e.source].cy + NH / 2,
    nodeMap[e.target].cx, nodeMap[e.target].cy - NH / 2,
  ),
}))

function stateOf(id) {
  if (completedNodes.value.has(id)) return 'completed'
  if (id === activeNode.value) return 'active'
  return 'pending'
}

function edgeState(e) {
  const srcDone = completedNodes.value.has(e.source)
  const tgtDone = completedNodes.value.has(e.target)
  if (srcDone && tgtDone) return 'completed'
  if (srcDone && e.target === activeNode.value) return 'active'
  return 'pending'
}
</script>

<style scoped>
.pipeline-svg { width: 100%; display: block; }

/* Edges */
.edge.pending   { stroke: var(--line-2); }
.edge.completed { stroke: rgba(31,157,88,0.55); }
.edge.active    { stroke: var(--accent); }

.arr-pending   { fill: var(--line-2); }
.arr-completed { fill: rgba(31,157,88,0.55); }
.arr-active    { fill: var(--accent); }

.edge-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  fill: var(--ink-3);
  letter-spacing: 0.08em;
}

/* Node boxes */
.node-box { stroke-width: 1.2; }
.node-box.pending   { fill: var(--bg-2);              stroke: var(--line-2); }
.node-box.completed { fill: rgba(31,157,88,0.10);     stroke: rgba(31,157,88,0.55); }
.node-box.active    { fill: rgba(14,149,168,0.10);    stroke: var(--accent); }

.node-step {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  fill: var(--ink-3);
}

.node-label { font-family: 'Inter', sans-serif; font-size: 11.5px; font-weight: 500; }
.node-label.pending   { fill: var(--ink-1); }
.node-label.completed { fill: var(--ok); }
.node-label.active    { fill: var(--accent); }

/* Active decorations */
.active-dot { fill: var(--accent); }
.active-ring {
  fill: none;
  stroke: var(--accent);
  stroke-width: 1.5;
  transform-box: fill-box;
  transform-origin: center;
  animation: ring 1.4s ease-out infinite;
}

@keyframes ring {
  from { transform: scale(1); opacity: 0.9; }
  to   { transform: scale(3.5); opacity: 0; }
}

.check-mark { stroke: var(--ok); stroke-width: 1.6; }
</style>
