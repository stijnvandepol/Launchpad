import { apiClient } from './client'

export const S = {
  PENDING:  'pending',
  CLONING:  'cloning',
  CLONED:   'cloned',
  BUILDING: 'building',
  RUNNING:  'running',
  FAILED:   'failed',
  STOPPED:  'stopped',
} as const

export type ProjectStatus = typeof S[keyof typeof S]

export interface Project {
  id: string
  name: string
  repo_url: string
  subdomain: string
  path: string
  port: number
  status: ProjectStatus
  error: string | null
  deployed_at: string | null
  updated_at: string | null
}

export interface CreateProjectPayload {
  name: string
  repo_url: string
  subdomain: string
}

export const projectsApi = {
  list:    ()          => apiClient.get<Project[]>('/projects'),
  create:  (data: CreateProjectPayload) => apiClient.post<Project>('/projects', data),
  clone:   (id: string) => apiClient.post<Project>(`/projects/${id}/clone`),
  deploy:  (id: string) => apiClient.post<Project>(`/projects/${id}/deploy`),
  restart: (id: string) => apiClient.post<Project>(`/projects/${id}/restart`),
  pull:    (id: string) => apiClient.post<Project>(`/projects/${id}/update`),
  stop:    (id: string) => apiClient.post<Project>(`/projects/${id}/stop`),
  remove:  (id: string) => apiClient.delete(`/projects/${id}`),
}
