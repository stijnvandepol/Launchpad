<template>
  <div class="flex h-screen overflow-hidden bg-gray-50">
    <!-- Sidebar -->
    <aside
      class="group flex flex-col bg-white border-r border-gray-200 transition-all duration-300 ease-out overflow-hidden shrink-0"
      :class="expanded ? 'w-56' : 'w-16'"
      @mouseenter="expanded = true"
      @mouseleave="expanded = false"
    >
      <!-- Logo -->
      <div class="h-14 flex items-center px-4 border-b border-gray-200 shrink-0">
        <div class="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0">
          <span class="text-blue-600 font-bold text-sm">L</span>
        </div>
        <span
          class="ml-3 text-sm font-semibold text-gray-900 whitespace-nowrap transition-opacity duration-200"
          :class="expanded ? 'opacity-100' : 'opacity-0'"
        >Launchpad</span>
      </div>

      <!-- Nav -->
      <nav class="flex-1 py-3 px-2 space-y-0.5">
        <router-link
          to="/"
          class="flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-all duration-150 relative"
          :class="route.path === '/' ? 'bg-blue-50 text-blue-700' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'"
        >
          <i class="pi pi-objects-column text-[15px] w-5 text-center shrink-0"></i>
          <span class="whitespace-nowrap transition-opacity duration-200" :class="expanded ? 'opacity-100' : 'opacity-0 w-0'">Dashboard</span>
          <div v-if="route.path === '/'" class="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-blue-600 rounded-r"></div>
        </router-link>
      </nav>

      <!-- User -->
      <div class="p-2 border-t border-gray-200 shrink-0">
        <div
          class="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-gray-100 transition-colors cursor-pointer"
          @click="auth.logout()"
        >
          <div class="w-7 h-7 rounded-md bg-gray-100 border border-gray-200 flex items-center justify-center text-xs font-mono font-medium text-gray-600 shrink-0">
            {{ initials }}
          </div>
          <div class="flex-1 min-w-0 transition-opacity duration-200" :class="expanded ? 'opacity-100' : 'opacity-0 w-0'">
            <p class="text-xs font-medium text-gray-700 truncate">{{ auth.user?.name ?? 'Beheerder' }}</p>
            <p class="text-[10px] text-gray-400 font-mono">{{ auth.user?.role ?? 'admin' }}</p>
          </div>
        </div>
      </div>
    </aside>

    <!-- Main -->
    <main class="flex-1 flex flex-col overflow-hidden">
      <!-- Topbar -->
      <header class="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
        <div class="flex items-center gap-2 text-sm">
          <i class="pi pi-home text-xs text-gray-400"></i>
          <i class="pi pi-angle-right text-gray-300 text-xs"></i>
          <span class="text-gray-900 font-medium">Dashboard</span>
        </div>
        <span class="text-[10px] font-mono text-gray-400">v1.0</span>
      </header>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto">
        <div class="p-6 animate-fade-in">
          <router-view />
        </div>
      </div>
    </main>

    <Toast position="bottom-right" />
    <ConfirmDialog />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'

const route = useRoute()
const auth = useAuthStore()
const expanded = ref(false)

const initials = computed(() => {
  const name = auth.user?.name || 'Beheerder'
  return name.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2)
})
</script>
