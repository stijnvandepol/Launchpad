<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50 px-4">
    <div class="fixed inset-0 bg-[linear-gradient(rgba(37,99,235,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(37,99,235,0.02)_1px,transparent_1px)] bg-[size:60px_60px]"></div>

    <div class="relative w-full max-w-sm animate-slide-up">
      <!-- Logo -->
      <div class="flex items-center justify-center gap-3 mb-10">
        <div class="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
          <span class="text-blue-600 font-bold text-lg">L</span>
        </div>
        <span class="text-xl font-semibold text-gray-900 tracking-tight">Launchpad</span>
      </div>

      <!-- Login card -->
      <div class="card p-8">
        <div class="space-y-5">
          <div v-if="errorMessage" class="flex items-center gap-2 bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-3 py-2.5 rounded-md">
            <i class="pi pi-exclamation-circle text-xs"></i>
            Inloggen mislukt. Probeer het opnieuw.
          </div>
          <a href="/auth/login" class="btn-primary w-full h-10 flex items-center justify-center no-underline">
            Inloggen met Accuro
          </a>
        </div>
      </div>

      <p class="text-center text-[10px] text-gray-400 font-mono mt-6">Launchpad &copy; {{ new Date().getFullYear() }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const errorMessage = computed(() => route.query.error === 'auth_failed')
</script>
