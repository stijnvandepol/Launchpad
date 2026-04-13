import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { setToken } from '@/api/client'
import { apiClient } from '@/api/client'
import router from '@/router'

interface User {
  name: string
  email: string
  role: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  function decodeJwt(jwt: string): User | null {
    try {
      const payload = JSON.parse(atob(jwt.split('.')[1]))
      return { name: payload.name, email: payload.email, role: payload.role }
    } catch {
      return null
    }
  }

  // Restore token on page load
  if (token.value) {
    setToken(token.value)
    user.value = decodeJwt(token.value)
  }

  // 401 interceptor
  apiClient.interceptors.response.use(
    (r) => r,
    (error) => {
      if (error.response?.status === 401) {
        logout()
      }
      return Promise.reject(error)
    }
  )

  function handleCallback(newToken: string) {
    token.value = newToken
    localStorage.setItem('token', newToken)
    setToken(newToken)
    user.value = decodeJwt(newToken)
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    setToken(null)
    router.push('/login')
  }

  return { token, user, isAuthenticated, handleCallback, logout }
})
