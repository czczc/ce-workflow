<template>
  <svg :viewBox="`0 0 100 ${height}`" preserveAspectRatio="none" class="sparkline-svg">
    <polyline v-if="points" :points="points"
      fill="none" :stroke="color" stroke-width="1.5"
      stroke-linecap="round" stroke-linejoin="round" />
    <circle v-if="last" :cx="last.x" :cy="last.y" r="2" :fill="color" />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data:   { type: Array,  required: true },
  color:  { type: String, default: 'var(--accent)' },
  height: { type: Number, default: 32 },
})

const PAD = 2

const points = computed(() => {
  const d = props.data
  if (!d?.length) return null
  const min = Math.min(...d)
  const max = Math.max(...d)
  const range = max - min || 1
  const h = props.height - PAD * 2
  return d.map((v, i) => {
    const x = (i / (d.length - 1)) * 100
    const y = PAD + h - ((v - min) / range) * h
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

const last = computed(() => {
  const d = props.data
  if (!d?.length) return null
  const min = Math.min(...d)
  const max = Math.max(...d)
  const range = max - min || 1
  const h = props.height - PAD * 2
  const v = d[d.length - 1]
  return { x: 100, y: PAD + h - ((v - min) / range) * h }
})
</script>

<style scoped>
.sparkline-svg { width: 100%; display: block; overflow: visible; }
</style>
