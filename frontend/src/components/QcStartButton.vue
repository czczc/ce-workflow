<template>
  <v-card>
    <v-card-text>
      <v-btn block color="secondary" @click="show = true">QC Start</v-btn>
      <v-alert v-if="show" type="info" class="mt-3" density="compact" closable @click:close="show = false">
        QC Start is not yet available.
      </v-alert>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref } from 'vue'
const show = ref(false)
</script>
