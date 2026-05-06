<template>
  <div class="console-grid">
    <div class="rail rail-left">
      <QcStartButton />
      <GraphFlow />
    </div>
    <div class="console-center">
      <ChatView />
    </div>
    <div class="rail rail-right">
      <TelemetryRail />
    </div>
  </div>
</template>

<script setup>
import ChatView from '../components/ChatView.vue'
import QcStartButton from '../components/QcStartButton.vue'
import GraphFlow from '../components/GraphFlow.vue'
import TelemetryRail from '../components/TelemetryRail.vue'
</script>

<style scoped>
.console-grid {
  display: grid;
  grid-template-columns: 320px 1fr 320px;
  height: 100%;
}

.rail-left  { border-right: 1px solid var(--line); overflow-y: auto; }
.rail-right { border-left:  1px solid var(--line); overflow: hidden; }
.console-center { overflow: hidden; }
</style>
