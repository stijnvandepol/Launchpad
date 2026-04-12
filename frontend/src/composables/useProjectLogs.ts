import { ref, onUnmounted } from 'vue'

export function useProjectLogs(projectId: string) {
  const logs = ref<string[]>([])
  const streaming = ref(false)
  let source: EventSource | null = null

  function start() {
    const token = localStorage.getItem('token')
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
