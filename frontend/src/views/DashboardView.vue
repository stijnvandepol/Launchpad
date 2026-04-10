<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-lg font-semibold text-gray-900">Dashboard</h1>
        <p class="text-sm text-gray-500">Beheer je demo deployments</p>
      </div>
      <button class="btn-primary" @click="showNewProject = true">
        <i class="pi pi-plus text-xs"></i>
        Nieuw project
      </button>
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-3 gap-4">
      <div class="stat-card">
        <p class="text-xs font-mono text-gray-500 uppercase tracking-wider">Projecten</p>
        <p class="text-2xl font-semibold text-gray-900">{{ projects.length }}</p>
      </div>
      <div class="stat-card">
        <p class="text-xs font-mono text-gray-500 uppercase tracking-wider">Actief</p>
        <p class="text-2xl font-semibold text-green-600">{{ runningCount }}</p>
      </div>
      <div class="stat-card">
        <p class="text-xs font-mono text-gray-500 uppercase tracking-wider">Domeinen</p>
        <div class="flex flex-wrap gap-1 pt-1">
          <a
            v-for="p in runningProjects"
            :key="p.id"
            :href="`https://${p.subdomain}.webvakwerk.nl`"
            target="_blank"
            rel="noopener noreferrer"
            class="badge bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
          >{{ p.subdomain }}</a>
          <span v-if="runningProjects.length === 0" class="text-sm text-gray-400">—</span>
        </div>
      </div>
    </div>

    <!-- Table -->
    <div class="card overflow-hidden">
      <div v-if="loading" class="p-8 text-center text-gray-400 text-sm">Laden…</div>
      <div v-else-if="fetchError" class="p-8 text-center text-red-400 text-sm">
        <i class="pi pi-exclamation-circle mr-2"></i>
        Projecten laden mislukt — ververs de pagina.
      </div>
      <table v-else class="w-full light-table">
        <thead>
          <tr>
            <th class="text-left px-4 py-3 text-xs font-mono text-gray-500 uppercase tracking-wider bg-gray-50 border-b border-gray-200">Naam</th>
            <th class="text-left px-4 py-3 text-xs font-mono text-gray-500 uppercase tracking-wider bg-gray-50 border-b border-gray-200">Repo</th>
            <th class="text-left px-4 py-3 text-xs font-mono text-gray-500 uppercase tracking-wider bg-gray-50 border-b border-gray-200">Status</th>
            <th class="text-left px-4 py-3 text-xs font-mono text-gray-500 uppercase tracking-wider bg-gray-50 border-b border-gray-200">Deployed</th>
            <th class="px-4 py-3 bg-gray-50 border-b border-gray-200"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="projects.length === 0">
            <td colspan="5" class="px-4 py-8 text-center text-sm text-gray-400">Geen projecten — maak er een aan.</td>
          </tr>
          <tr
            v-for="project in projects"
            :key="project.id"
            class="border-b border-gray-100 hover:bg-gray-50 transition-colors"
          >
            <!-- Naam -->
            <td class="px-4 py-3">
              <a
                :href="`https://${project.subdomain}.webvakwerk.nl`"
                target="_blank"
                rel="noopener noreferrer"
                class="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
              >{{ project.name }}</a>
            </td>
            <!-- Repo -->
            <td class="px-4 py-3">
              <span class="text-sm text-gray-500 font-mono">{{ truncate(project.repo_url, 40) }}</span>
            </td>
            <!-- Status -->
            <td class="px-4 py-3">
              <span
                class="badge"
                :class="project.status === 'running'
                  ? 'bg-green-50 text-green-700'
                  : 'bg-gray-100 text-gray-500'"
              >
                <span
                  class="w-1.5 h-1.5 rounded-full mr-1"
                  :class="project.status === 'running' ? 'bg-green-500' : 'bg-gray-400'"
                ></span>
                {{ project.status }}
              </span>
            </td>
            <!-- Deployed -->
            <td class="px-4 py-3">
              <span
                class="text-sm text-gray-500"
                :title="project.deployed_at ?? ''"
              >{{ relativeTime(project.deployed_at) }}</span>
            </td>
            <!-- Acties -->
            <td class="px-4 py-3">
              <div class="flex items-center gap-1 justify-end">
                <button
                  class="btn-primary text-xs px-2 py-1"
                  :disabled="project.status === 'running' || !!busy[project.id]"
                  @click="action(project, 'deploy')"
                  title="Deploy"
                >
                  <svg v-if="busy[project.id] === 'deploy'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                  <i v-else class="pi pi-play text-xs"></i>
                </button>
                <button
                  class="btn-secondary text-xs px-2 py-1"
                  :disabled="project.status === 'stopped' || !!busy[project.id]"
                  @click="action(project, 'update')"
                  title="Update (git pull + rebuild)"
                >
                  <svg v-if="busy[project.id] === 'update'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                  <i v-else class="pi pi-refresh text-xs"></i>
                </button>
                <button
                  class="btn-danger text-xs px-2 py-1"
                  :disabled="project.status === 'stopped' || !!busy[project.id]"
                  @click="confirmStop(project)"
                  title="Stop"
                >
                  <svg v-if="busy[project.id] === 'stop'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                  <i v-else class="pi pi-stop-circle text-xs"></i>
                </button>
                <button
                  class="btn-icon"
                  :disabled="project.status === 'running' || !!busy[project.id]"
                  @click="confirmDelete(project)"
                  title="Verwijder"
                >
                  <i class="pi pi-trash text-xs"></i>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Nieuw project dialog -->
    <Dialog v-model:visible="showNewProject" header="Nieuw project" :style="{ width: '28rem' }" modal>
      <form @submit.prevent="createProject" class="space-y-4">
        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wider">Naam</label>
          <input v-model="form.name" class="input" placeholder="Mijn App" required />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wider">Repo URL</label>
          <input v-model="form.repo_url" class="input" placeholder="https://github.com/user/repo" type="url" required />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1.5 uppercase tracking-wider">Subdomain</label>
          <input v-model="form.subdomain" class="input" placeholder="mijn-app" pattern="[a-z0-9][a-z0-9\-]{0,46}[a-z0-9]" required />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button type="button" class="btn-secondary" @click="showNewProject = false">Annuleren</button>
          <button type="submit" class="btn-primary" :disabled="creating">
            <svg v-if="creating" class="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
            <span v-else>Aanmaken</span>
          </button>
        </div>
      </form>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import Dialog from 'primevue/dialog'
