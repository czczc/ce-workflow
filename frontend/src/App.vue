<template>
  <v-app>
    <v-main style="height: 100vh">
      <v-container fluid style="height: 100%; padding: 8px">
        <v-row style="height: 100%" no-gutters>
          <v-col cols="12" md="4" lg="3" style="height: 100%; overflow-y: auto; padding-right: 8px">
            <UploadPanel />
            <QcStartButton />
          </v-col>
          <v-col cols="12" md="8" lg="9" style="height: 100%">
            <ChatView />
          </v-col>
        </v-row>
      </v-container>
    </v-main>
  </v-app>
</template>

<script setup>
import ChatView from './components/ChatView.vue'
import UploadPanel from './components/UploadPanel.vue'
import QcStartButton from './components/QcStartButton.vue'
</script>
