<template>
  <v-app>
    <v-main>
      <div class="app-layout">
        <v-tabs v-model="tab" bg-color="surface" density="compact">
          <v-tab value="workflow">QC Workflow</v-tab>
          <v-tab value="reports">Reports</v-tab>
        </v-tabs>
        <v-divider />
        <div class="app-content">
          <v-window v-model="tab">
            <v-window-item value="workflow">
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
            </v-window-item>
            <v-window-item value="reports" style="padding: 8px">
              <ReportsView />
            </v-window-item>
          </v-window>
        </div>
      </div>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref } from 'vue'
import ChatView from './components/ChatView.vue'
import UploadPanel from './components/UploadPanel.vue'
import QcStartButton from './components/QcStartButton.vue'
import ReportsView from './components/ReportsView.vue'

const tab = ref('workflow')
</script>

<style>
.v-main { height: 100vh; }
.v-main > .v-main__wrap { height: 100%; padding: 0; }
.app-layout { display: flex; flex-direction: column; height: 100%; }
.app-content { flex: 1; min-height: 0; overflow: hidden; }
.app-content .v-window,
.app-content .v-window__container,
.app-content .v-window-item { height: 100%; }
</style>
