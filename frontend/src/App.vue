<template>
  <v-app>
    <v-app-bar :elevation="0" height="48" class="lab-topbar">
      <div class="topbar-inner">
        <div class="brand">
          <div class="brand-mark">CE</div>
          <span class="brand-name">Cold Electronics QC</span>
          <span class="brand-sep"></span>
          <span class="brand-meta">v{{ version }} · QC-CTS-BNL-1</span>
        </div>

        <nav class="top-nav">
          <RouterLink v-for="link in navLinks" :key="link.to" :to="link.to" custom v-slot="{ navigate, isActive }">
            <button class="nav-btn" :class="{ active: isActive }" @click="navigate">
              <span v-if="isActive" class="nav-dot"></span>
              {{ link.label }}
            </button>
          </RouterLink>
        </nav>

        <div class="sys-pill">
          <span class="sys-status-dot"></span>
          bench online · 87.2 K
        </div>
      </div>
    </v-app-bar>

    <v-main>
      <div class="app-shell">
        <div class="app-body">
          <RouterView />
        </div>
        <div class="lab-statusbar">
          <span class="sb-item"><span class="sb-dot ok"></span>connected</span>
          <span class="sb-item"><span class="sb-dot info"></span>8 ASICs</span>
          <span class="sb-item">FW r417</span>
          <span class="sb-item">2 MHz · 128 ch</span>
          <span class="sb-spacer"></span>
          <span class="sb-item">{{ statusLabel }}</span>
          <span class="sb-item">{{ clock }}</span>
        </div>
      </div>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSharedSession } from './composables/useChat'

const { streaming, activeNode } = useSharedSession()
const version = __APP_VERSION__

const navLinks = [
  { to: '/chat',      label: 'Console' },
  { to: '/documents', label: 'Documents' },
  { to: '/reports',   label: 'Reports' },
]

const statusLabel = computed(() =>
  streaming.value ? `running · ${activeNode.value ?? '…'}` : 'idle'
)

const clock = ref('')
function tick() {
  clock.value = new Date().toISOString().slice(11, 19) + ' UTC'
}
tick()
let timer
onMounted(()   => { timer = setInterval(tick, 1000) })
onUnmounted(() => clearInterval(timer))
</script>

<style>
.v-main { height: 100vh; }
.v-main > .v-main__wrap { height: 100%; padding: 0; }
</style>

<style scoped>
.app-shell { display: flex; flex-direction: column; height: 100%; }
.app-body  { flex: 1; overflow: hidden; }

/* Topbar */
.lab-topbar :deep(.v-toolbar__content) {
  padding: 0;
  height: 48px !important;
  background: var(--bg-1);
  border-bottom: 1px solid var(--line);
}

.topbar-inner {
  display: flex;
  align-items: center;
  width: 100%;
  height: 100%;
  padding: 0 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.brand-mark {
  width: 22px;
  height: 22px;
  border-radius: 5px;
  background: linear-gradient(135deg, var(--accent) 0%, #0a6f7e 100%);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 12px var(--accent-glow);
}

.brand-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-0);
}

.brand-sep {
  width: 1px;
  height: 14px;
  background: var(--line-2);
}

.brand-meta {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--ink-2);
}

/* Nav */
.top-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: 20px;
}

.nav-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--r-md);
  border: 1px solid transparent;
  background: transparent;
  color: var(--ink-1);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 120ms, color 120ms;
  font-family: inherit;
}

.nav-btn:hover        { background: var(--bg-2); color: var(--ink-0); }
.nav-btn.active       { background: var(--bg-3); color: var(--ink-0); border-color: var(--line-2); }

.nav-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}

/* System pill */
.sys-pill {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  border-radius: 999px;
  font-size: 11px;
  color: var(--ink-1);
  flex-shrink: 0;
}

.sys-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ok);
  box-shadow: 0 0 8px var(--ok);
  flex-shrink: 0;
}

/* Statusbar */
.lab-statusbar {
  display: flex;
  align-items: center;
  gap: 16px;
  height: 24px;
  padding: 0 16px;
  background: var(--bg-1);
  border-top: 1px solid var(--line);
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  color: var(--ink-2);
  flex-shrink: 0;
}

.sb-item {
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}

.sb-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sb-dot.ok   { background: var(--ok); }
.sb-dot.info { background: var(--info); }

.sb-spacer { flex: 1; }
</style>
