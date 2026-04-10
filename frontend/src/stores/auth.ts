import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi } from '@/api/auth'
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

  // Restore token on page load
  if (token.value) {
    setToken(token.value)
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

  async function login(email: string, password: string) {
    const { data } = await loginApi(email, password)
    token.value = data.access_token
    localStorage.setItem('token', data.access_token)
    setToken(data.access_token)
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    setToken(null)
    router.push('/login')
  }

  return { token, user, isAuthenticated, login, logout }
})
