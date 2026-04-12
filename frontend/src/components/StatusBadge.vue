<template>
  <span class="badge" :class="badgeClass">
    <span class="w-1.5 h-1.5 rounded-full mr-1" :class="dotClass"></span>
    <svg
      v-if="spinning"
      class="animate-spin h-3 w-3 mr-1"
      viewBox="0 0 24 24"
    >
      <circle
        cx="12" cy="12" r="10"
        stroke="currentColor" stroke-width="3"
        fill="none" stroke-dasharray="31.4 31.4"
        stroke-linecap="round"
      />
    </svg>
    {{ status }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProjectStatus } from '@/api/projects'

const props = defineProps<{ status: ProjectStatus }>()

const spinning = computed(() =>
  props.status === 'cloning' || props.status === 'building'
)

const badgeClass = computed(() => ({
  'bg-gray-100 text-gray-500':    props.status === 'pending' || props.status === 'stopped',
  'bg-blue-50 text-blue-700':     props.status === 'cloning' || props.status === 'building',
  'bg-yellow-50 text-yellow-700': props.status === 'cloned',
  'bg-green-50 text-green-700':   props.status === 'running',
  'bg-red-50 text-red-700':       props.status === 'failed',
}))

const dotClass = computed(() => ({
  'bg-gray-400':   props.status === 'pending' || props.status === 'stopped',
  'bg-blue-500':   props.status === 'cloning' || props.status === 'building',
  'bg-yellow-500': props.status === 'cloned',
  'bg-green-500':  props.status === 'running',
  'bg-red-500':    props.status === 'failed',
}))
</script>
