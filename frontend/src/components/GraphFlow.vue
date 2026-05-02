<template>
  <v-card class="mt-2">
    <v-card-text style="padding: 4px">
      <div :style="{ height: graphHeight + 'px' }">
        <VueFlow
          :nodes="flowNodes"
          :edges="flowEdges"
          :fit-view-on-init="true"
          :nodes-draggable="false"
          :nodes-connectable="false"
          :edges-updatable="false"
          :zoom-on-scroll="false"
          :pan-on-drag="false"
        >
          <template #node-default="{ data }">
            <div :class="['graph-node', data.state]">{{ data.label }}</div>
          </template>
        </VueFlow>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { computed } from 'vue'
import { VueFlow } from '@vue-flow/core'
import dagre from '@dagrejs/dagre'
import '@vue-flow/core/dist/style.css'
import { graphNodes, graphEdges } from '../composables/graphConfig.js'
import { useChat } from '../composables/useChat.js'

const { activeNode, completedNodes } = useChat()

const NODE_W = 240
const NODE_H = 40
const NODE_TOP_OFFSET = 0

function layoutNodes(nodes, edges) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 20, ranksep: 60 })
  nodes.forEach(n => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach(e => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return nodes.map(n => {
    const pos = g.node(n.id)
    return { ...n, position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 + NODE_TOP_OFFSET } }
  })
}

const layouted = layoutNodes(graphNodes, graphEdges)
const graphHeight = Math.max(...layouted.map(n => n.position.y + NODE_H)) + 40

const flowNodes = computed(() =>
  layouted.map(n => ({
    id: n.id,
    position: n.position,
    type: 'default',
    data: {
      label: n.label,
      state: completedNodes.value.has(n.id)
        ? 'completed'
        : n.id === activeNode.value
        ? 'active'
        : 'pending',
    },
  }))
)

const flowEdges = graphEdges.map(e => ({
  id: e.id,
  source: e.source,
  target: e.target,
  label: e.label,
  type: 'smoothstep',
}))
</script>

<style>
/* Strip vue-flow's hardcoded default node styles so .graph-node takes full control */
.vue-flow__node-default {
  width: auto !important;
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  font-size: inherit !important;
  box-shadow: none !important;
}

.graph-node {
  width: 240px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 22px;
  font-weight: 500;
  letter-spacing: 0.04em;
  border: 1px solid rgba(0,0,0,0.15);
  cursor: default;
  user-select: none;
}

/* Edge label text */
.vue-flow__edge-text { font-size: 23px !important; }
.vue-flow__edge-textbg { display: none; }
.graph-node.pending   { background: #9e9e9e; color: #fff; }
.graph-node.completed { background: #4caf50; color: #fff; }
.graph-node.active    { background: #ffc107; color: #333; animation: pulse 1s ease-in-out infinite; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.6; }
}
</style>
