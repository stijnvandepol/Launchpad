import { ref, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

export function useProjectLogs(projectId: string) {
  const logs = ref<string[]>([])
  const streaming = ref(false)
  let source: EventSource | null = null

  function start() {
    // Token passed as query param because native EventSource does not support
    // custom headers. The backend require_user_sse dependency validates it.
    // Accept the short-lived JWT exposure in server access logs for this
    // personal/team-scale deployment.
    const auth = useAuthStore()
    const token = auth.token
    if (!token) return
    close()
    logs.value = []
    streaming.value = true
    source = new EventSource(`/projects/${projectId}/logs?token=${encodeURIComponent(token)}`)
    source.onmessage = (e) => {
      logs.value.push(e.data)
    }
    source.onerror = () => {
      streaming.value = false
      source?.close()
      source = null
    }
  }

  function close() {
    source?.close()
    source = null
    streaming.value = false
  }

  onUnmounted(close)

  return { logs, streaming, start, close }
}
