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

    <!-- Repo requirements info block -->
    <div class="card p-4">
      <button
        class="flex items-center gap-2 text-sm font-medium text-gray-700 w-full text-left"
        @click="showRepoInfo = !showRepoInfo"
      >
        <i class="pi pi-info-circle text-blue-500"></i>
        Vereisten voor je repository
        <i class="pi ml-auto text-gray-400 transition-transform" :class="showRepoInfo ? 'pi-chevron-up' : 'pi-chevron-down'"></i>
      </button>
      <div v-if="showRepoInfo" class="mt-3 text-sm text-gray-600 space-y-2 border-t border-gray-100 pt-3">
        <p>Zorg dat je repository voldoet aan de volgende vereisten:</p>
        <ul class="list-disc list-inside space-y-1 text-gray-500">
          <li>Een werkende <code class="bg-gray-100 px-1 rounded">Dockerfile</code> <strong>of</strong> <code class="bg-gray-100 px-1 rounded">docker-compose.yml</code> in de root</li>
          <li>De applicatie luistert op de poort die wordt doorgegeven via de <code class="bg-gray-100 px-1 rounded">PORT</code> omgevingsvariabele</li>
          <li>Optioneel: een <code class="bg-gray-100 px-1 rounded">.env.example</code> bestand voor documentatie</li>
        </ul>
        <p class="text-xs text-gray-400">Na het clonen wordt gecontroleerd of de vereiste bestanden aanwezig zijn.</p>
      </div>
    </div>

    <!-- Table -->
    <div class="card overflow-hidden">
      <div v-if="loading" class="p-8 text-center text-gray-400 text-sm">Laden…</div>
      <div v-else-if="fetchError" class="p-8 text-center text-red-400 text-sm font-mono">
        <i class="pi pi-exclamation-circle mr-2"></i>
        GET /projects failed: {{ fetchError }}
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
            <td colspan="5" class="px-4 py-8 text-center text-sm text-gray-400">
              Geen projecten — maak er een aan.
            </td>
          </tr>
          <tr
            v-for="project in projects"
            :key="project.id"
            class="border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer"
            @click="openLogs(project)"
          >
            <!-- Naam -->
            <td class="px-4 py-3" @click.stop>
              <a
                v-if="project.status === 'running'"
                :href="`https://${project.subdomain}.webvakwerk.nl`"
                target="_blank"
                rel="noopener noreferrer"
                class="text-sm font-medium text-gray-900 hover:text-blue-600 transition-colors"
              >{{ project.name }}</a>
              <span v-else class="text-sm font-medium text-gray-900">{{ project.name }}</span>
              <p v-if="project.error" class="text-xs text-red-500 mt-0.5 truncate max-w-xs" :title="project.error">
                {{ project.error }}
              </p>
            </td>
            <!-- Repo -->
            <td class="px-4 py-3">
              <span class="text-sm text-gray-500 font-mono">{{ truncate(project.repo_url, 40) }}</span>
            </td>
            <!-- Status -->
            <td class="px-4 py-3">
              <StatusBadge :status="project.status" />
            </td>
            <!-- Deployed -->
            <td class="px-4 py-3">
              <span class="text-sm text-gray-500" :title="project.deployed_at ?? ''">
                {{ relativeTime(project.deployed_at) }}
              </span>
            </td>
            <!-- Acties -->
            <td class="px-4 py-3" @click.stop>
              <div class="flex items-center gap-1 justify-end">
                <!-- Clone (pending, failed) -->
                <button
                  v-if="project.status === 'pending' || project.status === 'failed'"
                  class="btn-secondary text-xs px-2 py-1"
                  :disabled="!!busy[project.id]"
                  title="Clone repository"
                  @click="action(project, 'clone')"
                >
                  <svg v-if="busy[project.id] === 'clone'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                  <i v-else class="pi pi-download text-xs"></i>
                </button>

                <!-- Deploy (cloned, stopped, failed) -->
                <button
                  v-if="project.status === 'cloned' || project.status === 'stopped' || project.status === 'failed'"
                  class="btn-primary text-xs px-2 py-1"
                  :disabled="!!busy[project.id]"
                  title="Deploy"
                  @click="action(project, 'deploy')"
                >
                  <svg v-if="busy[project.id] === 'deploy'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                  <i v-else class="pi pi-play text-xs"></i>
                </button>

                <!-- Update + Restart (running) -->
                <template v-if="project.status === 'running'">
                  <button
                    class="btn-secondary text-xs px-2 py-1"
                    :disabled="!!busy[project.id]"
                    title="Pull (code updaten + images verwijderen)"
                    @click="action(project, 'pull')"
                  >
                    <svg v-if="busy[project.id] === 'pull'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                    <i v-else class="pi pi-refresh text-xs"></i>
                  </button>
                  <button
                    class="btn-secondary text-xs px-2 py-1"
                    :disabled="!!busy[project.id]"
                    title="Herstart"
                    @click="action(project, 'restart')"
                  >
                    <svg v-if="busy[project.id] === 'restart'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                    <i v-else class="pi pi-replay text-xs"></i>
                  </button>
                  <button
                    class="btn-danger text-xs px-2 py-1"
                    :disabled="!!busy[project.id]"
                    title="Stop"
                    @click="confirmStop(project)"
                  >
                    <svg v-if="busy[project.id] === 'stop'" class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/></svg>
                    <i v-else class="pi pi-stop-circle text-xs"></i>
                  </button>
                </template>

                <!-- Delete (stopped, failed, cloned) -->
                <button
                  v-if="['stopped', 'failed', 'cloned', 'pending'].includes(project.status)"
                  class="btn-icon"
                  :disabled="!!busy[project.id]"
                  title="Verwijder"
                  @click="confirmDelete(project)"
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

    <!-- Log Drawer -->
    <LogDrawer
      v-if="activeLogProject"
      :key="activeLogProject.id"
      :visible="showLogDrawer"
      :project-id="activeLogProject.id"
      :project-name="activeLogProject.name"
      :active-status="activeLogProject.status"
      @close="showLogDrawer = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import Dialog from 'primevue/dialog'
