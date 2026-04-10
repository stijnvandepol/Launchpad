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

      <!-- Form card -->
      <div class="card p-8">
        <form @submit.prevent="handleLogin" class="space-y-5">
          <div>
            <label class="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wider">E-mailadres</label>
            <input v-model="email" type="email" class="input" placeholder="naam@bedrijf.nl" required autofocus />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wider">Wachtwoord</label>
            <input v-model="password" type="password" class="input" placeholder="••••••••••••" required />
          </div>
          <div v-if="errorMsg" class="flex items-center gap-2 bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-3 py-2.5 rounded-md">
            <i class="pi pi-exclamation-circle text-xs"></i>
            {{ errorMsg }}
          </div>
          <button type="submit" class="btn-primary w-full h-10" :disabled="loading">
            <svg v-if="loading" class="animate-spin h-4 w-4" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round" />
            </svg>
            <span v-else>Inloggen</span>
          </button>
        </form>
      </div>

      <p class="text-center text-[10px] text-gray-400 font-mono mt-6">Launchpad &copy; {{ new Date().getFullYear() }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const email = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  errorMsg.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    router.push('/')
  } catch (err: any) {
    errorMsg.value = err.response?.data?.detail || 'Inloggen mislukt'
  } finally {
    loading.value = false
  }
}
</script>
