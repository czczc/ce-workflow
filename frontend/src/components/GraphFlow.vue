<template>
  <section class="pipeline-section">
    <div class="sect-head">
      <span class="mdi mdi-chip sect-icon"></span>
      <span>Pipeline</span>
      <span class="sect-count">{{ completedNodes.size }}/{{ nodes.length }}</span>
    </div>
    <div class="sect-body">
      <PipelineGraph />
    </div>
  </section>
</template>

<script setup>
import { useSharedSession } from '../composables/useChat.js'
import { graphNodes as nodes } from '../composables/graphConfig.js'
import PipelineGraph from './PipelineGraph.vue'

const { completedNodes } = useSharedSession()
</script>

<style scoped>
.sect-head {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 14px;
  border-bottom: 1px solid var(--line);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-2);
}

.sect-icon { font-size: 14px; }

.sect-count {
  margin-left: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
}

.sect-body { padding: 10px 14px; }
</style>