import StatusBadge from '@/components/StatusBadge.vue'
import LogDrawer from '@/components/LogDrawer.vue'
import { projectsApi, type Project } from '@/api/projects'

const toast = useToast()
const confirm = useConfirm()

const projects = ref<Project[]>([])
const loading = ref(true)
const fetchError = ref<string | null>(null)
const busy = ref<Record<string, string>>({})
const showNewProject = ref(false)
const creating = ref(false)
const showRepoInfo = ref(false)
const showLogDrawer = ref(false)
const activeLogProject = ref<Project | null>(null)

const form = ref({ name: '', repo_url: '', subdomain: '' })

const runningCount = computed(() => projects.value.filter(p => p.status === 'running').length)
const runningProjects = computed(() => projects.value.filter(p => p.status === 'running'))
const hasActiveJobs = computed(() =>
  projects.value.some(p => p.status === 'cloning' || p.status === 'building')
)

// ── Polling ───────────────────────────────────────────────────────────────────

let pollInterval: ReturnType<typeof setInterval> | null = null

function startPolling() {
  if (pollInterval) return
  pollInterval = setInterval(async () => {
    if (!hasActiveJobs.value) {
      stopPolling()
      return
    }
    await fetchProjects()
  }, 3000)
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

onUnmounted(stopPolling)

// ── Data fetching ─────────────────────────────────────────────────────────────

function _errorDetail(e: any): string {
  const status = e?.response?.status
  const detail = e?.response?.data?.detail ?? e?.message ?? 'unknown error'
  return status ? `HTTP ${status}: ${detail}` : detail
}

async function fetchProjects() {
  try {
    const { data } = await projectsApi.list()
    projects.value = data
    fetchError.value = null
    if (hasActiveJobs.value) startPolling()
    else stopPolling()
  } catch (e: any) {
    fetchError.value = _errorDetail(e)
  }
}

onMounted(async () => {
  loading.value = true
  await fetchProjects()
  loading.value = false
})

// ── Actions ───────────────────────────────────────────────────────────────────

const actionMap: Record<'clone' | 'deploy' | 'pull' | 'stop' | 'restart', (id: string) => Promise<any>> = {
  clone: projectsApi.clone,
  deploy: projectsApi.deploy,
  pull: projectsApi.pull,
  stop: projectsApi.stop,
  restart: projectsApi.restart,
}

async function action(project: Project, type: 'clone' | 'deploy' | 'pull' | 'stop' | 'restart') {
  busy.value[project.id] = type
  try {
    const { data } = await actionMap[type](project.id)
    // Optimistically update status in list
    const idx = projects.value.findIndex(p => p.id === project.id)
    if (idx !== -1) projects.value[idx] = data
    if (hasActiveJobs.value) startPolling()
  } catch (e: any) {
    toast.add({
      severity: 'error',
      summary: 'Fout',
      detail: _errorDetail(e),
      life: 4000,
    })
  } finally {
    delete busy.value[project.id]
  }
}

function confirmStop(project: Project) {
  confirm.require({
    message: `Stop container voor "${project.name}"?`,
    header: 'Container stoppen',
    icon: 'pi pi-exclamation-triangle',
    acceptClass: 'btn-danger',
    accept: () => action(project, 'stop'),
  })
}

function confirmDelete(project: Project) {
  confirm.require({
    message: `Verwijder project "${project.name}" inclusief bestanden en containers?`,
    header: 'Project verwijderen',
    icon: 'pi pi-trash',
    acceptClass: 'btn-danger',
    accept: async () => {
      busy.value[project.id] = 'delete'
      try {
        await projectsApi.remove(project.id)
        projects.value = projects.value.filter(p => p.id !== project.id)
      } catch (e: any) {
        toast.add({
          severity: 'error',
          summary: 'Fout',
          detail: _errorDetail(e),
          life: 4000,
        })
      } finally {
        delete busy.value[project.id]
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
    form.value = { name: '', repo_url: '', subdomain: '' }
    toast.add({ severity: 'success', summary: 'Aangemaakt', detail: data.name, life: 3000 })
  } catch (e: any) {
    toast.add({
      severity: 'error',
      summary: 'Fout',
      detail: _errorDetail(e),
      life: 4000,
    })
  } finally {
    creating.value = false
  }
}

// ── Log drawer ────────────────────────────────────────────────────────────────

function openLogs(project: Project) {
  activeLogProject.value = project
  showLogDrawer.value = true
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s
}

function relativeTime(iso: string | null): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'zojuist'
  if (mins < 60) return `${mins}m geleden`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}u geleden`
  return `${Math.floor(hours / 24)}d geleden`
}
</script>
