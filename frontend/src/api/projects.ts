import { apiClient } from './client'

export interface Project {
  id: string
  name: string
  repo_url: string
  subdomain: string
  path: string
  port: number
  status: 'running' | 'stopped'
  deployed_at: string | null
  updated_at: string | null
}

export interface CreateProjectPayload {
  name: string
  repo_url: string
  subdomain: string
  port: number
}

export const projectsApi = {
  list: () => apiClient.get<Project[]>('/projects'),
  create: (data: CreateProjectPayload) => apiClient.post<Project>('/projects', data),
  deploy: (id: string) => apiClient.post<Project>(`/projects/${id}/deploy`),
  update: (id: string) => apiClient.post<Project>(`/projects/${id}/update`),
  stop: (id: string) => apiClient.post<Project>(`/projects/${id}/stop`),
  remove: (id: string) => apiClient.delete(`/projects/${id}`),
}