import { projectsApi, type Project } from '@/api/projects'

const toast = useToast()
const confirm = useConfirm()

const projects = ref<Project[]>([])
const loading = ref(true)
const fetchError = ref(false)
const busy = ref<Record<string, string>>({})
const showNewProject = ref(false)
const creating = ref(false)

const form = ref({ name: '', repo_url: '', subdomain: '' })

const runningCount = computed(() => projects.value.filter(p => p.status === 'running').length)
const runningProjects = computed(() => projects.value.filter(p => p.status === 'running'))

async function fetchProjects() {
  fetchError.value = false
  try {
    const { data } = await projectsApi.list()
    projects.value = data
  } catch (e: any) {
    fetchError.value = true
    toast.add({ severity: 'error', summary: 'Fout', detail: e.response?.data?.detail || 'Laden mislukt', life: 4000 })
  } finally {
    loading.value = false
  }
}

async function action(project: Project, type: 'deploy' | 'update' | 'stop') {
  busy.value[project.id] = type
  try {
    const fn = type === 'deploy' ? projectsApi.deploy : type === 'update' ? projectsApi.update : projectsApi.stop
    const { data } = await fn(project.id)
    const idx = projects.value.findIndex(p => p.id === project.id)
    if (idx !== -1) projects.value[idx] = data
    toast.add({ severity: 'success', summary: 'Klaar', detail: `${type} geslaagd`, life: 3000 })
  } catch (e: any) {
    toast.add({ severity: 'error', summary: 'Fout', detail: e.response?.data?.detail || `${type} mislukt`, life: 5000 })
  } finally {
    busy.value[project.id] = ''
  }
}

function confirmStop(project: Project) {
  confirm.require({
    message: `Container "${project.name}" stoppen en domein verwijderen?`,
    header: 'Bevestig stop',
    icon: 'pi pi-stop-circle',
    acceptLabel: 'Stop',
    rejectLabel: 'Annuleren',
    acceptClass: 'btn-danger',
    accept: () => action(project, 'stop'),
  })
}

function confirmDelete(project: Project) {
  confirm.require({
    message: `Project "${project.name}" definitief verwijderen?`,
    header: 'Bevestig verwijdering',
    icon: 'pi pi-trash',
    acceptLabel: 'Verwijder',
    rejectLabel: 'Annuleren',
    accept: async () => {
      try {
        await projectsApi.remove(project.id)
        projects.value = projects.value.filter(p => p.id !== project.id)
        toast.add({ severity: 'success', summary: 'Verwijderd', detail: `"${project.name}" is verwijderd`, life: 3000 })
      } catch (e: any) {
        toast.add({ severity: 'error', summary: 'Fout', detail: e.response?.data?.detail || 'Verwijderen mislukt', life: 5000 })
      }
    },
  })
}

async function createProject() {
  creating.value = true
  try {
    const { data } = await projectsApi.create(form.value)
    projects.value.push(data)
    showNewProject.value = false
    form.value = { name: '', repo_url: '', subdomain: '', port: 3000 }
    toast.add({ severity: 'success', summary: 'Aangemaakt', detail: `"${data.name}" aangemaakt`, life: 3000 })
  } catch (e: any) {
    toast.add({ severity: 'error', summary: 'Fout', detail: e.response?.data?.detail || 'Aanmaken mislukt', life: 5000 })
  } finally {
    creating.value = false
  }
}

function truncate(str: string, max: number) {
  return str.length > max ? str.slice(0, max) + '…' : str
}

function relativeTime(iso: string | null): string {
  if (!iso) return '—'
  const diff = (new Date(iso).getTime() - Date.now()) / 1000
  const fmt = new Intl.RelativeTimeFormat('nl', { numeric: 'auto' })
  const abs = Math.abs(diff)
  if (abs < 60) return fmt.format(Math.round(diff), 'second')
  if (abs < 3600) return fmt.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return fmt.format(Math.round(diff / 3600), 'hour')
  return fmt.format(Math.round(diff / 86400), 'day')
}

onMounted(fetchProjects)
</script>
