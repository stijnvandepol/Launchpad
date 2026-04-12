<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-40 flex"
      @click.self="$emit('close')"
    >
      <!-- Overlay -->
      <div class="absolute inset-0 bg-black/40" @click="$emit('close')"></div>

      <!-- Drawer panel -->
      <div class="relative ml-auto w-full max-w-2xl bg-gray-950 shadow-xl flex flex-col h-full z-50">
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3 border-b border-gray-800">
          <div>
            <p class="text-sm font-medium text-gray-100">{{ projectName }}</p>
            <p class="text-xs text-gray-400 font-mono">logs</p>
          </div>
          <div class="flex items-center gap-3">
            <span v-if="streaming" class="flex items-center gap-1 text-xs text-green-400">
              <span class="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></span>
              live
            </span>
            <button class="text-gray-400 hover:text-gray-100 transition-colors" @click="$emit('close')">
              <i class="pi pi-times text-sm"></i>
            </button>
          </div>
        </div>

        <!-- Log output -->
        <div ref="logContainer" class="flex-1 overflow-y-auto p-4 font-mono text-xs text-gray-300 space-y-0.5">
          <div v-if="logs.length === 0" class="text-gray-500">Waiting for logs…</div>
          <div v-for="(line, i) in logs" :key="i" class="leading-5 whitespace-pre-wrap break-all">
            {{ line }}
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useProjectLogs } from '@/composables/useProjectLogs'

const props = defineProps<{
  visible: boolean
  projectId: string
  projectName: string
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const logContainer = ref<HTMLElement | null>(null)
const { logs, streaming, start, close } = useProjectLogs(props.projectId)

watch(() => props.visible, (val) => {
  if (val) start()
  else close()
})

watch(streaming, (val) => {
  if (!val && props.visible) emit('close')
})

watch(logs, async () => {
  await nextTick()
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}, { deep: true })
</script>
