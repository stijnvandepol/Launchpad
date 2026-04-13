<template>
  <div></div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

onMounted(async () => {
  const token = route.query.token as string | undefined
  if (!token) {
    router.replace('/login?error=auth_failed')
    return
  }
  auth.handleCallback(token)
  router.replace('/')
})
</script>
