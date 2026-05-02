<template>
  <v-app>
    <v-app-bar density="compact" elevation="1">
      <v-app-bar-title>CE Workflow</v-app-bar-title>
      <RouterLink v-for="link in navLinks" :key="link.to" :to="link.to" custom v-slot="{ navigate, isActive }">
        <v-btn :variant="isActive ? 'tonal' : 'text'" @click="navigate">{{ link.label }}</v-btn>
      </RouterLink>
    </v-app-bar>
    <v-main>
      <div class="app-content">
        <RouterView />
      </div>
    </v-main>
  </v-app>
</template>

<script setup>
const navLinks = [
  { to: '/chat', label: 'Chat' },
  { to: '/documents', label: 'Documents' },
  { to: '/reports', label: 'Reports' },
]
</script>

<style>
.v-main { height: 100vh; }
.v-main > .v-main__wrap { height: 100%; padding: 0; }
.app-content { height: 100%; overflow: hidden; }
</style>
